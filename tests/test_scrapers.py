"""Tests for scrapers — using httpx mocking."""

from __future__ import annotations

import json

import pytest

from career_ai.models import make_job_id


@pytest.fixture
def greenhouse_response() -> dict:
    return {
        "jobs": [
            {
                "id": 1001,
                "title": "Senior Frontend Engineer",
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1001",
                "location": {"name": "Remote"},
                "content": "<p>We need a React engineer.</p><ul><li>React 5+ years</li><li>TypeScript</li></ul>",
            },
            {
                "id": 1002,
                "title": "Junior Backend Engineer",  # Should be filtered by title filter
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1002",
                "location": {"name": "NYC"},
                "content": "<p>Node.js role.</p>",
            },
        ]
    }


@pytest.fixture
def lever_response() -> list:
    return [
        {
            "id": "lever-001",
            "text": "Senior React Developer",
            "hostedUrl": "https://jobs.lever.co/acme/lever-001",
            "categories": {"location": "Remote, EU"},
            "descriptionPlain": "Looking for a React developer with 4+ years experience.",
            "description": "<p>Looking for a React developer.</p>",
        }
    ]


@pytest.mark.asyncio
async def test_greenhouse_scraper_extracts_jobs(respx_mock, greenhouse_response):
    pytest.importorskip("respx")
    import respx
    import httpx
    from career_ai.scrapers.greenhouse import GreenhouseScraper

    api_url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    respx.get(api_url + "?content=true").mock(
        return_value=httpx.Response(200, json=greenhouse_response)
    )

    scraper = GreenhouseScraper("Acme", api_url)
    jobs = await scraper.fetch_jobs()

    assert len(jobs) == 2
    assert jobs[0].title == "Senior Frontend Engineer"
    assert jobs[0].source == "greenhouse"
    assert jobs[0].company == "Acme"
    assert jobs[0].job_id == make_job_id("https://job-boards.greenhouse.io/acme/jobs/1001")


@pytest.mark.asyncio
async def test_greenhouse_scraper_returns_empty_on_error(respx_mock):
    pytest.importorskip("respx")
    import respx
    import httpx
    from career_ai.scrapers.greenhouse import GreenhouseScraper

    api_url = "https://boards-api.greenhouse.io/v1/boards/bad/jobs"
    respx.get(api_url + "?content=true").mock(return_value=httpx.Response(404))

    scraper = GreenhouseScraper("Bad Co", api_url)
    jobs = await scraper.fetch_jobs()
    assert jobs == []


@pytest.mark.asyncio
async def test_lever_scraper_extracts_jobs(respx_mock, lever_response):
    pytest.importorskip("respx")
    import respx
    import httpx
    from career_ai.scrapers.lever import LeverScraper

    api_url = "https://api.lever.co/v0/postings/acme"
    respx.get(api_url + "?mode=json").mock(
        return_value=httpx.Response(200, json=lever_response)
    )

    scraper = LeverScraper("Acme", api_url)
    jobs = await scraper.fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0].title == "Senior React Developer"
    assert jobs[0].source == "lever"
    assert jobs[0].url == "https://jobs.lever.co/acme/lever-001"
    assert jobs[0].location == "Remote, EU"


def test_job_id_is_stable():
    url = "https://example.com/jobs/123"
    assert make_job_id(url) == make_job_id(url)
    assert len(make_job_id(url)) == 12


def test_title_filter_logic():
    from career_ai.pipeline.scan import _build_title_filter

    filter_cfg = {
        "positive": ["Frontend", "React"],
        "negative": ["Junior", "Intern"],
    }
    f = _build_title_filter(filter_cfg)

    assert f("Senior Frontend Engineer") is True
    assert f("React Developer") is True
    assert f("Junior Frontend Engineer") is False
    assert f("Backend Engineer") is False
    assert f("Frontend Intern") is False
