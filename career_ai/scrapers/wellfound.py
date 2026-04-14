"""Wellfound (AngelList Talent) scraper — optional, Playwright-based.

Wellfound has no public API, so this uses headless Chromium to scrape job cards.
Descriptions are not fetched (too expensive per-job) — score stage uses title+company only.

Only used when a company in portals.yml has:
  scan_method: playwright
  careers_url: https://wellfound.com/...
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from career_ai.models import Job, make_job_id


class WellfoundScraper:
    def __init__(self, company_name: str, careers_url: str) -> None:
        self.company_name = company_name
        self.careers_url = careers_url

    async def fetch_jobs(
        self,
        title_filter: Callable[[str], bool] | None = None,
    ) -> list[Job]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return []

        jobs: list[Job] = []
        now = datetime.now(timezone.utc).isoformat()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(self.careers_url, timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=15000)

                # Scroll to load lazy content
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 1000)")
                    await asyncio.sleep(1)

                # Extract job cards
                cards = await page.query_selector_all('[data-test="StartupResult"], .styles_component__job')
                for card in cards:
                    try:
                        title_el = await card.query_selector("h2, h3, [class*='title']")
                        title = (await title_el.inner_text()).strip() if title_el else ""

                        if title_filter and not title_filter(title):
                            continue

                        link_el = await card.query_selector("a")
                        href = await link_el.get_attribute("href") if link_el else ""
                        if not href:
                            continue
                        if not href.startswith("http"):
                            href = f"https://wellfound.com{href}"

                        location_el = await card.query_selector("[class*='location'], [class*='remote']")
                        location = (await location_el.inner_text()).strip() if location_el else ""

                        jobs.append(
                            Job(
                                job_id=make_job_id(href),
                                company=self.company_name,
                                title=title,
                                location=location,
                                url=href,
                                description="",  # Not fetched — too expensive
                                requirements=[],
                                source="wellfound",
                                scanned_at=now,
                            )
                        )
                    except Exception:
                        continue
            finally:
                await browser.close()

        return jobs
