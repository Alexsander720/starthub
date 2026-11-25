"""Tests for starthub.config: loading, ${ENV_VAR} expansion, validation, demo preset, atomic JSON."""
from __future__ import annotations

import json
from pathlib import Path

from starthub.config import (
    DEFAULT_CONFIG,
    expand_env_vars,
    is_widget_enabled,
    load_config,
    write_json_atomic,
)


def test_load_defaults_when_file_missing(tmp_path: Path):
    cfg = load_config(tmp_path / "nonexistent.json")
    assert cfg["language"] == "en"
    assert cfg["theme"]["mode"] == "multi_accent"
    assert cfg["widgets"]["system_monitor"]["enabled"] is True
    assert cfg["widgets"]["media_player"]["enabled"] is True
    assert cfg["widgets"]["peripherals"]["enabled"] is True
    assert cfg["widgets"]["weather"]["enabled"] is True
    # Tier 2 opt-in modules must default to disabled
    assert cfg["widgets"]["philips_hue"]["enabled"] is False
    assert cfg["widgets"]["phone_adb"]["enabled"] is False
    assert cfg["widgets"]["todoist"]["enabled"] is False
    assert cfg["widgets"]["ecoflow"]["enabled"] is False
    assert cfg["widgets"]["custom_json"]["enabled"] is False
    assert cfg["widgets"]["tile_switcher"]["enabled"] is False


def test_env_var_expansion_and_missing_vars(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "widgets": {
                    "todoist": {"enabled": True, "api_token": "${TEST_TODOIST_TOK}"},
                    "philips_hue": {"enabled": True, "app_key": "${UNSET_VAR_XYZ}"},
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_file, environ={"TEST_TODOIST_TOK": "dummy-token-value"})
    assert cfg["widgets"]["todoist"]["api_token"] == "dummy-token-value"
    assert cfg["widgets"]["philips_hue"]["app_key"] == ""


def test_validation_clamps_invalid_values(tmp_path: Path):
    cfg_file = tmp_path / "bad.json"
    cfg_file.write_text(
        json.dumps(
            {
                "language": "xx",
                "theme": {"mode": "rainbow", "accent_color": "not-a-color", "panel_alpha": 999, "corner_radius": -5},
                "window": {"left_width": 50, "right_width": 9000, "hide_delay_sec": 99},
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_file)
    assert cfg["language"] == "en"
    assert cfg["theme"]["mode"] == "multi_accent"
    assert cfg["theme"]["accent_color"] == "#58BCFF"
    assert cfg["theme"]["panel_alpha"] == 255
    assert cfg["theme"]["corner_radius"] == 0
    assert cfg["window"]["left_width"] == 300
    assert cfg["window"]["right_width"] == 560
    assert cfg["window"]["hide_delay_sec"] == 5.0


def test_windows_accent_keyword_preserved():
    cfg = load_config(overrides={"theme": {"accent_color": "windows", "mode": "single_accent"}})
    assert cfg["theme"]["accent_color"] == "windows"
    assert cfg["theme"]["mode"] == "single_accent"


def test_demo_config_enables_all_showcase_widgets():
    cfg = load_config(demo=True)
    for wid in ("phone_adb", "peripherals", "media_player", "system_monitor", "philips_hue", "ecoflow", "custom_json", "todoist"):
        assert is_widget_enabled(cfg, wid) is True


def test_write_json_atomic_leaves_no_temp_files(tmp_path: Path):
    target = tmp_path / "state.json"
    for i in range(5):
        assert write_json_atomic(target, {"step": i, "ok": True}) is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"step": 4, "ok": True}
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "state.json"]
    assert leftovers == []


def test_expand_env_vars_nested():
    raw = {"a": ["${X}", {"b": "prefix-${Y}"}], "c": 42}
    res = expand_env_vars(raw, environ={"X": "1", "Y": "2"})
    assert res == {"a": ["1", {"b": "prefix-2"}], "c": 42}
    assert DEFAULT_CONFIG["language"] == "en"
