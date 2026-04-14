"""Apply pipeline stage.

Generates ATS summary, cover letter, and keywords for a single job.
Writes materials back to cache and records the application in SQLite tracker.

OpenClaw rules enforced:
- Checks job.ats_summary == "" before calling Claude (never re-generates)
- Session state prevents double-applying within one process run
"""

from __future__ import annotations

from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel

from career_ai.ai.client import get_claude_client
from career_ai.models import Application, ApplicationStatus
from career_ai.session import get_session
from career_ai.storage.cache import find_job, update_job_in_cache
from career_ai.storage.tracker import get_tracker

console = Console()


def run_apply(job_id: str) -> None:
    session = get_session()

    if session.is_applied(job_id):
        console.print(f"[dim]Already generated materials for {job_id} this session.[/dim]")
        return

    job = find_job(job_id)
    if job is None:
        console.print(f"[red]Job '{job_id}' not found in cache. Run [bold]career scan[/bold] first.[/red]")
        raise typer.Exit(1)

    if job.ats_summary:
        console.print(f"[yellow]Materials already exist for {job_id}. Showing existing:[/yellow]")
        _print_materials(job.ats_summary, job.cover_letter, job.keywords)
        return

    console.print(f"[bold]Generating application for: {job.title} @ {job.company}[/bold]")

    client = get_claude_client()
    result = client.generate_application(job)

    if not result.get("ats_summary"):
        console.print("[red]Failed to generate application materials. Try again.[/red]")
        raise typer.Exit(1)

    # Write materials back to cache
    update_job_in_cache(job_id, {
        "ats_summary": result["ats_summary"],
        "cover_letter": result["cover_letter"],
        "keywords": result["keywords"],
    })

    # Record in tracker
    tracker = get_tracker()
    tracker.upsert_application(Application(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        status=ApplicationStatus.APPLIED,
        score=job.score,
        applied_at=datetime.now(timezone.utc).isoformat(),
    ))

    session.mark_applied(job_id)
    _print_materials(result["ats_summary"], result["cover_letter"], result["keywords"])

    console.print(
        f"\n[green]✓ Saved to cache and tracker.[/green] "
        f"Run [bold]career track[/bold] to see all applications."
    )


def _print_materials(ats_summary: str, cover_letter: str, keywords: list[str]) -> None:
    console.print(Panel(ats_summary, title="[bold cyan]ATS Summary[/bold cyan]", border_style="cyan"))
    console.print(Panel(cover_letter, title="[bold green]Cover Letter[/bold green]", border_style="green"))
    bullet_points = "\n".join(f"  • {k}" for k in keywords)
    console.print(Panel(bullet_points, title="[bold yellow]Keywords[/bold yellow]", border_style="yellow"))
