"""Auto pipeline — full automated job application pipeline in one command.

`career auto` runs the complete pipeline sequentially:
  1. scan  — discover new jobs from portals.yml (zero AI cost)
  2. score — score all unscored jobs via claude CLI
  3. apply — generate application materials for all jobs at or above min_score

Equivalent to running `career scan && career score && career apply <id>` for
every strong match, but in a single unattended command.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def run_auto(min_score: int = 70) -> None:
    """Run the full automated pipeline: scan → score → apply all strong matches.

    Args:
        min_score: Minimum score (0-100) to auto-generate application materials.
                   Default 70 — only "apply" and "strong" decisions.
    """
    console.print(
        Panel.fit(
            f"[bold cyan]career auto[/bold cyan] — Full automated pipeline\n"
            f"Stages: scan → score → apply (score ≥ {min_score})\n"
            f"[dim]Uses claude CLI — no API key required[/dim]",
            border_style="cyan",
        )
    )

    # ── Stage 1: Scan ────────────────────────────────────────────────────────
    console.rule("[cyan]Stage 1/3 — Scan[/cyan]")
    from career_ai.pipeline.scan import run_scan
    run_scan()

    # ── Stage 2: Score ───────────────────────────────────────────────────────
    console.rule("[cyan]Stage 2/3 — Score[/cyan]")
    from career_ai.pipeline.score import run_score
    run_score()

    # ── Stage 3: Apply all strong matches ────────────────────────────────────
    console.rule(f"[cyan]Stage 3/3 — Apply (score ≥ {min_score})[/cyan]")
    from career_ai.storage.cache import load_all_jobs
    from career_ai.pipeline.apply import run_apply

    all_jobs = load_all_jobs()
    candidates = [
        j for j in all_jobs
        if j.score >= min_score and not j.ats_summary
    ]

    if not candidates:
        console.print(f"[yellow]No unprocessed jobs with score ≥ {min_score}.[/yellow]")
    else:
        console.print(f"[green]{len(candidates)} job(s) to apply for.[/green]")
        applied = 0
        failed = 0
        for job in candidates:
            console.print(
                f"  → [bold]{job.title}[/bold] @ {job.company} "
                f"[dim](score={job.score}, id={job.job_id})[/dim]"
            )
            try:
                run_apply(job.job_id)
                applied += 1
            except Exception as exc:
                console.print(f"    [red]Failed: {exc}[/red]")
                failed += 1

        console.print()
        console.print(f"[green]Applied: {applied}[/green]  [red]Failed: {failed}[/red]")

    # ── Summary ──────────────────────────────────────────────────────────────
    console.rule("[cyan]Summary[/cyan]")
    _print_summary(min_score)


def _print_summary(min_score: int) -> None:
    """Print a compact summary table of all applications generated this run."""
    from career_ai.storage.tracker import get_tracker

    tracker = get_tracker()
    apps = tracker.get_all_applications()
    if not apps:
        console.print("[dim]No applications in tracker yet.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("ID", style="dim", width=14)
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Score", justify="right")
    table.add_column("Status")

    for app in sorted(apps, key=lambda a: a.score or 0, reverse=True)[:20]:
        score_str = str(app.score) if app.score else "—"
        score_color = (
            "green" if (app.score or 0) >= 80
            else "yellow" if (app.score or 0) >= 60
            else "red"
        )
        table.add_row(
            app.job_id,
            app.company,
            app.title,
            f"[{score_color}]{score_str}[/{score_color}]",
            app.status.value,
        )

    console.print(table)
    console.print(
        f"\n[dim]Run [bold]career track[/bold] for full application history.[/dim]"
    )
