"""Batch pipeline stage — runs parallel claude -p workers via batch-runner.sh.

`career batch` reads batch/batch-input.tsv and spawns one worker per job.
Workers write JSON results to batch/tracker-additions/, which are then merged
into data/career-ai.db and data/cache/*.json by merge_tracker_additions().
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()

_BATCH_DIR = Path("batch")
_INPUT_FILE = _BATCH_DIR / "batch-input.tsv"
_RUNNER = _BATCH_DIR / "batch-runner.sh"
_TRACKER_DIR = _BATCH_DIR / "tracker-additions"


def run_batch(
    parallel: int = 1,
    dry_run: bool = False,
    retry_failed: bool = False,
    job_id: str = "",
) -> None:
    """Run batch processing via batch-runner.sh.

    Spawns parallel claude -p workers for each pending job in batch-input.tsv.
    Results are merged into cache and SQLite tracker after all workers complete.
    """
    if not _RUNNER.exists():
        console.print("[red]batch-runner.sh not found. Expected: batch/batch-runner.sh[/red]")
        raise SystemExit(1)

    if not _INPUT_FILE.exists():
        console.print(f"[red]Input file not found: {_INPUT_FILE}[/red]")
        console.print("[yellow]Create it with columns: id<TAB>url<TAB>source<TAB>notes[/yellow]")
        raise SystemExit(1)

    # Check that claude CLI is available
    from career_ai.ai.client import _find_claude
    try:
        claude_exe = _find_claude()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc
    result = subprocess.run([claude_exe, "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        console.print("[red]claude CLI found but failed to run. Try: claude login[/red]")
        raise SystemExit(1)

    # Ensure profile context file exists
    from career_ai.ai.client import get_claude_client
    get_claude_client()  # writes batch/.profile-context.md

    # Build runner command
    cmd = ["bash", str(_RUNNER), "--parallel", str(parallel)]
    if dry_run:
        cmd.append("--dry-run")
    if retry_failed:
        cmd.append("--retry-failed")
    if job_id:
        cmd.extend(["--job-id", job_id])

    console.print(f"[cyan]Running batch workers (parallel={parallel}, dry_run={dry_run})...[/cyan]")

    # Stream output in real-time
    proc = subprocess.Popen(cmd, cwd=str(Path.cwd()))
    proc.wait()

    if proc.returncode != 0:
        console.print("[yellow]Batch runner finished with some failures. Check batch/logs/[/yellow]")


def merge_tracker_additions(tracker_dir: str | None = None) -> int:
    """Merge JSON results from batch/tracker-additions/ into cache and SQLite.

    Called automatically by batch-runner.sh after workers complete, and can be
    called manually via `career batch --merge-only`.

    Returns the number of records merged.
    """
    from career_ai.models import ApplicationStatus
    from career_ai.storage.cache import find_job, update_job_in_cache
    from career_ai.storage.tracker import get_tracker

    additions_dir = Path(tracker_dir) if tracker_dir else _TRACKER_DIR
    if not additions_dir.exists():
        return 0

    json_files = sorted(additions_dir.glob("*.json"))
    if not json_files:
        return 0

    tracker = get_tracker()
    merged = 0

    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            console.print(f"[yellow]Skipping malformed file: {f.name}[/yellow]")
            continue

        job_id = data.get("job_id", "")
        if not job_id:
            continue

        # Update cache with score + application materials
        updates: dict = {}
        if "score" in data:
            updates["score"] = data["score"]
        if "decision" in data:
            updates["decision"] = data["decision"]
        if "reasoning" in data:
            updates["reasoning"] = data["reasoning"]
        if "ats_summary" in data:
            updates["ats_summary"] = data["ats_summary"]
        if "cover_letter" in data:
            updates["cover_letter"] = data["cover_letter"]
        if "keywords" in data:
            updates["keywords"] = data["keywords"]

        if updates:
            update_job_in_cache(job_id, updates)

        # Upsert in SQLite tracker if we have application materials
        job = find_job(job_id)
        if job and data.get("ats_summary"):
            tracker.upsert_application(job, ApplicationStatus.APPLIED)

        merged += 1
        console.print(f"[green]Merged {job_id} (score={data.get('score', '?')})[/green]")

    return merged


def add_jobs_to_batch(urls: list[str], source: str = "manual") -> None:
    """Append jobs to batch/batch-input.tsv from a list of URLs.

    Generates job_id = sha256(url)[:12] for each URL.
    Skips URLs already present in the input file.
    """
    from career_ai.models import make_job_id

    _BATCH_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing IDs to avoid duplication
    existing_urls: set[str] = set()
    if _INPUT_FILE.exists():
        lines = _INPUT_FILE.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split("\t")
            if len(parts) >= 2:
                existing_urls.add(parts[1].strip())
    else:
        _INPUT_FILE.write_text("id\turl\tsource\tnotes\n", encoding="utf-8")

    added = 0
    with _INPUT_FILE.open("a", encoding="utf-8") as fh:
        for url in urls:
            url = url.strip()
            if not url or url in existing_urls:
                continue
            job_id = make_job_id(url)
            fh.write(f"{job_id}\t{url}\t{source}\t\n")
            existing_urls.add(url)
            added += 1

    console.print(f"[green]Added {added} job(s) to {_INPUT_FILE}[/green]")


def show_batch_status() -> None:
    """Display current batch state as a Rich table."""
    state_file = _BATCH_DIR / "batch-state.tsv"
    if not state_file.exists():
        console.print("[yellow]No batch state file found. Run 'career batch' first.[/yellow]")
        return

    lines = state_file.read_text(encoding="utf-8").splitlines()
    if len(lines) < 2:
        console.print("[yellow]Batch state is empty.[/yellow]")
        return

    table = Table(title="Batch Status", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("URL", max_width=50)
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Finished")

    status_colors = {
        "pending": "white",
        "running": "yellow",
        "completed": "green",
        "failed": "red",
        "dry-run": "blue",
    }

    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        job_id, url, source, _notes, status, score, _started, finished = parts[:8]
        color = status_colors.get(status, "white")
        table.add_row(
            job_id,
            url[:50] + ("…" if len(url) > 50 else ""),
            source,
            f"[{color}]{status}[/{color}]",
            score or "—",
            finished or "—",
        )

    console.print(table)
