"""Tests for storage layer — cache.py and tracker.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_ai.models import Application, ApplicationStatus, make_job_id
from career_ai.storage.cache import (
    append_jobs,
    find_job,
    get_all_seen_ids,
    load_unscored_jobs,
    update_job_in_cache,
)
from career_ai.storage.tracker import ApplicationTracker


# -- cache.py tests --

def test_get_all_seen_ids_empty(tmp_cache_dir):
    assert get_all_seen_ids() == set()


def test_append_and_seen_ids(tmp_cache_dir, sample_jobs):
    written = append_jobs(sample_jobs)
    assert written == len(sample_jobs)
    seen = get_all_seen_ids()
    assert seen == {j.job_id for j in sample_jobs}


def test_append_deduplicates(tmp_cache_dir, sample_jobs):
    append_jobs(sample_jobs)
    written_again = append_jobs(sample_jobs)
    assert written_again == 0  # All already seen


def test_load_unscored_filters_correctly(tmp_cache_dir, sample_jobs):
    append_jobs(sample_jobs)
    # Manually score first two
    for job in sample_jobs[:2]:
        update_job_in_cache(job.job_id, {"score": 75, "decision": "apply"})

    unscored = load_unscored_jobs()
    assert len(unscored) == 3
    assert all(j.score == 0 for j in unscored)


def test_find_job_returns_correct_job(tmp_cache_dir, sample_jobs):
    append_jobs(sample_jobs)
    target = sample_jobs[2]
    found = find_job(target.job_id)
    assert found is not None
    assert found.job_id == target.job_id
    assert found.company == target.company


def test_find_job_returns_none_for_unknown(tmp_cache_dir):
    result = find_job("nonexistent123")
    assert result is None


def test_update_job_in_cache(tmp_cache_dir, sample_jobs):
    append_jobs(sample_jobs)
    job = sample_jobs[0]
    result = update_job_in_cache(job.job_id, {"score": 85, "decision": "strong"})
    assert result is True
    updated = find_job(job.job_id)
    assert updated.score == 85
    assert updated.decision == "strong"


def test_update_job_returns_false_when_not_found(tmp_cache_dir):
    result = update_job_in_cache("notfound0000", {"score": 50})
    assert result is False


def test_same_day_appends_merge(tmp_cache_dir, sample_jobs):
    first_batch = sample_jobs[:3]
    second_batch = sample_jobs[2:]  # jobs[2] is duplicate

    append_jobs(first_batch)
    written = append_jobs(second_batch)
    # Only jobs[3] and jobs[4] are new (jobs[2] is duplicate)
    assert written == 2

    all_ids = get_all_seen_ids()
    assert len(all_ids) == 5


# -- tracker.py tests --

def test_tracker_creates_schema(tmp_db):
    apps = tmp_db.get_all_applications()
    assert apps == []


def test_tracker_upsert_insert(tmp_db, sample_jobs):
    job = sample_jobs[0]
    app = Application(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        status=ApplicationStatus.APPLIED,
        score=75,
    )
    tmp_db.upsert_application(app)
    results = tmp_db.get_all_applications()
    assert len(results) == 1
    assert results[0].job_id == job.job_id
    assert results[0].status == ApplicationStatus.APPLIED


def test_tracker_upsert_updates_existing(tmp_db, sample_jobs):
    job = sample_jobs[0]
    app = Application(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        status=ApplicationStatus.APPLIED,
        score=75,
    )
    tmp_db.upsert_application(app)
    # Update status
    app.status = ApplicationStatus.INTERVIEW
    tmp_db.upsert_application(app)

    results = tmp_db.get_all_applications()
    assert len(results) == 1  # No duplicate
    assert results[0].status == ApplicationStatus.INTERVIEW


def test_tracker_update_status(tmp_db, sample_jobs):
    job = sample_jobs[0]
    app = Application(
        job_id=job.job_id,
        company=job.company,
        title=job.title,
        status=ApplicationStatus.APPLIED,
    )
    tmp_db.upsert_application(app)
    ok = tmp_db.update_status(job.job_id, ApplicationStatus.OFFER, "Great offer!")
    assert ok is True
    updated = tmp_db.get_by_job_id(job.job_id)
    assert updated.status == ApplicationStatus.OFFER
    assert updated.notes == "Great offer!"


def test_tracker_update_status_returns_false_for_unknown(tmp_db):
    ok = tmp_db.update_status("notexist0000", ApplicationStatus.REJECTED)
    assert ok is False


def test_tracker_get_by_status(tmp_db, sample_jobs):
    for i, job in enumerate(sample_jobs):
        status = ApplicationStatus.APPLIED if i < 3 else ApplicationStatus.REJECTED
        tmp_db.upsert_application(Application(
            job_id=job.job_id, company=job.company, title=job.title, status=status
        ))

    applied = tmp_db.get_by_status(ApplicationStatus.APPLIED)
    rejected = tmp_db.get_by_status(ApplicationStatus.REJECTED)
    assert len(applied) == 3
    assert len(rejected) == 2
