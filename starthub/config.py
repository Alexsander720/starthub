"""Configuration loading, validation, presets, ${ENV_VAR} expansion, and safe atomic JSON I/O."""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("starthub.config")

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = REPO_ROOT / "locales"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_CACHE_DIR = REPO_ROOT / "cache"

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
CONFIG_SCHEMA_VERSION = 2

ALL_WIDGET_IDS: Tuple[str, ...] = (
    "phone_adb",
    "peripherals",
    "audio_control",
    "media_player",
    "system_monitor",
    "storage_network",
    "philips_hue",
    "ecoflow",
    "custom_json",
    "tasks",
    "focus_timer",
    "weather_card",
    "calendar_card",
    "quick_actions",
    "tile_switcher",
)

# Ready-to-use layout presets selectable in GUI Settings
LAYOUT_PRESETS: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "left_widgets": [
            "phone_adb",
            "peripherals",
            "audio_control",
            "media_player",
            "system_monitor",
            "storage_network",
            "focus_timer",
            "quick_actions",
            "philips_hue",
        ],
        "right_widgets": [
            "ecoflow",
            "custom_json",
            "weather_card",
            "tasks",
            "calendar_card",
            "tile_switcher",
        ],
        "enabled": {
            "peripherals": True,
            "audio_control": True,
            "media_player": True,
            "system_monitor": True,
            "storage_network": True,
            "weather": True,
            "tasks": True,
            "focus_timer": True,
            "calendar": True,
            "quick_actions": True,
        },
    },
    "minimal": {
        "left_widgets": ["audio_control", "media_player", "system_monitor"],
        "right_widgets": ["weather_card", "tasks", "calendar_card"],
        "enabled": {
            "peripherals": False,
            "audio_control": True,
            "media_player": True,
            "system_monitor": True,
            "storage_network": False,
            "weather": True,
            "tasks": True,
            "focus_timer": False,
            "calendar": True,
            "quick_actions": False,
        },
    },
    "productivity": {
        "left_widgets": ["audio_control", "media_player", "peripherals", "system_monitor"],
        "right_widgets": ["tasks", "focus_timer", "calendar_card", "quick_actions", "weather_card"],
        "enabled": {
            "peripherals": True,
            "audio_control": True,
            "media_player": True,
            "system_monitor": True,
            "storage_network": False,
            "weather": True,
            "tasks": True,
            "focus_timer": True,
            "calendar": True,
            "quick_actions": True,
        },
    },
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "config_version": CONFIG_SCHEMA_VERSION,
    "language": "en",
    "updates": {
        "check_enabled": True,
    },
    "theme": {
        "preset": "fluent_dark",
        "mode": "multi_accent",
        "accent_color": "#58BCFF",
        "panel_alpha": 180,
        "blur": True,
        "corner_radius": 14,
        "custom_colors": {
            "panel_bg": "",
            "tile_bg": "",
            "border": "",
            "text_primary": "",
            "text_secondary": "",
        },
        "role_overrides": {},
    },
    "window": {
        "trigger_mode": "auto",  # "auto" (Start11 -> Win11 Start) | "start11" | "windows11" | "hotkey"
        "hotkey_enabled": True,
        "hotkey": "Alt+Space",
        "left_width": 416,
        "right_width": 430,
        "min_wing_width": 300,
        "adaptive_width": True,
        "outer_width": 344,
        "gap": 10,
        "fallback_height": 774,
        "hide_delay_sec": 0.65,
        "idle_poll_ms": 40,
        "fade_animation": True,
        "fade_duration_ms": 120,
        "center_overlay": True,
        "center_overlay_safety_margin": 14,
        "outer_columns": False,
        "start_menu_class": "DV2ControlHost",
    },
    "layout": {
        "left_widgets": [
            "phone_adb",
            "peripherals",
            "audio_control",
            "media_player",
            "system_monitor",
            "storage_network",
            "focus_timer",
            "quick_actions",
            "philips_hue",
        ],
        "right_widgets": [
            "ecoflow",
            "custom_json",
            "weather_card",
            "tasks",
            "calendar_card",
            "tile_switcher",
        ],
    },
    "widgets": {
        "system_monitor": {
            "enabled": True,
            "poll_interval_sec": 2.0,
        },
        "storage_network": {
            "enabled": True,
            "poll_interval_sec": 2.0,
            "drives": ["auto"],
            "max_drives": 3,
        },
        "audio_control": {
            "enabled": True,
            "poll_interval_sec": 1.5,
        },
        "media_player": {
            "enabled": True,
            "poll_interval_sec": 1.5,
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
            "show_bt_batteries": True,
            "auto_hide_offline": False,
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
            "auto_geocode": True,
            "timezone": "auto",
            "units": "metric",
            "refresh_minutes": 20,
            "show_card": "auto",  # True | False | "auto" (hides wing card when Start11 center overlay is active)
        },
        "tasks": {
            "enabled": True,
            "mode": "auto",  # "auto" (Todoist when enabled+token else local) | "local" | "todoist"
            "title": "",
        },
        "focus_timer": {
            "enabled": True,
            "work_minutes": 25,
            "break_minutes": 5,
            "sound_on_done": True,
        },
        "calendar": {
            "enabled": True,
        },
        "quick_actions": {
            "enabled": True,
            "items": [
                {"id": "snip", "label": "Snip", "icon": "camera", "action": "snip"},
                {"id": "terminal", "label": "Terminal", "icon": "terminal", "action": "terminal"},
                {"id": "lock", "label": "Lock", "icon": "lock", "action": "lock"},
                {"id": "settings", "label": "Settings", "icon": "gear", "action": "starthub_settings"},
            ],
        },
        "philips_hue": {
            "enabled": False,
            "backend": "hue",  # "hue" | "home_assistant" | "wled"
            "bridge_ip": "",
            "app_key": "",
            "ha_url": "",
            "ha_token": "",
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


def load_raw_user_config(path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Read raw config.json WITHOUT expanding ${ENV_VAR} placeholders (safe for GUI editing)."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw = read_json_safe(cfg_path, {})
    return raw if isinstance(raw, dict) else {}


def migrate_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Non-destructively migrate older StartHub config.json files to the latest schema version."""
    data = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    ver = int(data.get("config_version", 1) or 1)
    if ver < 2:
        # Migrate legacy "todoist" widget ID inside layout arrays -> unified "tasks"
        lay = data.get("layout")
        if isinstance(lay, dict):
            for key in ("left_widgets", "right_widgets"):
                if isinstance(lay.get(key), list):
                    lay[key] = ["tasks" if w == "todoist" else w for w in lay[key]]
        # Ensure new theme customization sub-dicts exist cleanly
        theme = data.setdefault("theme", {})
        if isinstance(theme, dict):
            theme.setdefault("preset", "fluent_dark")
            theme.setdefault("custom_colors", {})
            theme.setdefault("role_overrides", {})
        data["config_version"] = CONFIG_SCHEMA_VERSION
    return data


def export_profile_data(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Export a shareable theme + widget layout profile (strictly zero API keys, IPs, or personal paths)."""
    return {
        "starthub_profile": True,
        "config_version": CONFIG_SCHEMA_VERSION,
        "theme": copy.deepcopy(cfg.get("theme", {})),
        "window": {
            k: cfg.get("window", {}).get(k)
            for k in (
                "trigger_mode",
                "left_width",
                "right_width",
                "gap",
                "adaptive_width",
                "fade_animation",
                "center_overlay",
                "center_overlay_safety_margin",
            )
            if k in cfg.get("window", {})
        },
        "layout": copy.deepcopy(cfg.get("layout", {})),
    }


def save_config_patch(path: Optional[Path | str], patch: Dict[str, Any]) -> bool:
    """Merge a partial update into raw config.json without clobbering ${ENV_VAR} placeholders."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    existing = load_raw_user_config(cfg_path)
    if not existing:
        example = REPO_ROOT / "config.example.json"
        if example.is_file():
            existing = read_json_safe(example, {})
        if not isinstance(existing, dict) or not existing:
            existing = copy.deepcopy(DEFAULT_CONFIG)
    existing = migrate_config(existing)
    merged = deep_merge(existing, patch)
    merged["config_version"] = CONFIG_SCHEMA_VERSION
    return write_json_atomic(cfg_path, merged)


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
    valid_presets = ("fluent_dark", "fluent_light", "amoled_black", "catppuccin_mocha", "nord", "tokyo_night")
    preset = str(theme.get("preset", "fluent_dark")).strip().lower()
    theme["preset"] = preset if preset in valid_presets else "fluent_dark"
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
    if not isinstance(theme.get("custom_colors"), dict):
        theme["custom_colors"] = {}
    if not isinstance(theme.get("role_overrides"), dict):
        theme["role_overrides"] = {}

    win = cfg.setdefault("window", {})
    tmode = str(win.get("trigger_mode", "auto")).strip().lower()
    win["trigger_mode"] = tmode if tmode in ("auto", "start11", "windows11", "hotkey") else "auto"
    win["hotkey_enabled"] = bool(win.get("hotkey_enabled", True))
    win["hotkey"] = str(win.get("hotkey") or "Alt+Space").strip()
    win["left_width"] = _clamp_int(win.get("left_width", 416), 300, 560, 416)
    win["right_width"] = _clamp_int(win.get("right_width", 430), 300, 560, 430)
    win["min_wing_width"] = _clamp_int(win.get("min_wing_width", 300), 260, 420, 300)
    win["adaptive_width"] = bool(win.get("adaptive_width", True))
    win["outer_width"] = _clamp_int(win.get("outer_width", 344), 280, 460, 344)
    win["gap"] = _clamp_int(win.get("gap", 10), 0, 48, 10)
    win["fallback_height"] = _clamp_int(win.get("fallback_height", 774), 500, 1440, 774)
    win["hide_delay_sec"] = _clamp_float(win.get("hide_delay_sec", 0.65), 0.1, 5.0, 0.65)
    win["idle_poll_ms"] = _clamp_int(win.get("idle_poll_ms", 40), 16, 250, 40)
    win["fade_animation"] = bool(win.get("fade_animation", True))
    win["fade_duration_ms"] = _clamp_int(win.get("fade_duration_ms", 120), 40, 400, 120)
    win["center_overlay"] = bool(win.get("center_overlay", True))
    win["center_overlay_safety_margin"] = _clamp_int(win.get("center_overlay_safety_margin", 14), 0, 48, 14)
    win["outer_columns"] = bool(win.get("outer_columns", False))
    win["start_menu_class"] = str(win.get("start_menu_class") or "DV2ControlHost")

    widgets = cfg.setdefault("widgets", {})
    weather = widgets.setdefault("weather", {})
    lat = weather.get("latitude", 50.4501)
    lon = weather.get("longitude", 30.5234)
    weather["latitude"] = None if lat is None or lat == "" else _clamp_float(lat, -90.0, 90.0, 50.4501)
    weather["longitude"] = None if lon is None or lon == "" else _clamp_float(lon, -180.0, 180.0, 30.5234)
    weather["auto_geocode"] = bool(weather.get("auto_geocode", True))
    weather["refresh_minutes"] = _clamp_int(weather.get("refresh_minutes", 20), 5, 180, 20)
    units = str(weather.get("units", "metric")).strip().lower()
    weather["units"] = units if units in ("metric", "imperial") else "metric"
    sc = weather.get("show_card", "auto")
    if isinstance(sc, str):
        sc_low = sc.strip().lower()
        if sc_low == "auto":
            weather["show_card"] = "auto"
        elif sc_low in ("true", "1", "yes", "always"):
            weather["show_card"] = True
        else:
            weather["show_card"] = False
    else:
        weather["show_card"] = bool(sc)

    focus = widgets.setdefault("focus_timer", {})
    focus["work_minutes"] = _clamp_int(focus.get("work_minutes", 25), 1, 180, 25)
    focus["break_minutes"] = _clamp_int(focus.get("break_minutes", 5), 1, 60, 5)
    focus["sound_on_done"] = bool(focus.get("sound_on_done", True))

    sn = widgets.setdefault("storage_network", {})
    sn["max_drives"] = _clamp_int(sn.get("max_drives", 3), 1, 4, 3)

    tasks = widgets.setdefault("tasks", {})
    t_mode = str(tasks.get("mode", "auto")).strip().lower()
    tasks["mode"] = t_mode if t_mode in ("auto", "local", "todoist") else "auto"

    return cfg


def build_demo_config(base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Enable all showcase Tier 1 + Tier 2 widgets for --demo without touching user secrets."""
    cfg = copy.deepcopy(base if base is not None else DEFAULT_CONFIG)
    widgets = cfg["widgets"]
    widgets["system_monitor"]["enabled"] = True
    widgets["storage_network"]["enabled"] = True
    widgets["audio_control"]["enabled"] = True
    widgets["media_player"]["enabled"] = True
    widgets["media_player"]["spotify_like"]["enabled"] = True
    widgets["peripherals"]["enabled"] = True
    widgets["peripherals"]["show_mouse"] = True
    widgets["peripherals"]["show_keyboard"] = True
    widgets["peripherals"]["show_gamepad"] = True
    widgets["peripherals"]["show_handheld"] = True
    widgets["peripherals"]["show_bluetooth"] = True
    widgets["peripherals"]["auto_hide_offline"] = False
    widgets["weather"]["enabled"] = True
    widgets["weather"]["show_card"] = False
    widgets["calendar"]["enabled"] = False
    widgets["tasks"]["enabled"] = True
    widgets["focus_timer"]["enabled"] = False
    widgets["quick_actions"]["enabled"] = False
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
        "tasks",
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

    user_data = migrate_config(user_data)
    merged = deep_merge(DEFAULT_CONFIG, user_data)
    if overrides:
        merged = deep_merge(merged, overrides)
    expanded = expand_env_vars(merged, environ=environ)
    validated = validate_config(expanded)
    if demo:
        return build_demo_config(validated)
    return validated


def is_widget_enabled(
    cfg: Dict[str, Any],
    widget_id: str,
    *,
    center_overlay_active: bool = False,
) -> bool:
    """Return whether a given layout widget ID should be displayed."""
    widgets = cfg.get("widgets", {})
    if widget_id == "weather_card":
        w = widgets.get("weather", {})
        if not w.get("enabled", True):
            return False
        sc = w.get("show_card", "auto")
        if sc == "auto":
            return not center_overlay_active
        return bool(sc)
    if widget_id == "calendar_card":
        return bool(widgets.get("calendar", {}).get("enabled", True))
    if widget_id == "custom_json":
        c = widgets.get("custom_json", {})
        return bool(c.get("enabled", False) and c.get("cards"))
    if widget_id in ("tasks", "todoist"):
        # Backwards-compatible: either new "tasks" card or legacy "todoist" widget ID
        if widget_id == "todoist":
            return bool(widgets.get("todoist", {}).get("enabled", False))
        t_cfg = widgets.get("tasks", {})
        td_cfg = widgets.get("todoist", {})
        return bool(t_cfg.get("enabled", True) or td_cfg.get("enabled", False))
    return bool(widgets.get(widget_id, {}).get("enabled", False))
