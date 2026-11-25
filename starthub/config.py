"""Configuration loading, validation, ${ENV_VAR} expansion, and safe atomic JSON I/O."""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("starthub.config")

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "locales"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_CACHE_DIR = REPO_ROOT / "cache"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

DEFAULT_CONFIG: Dict[str, Any] = {
    "language": "en",
    "theme": {
        "mode": "multi_accent",
        "accent_color": "#58BCFF",
        "panel_alpha": 180,
        "blur": True,
        "corner_radius": 14,
    },
    "window": {
        "left_width": 416,
        "right_width": 430,
        "outer_width": 344,
        "gap": 10,
        "fallback_height": 774,
        "hide_delay_sec": 0.65,
        "center_overlay": True,
        "outer_columns": False,
        "start_menu_class": "DV2ControlHost",
    },
    "layout": {
        "left_widgets": [
            "phone_adb",
            "peripherals",
            "media_player",
            "system_monitor",
            "philips_hue",
        ],
        "right_widgets": [
            "ecoflow",
            "custom_json",
            "todoist",
            "weather_card",
            "calendar_card",
        ],
    },
    "widgets": {
        "system_monitor": {
            "enabled": True,
            "poll_interval_sec": 2.0,
        },
        "media_player": {
            "enabled": True,
            "poll_interval_sec": 2.0,
            "preferred_apps": ["spotify", "ytmusic", "tidal", "music"],
            "spotify_like": {
                "enabled": False,
                "client_id": "",
            },
        },
        "peripherals": {
            "enabled": True,
            "show_mouse": True,
            "show_keyboard": True,
            "show_gamepad": True,
            "show_handheld": False,
            "show_bluetooth": True,
            "dsx_udp_enabled": False,
            "dsx_udp_port": 6969,
            "handheld_name": "Handheld",
            "handheld_battery_file": "",
        },
        "weather": {
            "enabled": True,
            "city": "Kyiv",
            "latitude": 50.4501,
            "longitude": 30.5234,
            "timezone": "auto",
            "units": "metric",
            "refresh_minutes": 20,
            "show_card": True,
        },
        "calendar": {
            "enabled": True,
        },
        "philips_hue": {
            "enabled": False,
            "bridge_ip": "",
            "app_key": "",
            "poll_interval_sec": 8.0,
            "targets": [
                {"id": "1", "kind": "groups", "label": "Desk Light", "icon": "bulb", "dimmer": True},
                {"id": "2", "kind": "lights", "label": "Monitor Bar", "icon": "monitor", "dimmer": False},
            ],
        },
        "phone_adb": {
            "enabled": False,
            "device_name": "Android Phone",
            "adb_path": "adb",
            "scrcpy_path": "scrcpy",
            "device_serial": "",
            "wifi_address": "",
            "unlock_pin": "",
            "enable_sms_otp": False,
            "enable_photos": True,
            "auto_clip_sync": True,
            "frame_image_path": "",
            "image_editor_path": "",
        },
        "todoist": {
            "enabled": False,
            "api_token": "",
            "poll_interval_sec": 30.0,
            "projects": [],
        },
        "ecoflow": {
            "enabled": False,
            "mode": "mqtt",
            "email": "",
            "password": "",
            "device_sn": "",
            "device_name": "EcoFlow Station",
            "region": "europe",
            "state_file": "",
            "command_file": "",
            "image_path": "",
            "charge_watt_steps": [200, 400, 600, 800, 1000, 1500],
        },
        "custom_json": {
            "enabled": False,
            "allow_remote_urls": False,
            "cards": [],
        },
        "tile_switcher": {
            "enabled": False,
            "packs_dir": "packs",
        },
    },
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override onto a copy of base."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def expand_env_vars(value: Any, environ: Optional[Dict[str, str]] = None) -> Any:
    """Expand ${VAR_NAME} placeholders in strings; unset vars expand to empty string."""
    env = os.environ if environ is None else environ
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: env.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [expand_env_vars(item, env) for item in value]
    if isinstance(value, dict):
        return {k: expand_env_vars(v, env) for k, v in value.items()}
    return value


def write_json_atomic(path: Path | str, payload: Any, retries: int = 5, retry_delay: float = 0.03) -> bool:
    """Atomically write JSON with Windows sharing retries and guaranteed temp-file cleanup."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.stem}_",
            suffix=".tmp",
            delete=False,
        ) as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            temp_path = fh.name
        for attempt in range(max(1, retries)):
            try:
                os.replace(temp_path, str(target))
                temp_path = None
                return True
            except PermissionError:
                if attempt + 1 >= retries:
                    raise
                time.sleep(retry_delay)
    except Exception as exc:
        logger.debug("Atomic write failed for %s: %s", target, exc)
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    return False


def read_json_safe(path: Path | str, default: Any = None) -> Any:
    try:
        target = Path(path)
        if target.is_file():
            return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        pass
    return copy.deepcopy(default)


def _clamp_int(val: Any, lo: int, hi: int, fallback: int) -> int:
    try:
        return max(lo, min(hi, int(val)))
    except (TypeError, ValueError):
        return fallback


def _clamp_float(val: Any, lo: float, hi: float, fallback: float) -> float:
    try:
        num = float(val)
        return max(lo, min(hi, num))
    except (TypeError, ValueError):
        return fallback


def validate_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and clamp configuration values so invalid user edits never crash the UI."""
    lang = str(cfg.get("language", "en")).strip().lower()
    cfg["language"] = lang if lang in ("en", "ru", "uk") else "en"

    theme = cfg.setdefault("theme", {})
    mode = str(theme.get("mode", "multi_accent")).strip().lower()
    theme["mode"] = mode if mode in ("multi_accent", "single_accent") else "multi_accent"
    accent = str(theme.get("accent_color", "#58BCFF")).strip()
    if accent.lower() != "windows" and not re.fullmatch(r"#?[0-9a-fA-F]{6}", accent):
        accent = "#58BCFF"
    elif accent.lower() != "windows" and not accent.startswith("#"):
        accent = "#" + accent
    theme["accent_color"] = accent
    theme["panel_alpha"] = _clamp_int(theme.get("panel_alpha", 180), 80, 255, 180)
    theme["blur"] = bool(theme.get("blur", True))
    theme["corner_radius"] = _clamp_int(theme.get("corner_radius", 14), 0, 24, 14)

    win = cfg.setdefault("window", {})
    win["left_width"] = _clamp_int(win.get("left_width", 416), 340, 560, 416)
    win["right_width"] = _clamp_int(win.get("right_width", 430), 340, 560, 430)
    win["outer_width"] = _clamp_int(win.get("outer_width", 344), 280, 460, 344)
    win["gap"] = _clamp_int(win.get("gap", 10), 0, 48, 10)
    win["fallback_height"] = _clamp_int(win.get("fallback_height", 774), 500, 1440, 774)
    win["hide_delay_sec"] = _clamp_float(win.get("hide_delay_sec", 0.65), 0.1, 5.0, 0.65)
    win["center_overlay"] = bool(win.get("center_overlay", True))
    win["outer_columns"] = bool(win.get("outer_columns", False))
    win["start_menu_class"] = str(win.get("start_menu_class") or "DV2ControlHost")

    widgets = cfg.setdefault("widgets", {})
    weather = widgets.setdefault("weather", {})
    weather["latitude"] = _clamp_float(weather.get("latitude", 50.4501), -90.0, 90.0, 50.4501)
    weather["longitude"] = _clamp_float(weather.get("longitude", 30.5234), -180.0, 180.0, 30.5234)
    weather["refresh_minutes"] = _clamp_int(weather.get("refresh_minutes", 20), 5, 180, 20)
    units = str(weather.get("units", "metric")).strip().lower()
    weather["units"] = units if units in ("metric", "imperial") else "metric"

    return cfg


def build_demo_config(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Enable all showcase Tier 1 + Tier 2 widgets for --demo without touching user secrets."""
    cfg = copy.deepcopy(base if base is not None else DEFAULT_CONFIG)
    widgets = cfg["widgets"]
    widgets["system_monitor"]["enabled"] = True
    widgets["media_player"]["enabled"] = True
    widgets["media_player"]["spotify_like"]["enabled"] = True
    widgets["peripherals"]["enabled"] = True
    widgets["peripherals"]["show_mouse"] = True
    widgets["peripherals"]["show_keyboard"] = True
    widgets["peripherals"]["show_gamepad"] = True
    widgets["peripherals"]["show_handheld"] = True
    widgets["peripherals"]["show_bluetooth"] = True
    widgets["weather"]["enabled"] = True
    widgets["weather"]["show_card"] = False
    widgets["calendar"]["enabled"] = False
    widgets["philips_hue"]["enabled"] = True
    widgets["phone_adb"]["enabled"] = True
    widgets["phone_adb"]["device_name"] = "Pixel 9 Pro"
    widgets["phone_adb"]["enable_sms_otp"] = True
    widgets["phone_adb"]["enable_photos"] = True
    widgets["todoist"]["enabled"] = True
    widgets["ecoflow"]["enabled"] = True
    widgets["ecoflow"]["device_name"] = "DELTA 3 Max"
    widgets["custom_json"]["enabled"] = True
    widgets["custom_json"]["cards"] = [
        {"id": "ai_quotas", "title": "AI Quotas", "source": "", "refresh_sec": 30, "click_url": ""},
        {"id": "homelab", "title": "Home Lab", "source": "", "refresh_sec": 30, "click_url": ""},
    ]
    widgets["tile_switcher"]["enabled"] = True
    cfg["layout"]["left_widgets"] = [
        "phone_adb",
        "peripherals",
        "media_player",
        "system_monitor",
        "philips_hue",
    ]
    cfg["layout"]["right_widgets"] = [
        "ecoflow",
        "custom_json",
        "todoist",
    ]
    return validate_config(cfg)


def load_config(
    path: Optional[Path | str] = None,
    *,
    demo: bool = False,
    overrides: Optional[Dict[str, Any]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Load config.json (if present), merge defaults, expand ${ENV_VAR}, and validate."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    user_data: Dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                user_data = raw
        except Exception as exc:
            logger.warning("Could not parse %s (%s); using defaults", cfg_path, exc)

    merged = deep_merge(DEFAULT_CONFIG, user_data)
    if overrides:
        merged = deep_merge(merged, overrides)
    expanded = expand_env_vars(merged, environ=environ)
    validated = validate_config(expanded)
    if demo:
        return build_demo_config(validated)
    return validated


def is_widget_enabled(cfg: Dict[str, Any], widget_id: str) -> bool:
    """Return whether a given layout widget ID should be displayed."""
    widgets = cfg.get("widgets", {})
    if widget_id == "weather_card":
        w = widgets.get("weather", {})
        return bool(w.get("enabled", True) and w.get("show_card", True))
    if widget_id == "calendar_card":
        return bool(widgets.get("calendar", {}).get("enabled", True))
    if widget_id == "custom_json":
        c = widgets.get("custom_json", {})
        return bool(c.get("enabled", False) and c.get("cards"))
    return bool(widgets.get(widget_id, {}).get("enabled", False))
