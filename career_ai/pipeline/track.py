"""Track pipeline stage — zero token cost.

Reads all applications from SQLite and renders a Rich table.
No AI. No cache reads. Pure tracker query.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from career_ai.models import ApplicationStatus
from career_ai.storage.tracker import get_tracker

console = Console()

_STATUS_COLORS = {
    ApplicationStatus.APPLIED.value:   "green",
    ApplicationStatus.INTERVIEW.value: "yellow",
    ApplicationStatus.OFFER.value:     "bright_green",
    ApplicationStatus.REJECTED.value:  "red",
    ApplicationStatus.DISCARDED.value: "dim",
    ApplicationStatus.SCORED.value:    "blue",
    ApplicationStatus.PENDING.value:   "white",
}


def run_track() -> None:
    tracker = get_tracker()
    apps = tracker.get_all_applications()

    if not apps:
        console.print(
            "[dim]No applications yet. Run [bold]career apply <job_id>[/bold] to start.[/dim]"
        )
        return

    table = Table(title=f"Application Tracker ({len(apps)} entries)", show_header=True)
    table.add_column("Job ID", style="dim", width=14)
    table.add_column("Company", style="cyan")
    table.add_column("Title", max_width=40)
    table.add_column("Score", justify="right", width=6)
    table.add_column("Status", width=12)
    table.add_column("Applied At", style="dim", width=12)
    table.add_column("Notes", style="dim", max_width=30)

    for app in apps:
        status_val = app.status.value
        color = _STATUS_COLORS.get(status_val, "white")
        score_color = "bright_green" if app.score >= 70 else ("yellow" if app.score >= 50 else "dim")
        applied = app.applied_at[:10] if app.applied_at else "-"

        table.add_row(
            app.job_id,
            app.company,
            app.title,
            f"[{score_color}]{app.score or '—'}[/{score_color}]",
            f"[{color}]{status_val}[/{color}]",
            applied,
            app.notes[:30] if app.notes else "",
        )

    console.print(table)

    # Summary counts
    by_status: dict[str, int] = {}
    for app in apps:
        by_status[app.status.value] = by_status.get(app.status.value, 0) + 1

    summary = "  ".join(
        f"[{_STATUS_COLORS.get(s, 'white')}]{s}[/{_STATUS_COLORS.get(s, 'white')}]: {n}"
        for s, n in sorted(by_status.items())
    )
    console.print(f"\n{summary}")
