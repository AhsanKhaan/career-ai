"""Scan pipeline stage — OpenClaw Rule 2: ZERO TOKENS.

career scan hits job APIs directly via HTTP.
No Claude API calls. No AI. No token cost.

Flow:
1. Load config (singleton, cached)
2. Build seen_ids set from existing cache (dedup)
3. For each enabled company in portals.yml, detect API type and fire request
4. Apply title_filter locally (string matching)
5. Write NEW jobs only to data/cache/YYYY-MM-DD.json
"""

from __future__ import annotations

import asyncio
from typing import Callable

from rich.console import Console
from rich.table import Table

from career_ai.config import get_config
from career_ai.models import Job
from career_ai.storage.cache import append_jobs, get_all_seen_ids

console = Console()

_CONCURRENCY = 10  # Max simultaneous HTTP requests


def run_scan() -> None:
    asyncio.run(_async_scan())


async def _async_scan() -> None:
    cfg = get_config()
    portals = cfg.portals

    seen_ids = get_all_seen_ids()
    companies = [c for c in portals.get("tracked_companies", []) if c.get("enabled", True)]

    if not companies:
        console.print("[yellow]No enabled companies in portals.yml[/yellow]")
        return

    title_filter = _build_title_filter(portals.get("title_filter", {}))

    console.print(f"[bold]Scanning {len(companies)} companies...[/bold]")

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    tasks = [_scan_company(c, seen_ids, title_filter, semaphore) for c in companies]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect all new jobs
    all_new: list[Job] = []
    errors: list[str] = []

    for company, result in zip(companies, results):
        if isinstance(result, Exception):
            errors.append(f"{company.get('name', '?')}: {result}")
        elif isinstance(result, list):
            all_new.extend(result)

    # Write to cache (dedup happens inside append_jobs)
    written = append_jobs(all_new, source_count=len(companies))

    _print_results(all_new, written, errors)


async def _scan_company(
    company: dict,
    seen_ids: set[str],
    title_filter: Callable[[str], bool],
    semaphore: asyncio.Semaphore,
) -> list[Job]:
    """Detect scraper type, fetch jobs, apply filters."""
    async with semaphore:
        name = company.get("name", "Unknown")
        careers_url = company.get("careers_url", "")
        api_url = company.get("api", "")
        scan_method = company.get("scan_method", "").lower()

        jobs: list[Job] = []

        try:
            if api_url or _is_greenhouse_url(careers_url):
                from career_ai.scrapers.greenhouse import GreenhouseScraper
                scraper = GreenhouseScraper(name, api_url or careers_url)
                jobs = await scraper.fetch_jobs()

            elif _is_lever_url(careers_url):
                from career_ai.scrapers.lever import LeverScraper
                scraper = LeverScraper(name, careers_url)
                jobs = await scraper.fetch_jobs()

            elif _is_ashby_url(careers_url):
                from career_ai.scrapers.ashby import AshbyScraper
                scraper = AshbyScraper(name, careers_url)
                jobs = await scraper.fetch_jobs(title_filter=title_filter)

            elif scan_method == "playwright" or "wellfound.com" in careers_url:
                from career_ai.scrapers.wellfound import WellfoundScraper
                scraper = WellfoundScraper(name, careers_url)
                jobs = await scraper.fetch_jobs(title_filter=title_filter)

            # For websearch-method companies, skip silently (no scraper yet)

        except Exception as e:
            console.print(f"[red]  ✗ {name}: {e}[/red]")
            return []

        # Apply title filter (for scrapers that don't filter internally)
        if not _is_ashby_url(careers_url) and "wellfound.com" not in careers_url:
            jobs = [j for j in jobs if title_filter(j.title)]

        # Apply dedup against cache
        jobs = [j for j in jobs if j.job_id not in seen_ids]

        return jobs


def _build_title_filter(title_filter_cfg: dict) -> Callable[[str], bool]:
    """Build a filter function from portals.yml title_filter section."""
    positives = [k.lower() for k in title_filter_cfg.get("positive", [])]
    negatives = [k.lower() for k in title_filter_cfg.get("negative", [])]

    def passes(title: str) -> bool:
        t = title.lower()
        if positives and not any(p in t for p in positives):
            return False
        if any(n in t for n in negatives):
            return False
        return True

    return passes


def _is_greenhouse_url(url: str) -> bool:
    return "greenhouse.io" in url


def _is_lever_url(url: str) -> bool:
    return "lever.co" in url


def _is_ashby_url(url: str) -> bool:
    return "ashbyhq.com" in url


def _print_results(all_new: list[Job], written: int, errors: list[str]) -> None:
    if not all_new and not errors:
        console.print("[dim]Nothing new found.[/dim]")
        return

    if all_new:
        table = Table(title=f"New Jobs Found: {written}", show_header=True)
        table.add_column("Company", style="cyan")
        table.add_column("Title")
        table.add_column("Location", style="dim")
        table.add_column("Job ID", style="dim")

        for job in all_new[:50]:  # Show at most 50 rows
            table.add_row(job.company, job.title, job.location, job.job_id)

        if len(all_new) > 50:
            table.add_row(f"... and {len(all_new) - 50} more", "", "", "")

        console.print(table)

    for err in errors:
        console.print(f"[red]Error: {err}[/red]")

    console.print(
        f"\n[green]✓ {written} new jobs cached.[/green] "
        f"Run [bold]career score[/bold] to score them."
    )
