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

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from career_ai.ai.prompts import load_prompt
from career_ai.models import Job

_CLIENT: "CareerAIClient | None" = None
_BATCH_SIZE = 20  # Jobs per scoring call
_CTX_FILE = Path("batch/profile-context.md")
_TIMEOUT = 180  # seconds per claude -p call
_CLAUDE_EXE: str | None = None  # resolved once, cached


def _find_claude() -> str:
    """Locate the claude CLI executable.

    Search order:
    1. shutil.which("claude") — finds it if it's on PATH
    2. Windows UWP package install location (Claude Desktop app)
    3. Common manual install locations (~/.local/bin, /usr/local/bin)

    Raises RuntimeError with install instructions if not found.
    """
    global _CLAUDE_EXE
    if _CLAUDE_EXE is not None:
        return _CLAUDE_EXE

    # 1. Windows: Claude Desktop (UWP) installs to a versioned package path.
    #    Check this first — ~/.local/bin may contain an unrelated API-key-based
    #    CLI that returns "Invalid API key" and causes confusing failures.
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            pattern = os.path.join(
                local_app_data,
                "Packages", "Claude_*",
                "LocalCache", "Roaming", "Claude", "claude-code",
                "*", "claude.exe",
            )
            matches = sorted(glob.glob(pattern), reverse=True)  # newest version first
            if matches:
                _CLAUDE_EXE = matches[0]
                return _CLAUDE_EXE

    # 2. Standard PATH lookup (Unix, or Windows if UWP not found)
    found = shutil.which("claude")
    if found:
        _CLAUDE_EXE = found
        return _CLAUDE_EXE

    # 3. Common Unix locations not always on PATH
    for candidate in [
        Path.home() / ".local" / "bin" / "claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]:
        if candidate.is_file():
            _CLAUDE_EXE = str(candidate)
            return _CLAUDE_EXE

    raise RuntimeError(
        "claude CLI not found. Install it from https://claude.ai/download\n"
        "Then log in: claude login\n"
        "If already installed, ensure its directory is on your PATH."
    )


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

        The prompt is piped via stdin to avoid Windows command-line length limits and
        shell encoding issues with large, multi-line prompts containing special characters.
        """
        claude_exe = _find_claude()

        # Pass the prompt via stdin (claude -p reads from stdin when no positional arg given).
        # This avoids Windows 32KB command-line arg limit and CP1252 quoting issues.
        # PYTHONUTF8=1 ensures the subprocess decodes/encodes everything as UTF-8.
        env = {**os.environ, "PYTHONUTF8": "1"}
        result = subprocess.run(
            [
                claude_exe, "-p",
                "--dangerously-skip-permissions",
                "--append-system-prompt-file", str(_CTX_FILE),
            ],
            input=user_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_TIMEOUT,
            cwd=str(Path.cwd()),  # Project root → CLAUDE.md loaded as context
            env=env,
        )
        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "(no stderr)"
            stdout = result.stdout[:200] if result.stdout else "(no stdout)"
            raise RuntimeError(
                f"claude CLI exited with code {result.returncode}.\n"
                f"exe: {claude_exe}\n"
                f"ctx_file: {str(_CTX_FILE)} (exists: {_CTX_FILE.exists()})\n"
                f"cwd: {str(Path.cwd())}\n"
                f"stderr: {stderr}\n"
                f"stdout: {stdout}"
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
