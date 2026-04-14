"""Tests for scoring pipeline stage and AI client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from career_ai.ai.client import (
    CareerAIClient,
    _check_apply_constraints,
    _parse_json_array,
    _parse_json_object,
    _BATCH_SIZE,
)
from career_ai.models import Job, make_job_id


@pytest.fixture
def client(tmp_path, monkeypatch) -> CareerAIClient:
    # Point _CTX_FILE to tmp dir so we don't write to project root during tests
    monkeypatch.chdir(tmp_path)
    return CareerAIClient(profile_yaml="name: Test User\nroles: [Frontend]")


def test_parse_json_array_valid():
    text = '[{"job_id": "abc", "score": 80, "decision": "apply", "reasoning": "good"}]'
    result = _parse_json_array(text)
    assert result is not None
    assert result[0]["score"] == 80


def test_parse_json_array_with_preamble():
    text = 'Here are the scores:\n[{"job_id": "abc", "score": 70, "decision": "apply", "reasoning": "ok"}]'
    result = _parse_json_array(text)
    assert result is not None
    assert len(result) == 1


def test_parse_json_array_invalid_returns_none():
    assert _parse_json_array("not json at all") is None
    assert _parse_json_array("") is None


def test_parse_json_object_valid():
    text = '{"ats_summary": "Great fit", "cover_letter": "Dear...", "keywords": ["React"]}'
    result = _parse_json_object(text)
    assert result is not None
    assert result["ats_summary"] == "Great fit"


def test_check_apply_constraints_valid():
    result = {
        "ats_summary": "Short summary.",
        "cover_letter": "Short cover letter.",
        "keywords": ["React", "TypeScript", "Node.js", "AWS", "Next.js"],
    }
    violations = _check_apply_constraints(result)
    assert violations == []


def test_check_apply_constraints_ats_too_long():
    long_summary = " ".join(["word"] * 85)
    result = {
        "ats_summary": long_summary,
        "cover_letter": "Short.",
        "keywords": ["a", "b", "c", "d", "e"],
    }
    violations = _check_apply_constraints(result)
    assert any("ats_summary" in v for v in violations)


def test_check_apply_constraints_cover_too_long():
    long_cover = " ".join(["word"] * 125)
    result = {
        "ats_summary": "Short.",
        "cover_letter": long_cover,
        "keywords": ["a", "b", "c", "d", "e"],
    }
    violations = _check_apply_constraints(result)
    assert any("cover_letter" in v for v in violations)


def test_check_apply_constraints_wrong_keyword_count():
    result = {
        "ats_summary": "Short.",
        "cover_letter": "Short.",
        "keywords": ["React", "TypeScript"],  # Only 2, need 5
    }
    violations = _check_apply_constraints(result)
    assert any("keywords" in v for v in violations)


def test_score_batch_calls_api_once_for_20_jobs(client):
    jobs = [
        Job(
            job_id=make_job_id(f"https://example.com/{i}"),
            company="Acme",
            title="Frontend Engineer",
            location="Remote",
            url=f"https://example.com/{i}",
            description="React role",
            requirements=[],
            source="greenhouse",
            scanned_at="2026-04-14",
        )
        for i in range(20)
    ]

    mock_response = json.dumps([
        {"job_id": j.job_id, "score": 75, "decision": "apply", "reasoning": "good"} for j in jobs
    ])

    with patch("career_ai.ai.client.load_prompt", return_value="score prompt"):
        with patch.object(client, "_call", return_value=mock_response) as mock_call:
            results = client.score_batch(jobs)
            # Should be called exactly once for 20 jobs
            assert mock_call.call_count == 1
            assert len(results) == 20


def test_score_batch_retries_on_parse_failure(client):
    jobs = [
        Job(
            job_id=make_job_id("https://example.com/1"),
            company="Acme",
            title="Frontend",
            location="Remote",
            url="https://example.com/1",
            description="React",
            requirements=[],
            source="greenhouse",
            scanned_at="2026-04-14",
        )
    ]

    valid_response = json.dumps([
        {"job_id": jobs[0].job_id, "score": 80, "decision": "apply", "reasoning": "ok"}
    ])

    call_count = 0
    def mock_call(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "invalid json garbage"
        return valid_response

    with patch("career_ai.ai.client.load_prompt", return_value="score prompt"):
        with patch.object(client, "_call", side_effect=mock_call):
            results = client.score_batch(jobs)
            assert call_count == 2  # First call failed, second succeeded
            assert results[0]["score"] == 80


def test_score_batch_marks_error_after_two_failures(client):
    jobs = [
        Job(
            job_id=make_job_id("https://example.com/1"),
            company="Acme",
            title="Frontend",
            location="Remote",
            url="https://example.com/1",
            description="React",
            requirements=[],
            source="greenhouse",
            scanned_at="2026-04-14",
        )
    ]

    with patch("career_ai.ai.client.load_prompt", return_value="score prompt"):
        with patch.object(client, "_call", return_value="not json"):
            results = client.score_batch(jobs)
            assert results[0]["score"] == -1
            assert results[0]["decision"] == "error"
