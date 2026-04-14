"""Tests for config.py — singleton loader and validation."""

from __future__ import annotations

import pytest

from career_ai.config import ConfigError, get_config, reset_config


def test_loads_valid_config(profile_yml_file, portals_yml_file):
    cfg = get_config(str(profile_yml_file), str(portals_yml_file))
    assert cfg.profile["candidate"]["full_name"] == "Test User"
    assert cfg.portals["tracked_companies"][0]["name"] == "Acme Corp"


def test_singleton_returns_same_object(profile_yml_file, portals_yml_file):
    cfg1 = get_config(str(profile_yml_file), str(portals_yml_file))
    cfg2 = get_config()  # No args — should return cached
    assert cfg1 is cfg2


def test_missing_profile_raises(tmp_path, portals_yml_file):
    with pytest.raises(ConfigError, match="profile.yml not found"):
        get_config(str(tmp_path / "missing.yml"), str(portals_yml_file))


def test_missing_portals_raises(tmp_path, profile_yml_file):
    with pytest.raises(ConfigError, match="portals.yml not found"):
        get_config(str(profile_yml_file), str(tmp_path / "missing.yml"))


def test_missing_full_name_raises(tmp_path, portals_yml_file):
    import yaml
    p = tmp_path / "bad_profile.yml"
    p.write_text(yaml.dump({"candidate": {}, "target_roles": {"primary": ["Engineer"]}}))
    with pytest.raises(ConfigError, match="full_name"):
        get_config(str(p), str(portals_yml_file))


def test_missing_target_roles_raises(tmp_path, portals_yml_file):
    import yaml
    p = tmp_path / "bad_profile.yml"
    p.write_text(yaml.dump({"candidate": {"full_name": "Test"}, "target_roles": {}}))
    with pytest.raises(ConfigError, match="target_roles.primary"):
        get_config(str(p), str(portals_yml_file))


def test_reset_allows_reload(profile_yml_file, portals_yml_file):
    cfg1 = get_config(str(profile_yml_file), str(portals_yml_file))
    reset_config()
    cfg2 = get_config(str(profile_yml_file), str(portals_yml_file))
    assert cfg1 is not cfg2
