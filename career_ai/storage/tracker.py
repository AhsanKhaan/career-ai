"""Application tracker backed by SQLite.

Uses Python's stdlib sqlite3 — zero extra dependencies.
Schema is created on first use.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from career_ai.models import Application, ApplicationStatus

DB_PATH = Path("data/career-ai.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    job_id      TEXT PRIMARY KEY,
    company     TEXT NOT NULL,
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    score       INTEGER DEFAULT 0,
    applied_at  TEXT,
    notes       TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class ApplicationTracker:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def upsert_application(self, app: Application) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO applications
                    (job_id, company, title, status, score, applied_at, notes, created_at, updated_at)
                VALUES
                    (:job_id, :company, :title, :status, :score, :applied_at, :notes, :now, :now)
                ON CONFLICT(job_id) DO UPDATE SET
                    status     = excluded.status,
                    score      = excluded.score,
                    applied_at = COALESCE(excluded.applied_at, applications.applied_at),
                    notes      = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                {
                    "job_id": app.job_id,
                    "company": app.company,
                    "title": app.title,
                    "status": app.status.value,
                    "score": app.score,
                    "applied_at": app.applied_at,
                    "notes": app.notes,
                    "now": now,
                },
            )

    def update_status(self, job_id: str, status: ApplicationStatus, notes: str = "") -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE applications SET status=?, notes=?, updated_at=? WHERE job_id=?",
                (status.value, notes, now, job_id),
            )
            return cursor.rowcount > 0

    def get_all_applications(self) -> list[Application]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM applications ORDER BY updated_at DESC"
            ).fetchall()
        return [_row_to_app(r) for r in rows]

    def get_by_status(self, status: ApplicationStatus) -> list[Application]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM applications WHERE status=? ORDER BY updated_at DESC",
                (status.value,),
            ).fetchall()
        return [_row_to_app(r) for r in rows]

    def get_by_job_id(self, job_id: str) -> Optional[Application]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM applications WHERE job_id=?", (job_id,)
            ).fetchone()
        return _row_to_app(row) if row else None


def _row_to_app(row: sqlite3.Row) -> Application:
    return Application(
        job_id=row["job_id"],
        company=row["company"],
        title=row["title"],
        status=ApplicationStatus(row["status"]),
        score=row["score"],
        applied_at=row["applied_at"],
        notes=row["notes"] or "",
    )


_TRACKER: ApplicationTracker | None = None


def get_tracker(db_path: Path = DB_PATH) -> ApplicationTracker:
    """Return process-level tracker singleton."""
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = ApplicationTracker(db_path)
    return _TRACKER


def reset_tracker() -> None:
    """Reset singleton — used in tests only."""
    global _TRACKER
    _TRACKER = None
