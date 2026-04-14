"""Session state — OpenClaw Rule 5.

Tracks what has been processed in this process run to prevent re-work.
Each pipeline stage checks this before doing any computation.
"""

from __future__ import annotations


class SessionState:
    """In-memory state for a single career-ai process run."""

    def __init__(self) -> None:
        self._scored_ids: set[str] = set()
        self._applied_ids: set[str] = set()

    def mark_scored(self, job_id: str) -> None:
        self._scored_ids.add(job_id)

    def mark_applied(self, job_id: str) -> None:
        self._applied_ids.add(job_id)

    def is_scored(self, job_id: str) -> bool:
        return job_id in self._scored_ids

    def is_applied(self, job_id: str) -> bool:
        return job_id in self._applied_ids


_SESSION: SessionState | None = None


def get_session() -> SessionState:
    """Return the process-level session singleton."""
    global _SESSION
    if _SESSION is None:
        _SESSION = SessionState()
    return _SESSION


def reset_session() -> None:
    """Reset singleton — used in tests only."""
    global _SESSION
    _SESSION = None
