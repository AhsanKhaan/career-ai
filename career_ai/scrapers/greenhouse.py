"""Greenhouse scraper.

API: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
The ?content=true param returns full job descriptions in a single call.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from career_ai.models import Job
from career_ai.scrapers.base import BaseScraper

_TIMEOUT = 15.0


class GreenhouseScraper(BaseScraper):
    async def fetch_jobs(self) -> list[Job]:
        url = self.api_url
        if "?" not in url:
            url = url + "?content=true"
        elif "content=true" not in url:
            url = url + "&content=true"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return []

        jobs: list[Job] = []
        now = datetime.now(timezone.utc).isoformat()

        for j in data.get("jobs", []):
            job_url = j.get("absolute_url", "")
            if not job_url:
                continue
            html = j.get("content", "")
            location = j.get("location", {})
            if isinstance(location, dict):
                location = location.get("name", "")

            jobs.append(
                Job(
                    job_id=self._make_job_id(job_url),
                    company=self.company_name,
                    title=j.get("title", ""),
                    location=location,
                    url=job_url,
                    description=self._strip_html(html)[:8000],
                    requirements=self._extract_requirements(html),
                    source="greenhouse",
                    scanned_at=now,
                )
            )
        return jobs


def build_api_url(slug: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
