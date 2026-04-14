"""Score pipeline stage.

Loads unscored jobs from cache, calls Claude in batches of 20,
writes scores back to cache in-place.

OpenClaw rules enforced:
- Only processes jobs with score == 0 (incremental, never re-scores)
- Session state prevents double-scoring within one process run
- Profile YAML is cached in the system block — not re-tokenized per batch
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from career_ai.ai.client import get_claude_client, _BATCH_SIZE
from career_ai.session import get_session
from career_ai.storage.cache import load_unscored_jobs, update_job_in_cache

console = Console()


def run_score() -> None:
    session = get_session()
    all_unscored = load_unscored_jobs()

    # Filter out anything scored this session (in-memory dedup)
    to_score = [j for j in all_unscored if not session.is_scored(j.job_id)]

    if not to_score:
        console.print("[dim]No unscored jobs. Run [bold]career scan[/bold] first.[/dim]")
        return

    console.print(f"[bold]Scoring {len(to_score)} jobs...[/bold]")

    client = get_claude_client()
    batches = _chunked(to_score, _BATCH_SIZE)
    scored_results: list[dict] = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Calling Claude API...", total=len(batches))

        for batch in batches:
            results = client.score_batch(batch)
            for r in results:
                job_id = r.get("job_id", "")
                score = r.get("score", 0)
                decision = r.get("decision", "")
                reasoning = r.get("reasoning", "")

                update_job_in_cache(job_id, {
                    "score": score,
                    "decision": decision,
                    "reasoning": reasoning,
                })
                session.mark_scored(job_id)
                scored_results.append(r)

            progress.advance(task)

    _print_scores(scored_results)


def _chunked(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _print_scores(results: list[dict]) -> None:
    if not results:
        return

    table = Table(title="Scoring Results", show_header=True)
    table.add_column("Job ID", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Decision")
    table.add_column("Reasoning", max_width=60)

    decision_colors = {"strong": "bright_green", "apply": "green", "skip": "dim", "error": "red"}

    # Sort by score descending
    for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
        score = r.get("score", 0)
        decision = r.get("decision", "")
        color = decision_colors.get(decision, "white")
        score_color = "bright_green" if score >= 70 else ("yellow" if score >= 50 else "dim")

        table.add_row(
            r.get("job_id", ""),
            f"[{score_color}]{score}[/{score_color}]",
            f"[{color}]{decision}[/{color}]",
            r.get("reasoning", "")[:80],
        )

    console.print(table)
    apply_count = sum(1 for r in results if r.get("decision") in ("apply", "strong"))
    console.print(
        f"\n[green]{apply_count} jobs worth applying to.[/green] "
        f"Run [bold]career apply <job_id>[/bold] to generate materials."
    )
