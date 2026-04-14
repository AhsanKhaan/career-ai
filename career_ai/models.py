"""Central data models for career-ai.

All pipeline stages pass Job and Application objects.
job_id is deterministic: sha256(url)[:12] — stable across re-scans.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    SCORED = "scored"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    DISCARDED = "discarded"


@dataclass
class Job:
    job_id: str
    company: str
    title: str
    location: str
    url: str
    description: str
    requirements: list[str]
    source: str           # "greenhouse" | "lever" | "ashby" | "wellfound"
    scanned_at: str       # ISO 8601
    score: int = 0        # 0-100, set by score stage; -1 = scoring error
    decision: str = ""    # "apply" | "strong" | "skip" | ""
    reasoning: str = ""
    ats_summary: str = ""
    cover_letter: str = ""
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "url": self.url,
            "description": self.description,
            "requirements": self.requirements,
            "source": self.source,
            "scanned_at": self.scanned_at,
            "score": self.score,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "ats_summary": self.ats_summary,
            "cover_letter": self.cover_letter,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Job":
        return cls(
            job_id=d["job_id"],
            company=d["company"],
            title=d.get("title", ""),
            location=d.get("location", ""),
            url=d.get("url", ""),
            description=d.get("description", ""),
            requirements=d.get("requirements", []),
            source=d.get("source", ""),
            scanned_at=d.get("scanned_at", ""),
            score=d.get("score", 0),
            decision=d.get("decision", ""),
            reasoning=d.get("reasoning", ""),
            ats_summary=d.get("ats_summary", ""),
            cover_letter=d.get("cover_letter", ""),
            keywords=d.get("keywords", []),
        )


@dataclass
class Application:
    job_id: str
    company: str
    title: str
    status: ApplicationStatus
    score: int = 0
    applied_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "company": self.company,
            "title": self.title,
            "status": self.status.value,
            "score": self.score,
            "applied_at": self.applied_at,
            "notes": self.notes,
        }


def make_job_id(url: str) -> str:
    """Deterministic job ID from URL. Same URL always produces same ID."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]
