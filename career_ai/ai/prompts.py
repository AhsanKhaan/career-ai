"""Prompt loader — OpenClaw Rule 4.

Prompt templates live in prompts/*.md files, not hardcoded in Python.
They are loaded on-demand: scan stage reads zero prompt files.
Only score/apply commands load their respective template.

Profile content is NOT in these files — it comes from the
cached system block in ai/client.py.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path("prompts")


def load_prompt(name: str, **kwargs: str) -> str:
    """Load prompts/{name}.md and substitute {placeholders}.

    Args:
        name: prompt file name without extension (e.g. "score", "apply")
        **kwargs: placeholder substitutions

    Returns:
        Formatted prompt string ready for Claude API
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    template = path.read_text(encoding="utf-8")
    return template.format(**kwargs)
