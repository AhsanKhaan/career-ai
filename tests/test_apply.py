"""Tests for apply pipeline stage."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from career_ai.models import Job, make_job_id
from career_ai.storage.cache import append_jobs


@pytest.fixture
def sample_job() -> Job:
    return Job(
        job_id=make_job_id("https://example.com/jobs/frontend-001"),
        company="Acme Corp",
        title="Senior Frontend Engineer",
        location="Remote",
        url="https://example.com/jobs/frontend-001",
        description="We need a React engineer with 5+ years experience in TypeScript and Next.js.",
        requirements=["React", "TypeScript", "Next.js"],
        source="greenhouse",
        scanned_at="2026-04-14T10:00:00Z",
        score=80,
        decision="apply",
    )


@pytest.fixture
def mock_apply_response(sample_job) -> str:
    return json.dumps({
        "ats_summary": "Senior Frontend Engineer with 5+ years building React applications at scale.",
        "cover_letter": "Dear Hiring Team,\n\nI am excited about this role. My experience with React and TypeScript aligns perfectly with your requirements. I have built production systems serving 100K+ users.\n\nLooking forward to discussing further.",
        "keywords": ["React", "TypeScript", "Next.js", "Frontend", "JavaScript"],
    })


def test_apply_generates_materials(tmp_cache_dir, sample_job, mock_apply_response, profile_yml_file, portals_yml_file):
    from career_ai.config import get_config
    get_config(str(profile_yml_file), str(portals_yml_file))

    append_jobs([sample_job])

    with patch("career_ai.ai.client.CareerAIClient._call", return_value=mock_apply_response):
        with patch("career_ai.ai.client.anthropic.Anthropic"):
            from career_ai.pipeline.apply import run_apply
            run_apply(sample_job.job_id)

    from career_ai.storage.cache import find_job
    updated = find_job(sample_job.job_id)
    assert updated is not None
    assert updated.ats_summary != ""
    assert len(updated.keywords) == 5


def test_apply_skips_if_already_has_summary(tmp_cache_dir, sample_job, capsys):
    sample_job.ats_summary = "Already generated."
    append_jobs([sample_job])

    with patch("career_ai.ai.client.CareerAIClient._call") as mock_call:
        with patch("career_ai.ai.client.anthropic.Anthropic"):
            from career_ai.pipeline.apply import run_apply
            run_apply(sample_job.job_id)
            # Should not call Claude if materials already exist
            mock_call.assert_not_called()


def test_apply_exits_if_job_not_found(tmp_cache_dir):
    import typer
    with pytest.raises(typer.Exit):
        from career_ai.pipeline.apply import run_apply
        run_apply("nonexistent0000")


def test_apply_records_in_tracker(tmp_cache_dir, sample_job, mock_apply_response, profile_yml_file, portals_yml_file):
    from career_ai.config import get_config
    get_config(str(profile_yml_file), str(portals_yml_file))

    append_jobs([sample_job])

    with patch("career_ai.ai.client.CareerAIClient._call", return_value=mock_apply_response):
        with patch("career_ai.ai.client.anthropic.Anthropic"):
            from career_ai.pipeline.apply import run_apply
            run_apply(sample_job.job_id)

    from career_ai.storage.tracker import get_tracker
    from career_ai.models import ApplicationStatus
    tracker = get_tracker()
    app = tracker.get_by_job_id(sample_job.job_id)
    assert app is not None
    assert app.status == ApplicationStatus.APPLIED
