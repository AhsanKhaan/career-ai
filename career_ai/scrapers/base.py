"""Abstract base scraper.

All scrapers produce a list[Job] from a company slug + API URL.
job_id is always computed via make_job_id(url) for stable deduplication.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from career_ai.models import Job, make_job_id


class BaseScraper(ABC):
    def __init__(self, company_name: str, api_url: str) -> None:
        self.company_name = company_name
        self.api_url = api_url

    @abstractmethod
    async def fetch_jobs(self) -> list[Job]:
        """Fetch raw job data from the portal API and return normalized Jobs."""
        ...

    def _make_job_id(self, url: str) -> str:
        return make_job_id(url)

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags and collapse whitespace."""
        text = re.sub(r"<[^>]+>", " ", html or "")
        return re.sub(r"\s+", " ", text).strip()

    def _extract_requirements(self, html: str) -> list[str]:
        """Extract <li> items from requirements/qualifications sections of HTML."""
        items: list[str] = []
        # Find <li> tags after headings that indicate requirements
        req_section = re.search(
            r"(?:requirements|qualifications|what you.ll need|you have)(.*?)(?:<h\d|$)",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        source = req_section.group(1) if req_section else html
        for li in re.findall(r"<li[^>]*>(.*?)</li>", source, re.IGNORECASE | re.DOTALL):
            cleaned = self._strip_html(li).strip()
            if cleaned and len(cleaned) < 200:
                items.append(cleaned)
        return items[:15]  # cap at 15 requirements
