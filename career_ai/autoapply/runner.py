"""Auto-apply orchestrator.

Safety rules (non-negotiable):
1. career apply <job_id> MUST run first — ats_summary must exist
2. Shows exactly what will happen and requires "yes" confirmation
3. fill_and_pause: fills form, then STOPS — user reviews in browser
4. Submit only happens after user presses Enter in terminal
5. Never auto-submits without explicit human confirmation
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel

from career_ai.config import get_config
from career_ai.storage.cache import find_job

console = Console()


def run_autoapply(job_id: str) -> None:
    job = find_job(job_id)
    if job is None:
        console.print(
            f"[red]Job '{job_id}' not found. Run [bold]career scan[/bold] first.[/red]"
        )
        raise typer.Exit(1)

    if not job.ats_summary:
        console.print(
            f"[yellow]No application materials found for {job_id}.\n"
            f"Run [bold]career apply {job_id}[/bold] first.[/yellow]"
        )
        raise typer.Exit(1)

    handler = _detect_handler(job.url)
    if handler is None:
        console.print(
            f"[red]No auto-apply handler for URL: {job.url}\n"
            "Supported: Greenhouse, Lever, Ashby[/red]"
        )
        raise typer.Exit(1)

    # Safety gate — show preview
    console.print(
        Panel(
            f"[bold]Auto-apply will:[/bold]\n\n"
            f"1. Open [link={job.url}]{job.url}[/link]\n"
            f"2. Fill the application form with your profile data\n"
            f"3. Upload your resume (if configured)\n"
            f"4. [bold yellow]PAUSE[/bold yellow] — you review the filled form in the browser\n"
            f"5. Submit [bold]only after you confirm[/bold] here in the terminal\n\n"
            f"[dim]Job: {job.title} @ {job.company}[/dim]",
            title="[yellow]Auto-Apply Preview[/yellow]",
            border_style="yellow",
        )
    )

    confirm = typer.prompt("Type 'yes' to continue (or press Ctrl+C to abort)")
    if confirm.strip().lower() != "yes":
        console.print("[dim]Aborted.[/dim]")
        raise typer.Exit(0)

    cfg = get_config()
    asyncio.run(handler.fill_and_pause(job, cfg.profile))


def _detect_handler(url: str):
    """Return the appropriate form handler based on URL, or None."""
    if "greenhouse.io" in url or "grnh.se" in url:
        from career_ai.autoapply.forms.greenhouse import GreenhouseFormHandler
        return GreenhouseFormHandler()
    if "lever.co" in url:
        from career_ai.autoapply.forms.lever import LeverFormHandler
        return LeverFormHandler()
    if "ashbyhq.com" in url or "jobs.ashbyhq.com" in url:
        from career_ai.autoapply.forms.ashby import AshbyFormHandler
        return AshbyFormHandler()
    return None
