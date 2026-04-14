"""Ashby scraper.

List API:  https://api.ashbyhq.com/posting-api/job-board/{slug}
Detail API: https://api.ashbyhq.com/posting-api/job-board/{slug}/job-posting/{id}

Two-call strategy:
1. Fetch all job listings (fast, no description)
2. Fetch description only for jobs that pass the title filter
   (passed in as seen_filter callable to avoid tight coupling)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

from career_ai.models import Job
from career_ai.scrapers.base import BaseScraper

_TIMEOUT = 15.0


class AshbyScraper(BaseScraper):
    async def fetch_jobs(
        self,
        title_filter: Callable[[str], bool] | None = None,
    ) -> list[Job]:
        list_url = self.api_url
        if "includeCompensation" not in list_url:
            list_url = list_url + ("&" if "?" in list_url else "?") + "includeCompensation=true"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(list_url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return []

        raw_jobs = data.get("jobs", [])
        now = datetime.now(timezone.utc).isoformat()
        jobs: list[Job] = []

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            for j in raw_jobs:
                title = j.get("title", "")
                # Apply title filter before fetching description (saves API calls)
                if title_filter and not title_filter(title):
                    continue

                job_url = j.get("jobUrl", "")
                if not job_url:
                    continue

                location = j.get("location", "") or j.get("locationName", "")
                ashby_id = j.get("id", "")
                description = ""
                requirements: list[str] = []

                # Fetch full description for filtered jobs only
                if ashby_id:
                    slug = _extract_slug(self.api_url)
                    detail_url = (
                        f"https://api.ashbyhq.com/posting-api/job-board"
                        f"/{slug}/job-posting/{ashby_id}"
                    )
                    try:
                        detail_resp = await client.get(detail_url)
                        if detail_resp.status_code == 200:
                            detail = detail_resp.json()
                            html = detail.get("descriptionHtml", "")
                            description = self._strip_html(html)[:8000]
                            requirements = self._extract_requirements(html)
                    except httpx.HTTPError:
                        pass

                jobs.append(
                    Job(
                        job_id=self._make_job_id(job_url),
                        company=self.company_name,
                        title=title,
                        location=location,
                        url=job_url,
                        description=description,
                        requirements=requirements,
                        source="ashby",
                        scanned_at=now,
                    )
                )
        return jobs


def _extract_slug(api_url: str) -> str:
    """Extract company slug from Ashby API URL."""
    parts = api_url.rstrip("/").split("/")
    return parts[-1] if parts else ""


def build_api_url(slug: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
