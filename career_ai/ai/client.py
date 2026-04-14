"""Claude API client — OpenClaw Rules 3 & 4.

OpenClaw Rule 3: Profile YAML is embedded in the system block with
cache_control: ephemeral — tokenized exactly once per session.
All subsequent score/apply calls hit the Anthropic prompt cache
at ~10% of the input token cost.

OpenClaw Rule 4: Prompts are loaded from prompts/*.md on-demand.

This module never imports from pipeline/ — it is a pure utility.
"""

from __future__ import annotations

import json
import re

import anthropic

from career_ai.ai.prompts import load_prompt
from career_ai.models import Job

_MODEL = "claude-opus-4-5"
_CLIENT: "CareerAIClient | None" = None

_BATCH_SIZE = 20  # Jobs per Claude scoring call


class CareerAIClient:
    def __init__(self, profile_yaml: str) -> None:
        self._client = anthropic.Anthropic()
        # OpenClaw: profile embedded ONCE as a cached system block.
        # cache_control: ephemeral → Anthropic caches these tokens for up to 5 min.
        # A session scoring 100 jobs (5 calls) tokenizes the profile exactly once.
        self._system: list[dict] = [
            {
                "type": "text",
                "text": (
                    "You are an expert career advisor. "
                    "The following is the candidate's profile — use it for all evaluations.\n\n"
                    f"CANDIDATE PROFILE:\n{profile_yaml}"
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _call(self, user_prompt: str, max_tokens: int) -> str:
        msg = self._client.messages.create(
            model=_MODEL,
            max_tokens=max_tokens,
            system=self._system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return msg.content[0].text

    def score_batch(self, jobs: list[Job]) -> list[dict]:
        """Score up to BATCH_SIZE jobs in a single API call.

        Returns a list of {job_id, score, decision, reasoning} dicts.
        On parse failure, jobs in the batch are marked score=-1.
        """
        job_summaries = [
            {
                "job_id": j.job_id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "description_excerpt": j.description[:500],
            }
            for j in jobs
        ]
        prompt = load_prompt("score", jobs_json=json.dumps(job_summaries, ensure_ascii=False))

        raw = self._call(prompt, max_tokens=4096)
        results = _parse_json_array(raw)

        if results is None:
            # One retry with explicit instruction
            raw = self._call(prompt + "\n\nReturn ONLY the JSON array.", max_tokens=4096)
            results = _parse_json_array(raw)

        if results is None:
            # Mark all jobs in batch as error
            return [{"job_id": j.job_id, "score": -1, "decision": "error", "reasoning": ""} for j in jobs]

        return results

    def generate_application(self, job: Job) -> dict:
        """Generate ATS summary, cover letter, and keywords for one job.

        Returns {ats_summary, cover_letter, keywords}.
        Validates word counts after generation; retries once if violated.
        """
        prompt = load_prompt(
            "apply",
            job_title=job.title,
            job_company=job.company,
            job_location=job.location,
            job_url=job.url,
            job_description=job.description[:4000],
        )

        raw = self._call(prompt, max_tokens=1024)
        result = _parse_json_object(raw)

        if result is None:
            raw = self._call(prompt + "\n\nReturn ONLY valid JSON.", max_tokens=1024)
            result = _parse_json_object(raw)

        if result is None:
            return {"ats_summary": "", "cover_letter": "", "keywords": []}

        # Validate constraints; retry once if violated
        violations = _check_apply_constraints(result)
        if violations:
            correction = (
                f"\n\nPrevious output violated these constraints: {'; '.join(violations)}. "
                "Regenerate strictly within limits."
            )
            raw = self._call(prompt + correction, max_tokens=1024)
            result = _parse_json_object(raw) or result

        return {
            "ats_summary": result.get("ats_summary", ""),
            "cover_letter": result.get("cover_letter", ""),
            "keywords": result.get("keywords", [])[:5],
        }


def get_claude_client() -> CareerAIClient:
    """Return process-level singleton, initialized with profile on first call.

    OpenClaw: profile YAML read once, passed to client constructor once.
    All subsequent calls reuse the same client (and its cached system block).
    """
    global _CLIENT
    if _CLIENT is None:
        import yaml
        from career_ai.config import get_config

        cfg = get_config()
        profile_yaml = yaml.dump(cfg.profile, allow_unicode=True, default_flow_style=False)
        _CLIENT = CareerAIClient(profile_yaml)
    return _CLIENT


def reset_claude_client() -> None:
    """Reset singleton — used in tests only."""
    global _CLIENT
    _CLIENT = None


def _parse_json_array(text: str) -> list[dict] | None:
    """Extract and parse the first JSON array from a Claude response."""
    text = text.strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        result = json.loads(match.group())
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return None


def _parse_json_object(text: str) -> dict | None:
    """Extract and parse the first JSON object from a Claude response."""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        result = json.loads(match.group())
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return None


def _check_apply_constraints(result: dict) -> list[str]:
    """Return list of constraint violations for apply output."""
    violations = []
    summary = result.get("ats_summary", "")
    cover = result.get("cover_letter", "")
    keywords = result.get("keywords", [])

    if len(summary.split()) > 80:
        violations.append(f"ats_summary exceeds 80 words ({len(summary.split())} words)")
    if len(cover.split()) > 120:
        violations.append(f"cover_letter exceeds 120 words ({len(cover.split())} words)")
    if not isinstance(keywords, list) or len(keywords) != 5:
        violations.append(f"keywords must be a list of exactly 5 items (got {len(keywords)})")

    return violations
