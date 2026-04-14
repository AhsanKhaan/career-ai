"""Claude CLI client — no API key required.

Uses `claude -p --dangerously-skip-permissions` (same pattern as career-ops batch runner).
Requires the `claude` CLI to be installed and logged in (Claude Max / Pro subscription).

Install Claude Code CLI: https://claude.ai/download
Then log in: claude login

OpenClaw rules maintained:
- Profile YAML written once to batch/.profile-context.md (singleton)
- Passed via --append-system-prompt-file on every call
- CLAUDE.md loaded automatically (cwd = project root)
- Incremental: score/apply stages skip already-processed jobs
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from career_ai.ai.prompts import load_prompt
from career_ai.models import Job

_CLIENT: "CareerAIClient | None" = None
_BATCH_SIZE = 20  # Jobs per scoring call
_CTX_FILE = Path("batch/.profile-context.md")
_TIMEOUT = 180  # seconds per claude -p call


class CareerAIClient:
    def __init__(self, profile_yaml: str) -> None:
        self._profile_yaml = profile_yaml
        # Write profile context file once per session (OpenClaw: profile read once)
        _CTX_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CTX_FILE.write_text(
            "You are an expert career advisor.\n"
            "The following is the candidate's complete profile. "
            "Use it for all scoring and application generation.\n\n"
            f"CANDIDATE PROFILE:\n\n{profile_yaml}",
            encoding="utf-8",
        )

    def _call(self, user_prompt: str) -> str:
        """Invoke claude CLI in non-interactive mode.

        Equivalent to career-ops:
          claude -p --dangerously-skip-permissions --append-system-prompt-file profile.md "prompt"
        """
        result = subprocess.run(
            [
                "claude", "-p",
                "--dangerously-skip-permissions",
                "--append-system-prompt-file", str(_CTX_FILE),
                user_prompt,
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=str(Path.cwd()),  # Project root → CLAUDE.md loaded as context
        )
        if result.returncode != 0:
            stderr = result.stderr[:300] if result.stderr else "(no stderr)"
            raise RuntimeError(
                f"claude CLI exited with code {result.returncode}.\n"
                f"Is 'claude' installed and logged in? Run: claude login\n"
                f"stderr: {stderr}"
            )
        return result.stdout.strip()

    def score_batch(self, jobs: list[Job]) -> list[dict]:
        """Score up to BATCH_SIZE jobs in a single claude -p call.

        Returns list of {job_id, score, decision, reasoning}.
        On parse failure marks all jobs as score=-1.
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

        raw = self._call(prompt)
        results = _parse_json_array(raw)

        if results is None:
            raw = self._call(prompt + "\n\nReturn ONLY the JSON array, no other text.")
            results = _parse_json_array(raw)

        if results is None:
            return [
                {"job_id": j.job_id, "score": -1, "decision": "error", "reasoning": "parse failure"}
                for j in jobs
            ]
        return results

    def generate_application(self, job: Job) -> dict:
        """Generate ATS summary, cover letter, and keywords for one job.

        Returns {ats_summary, cover_letter, keywords}.
        """
        prompt = load_prompt(
            "apply",
            job_title=job.title,
            job_company=job.company,
            job_location=job.location,
            job_url=job.url,
            job_description=job.description[:4000],
        )

        raw = self._call(prompt)
        result = _parse_json_object(raw)

        if result is None:
            raw = self._call(prompt + "\n\nReturn ONLY valid JSON, nothing else.")
            result = _parse_json_object(raw)

        if result is None:
            return {"ats_summary": "", "cover_letter": "", "keywords": []}

        violations = _check_apply_constraints(result)
        if violations:
            correction = (
                f"\n\nPrevious output violated constraints: {'; '.join(violations)}. "
                "Regenerate strictly within limits."
            )
            raw = self._call(prompt + correction)
            result = _parse_json_object(raw) or result

        return {
            "ats_summary": result.get("ats_summary", ""),
            "cover_letter": result.get("cover_letter", ""),
            "keywords": result.get("keywords", [])[:5],
        }


def get_claude_client() -> CareerAIClient:
    """Return process-level singleton.

    Profile YAML is read from config once and written to the context file.
    All subsequent calls reuse the same client and context file.
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
    if _CTX_FILE.exists():
        _CTX_FILE.unlink(missing_ok=True)


def _parse_json_array(text: str) -> list[dict] | None:
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
    violations = []
    summary = result.get("ats_summary", "")
    cover = result.get("cover_letter", "")
    keywords = result.get("keywords", [])
    if len(summary.split()) > 80:
        violations.append(f"ats_summary exceeds 80 words ({len(summary.split())})")
    if len(cover.split()) > 120:
        violations.append(f"cover_letter exceeds 120 words ({len(cover.split())})")
    if not isinstance(keywords, list) or len(keywords) != 5:
        violations.append(f"keywords must be exactly 5 items (got {len(keywords)})")
    return violations
