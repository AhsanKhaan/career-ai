"""Job scan cache — append-only JSON files in data/cache/.

One file per scan date: data/cache/YYYY-MM-DD.json
Each file contains scan metadata + list of Job objects.

OpenClaw rules enforced here:
- get_all_seen_ids() builds a set of known IDs without loading full job objects
- load_unscored_jobs() skips jobs that already have a score
- update_job_in_cache() mutates in-place — no re-scraping needed
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from career_ai.models import Job

CACHE_DIR = Path("data/cache")


def _ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_all_seen_ids() -> set[str]:
    """Fast dedup check: read only job_id fields, not full job objects."""
    seen: set[str] = set()
    if not CACHE_DIR.exists():
        return seen
    for f in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for j in data.get("jobs", []):
                if "job_id" in j:
                    seen.add(j["job_id"])
        except (json.JSONDecodeError, OSError):
            continue
    return seen


def load_all_jobs() -> list[Job]:
    """Load all jobs ever cached, across all dated files."""
    jobs: list[Job] = []
    if not CACHE_DIR.exists():
        return jobs
    for f in sorted(CACHE_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for j in data.get("jobs", []):
                jobs.append(Job.from_dict(j))
        except (json.JSONDecodeError, OSError):
            continue
    return jobs


def load_unscored_jobs() -> list[Job]:
    """Return jobs that haven't been scored yet (score == 0)."""
    return [j for j in load_all_jobs() if j.score == 0]


def find_job(job_id: str) -> Job | None:
    """Find a single job by ID across all cache files."""
    if not CACHE_DIR.exists():
        return None
    for f in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            for j in data.get("jobs", []):
                if j.get("job_id") == job_id:
                    return Job.from_dict(j)
        except (json.JSONDecodeError, OSError):
            continue
    return None


def append_jobs(new_jobs: list[Job], source_count: int = 0) -> int:
    """Write new jobs to today's cache file. Returns count of jobs written.

    If today's file already exists, loads it first and deduplicates before
    appending — safe to call multiple times per day.
    """
    _ensure_cache_dir()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"{today}.json"

    existing_ids: set[str] = set()
    existing_jobs: list[dict] = []
    existing_meta: dict = {}

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            existing_jobs = data.get("jobs", [])
            existing_ids = {j["job_id"] for j in existing_jobs if "job_id" in j}
            existing_meta = {k: v for k, v in data.items() if k != "jobs"}
        except (json.JSONDecodeError, OSError):
            pass

    truly_new = [j for j in new_jobs if j.job_id not in existing_ids]
    if not truly_new:
        return 0

    all_jobs = existing_jobs + [j.to_dict() for j in truly_new]
    payload = {
        **existing_meta,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "source_count": source_count,
        "total_jobs": len(all_jobs),
        "new_this_run": len(truly_new),
        "jobs": all_jobs,
    }
    cache_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(truly_new)


def update_job_in_cache(job_id: str, updates: dict) -> bool:
    """Find a job by ID in any cache file and update its fields in-place.

    Returns True if the job was found and updated, False if not found.
    """
    if not CACHE_DIR.exists():
        return False
    for f in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            modified = False
            for job in data.get("jobs", []):
                if job.get("job_id") == job_id:
                    job.update(updates)
                    modified = True
            if modified:
                f.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False
