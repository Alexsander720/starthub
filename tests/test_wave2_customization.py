"""Tests for Wave 2 features: 6 theme presets, custom colors/roles, Zero-Overlap Start11 guard, migrations & updater."""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from PIL import Image, ImageDraw

from starthub.config import (
    CONFIG_SCHEMA_VERSION,
    export_profile_data,
    load_config,
    migrate_config,
    save_config_patch,
)
from starthub.i18n import I18n
from starthub.layout import calibrated_tile_grid, center_layouts
from starthub.surface import FontBank
from starthub.theme import THEME_PRESETS, Theme
from starthub.updater import check_for_updates, is_newer_version, parse_semver
from starthub.widgets import RenderContext
from starthub.widgets.peripherals import draw_bt_drawer
from starthub.widgets.weather_clock import draw_weather_card


# --------------------------------------------------------------------------- #
# 1. Theme Presets, Custom Surface Colors & Role Overrides
# --------------------------------------------------------------------------- #

def test_all_six_theme_presets_load_distinctly():
    expected = {"fluent_dark", "fluent_light", "amoled_black", "catppuccin_mocha", "nord", "tokyo_night"}
    assert set(THEME_PRESETS.keys()) == expected
    seen_bg = set()
    for name in expected:
        cfg = load_config(overrides={"theme": {"preset": name}})
        theme = Theme.from_config(cfg)
        assert theme.preset == name
        assert theme.is_light == (name == "fluent_light")
        seen_bg.add(theme.panel_rgb)
    assert len(seen_bg) == 6


def test_custom_surface_colors_and_auto_light_detection():
    cfg = load_config(
        overrides={
            "theme": {
                "preset": "fluent_dark",
                "custom_colors": {
                    "panel_bg": "#F4F6FA",
                    "tile_bg": "#E6EBF3",
                    "border": "#CBD5E1",
                    "text_primary": "#111827",
                    "text_secondary": "#475569",
                },
                "role_overrides": {
                    "audio": "#FF3366",
                    "focus_work": "#00AA88",
                },
            }
        }
    )
    theme = Theme.from_config(cfg)
    assert theme.is_light is True
    assert theme.panel_rgb == (244, 246, 250)
    assert theme.tile_bg == (230, 235, 243, 255)
    assert theme.text_primary == (17, 24, 39, 255)
    assert theme.role("audio") == (255, 51, 102)
    assert theme.role("focus_work") == (0, 170, 136)
    # Critical alert colors remain readable and preserved even with custom overrides
    assert theme.monitor_bar_color(95) == theme.alert_danger
    assert theme.monitor_bar_color(75) == theme.alert_warn


def test_fluent_light_renders_bt_popup_and_weather_card_cleanly():
    cfg = load_config(overrides={"theme": {"preset": "fluent_light"}})
    theme = Theme.from_config(cfg)
    assert theme.is_light is True
    img = Image.new("RGBA", (832, 800), (*theme.panel_rgb, 255))
    ctx = RenderContext(
        img=img,
        draw=ImageDraw.Draw(img),
        scale=2,
        theme=theme,
        fonts=FontBank(),
        i18n=I18n("en"),
        hover=None,
        hotspots=[],
        img_cache={},
    )
    draw_bt_drawer(
        ctx,
        (12, 12, 404, 320),
        {
            "bt_on": True,
            "bt_devices": [
                {"name": "Sony WH-1000XM5", "connected": True, "battery": 85},
                {"name": "Keychron Q1 Pro", "connected": False, "battery": None},
            ],
        },
        on_toggle_radio=lambda: None,
        on_close=lambda: None,
        on_open_settings=lambda: None,
    )
    draw_weather_card(
        ctx,
        (12, 340, 404, 580),
        {
            "city": "Kyiv",
            "units": "metric",
            "current": {"temperature_2m": 18, "apparent_temperature": 17, "weather_code": 2, "wind_speed_10m": 3.4},
            "daily": {
                "time": ["2026-11-26", "2026-11-27"],
                "temperature_2m_min": [12, 10],
                "temperature_2m_max": [21, 18],
                "weather_code": [1, 61],
            },
        },
        now=datetime.datetime(2026, 11, 26, 10, 0),
    )
    assert img.size == (832, 800)


