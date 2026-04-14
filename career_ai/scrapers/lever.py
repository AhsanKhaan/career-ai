"""Lever scraper.

API: https://api.lever.co/v0/postings/{slug}?mode=json
Response is a top-level list of posting objects.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from career_ai.models import Job
from career_ai.scrapers.base import BaseScraper

_TIMEOUT = 15.0


class LeverScraper(BaseScraper):
    async def fetch_jobs(self) -> list[Job]:
        url = self.api_url
        if "mode=json" not in url:
            url = url + ("&" if "?" in url else "?") + "mode=json"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError:
            return []

        if not isinstance(data, list):
            return []

        jobs: list[Job] = []
        now = datetime.now(timezone.utc).isoformat()

        for j in data:
            job_url = j.get("hostedUrl", "")
            if not job_url:
                continue

            categories = j.get("categories", {})
            location = categories.get("location", "") if isinstance(categories, dict) else ""

            # Description is HTML in j["descriptionPlain"] or j["description"]
            html = j.get("description", "")
            plain = j.get("descriptionPlain", "")
            description = plain if plain else self._strip_html(html)

            jobs.append(
                Job(
                    job_id=self._make_job_id(job_url),
                    company=self.company_name,
                    title=j.get("text", ""),
                    location=location,
                    url=job_url,
                    description=description[:8000],
                    requirements=self._extract_requirements(html),
                    source="lever",
                    scanned_at=now,
                )
            )
        return jobs


def build_api_url(slug: str) -> str:
    return f"https://api.lever.co/v0/postings/{slug}"
