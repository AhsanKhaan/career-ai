"""Fetch a single job posting from an arbitrary URL.

Unlike the Greenhouse/Lever/Ashby scrapers which hit structured list APIs,
this uses the `claude` CLI's WebFetch tool to read and parse a single
posting page. Works for any site, including SPA boards where raw HTML
scraping would fail.

Returns a fully-populated Job object. No Playwright, no httpx — the
claude worker does the fetch.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from career_ai.ai.client import get_claude_client
from career_ai.ai.prompts import load_prompt
from career_ai.models import Job, make_job_id


def fetch_job_from_url(url: str) -> Job:
    """Fetch a job posting from any URL via claude WebFetch.

    Raises:
        ValueError: If the URL is malformed.
        RuntimeError: If claude returns an empty/unparseable response twice.
    """
    if not _looks_like_url(url):
        raise ValueError(f"Not a valid URL: {url!r}")

    client = get_claude_client()
    prompt = load_prompt("extract_jd", url=url)

    raw = client._call(prompt)
    data = _parse_json_object(raw)

    if data is None or not data.get("title"):
        # One retry with stricter suffix
        raw = client._call(prompt + "\n\nReturn ONLY the JSON object. No other text.")
        data = _parse_json_object(raw)

    if data is None:
        raise RuntimeError(
            f"Could not extract job posting from {url}. "
            "The page may be behind a login wall or the claude worker timed out."
        )

    # If the page returned nothing (404, login wall), data has empty fields
    # and we still build a minimal Job — caller decides whether to proceed.
    title = (data.get("title") or "").strip()
    if not title:
        raise RuntimeError(
            f"Fetched {url} but the posting has no title. "
            "It may be expired, behind a login, or not a job page."
        )

    source = (data.get("source") or "").strip().lower() or _infer_source(url)

    return Job(
        job_id=make_job_id(url),
        company=(data.get("company") or "").strip(),
        title=title,
        location=(data.get("location") or "").strip(),
        url=url,
        description=(data.get("description") or "").strip(),
        requirements=[str(r).strip() for r in data.get("requirements", []) if str(r).strip()],
        source=source,
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


def _looks_like_url(s: str) -> bool:
    try:
        p = urlparse(s)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except ValueError:
        return False


def _infer_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "greenhouse.io" in host or "grnh.se" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "ashbyhq.com" in host:
        return "ashby"
    if "myworkdayjobs.com" in host or "workday" in host:
        return "workday"
    if "wellfound.com" in host or "angel.co" in host:
        return "wellfound"
    return "url"


def _parse_json_object(text: str) -> dict | None:
    """Extract the first {...} block from claude's response and parse it."""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        result = json.loads(match.group())
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None
