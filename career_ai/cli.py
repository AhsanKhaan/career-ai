"""CLI entry point.

Commands use lazy imports so that 'career scan' never imports
Playwright or the Anthropic SDK unless those commands are invoked.

OpenClaw: profile.yml and portals.yml are NOT read at import time.
Config is only loaded when a command that needs it actually runs.
"""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

# Load .env before anything else (sets ANTHROPIC_API_KEY etc.)
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
