"""CLI entry point.

Commands use lazy imports so that 'career scan' never imports
Playwright or the claude CLI client unless those commands are invoked.

No API key required — all AI calls go through the `claude` CLI
(Claude Max/Pro subscription).

OpenClaw: profile.yml and portals.yml are NOT read at import time.
Config is only loaded when a command that needs it actually runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

# Windows: reconfigure stdout/stderr to UTF-8 so Rich can render ✓, ✗, etc.
# Without this, CP1252 terminals crash on any non-ASCII character.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Load .env if present (optional — no API key required for claude CLI usage)
load_dotenv(Path(".env"), override=False)

app = typer.Typer(
    name="career",
    help="AI-powered job search automation. Pipeline: scan → score → apply → track.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def scan() -> None:
    """Discover new jobs from portals.yml and cache them. Zero AI cost."""
    from career_ai.pipeline.scan import run_scan
    run_scan()


@app.command()
def score() -> None:
    """Score all unscored cached jobs against your profile (0-100)."""
    from career_ai.pipeline.score import run_score
    run_score()


@app.command()
def apply(
    job_id: str = typer.Argument(..., help="Job ID from scan results (12-char hex)"),
) -> None:
    """Generate ATS summary, cover letter, and keywords for a job."""
    from career_ai.pipeline.apply import run_apply
    run_apply(job_id)


@app.command()
def autoapply(
    job_id: str = typer.Argument(..., help="Job ID to auto-apply for"),
) -> None:
    """Playwright form fill — pauses before submit, you confirm explicitly."""
    from career_ai.autoapply.runner import run_autoapply
    run_autoapply(job_id)


@app.command()
def track() -> None:
    """Show application status table. Zero AI cost."""
    from career_ai.pipeline.track import run_track
    run_track()


@app.command()
def batch(
    parallel: int = typer.Option(1, "--parallel", "-p", help="Number of concurrent claude workers"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without executing workers"),
    retry_failed: bool = typer.Option(False, "--retry-failed", help="Retry previously failed jobs"),
    job_id: str = typer.Option("", "--job-id", help="Process a single job by ID"),
    merge_only: bool = typer.Option(False, "--merge-only", help="Merge tracker-additions without running workers"),
    add_url: list[str] = typer.Option([], "--add", help="Add job URLs to batch-input.tsv"),
    show_status: bool = typer.Option(False, "--status", help="Show batch state table"),
) -> None:
    """Run parallel claude workers for deep per-job evaluation (A-G scoring blocks).

    Reads batch/batch-input.tsv. Add jobs with --add <url>.
    Workers write JSON to batch/tracker-additions/, then merged into cache + SQLite.

    Examples:
      career batch --add https://jobs.lever.co/company/abc123
      career batch --parallel 3
      career batch --retry-failed
      career batch --status
    """
    from career_ai.pipeline.batch import (
        add_jobs_to_batch,
        merge_tracker_additions,
        run_batch,
        show_batch_status,
    )

    if add_url:
        add_jobs_to_batch(list(add_url))
        return

    if show_status:
        show_batch_status()
        return

    if merge_only:
        count = merge_tracker_additions()
        console.print(f"[green]Merged {count} record(s).[/green]")
        return

    run_batch(parallel=parallel, dry_run=dry_run, retry_failed=retry_failed, job_id=job_id)


@app.command()
def auto(
    min_score: int = typer.Option(70, "--min-score", "-s", help="Minimum score to auto-apply (0-100)"),
) -> None:
    """Full automated pipeline: scan → score → apply all strong matches.

    Runs all three pipeline stages in sequence. Applies for every job
    with score >= min_score that doesn't already have application materials.

    Equivalent to: career scan && career score && career apply <each strong job>
    """
    from career_ai.pipeline.auto import run_auto
    run_auto(min_score=min_score)


@app.command()
def status(
    job_id: str = typer.Argument(..., help="Job ID to update"),
    new_status: str = typer.Argument(..., help="New status: applied|interview|offer|rejected|discarded"),
    notes: str = typer.Option("", "--notes", "-n", help="Optional notes"),
) -> None:
    """Update the status of an application in the tracker."""
    from career_ai.models import ApplicationStatus
    from career_ai.storage.tracker import get_tracker

    try:
        s = ApplicationStatus(new_status.lower())
    except ValueError:
        valid = ", ".join(v.value for v in ApplicationStatus)
        console.print(f"[red]Invalid status '{new_status}'. Valid values: {valid}[/red]")
        raise typer.Exit(1)

    tracker = get_tracker()
    ok = tracker.update_status(job_id, s, notes)
    if ok:
        console.print(f"[green]✓ {job_id} → {new_status}[/green]")
    else:
        console.print(f"[yellow]Job {job_id} not found in tracker.[/yellow]")
        raise typer.Exit(1)
