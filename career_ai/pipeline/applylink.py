"""One-shot URL → tailored résumé → auto-apply.

Flow:
  1. make_job_id(url) — deterministic, so re-running the same URL is idempotent
  2. Fetch JD via claude WebFetch (career_ai.scrapers.url_fetcher)
  3. Persist Job to data/cache/<today>.json
  4. Generate ats_summary + cover_letter + keywords (reuses apply client)
  5. Generate tailored résumé JSON → output/resume-<id>.docx → .pdf
  6. Record in SQLite tracker as SCORED
  7. If URL matches a known form handler, show preview + confirmation
  8. handler.fill_and_pause(...) — browser pauses before submit
  9. Tracker status → APPLIED

Idempotency: if the job is already in cache with ats_summary set, steps
2-5 are skipped. A stale résumé PDF is always re-generated so the user
can iterate on their profile.yml without a manual rm.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from career_ai.ai.client import get_claude_client
from career_ai.autoapply.runner import _detect_handler
from career_ai.config import get_config
from career_ai.models import Application, ApplicationStatus, Job, make_job_id
from career_ai.resume import convert_to_pdf, generate_resume, render_docx
from career_ai.scrapers.url_fetcher import fetch_job_from_url
from career_ai.storage.cache import append_jobs, find_job, update_job_in_cache
from career_ai.storage.tracker import get_tracker

console = Console()

OUTPUT_DIR = Path("output")


def run_applylink(url: str) -> None:
    """Execute the full paste-a-link pipeline for `url`."""
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        console.print(f"[red]Not a valid URL: {url!r}[/red]")
        raise typer.Exit(1)

    cfg = get_config()  # validates profile.yml + portals.yml exist
    job_id = make_job_id(url)

    # 1. Fetch JD (skip if already cached with materials)
    job = find_job(job_id)
    if job is not None and job.ats_summary:
        console.print(f"[dim][1/7] Job already cached with materials: {job_id}[/dim]")
    else:
        console.print(f"[cyan][1/7] Fetching JD from {url}…[/cyan]")
        try:
            job = fetch_job_from_url(url)
        except RuntimeError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        console.print(f"[green]  ↳ {job.title} @ {job.company} ({job.location or 'no location'})[/green]")
        append_jobs([job])  # writes to today's cache file

    # 2. Generate ATS materials if missing
    if not job.ats_summary:
        console.print("[cyan][2/7] Generating ATS summary, cover letter, keywords…[/cyan]")
        client = get_claude_client()
        materials = client.generate_application(job)
        if not materials.get("ats_summary"):
            console.print("[red]Failed to generate application materials.[/red]")
            raise typer.Exit(1)
        update_job_in_cache(job_id, {
            "ats_summary": materials["ats_summary"],
            "cover_letter": materials["cover_letter"],
            "keywords": materials["keywords"],
        })
        job.ats_summary = materials["ats_summary"]
        job.cover_letter = materials["cover_letter"]
        job.keywords = materials["keywords"]
        console.print(f"[green]  ↳ {len(job.keywords)} keywords: {', '.join(job.keywords[:5])}[/green]")
    else:
        console.print("[dim][2/7] Materials already exist — reusing.[/dim]")

    # 3. Tailored résumé
    console.print("[cyan][3/7] Tailoring résumé for this job…[/cyan]")
    resume_json = generate_resume(job, job.keywords)
    if not resume_json.get("name"):
        # Fall back to profile name so rendering still works
        resume_json["name"] = cfg.profile.get("candidate", {}).get("full_name", "Candidate")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    docx_path = OUTPUT_DIR / f"resume-{job_id}.docx"
    pdf_path = OUTPUT_DIR / f"resume-{job_id}.pdf"

    try:
        render_docx(resume_json, docx_path)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]  ↳ DOCX: {docx_path}[/green]")

    converted = convert_to_pdf(docx_path, pdf_path)
    if converted is not None:
        console.print(f"[green]  ↳ PDF:  {pdf_path}[/green]")
        resume_upload = pdf_path
    else:
        console.print(
            "[yellow]  ↳ PDF conversion unavailable (Word/LibreOffice not found). "
            "Will upload the DOCX instead — all major ATS systems accept it.[/yellow]"
        )
        resume_upload = docx_path

    # 4. Tracker entry (SCORED until we actually submit)
    tracker = get_tracker()
    tracker.upsert_application(Application(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        status=ApplicationStatus.SCORED,
        score=job.score,
    ))
    console.print(f"[dim][4/7] Tracker updated: status=scored, job_id={job_id}[/dim]")

    # 5. Detect autoapply handler
    handler = _detect_handler(job.url)
    if handler is None:
        console.print(Panel(
            f"No auto-apply handler for this URL host.\n"
            f"Supported: Greenhouse, Lever, Ashby.\n\n"
            f"Your tailored materials are ready:\n"
            f"  • Résumé:      {resume_upload}\n"
            f"  • Cover letter: in cache (run [bold]career apply {job_id}[/bold] to reprint)\n"
            f"  • Keywords:    {', '.join(job.keywords[:5])}\n\n"
            f"Apply manually at: {job.url}",
            title="[yellow]Materials ready — manual apply[/yellow]",
            border_style="yellow",
        ))
        return

    # 6. Preview + confirmation
    console.print(Panel(
        f"[bold]Auto-apply will:[/bold]\n\n"
        f"1. Open [link={job.url}]{job.url}[/link]\n"
        f"2. Fill the form with your profile data\n"
        f"3. Upload [bold]{resume_upload.name}[/bold]\n"
        f"4. [bold yellow]PAUSE[/bold yellow] — you review the filled form in the browser\n"
        f"5. Submit [bold]only after you confirm[/bold] here in the terminal\n\n"
        f"[dim]Job: {job.title} @ {job.company}[/dim]",
        title="[yellow][5/7] Auto-Apply Preview[/yellow]",
        border_style="yellow",
    ))

    confirm = typer.prompt("Type 'yes' to continue (or press Ctrl+C to abort)")
    if confirm.strip().lower() != "yes":
        console.print("[dim]Aborted. Materials saved; tracker status = scored.[/dim]")
        return

    # 7. Fill form + pause
    console.print("[cyan][6/7] Opening browser…[/cyan]")
    asyncio.run(handler.fill_and_pause(job, cfg.profile, resume_pdf=resume_upload))

    # 8. Mark applied (we only reach here if the browser flow didn't raise)
    tracker.upsert_application(Application(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        status=ApplicationStatus.APPLIED,
        score=job.score,
        applied_at=datetime.now(timezone.utc).isoformat(),
    ))
    console.print("[green][7/7] ✓ Marked as applied in tracker.[/green]")
