"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from career_ai.config import reset_config
from career_ai.models import ApplicationStatus, Job
from career_ai.session import reset_session
from career_ai.storage.tracker import reset_tracker


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all module-level singletons before each test."""
    reset_config()
    reset_session()
    reset_tracker()
    from career_ai.ai.client import reset_claude_client
    reset_claude_client()
    yield


@pytest.fixture
def mock_profile() -> dict:
    return {
        "candidate": {
            "full_name": "Test User",
            "email": "test@example.com",
            "phone": "+1-555-0000",
            "location": "Remote",
        },
        "target_roles": {
            "primary": ["Senior Frontend Engineer", "Full Stack Engineer"],
        },
        "narrative": {
            "headline": "Senior Engineer with 5+ years",
            "superpowers": ["React", "TypeScript"],
        },
        "compensation": {"target_range": "$120k-$150k"},
    }


@pytest.fixture
def mock_portals() -> dict:
    return {
        "title_filter": {
            "positive": ["Frontend", "React", "Full Stack"],
            "negative": ["Junior", "Intern"],
        },
        "tracked_companies": [
            {
                "name": "Acme Corp",
                "careers_url": "https://job-boards.greenhouse.io/acme",
                "api": "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
                "enabled": True,
            },
            {
                "name": "Widgets Inc",
                "careers_url": "https://jobs.lever.co/widgets",
                "enabled": True,
            },
        ],
    }


@pytest.fixture
def sample_jobs() -> list[Job]:
    from career_ai.models import make_job_id
    return [
        Job(
            job_id=make_job_id(f"https://example.com/jobs/{i}"),
            company=f"Company {i}",
            title="Senior Frontend Engineer",
            location="Remote",
            url=f"https://example.com/jobs/{i}",
            description="We are looking for a React engineer...",
            requirements=["React", "TypeScript", "5+ years"],
            source="greenhouse",
            scanned_at="2026-04-14T10:00:00Z",
        )
        for i in range(5)
    ]


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """A temporary cache directory — patches CACHE_DIR in storage.cache."""
    import career_ai.storage.cache as cache_mod
    original = cache_mod.CACHE_DIR
    cache_mod.CACHE_DIR = tmp_path / "cache"
    (tmp_path / "cache").mkdir()
    yield tmp_path / "cache"
    cache_mod.CACHE_DIR = original


@pytest.fixture
def tmp_db(tmp_path: Path):
    """A temporary SQLite database."""
    from career_ai.storage.tracker import ApplicationTracker
    db = tmp_path / "test.db"
    return ApplicationTracker(db_path=db)


@pytest.fixture
def profile_yml_file(tmp_path: Path, mock_profile: dict) -> Path:
    import yaml
    p = tmp_path / "profile.yml"
    p.write_text(yaml.dump(mock_profile), encoding="utf-8")
    return p


@pytest.fixture
def portals_yml_file(tmp_path: Path, mock_portals: dict) -> Path:
    import yaml
    p = tmp_path / "portals.yml"
    p.write_text(yaml.dump(mock_portals), encoding="utf-8")
    return p
