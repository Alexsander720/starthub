"""Tests for multi_accent vs single_accent theme engine and critical alert preservation."""
from __future__ import annotations

from starthub.config import load_config
from starthub.theme import Theme, parse_hex_color


def test_parse_hex_color():
    assert parse_hex_color("#58BCFF") == (88, 188, 255)
    assert parse_hex_color("ff0080") == (255, 0, 128)
    assert parse_hex_color("invalid", default=(1, 2, 3)) == (1, 2, 3)


def test_multi_accent_has_distinct_category_colors():
    cfg = load_config(overrides={"theme": {"mode": "multi_accent"}})
    theme = Theme.from_config(cfg)
    assert not theme.is_single_accent
    assert theme.role("media") != theme.role("hue")
    assert theme.role("todoist") != theme.role("bluetooth")
    assert theme.role("ecoflow_in") != theme.role("ecoflow_out")


def test_single_accent_unifies_roles_around_accent():
    cfg = load_config(overrides={"theme": {"mode": "single_accent", "accent_color": "#7C5CFF"}})
    theme = Theme.from_config(cfg)
    assert theme.is_single_accent
    assert theme.accent == (124, 92, 255)
    # Primary category roles collapse to the chosen single accent
    assert theme.role("media") == theme.accent
    assert theme.role("hue") == theme.accent
    assert theme.role("todoist") == theme.accent
    assert theme.role("ecoflow_soc") == theme.accent
    assert theme.role("mouse") == theme.accent


def test_single_accent_always_preserves_critical_alerts():
    cfg = load_config(overrides={"theme": {"mode": "single_accent", "accent_color": "#58BCFF"}})
    theme = Theme.from_config(cfg)
    assert theme.monitor_bar_color(40) == theme.accent
    assert theme.monitor_bar_color(75) == theme.alert_warn
    assert theme.monitor_bar_color(95) == theme.alert_danger
    assert theme.status_color("danger") == theme.alert_danger
    assert theme.status_color("blackout") == theme.alert_danger
    assert theme.status_color("warn") == theme.alert_warn
    assert theme.status_color("ok") == theme.accent
