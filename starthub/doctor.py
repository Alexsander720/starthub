"""Sanitized environment & runtime diagnostics (`python -m starthub --doctor`).

Never outputs secrets, tokens, LAN IPs, serial numbers, emails, or personal file paths.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import platform
import shutil
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .config import DEFAULT_CONFIG_PATH, is_widget_enabled, load_config
from .surface import IS_WINDOWS, find_native_win11_start_rect


def _has_mod(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _probe_monitors() -> List[str]:
    if not IS_WINDOWS:
        return ["non-windows"]
    try:
        import win32api

        out = []
        for idx, (_hm, _hdc, rect) in enumerate(win32api.EnumDisplayMonitors(), 1):
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            out.append(f"Display {idx}: {w}x{h}")
        return out or ["unknown"]
    except Exception:
        return ["unavailable"]


def _probe_gpu_backend() -> str:
    if _has_mod("pynvml"):
        try:
            import pynvml

            pynvml.nvmlInit()
            cnt = pynvml.nvmlDeviceGetCount()
            if cnt > 0:
                return f"nvidia-nvml ({cnt} GPU)"
        except Exception:
            pass
    if shutil.which("nvidia-smi"):
        return "nvidia-smi"
    if IS_WINDOWS and _has_mod("win32pdh"):
        return "windows-pdh (AMD/Intel/Generic)"
    return "unavailable"


def _probe_start_menus(start_class: str) -> Dict[str, Any]:
    if not IS_WINDOWS:
        return {"start11_hwnd": False, "win11_native_open": False}
    start11 = False
    try:
        import win32gui

        start11 = bool(win32gui.FindWindow(start_class, None))
    except Exception:
        pass
    win11_open = find_native_win11_start_rect() is not None
    return {"start11_hwnd": start11, "win11_native_open": win11_open}


def _probe_audio_endpoints() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        import ctypes
        from .providers.audio import query_windows_audio_state

        ctypes.windll.ole32.CoInitializeEx(None, 2)
        try:
            st = query_windows_audio_state()
            return len(st.get("devices") or [])
        finally:
            ctypes.windll.ole32.CoUninitialize()
    except Exception:
        return 0


def run_diagnostics(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Collect a completely sanitized diagnostic snapshot safe to paste into GitHub Issues."""
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    cfg = load_config(cfg_path)

    enabled_left = [w for w in cfg["layout"]["left_widgets"] if is_widget_enabled(cfg, w)]
    enabled_right = [w for w in cfg["layout"]["right_widgets"] if is_widget_enabled(cfg, w)]

    core_deps = {
        "Pillow": _has_mod("PIL"),
        "psutil": _has_mod("psutil"),
        "requests": _has_mod("requests"),
        "pystray": _has_mod("pystray"),
        "pywin32": _has_mod("win32gui"),
        "winrt_smtc": _has_mod("winrt.windows.media.control"),
    }
    optional_deps = {
        "nvidia_ml_py": _has_mod("pynvml"),
        "hidapi": _has_mod("hid"),
        "paho_mqtt": _has_mod("paho"),
        "protobuf": _has_mod("google.protobuf"),
    }
    external_tools = {
        "adb": bool(shutil.which("adb")),
        "scrcpy": bool(shutil.which("scrcpy")),
    }

    return {
        "version": __version__,
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "config_exists": cfg_path.is_file(),
        "language": cfg["language"],
        "config_version": cfg.get("config_version", 2),
        "theme_preset": cfg["theme"].get("preset", "fluent_dark"),
        "theme_mode": cfg["theme"]["mode"],
        "accent_is_windows": str(cfg["theme"]["accent_color"]).lower() == "windows",
        "blur": bool(cfg["theme"]["blur"]),
        "trigger_mode": cfg["window"]["trigger_mode"],
        "hotkey": cfg["window"]["hotkey"] if cfg["window"]["hotkey_enabled"] else "disabled",
        "adaptive_width": bool(cfg["window"]["adaptive_width"]),
        "fade_animation": bool(cfg["window"]["fade_animation"]),
        "monitors": _probe_monitors(),
        "start_menus": _probe_start_menus(cfg["window"]["start_menu_class"]),
        "gpu_backend": _probe_gpu_backend(),
        "audio_endpoints": _probe_audio_endpoints(),
        "core_deps": core_deps,
        "optional_deps": optional_deps,
        "external_tools": external_tools,
        "enabled_left": enabled_left,
        "enabled_right": enabled_right,
    }


def format_diagnostics(report: Dict[str, Any]) -> str:
    """Format diagnostic dict into a clean Markdown block ready for GitHub Issue reports."""
    def mark(ok: bool) -> str:
        return "OK" if ok else "missing"

    lines = [
        f"StartHub Diagnostics (v{report['version']})",
        "=" * 42,
        f"OS            : {report['os']}",
        f"Python        : {report['python']}",
        f"Config file   : {'found' if report['config_exists'] else 'using defaults'}",
        f"Language      : {report['language']}",
        f"Theme         : {report.get('theme_preset', 'fluent_dark')} / {report['theme_mode']} (windows_accent={report['accent_is_windows']}, blur={report['blur']})",
        f"Trigger mode  : {report['trigger_mode']} (hotkey={report['hotkey']}, adaptive={report['adaptive_width']}, fade={report['fade_animation']})",
        f"Monitors      : {', '.join(report['monitors'])}",
        f"Start11 HWND  : {report['start_menus']['start11_hwnd']}",
        f"GPU backend   : {report['gpu_backend']}",
        f"Audio outputs : {report['audio_endpoints']}",
        "",
        "Core dependencies:",
        "  " + ", ".join(f"{k}={mark(v)}" for k, v in report["core_deps"].items()),
        "Optional dependencies:",
        "  " + ", ".join(f"{k}={mark(v)}" for k, v in report["optional_deps"].items()),
        "External CLI tools:",
        "  " + ", ".join(f"{k}={mark(v)}" for k, v in report["external_tools"].items()),
        "",
        f"Enabled left  : {', '.join(report['enabled_left']) or '(none)'}",
        f"Enabled right : {', '.join(report['enabled_right']) or '(none)'}",
    ]
    return "\n".join(lines)
