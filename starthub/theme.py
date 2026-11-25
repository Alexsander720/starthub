"""Theme engine supporting multi_accent and single_accent palettes + Windows DWM AccentColor."""
from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Any, Dict, Tuple

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]

DEFAULT_ACCENT: RGB = (88, 188, 255)

MULTI_ACCENT_ROLES: Dict[str, RGB] = {
    "primary": (88, 188, 255),
    "monitor_normal": (121, 183, 213),
    "media": (99, 196, 125),
    "media_heart": (99, 212, 140),
    "hue": (240, 194, 121),
    "mouse": (76, 175, 255),
    "keyboard": (102, 197, 204),
    "gamepad": (172, 128, 255),
    "handheld": (72, 218, 148),
    "bluetooth": (59, 130, 246),
    "phone_screen": (58, 130, 246),
    "phone_shot": (16, 185, 129),
    "phone_sync": (72, 197, 120),
    "phone_sms": (96, 165, 250),
    "phone_otp": (74, 222, 128),
    "ecoflow_soc": (74, 222, 94),
    "ecoflow_in": (88, 188, 255),
    "ecoflow_out": (255, 182, 78),
    "ecoflow_backup": (88, 228, 138),
    "ecoflow_limit": (56, 189, 248),
    "ecoflow_usb": (52, 211, 153),
    "ecoflow_dc": (52, 211, 153),
    "ecoflow_beep": (192, 132, 252),
    "todoist": (242, 85, 72),
    "custom_0": (88, 188, 255),
    "custom_1": (232, 122, 82),
    "custom_2": (45, 212, 191),
    "weather": (93, 166, 255),
    "calendar": (42, 116, 230),
    "toast": (25, 118, 232),
}

# Subtle tonal shifts used in single_accent mode so multi-column cards stay legible
# while adhering strictly to a unified single-accent aesthetic.
_SINGLE_TONE_FACTORS: Dict[str, Tuple[float, float]] = {
    "ecoflow_out": (0.85, 1.05),
    "ecoflow_backup": (0.92, 1.08),
    "custom_1": (0.82, 1.04),
    "custom_2": (0.72, 0.96),
    "keyboard": (0.88, 1.02),
    "gamepad": (0.80, 0.98),
    "handheld": (0.90, 1.05),
    "phone_shot": (0.86, 1.04),
}


def parse_hex_color(value: str, default: RGB = DEFAULT_ACCENT) -> RGB:
    cleaned = str(value or "").strip().lstrip("#")
    if len(cleaned) != 6:
        return default
    try:
        return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))
    except ValueError:
        return default


def read_windows_accent_color(default: RGB = DEFAULT_ACCENT) -> RGB:
    """Read Windows 11 DWM AccentColor (ABGR DWORD) from HKCU registry."""
    try:
        import winreg
    except ImportError:
        return default
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
            val, _ = winreg.QueryValueEx(key, "AccentColor")
            val = int(val)
            r = val & 0xFF
            g = (val >> 8) & 0xFF
            b = (val >> 16) & 0xFF
            # Ensure minimum brightness for legibility on dark acrylic panels
            h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            if l < 0.45:
                l = 0.58
                nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
                return (int(round(nr * 255)), int(round(ng * 255)), int(round(nb * 255)))
            return (r, g, b)
    except Exception:
        return default


