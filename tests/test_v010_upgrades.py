"""Tests for new v0.1.0 upgrades: Audio, Storage/Net, LocalTasks, FocusTimer, Hotkeys, DPI adaptive layout, Custom JSON layouts, Doctor, and safe config patching."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image, ImageDraw

from starthub.config import is_widget_enabled, load_config, load_raw_user_config, save_config_patch
from starthub.doctor import format_diagnostics, run_diagnostics
from starthub.i18n import I18n
from starthub.layout import panel_layout, standalone_panel_layout
from starthub.providers.audio import shorten_audio_name
from starthub.providers.custom_json import normalize_custom_card
from starthub.providers.focus_timer import FocusTimerProvider
from starthub.providers.local_tasks import LocalTasksProvider
from starthub.providers.storage_network import StorageNetworkProvider, format_bytes_rate, format_gb
from starthub.providers.weather import geocode_city
from starthub.renderer import HubRenderer
from starthub.surface import FontBank, parse_hotkey_spec
from starthub.theme import Theme
from starthub.widgets import RenderContext
from starthub.widgets.custom_json import draw_custom_json_card


def test_parse_hotkey_spec_valid_and_invalid():
    assert parse_hotkey_spec("Alt+Space") == (0x4001, 0x20)
    assert parse_hotkey_spec("Ctrl+Shift+H") == (0x4006, ord("H"))
    assert parse_hotkey_spec("Win+F12") == (0x4008, 0x7B)
    assert parse_hotkey_spec("Space") is None  # requires at least one modifier
    assert parse_hotkey_spec("") is None


def test_adaptive_dpi_panel_layout_never_overlaps_start_menu():
    # Tight 1536x864 (1080p at 125% DPI) with centered 640px Start menu
    work = (0, 0, 1536, 824)
    start = (448, 80, 1088, 800)  # 448px free on each side
    lay = panel_layout(start, work, left_width=416, right_width=430, gap=10, adaptive_width=True, min_wing_width=300)
    assert "left" in lay and "right" in lay
    # Neither wing may overlap start [448..1088]
    assert lay["left"][0] + lay["left"][2] <= start[0]
    assert lay["right"][0] >= start[2]

    # Very tight laptop screen where only 350px exists on each side -> wings adaptively narrow instead of colliding
    work_tight = (0, 0, 1366, 728)
    start_tight = (363, 40, 1003, 700)  # 363px left, 363px right
    lay2 = panel_layout(start_tight, work_tight, left_width=416, right_width=430, gap=10, adaptive_width=True, min_wing_width=300)
    assert lay2["left"][2] < 416 and lay2["left"][2] >= 300
    assert lay2["left"][0] + lay2["left"][2] <= start_tight[0]
    assert lay2["right"][0] >= start_tight[2]

    # Left-aligned Windows 11 Start menu -> left wing skipped cleanly instead of covering Start
    start_left = (12, 60, 652, 760)
    lay3 = panel_layout(start_left, work, left_width=416, right_width=430, gap=10, adaptive_width=True, min_wing_width=300)
    assert "left" not in lay3
    assert "right" in lay3 and lay3["right"][0] >= start_left[2]


def test_standalone_hotkey_layout():
    lay = standalone_panel_layout((0, 0, 1920, 1040), left_width=416, right_width=430, wing_height=774)
    assert "left" in lay and "right" in lay
    assert lay["left"][0] >= 0
    assert lay["right"][0] + lay["right"][2] <= 1920


def test_save_config_patch_preserves_env_var_placeholders(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "theme": {"mode": "multi_accent"},
                "widgets": {"todoist": {"enabled": True, "api_token": "${TODOIST_API_TOKEN}"}},
            }
        ),
        encoding="utf-8",
    )
    assert save_config_patch(cfg_path, {"theme": {"mode": "single_accent"}}) is True
    raw = load_raw_user_config(cfg_path)
    assert raw["theme"]["mode"] == "single_accent"
    # Secret placeholder MUST stay intact, never overwritten!
    assert raw["widgets"]["todoist"]["api_token"] == "${TODOIST_API_TOKEN}"


def test_local_tasks_crud(tmp_path: Path):
    i18n = I18n("en")
    prov = LocalTasksProvider({}, tmp_path, i18n)
    snap0 = prov.snapshot()
    assert snap0["is_local"] is True
    initial_count = len(snap0["tasks"])
    assert initial_count >= 1

    assert prov.add_task("Ship StartHub v0.1.0") is True
    snap1 = prov.snapshot()
    assert snap1["tasks"][0]["content"] == "Ship StartHub v0.1.0"
    assert len(snap1["tasks"]) == initial_count + 1

    prov.complete_task(0)
    snap2 = prov.snapshot()
    assert len(snap2["tasks"]) == initial_count


def test_focus_timer_state_transitions():
    i18n = I18n("en")
    ft = FocusTimerProvider({"work_minutes": 25, "break_minutes": 5, "sound_on_done": False}, i18n)
    assert ft.snapshot()["display"] == "25:00"
    assert ft.snapshot()["phase"] == "work"
    ft.toggle()
    assert ft.snapshot()["running"] is True
    ft.switch_phase()
    assert ft.snapshot()["phase"] == "break"
    assert ft.snapshot()["display"] == "05:00"
    assert ft.snapshot()["running"] is False
    ft.reset()
    assert ft.snapshot()["display"] == "05:00"


def test_storage_network_formatting_and_poll():
    assert format_bytes_rate(512) == "512 B/s"
    assert format_bytes_rate(2048) == "2.0 KB/s"
    assert format_bytes_rate(5 * 1024 * 1024) == "5.0 MB/s"
    assert format_gb(512 * 1024**3) == "512 GB"
    assert format_gb(2 * 1024**4) == "2.0 TB"

    prov = StorageNetworkProvider({"enabled": True, "drives": ["auto"], "max_drives": 2})
    snap = prov.poll_once()
    assert isinstance(snap["drives"], list)
    assert len(snap["drives"]) >= 1


def test_audio_name_shortener():
    assert shorten_audio_name("Headphones (Sony WH-1000XM5 Stereo)") == "Headphones · Sony WH-1000XM5 Stereo"
    assert shorten_audio_name("Speakers (Realtek USB Audio)") == "Speakers · Realtek USB Audio"
    assert shorten_audio_name("") == "Audio"


def test_geocode_city_mocked():
    sess = MagicMock()
    resp = MagicMock()
    resp.json.return_value = {
        "results": [
            {"name": "London", "admin1": "England", "country": "United Kingdom", "latitude": 51.50853, "longitude": -0.12574, "timezone": "Europe/London"}
        ]
    }
    sess.get.return_value = resp
    matches = geocode_city("London", session=sess)
    assert len(matches) == 1
    assert matches[0]["name"] == "London"
    assert matches[0]["latitude"] == 51.5085
    assert matches[0]["timezone"] == "Europe/London"


def test_custom_json_all_three_layouts_render():
    i18n = I18n("en")
    theme = Theme()
    fonts = FontBank()
    for layout_name, payload in (
        ("columns", {"title": "Lab", "layout": "columns", "metrics": [{"label": "CPU", "value": "40%", "percent": 40}]}),
        ("hero", {"title": "BTC", "layout": "hero", "hero_value": "$94k", "hero_sub": "+3%", "metrics": [{"label": "ETH", "value": "$3.4k"}]}),
        ("list", {"title": "AI", "layout": "list", "items": [{"label": "qwen2.5", "value": "ACTIVE", "status": "ok"}]}),
    ):
        norm = normalize_custom_card({"id": layout_name, "title": layout_name}, payload)
        assert norm["layout"] == layout_name
        img = Image.new("RGBA", (800, 320), (0, 0, 0, 0))
        ctx = RenderContext(img, ImageDraw.Draw(img), 2, theme, fonts, i18n, None, [], {})
        draw_custom_json_card(ctx, (0, 0, 400, 150), norm, on_open_url=lambda _u: None)
        assert img.getbbox() is not None


def test_independent_tile_switcher_renders_without_tasks():
    cfg = load_config(
        overrides={
            "widgets": {
                "tasks": {"enabled": False},
                "todoist": {"enabled": False},
                "tile_switcher": {"enabled": True},
            }
        }
    )
    i18n = I18n("en")
    renderer = HubRenderer(cfg, Theme.from_config(cfg), i18n)
    specs = renderer.build_wing_specs("right", {})
    assert any(s.key == "tile_switcher" for s in specs)


def test_weather_show_card_auto_deduplication():
    cfg = load_config()
    assert is_widget_enabled(cfg, "weather_card", center_overlay_active=False) is True
    assert is_widget_enabled(cfg, "weather_card", center_overlay_active=True) is False


def test_doctor_diagnostics_is_sanitized(tmp_path: Path):
    rep = run_diagnostics(tmp_path / "nonexistent.json")
    txt = format_diagnostics(rep)
    assert "StartHub Diagnostics" in txt
    assert "Trigger mode" in txt
    assert "GPU backend" in txt