# --------------------------------------------------------------------------- #
# 2. Config Migrations & Zero-Secret Profile Export
# --------------------------------------------------------------------------- #

def test_migrate_config_v1_to_v2_and_preserves_env_vars(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    v1_raw = {
        "language": "en",
        "theme": {"mode": "multi_accent", "accent_color": "#58BCFF"},
        "layout": {
            "left_widgets": ["audio_control", "media_player"],
            "right_widgets": ["ecoflow", "todoist"],
        },
        "widgets": {
            "todoist": {"enabled": True, "api_token": "${TODOIST_API_TOKEN}"},
            "ecoflow": {"enabled": False, "password": "${ECOFLOW_PASSWORD}"},
        },
    }
    cfg_file.write_text(json.dumps(v1_raw), encoding="utf-8")

    migrated = migrate_config(v1_raw)
    assert migrated["config_version"] == CONFIG_SCHEMA_VERSION
    assert "tasks" in migrated["layout"]["right_widgets"]
    assert "todoist" not in migrated["layout"]["right_widgets"]
    assert migrated["widgets"]["todoist"]["api_token"] == "${TODOIST_API_TOKEN}"

    assert save_config_patch(cfg_file, {"theme": {"preset": "catppuccin_mocha"}})
    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved["config_version"] == CONFIG_SCHEMA_VERSION
    assert saved["theme"]["preset"] == "catppuccin_mocha"
    assert saved["widgets"]["todoist"]["api_token"] == "${TODOIST_API_TOKEN}"
    assert saved["widgets"]["ecoflow"]["password"] == "${ECOFLOW_PASSWORD}"


def test_export_profile_data_never_leaks_secrets():
    cfg = load_config(
        overrides={
            "theme": {"preset": "tokyo_night", "role_overrides": {"audio": "#FFAA00"}},
            "widgets": {
                "philips_hue": {"enabled": True, "bridge_ip": "192.0.2.50", "app_key": "SUPER_SECRET_HUE_KEY"},
                "todoist": {"enabled": True, "api_token": "SUPER_SECRET_TODOIST_TOKEN"},
                "ecoflow": {"enabled": True, "email": "private@example.com", "password": "MY_PASSWORD_123", "device_sn": "SN999999"},
                "phone_adb": {"enabled": True, "unlock_pin": "9876", "device_serial": "SERIAL_XYZ"},
            },
        }
    )
    prof = export_profile_data(cfg)
    serialized = json.dumps(prof)
    assert prof["starthub_profile"] is True
    assert prof["theme"]["preset"] == "tokyo_night"
    assert "layout" in prof and "window" in prof
    for secret in ("SUPER_SECRET_HUE_KEY", "SUPER_SECRET_TODOIST_TOKEN", "MY_PASSWORD_123", "private@example.com", "192.0.2.50", "9876", "SN999999"):
        assert secret not in serialized


# --------------------------------------------------------------------------- #
# 3. Update Checker (Semver + Mocked API + Cache)
# --------------------------------------------------------------------------- #

def test_semver_comparison():
    assert parse_semver("v0.2.0") == (0, 2, 0)
    assert parse_semver("1.4") == (1, 4, 0)
    assert is_newer_version("v0.2.0", "0.1.0") is True
    assert is_newer_version("0.1.0", "0.1.0") is False
    assert is_newer_version("0.0.9", "0.1.0") is False


def test_update_checker_mocked_and_cached(tmp_path: Path):
    class _FakeResp:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._payload

    class _FakeSession:
        def __init__(self, resp):
            self.resp = resp
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return self.resp

    sess = _FakeSession(_FakeResp(200, {"tag_name": "v0.3.0", "html_url": "https://github.com/Alexsander720/starthub/releases/tag/v0.3.0"}))
    r1 = check_for_updates(cache_dir=tmp_path, force=True, session=sess)
    assert r1["checked"] is True
    assert r1["update_available"] is True
    assert r1["latest_version"] == "0.3.0"
    assert r1["from_cache"] is False
    assert sess.calls == 1

    # Second non-forced call hits 24h cache without hitting network
    r2 = check_for_updates(cache_dir=tmp_path, force=False, session=sess)
    assert r2["from_cache"] is True
    assert r2["update_available"] is True
    assert sess.calls == 1

    # 404 (no published releases yet) returns clean up-to-date result without error
    sess_404 = _FakeSession(_FakeResp(404, {}))
    r3 = check_for_updates(cache_dir=tmp_path, force=True, session=sess_404)
    assert r3["checked"] is True
    assert r3["update_available"] is False
    assert r3["error"] == ""


# --------------------------------------------------------------------------- #
# 4. Zero-Overlap Start11 Guard & Resilient Groups Registry Parsing
# --------------------------------------------------------------------------- #

def _make_start11_fixture(extra_group_fields: str = ""):
    unit = 52.0
    gap = unit / 13.0
    stride = 6 * unit + 3 * gap
    width = round(2 * stride - 4 * gap)
    header = 47 * unit / 52.0
    client_w = round(width + 23 * unit / 52.0)
    client_h = 680

    registry = {
        "Start8": {"MenuMode": "2", "TileMode": "0", "RightIconMode": "0", "Win10WidthC": "2"},
        "Groups": {
            "0": f"G0|Pinned|0|0|0|0|0|1|0|0||0||9999|0|0||-1|{extra_group_fields}",
            "1": f"G1|Tools|0|0|0|0|1|2|0|0||0||9999|0|0||-1|{extra_group_fields}",
        },
        "GroupContents\\G0": {
            "0": "app1|-1|1|0|0|-1||1|1|0|-1",
            "1": "app2|-1|1|2|0|-1||2|1|0|-1",
        },
        "GroupContents\\G1": {
            "0": "app3|-1|1|0|0|-1||1|1|0|-1",
        },
    }
    native = {
        "visible": True,
        "scroll": (0, 0),
        "rect": (920, 460, 920 + client_w, 460 + client_h),
        "client": (client_w, client_h),
        "items": [
            (round(0 * unit), round(header), round(2 * unit - gap), round(header + 2 * unit - gap)),
            (round(2 * unit), round(header), round(4 * unit - gap), round(header + 2 * unit - gap)),
        ],
    }
    start_rect = (900, 400, 920 + client_w + 20, 460 + client_h + 20)
    return registry, native, start_rect


def test_calibrated_tile_grid_resilient_to_future_start11_fields():
    # Extra trailing fields appended by a future Start11 update still parse cleanly
    reg, native, start_rect = _make_start11_fixture(extra_group_fields="|new_v3_flag|42|extra")
    grid = calibrated_tile_grid(reg, native)
    assert grid is not None
    assert len(grid["groups"]) == 2
    assert len(grid["native_items"]) == 2
    overlays = center_layouts(start_rect, (0, 0, 2560, 1400), grid, safety_margin=14)
    assert "center_weather" in overlays and "center_clock" in overlays


def test_zero_overlap_guard_pushes_or_yields_when_native_tile_reaches_bottom():
    reg, native, start_rect = _make_start11_fixture()
    grid = calibrated_tile_grid(reg, native)
    assert grid is not None
    # Simulate an untracked/expanded tile occupying the lower part of column 0
    grid["native_items"].append((0, 460, 280, 620))
    overlays = center_layouts(start_rect, (0, 0, 2560, 1400), grid, safety_margin=14)
    # Column 0 ("center_weather") MUST yield (no room >= CENTER_MIN_H below y=620)
    assert "center_weather" not in overlays
    # Column 1 ("center_clock") has plenty of empty space and remains unaffected
    assert "center_clock" in overlays


def test_zero_overlap_guard_respects_occluders():
    reg, native, start_rect = _make_start11_fixture()
    grid = calibrated_tile_grid(reg, native)
    assert grid is not None
    # Simulate a visible tile-folder popup or search overlay covering column 1
    nl, nt, nr, nb = grid["native_rect"]
    g1 = grid["groups"][1]
    popup_rect = (nl + g1["left"], nt + 120, nl + g1["left"] + g1["width"], nb - 20)
    overlays = center_layouts(start_rect, (0, 0, 2560, 1400), grid, safety_margin=14, occluders=[popup_rect])
    assert "center_weather" in overlays
    assert "center_clock" not in overlays