def adjust_tone(rgb: RGB, sat_scale: float = 1.0, light_scale: float = 1.0) -> RGB:
    h, l, s = colorsys.rgb_to_hls(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    s = max(0.0, min(1.0, s * sat_scale))
    l = max(0.15, min(0.85, l * light_scale))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def mix_rgb(fg: RGB, bg: RGB, ratio: float) -> RGB:
    t = max(0.0, min(1.0, ratio))
    return (
        int(round(fg[0] * t + bg[0] * (1.0 - t))),
        int(round(fg[1] * t + bg[1] * (1.0 - t))),
        int(round(fg[2] * t + bg[2] * (1.0 - t))),
    )


@dataclass(frozen=True)
class Theme:
    mode: str = "multi_accent"
    accent: RGB = DEFAULT_ACCENT
    panel_alpha: int = 180
    blur: bool = True
    corner_radius: int = 14

    # Surface palette
    panel_rgb: RGB = (33, 33, 33)
    edge_rgba: RGBA = (64, 64, 64, 160)
    tile_bg: RGBA = (37, 41, 50, 255)
    tile_bg_inactive: RGBA = (31, 34, 42, 255)
    tile_bg_hover: RGBA = (46, 52, 66, 255)
    tile_edge: RGBA = (58, 64, 76, 255)
    track_bg: RGBA = (52, 55, 64, 255)
    divider: RGBA = (46, 49, 58, 255)

    # Typography
    text_primary: RGBA = (245, 247, 252, 255)
    text_secondary: RGBA = (182, 189, 199, 255)
    text_muted: RGBA = (145, 152, 168, 255)

    # Critical alerts — ALWAYS preserved in both multi_accent and single_accent
    alert_danger: RGB = (239, 96, 86)
    alert_warn: RGB = (245, 179, 66)
    alert_ok: RGB = (74, 222, 128)

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Theme":
        t = cfg.get("theme", {})
        mode = str(t.get("mode", "multi_accent")).lower()
        if mode not in ("multi_accent", "single_accent"):
            mode = "multi_accent"
        raw_accent = str(t.get("accent_color", "#58BCFF")).strip()
        if raw_accent.lower() == "windows":
            accent = read_windows_accent_color()
        else:
            accent = parse_hex_color(raw_accent)
        return cls(
            mode=mode,
            accent=accent,
            panel_alpha=max(80, min(255, int(t.get("panel_alpha", 180)))),
            blur=bool(t.get("blur", True)),
            corner_radius=max(0, min(24, int(t.get("corner_radius", 14)))),
        )

    @property
    def is_single_accent(self) -> bool:
        return self.mode == "single_accent"

    @property
    def panel_bg(self) -> RGBA:
        return (*self.panel_rgb, self.panel_alpha)

    @property
    def card_bg(self) -> RGBA:
        return (*self.panel_rgb, self.panel_alpha)

    @property
    def panel_edge(self) -> RGBA:
        return self.edge_rgba

    @property
    def card_edge(self) -> RGBA:
        return self.edge_rgba

    def role(self, name: str) -> RGB:
        """Resolve a semantic UI role color respecting multi_accent vs single_accent."""
        if not self.is_single_accent:
            return MULTI_ACCENT_ROLES.get(name, self.accent)
        if name in _SINGLE_TONE_FACTORS:
            sat_s, light_s = _SINGLE_TONE_FACTORS[name]
            return adjust_tone(self.accent, sat_s, light_s)
        return self.accent

    def role_rgba(self, name: str, alpha: int = 255) -> RGBA:
        return (*self.role(name), alpha)

    def tint_dark(self, rgb: RGB, ratio: float = 0.20, alpha: int = 255) -> RGBA:
        """Return a deep, dark pill/button background subtly tinted by rgb."""
        base = mix_rgb(rgb, (24, 27, 34), ratio)
        return (*base, alpha)

    def tint_hover(self, rgb: RGB, ratio: float = 0.30, alpha: int = 255) -> RGBA:
        base = mix_rgb(rgb, (34, 38, 48), ratio)
        return (*base, alpha)

    def monitor_bar_color(self, value: float | int | None) -> RGB:
        """Progress color for CPU/GPU/RAM; >90% danger and >70% warn always preserved."""
        if value is not None:
            if value > 90:
                return self.alert_danger
            if value > 70:
                return self.alert_warn
        return self.role("monitor_normal")

    def status_color(self, status: str, fallback_role: str = "primary") -> RGB:
        """Map metric status ('ok' | 'warn' | 'danger' | 'info') with alert preservation."""
        st = (status or "").lower()
        if st in ("danger", "critical", "error", "blackout"):
            return self.alert_danger
        if st in ("warn", "warning", "stale"):
            return self.alert_warn
        if st == "ok" and not self.is_single_accent:
            return self.alert_ok
        return self.role(fallback_role)
