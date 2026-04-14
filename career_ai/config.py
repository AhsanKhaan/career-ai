"""Config loader — OpenClaw Rule 1.

profile.yml and portals.yml are loaded exactly once per process.
All subsequent calls return the cached Config object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


@dataclass
class Config:
    profile: dict
    portals: dict


_CONFIG: Config | None = None


def get_config(
    profile_path: str | None = None,
    portals_path: str | None = None,
) -> Config:
    """Return config singleton. Reads files only on first call."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = _load(profile_path, portals_path)
    return _CONFIG


def reset_config() -> None:
    """Reset singleton — used in tests only."""
    global _CONFIG
    _CONFIG = None


def _load(profile_path: str | None, portals_path: str | None) -> Config:
    p_path = Path(
        profile_path
        or os.environ.get("CAREER_AI_PROFILE", "config/profile.yml")
    )
    o_path = Path(
        portals_path
        or os.environ.get("CAREER_AI_PORTALS", "config/portals.yml")
    )

    if not p_path.exists():
        raise ConfigError(
            f"profile.yml not found at '{p_path}'.\n"
            "Run: cp config/profile.example.yml config/profile.yml"
        )
    if not o_path.exists():
        raise ConfigError(
            f"portals.yml not found at '{o_path}'.\n"
            "Run: cp config/portals.example.yml config/portals.yml"
        )

    with p_path.open(encoding="utf-8") as f:
        profile = yaml.safe_load(f) or {}

    with o_path.open(encoding="utf-8") as f:
        portals = yaml.safe_load(f) or {}

    _validate(profile, portals)
    return Config(profile=profile, portals=portals)


def _validate(profile: dict, portals: dict) -> None:
    errors = []

    candidate = profile.get("candidate", {})
    if not candidate.get("full_name"):
        errors.append("profile.yml: missing candidate.full_name")

    target_roles = profile.get("target_roles", {})
    if not target_roles.get("primary"):
        errors.append("profile.yml: missing target_roles.primary (list of role titles)")

    if not portals.get("tracked_companies"):
        errors.append("portals.yml: missing tracked_companies list")

    if errors:
        raise ConfigError("Configuration errors:\n" + "\n".join(f"  • {e}" for e in errors))
