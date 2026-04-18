"""Tests for the applylink pipeline.

The orchestrator does a lot, so we mock the three external boundaries:
1. claude CLI (CareerAIClient._call)                     — stubbed with canned JSON
2. docx2pdf conversion (convert_to_pdf)                  — returns the docx path (as if converted)
3. _detect_handler                                       — returns None so we stop before browser

We verify:
- URL → Job is cached
- ATS materials are written back to cache
- Tailored résumé DOCX is created on disk
- Tracker row is created as SCORED
- No browser is launched when handler is None
- Re-running with the same URL is idempotent (no duplicate claude calls)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from career_ai.models import make_job_id


TEST_URL = "https://jobs.lever.co/acme/abc-123"
TEST_JOB_ID = make_job_id(TEST_URL)


@pytest.fixture
def fake_jd_response() -> str:
    return json.dumps({
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "description": "We need a Python engineer with 5+ years building distributed systems.",
        "requirements": ["Python", "PostgreSQL", "Kubernetes"],
        "source": "lever",
    })


@pytest.fixture
def fake_materials_response() -> str:
    return json.dumps({
        "ats_summary": "Senior Backend Engineer with 7 years scaling Python distributed systems.",
        "cover_letter": "Dear Hiring Team,\n\nParagraph one.\n\nParagraph two.\n\nParagraph three.",
        "keywords": ["Python", "PostgreSQL", "Kubernetes", "Distributed Systems", "Backend"],
    })


@pytest.fixture
def fake_resume_response() -> str:
    return json.dumps({
        "name": "Test User",
        "contact": {
            "email": "test@example.com",
            "phone": "+1-555-0000",
            "location": "Remote",
            "links": [],
        },
        "summary": "Senior Backend Engineer with 7 years scaling Python services.",
        "experience": [
            {
                "company": "Acme Corp",
                "title": "Staff Engineer",
                "dates": "2021 - Present",
                "location": "Remote",
                "bullets": ["Built stuff", "Scaled things"],
            }
        ],
        "skills": ["Python", "PostgreSQL", "Kubernetes"],
        "education": [],
    })


@pytest.fixture
def configured_project(
    tmp_cache_dir,
    profile_yml_file,
    portals_yml_file,
    tmp_path: Path,
    monkeypatch,
):
    """Point config at temp profile, tracker at temp db, output at temp dir."""
    from career_ai.config import get_config
    get_config(str(profile_yml_file), str(portals_yml_file))

    # Redirect tracker to tmp db (patch the singleton, since DB_PATH default
    # is frozen at function-definition time)
    import career_ai.storage.tracker as tracker_mod
    from career_ai.storage.tracker import ApplicationTracker
    tracker_mod._TRACKER = ApplicationTracker(db_path=tmp_path / "tracker.db")

    # Redirect output dir so tests don't pollute the repo
    import career_ai.pipeline.applylink as applylink_mod
    monkeypatch.setattr(applylink_mod, "OUTPUT_DIR", tmp_path / "output")

    return tmp_path


def test_applylink_happy_path_no_handler(
    configured_project,
    fake_jd_response,
    fake_materials_response,
    fake_resume_response,
):
    """URL with no matching form handler: steps 1-4 run, no browser, exits clean."""
    responses = iter([fake_jd_response, fake_materials_response, fake_resume_response])

    with patch("career_ai.ai.client.CareerAIClient._call", side_effect=lambda _p: next(responses)):
        # Force "no handler" path — Workday URL
        workday_url = "https://acme.wd1.myworkdayjobs.com/en-US/jobs/abc-456"
        with patch(
            "career_ai.pipeline.applylink._detect_handler",
            return_value=None,
        ):
            from career_ai.pipeline.applylink import run_applylink
            run_applylink(workday_url)

    # Job cached
    from career_ai.storage.cache import find_job
    wd_id = make_job_id(workday_url)
    cached = find_job(wd_id)
    assert cached is not None
    assert cached.title == "Senior Backend Engineer"
    assert cached.company == "Acme"
    assert cached.ats_summary.startswith("Senior Backend Engineer")
    assert len(cached.keywords) == 5

    # Résumé DOCX exists on disk
    docx = configured_project / "output" / f"resume-{wd_id}.docx"
    assert docx.exists()

    # Tracker has the row as SCORED (no handler → never reached APPLIED)
    from career_ai.models import ApplicationStatus
    from career_ai.storage.tracker import get_tracker
    app = get_tracker().get_by_job_id(wd_id)
    assert app is not None
    assert app.status == ApplicationStatus.SCORED


def test_applylink_invalid_url_exits(configured_project):
    import typer
    with pytest.raises(typer.Exit):
        from career_ai.pipeline.applylink import run_applylink
        run_applylink("not-a-url")


def test_applylink_idempotent_on_rerun(
    configured_project,
    fake_jd_response,
    fake_materials_response,
    fake_resume_response,
):
    """Second call with the same URL should skip JD fetch + materials generation."""
    responses = iter([fake_jd_response, fake_materials_response, fake_resume_response])

    with patch("career_ai.ai.client.CareerAIClient._call", side_effect=lambda _p: next(responses)) as mock_call, \
         patch("career_ai.pipeline.applylink._detect_handler", return_value=None):
        from career_ai.pipeline.applylink import run_applylink
        run_applylink(TEST_URL)

    first_call_count = mock_call.call_count
    assert first_call_count == 3  # JD + materials + résumé

    # Reset the session singleton so the second call re-enters cleanly
    from career_ai.session import reset_session
    reset_session()

    # Second run: JD fetch + materials should be skipped, only résumé regenerated
    with patch(
        "career_ai.ai.client.CareerAIClient._call",
        return_value=fake_resume_response,
    ) as mock_call2, \
         patch("career_ai.pipeline.applylink._detect_handler", return_value=None):
        from career_ai.pipeline.applylink import run_applylink
        run_applylink(TEST_URL)

    # Exactly one call (résumé regenerated; JD + materials skipped)
    assert mock_call2.call_count == 1


def test_applylink_fetch_failure_exits(configured_project):
    """If claude returns garbage twice, we exit without crashing."""
    with patch("career_ai.ai.client.CareerAIClient._call", return_value="not json at all"):
        import typer
        with pytest.raises(typer.Exit):
            from career_ai.pipeline.applylink import run_applylink
            run_applylink(TEST_URL)
