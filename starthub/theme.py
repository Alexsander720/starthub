"""Full customizable Theme engine: 6 built-in presets, Light/Dark modes, custom surface colors & per-widget role overrides."""
from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]

DEFAULT_ACCENT: RGB = (88, 188, 255)

MULTI_ACCENT_ROLES: Dict[str, RGB] = {
    "primary": (88, 188, 255),
    "monitor_normal": (121, 183, 213),
    "audio": (96, 165, 250),
    "storage": (56, 189, 248),
    "network_down": (74, 222, 128),
    "network_up": (192, 132, 252),
    "focus_work": (249, 115, 22),
    "focus_break": (52, 211, 153),
    "quick_actions": (129, 140, 248),
    "tile_bar": (88, 188, 255),
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

# Built-in community-favorite visual presets selectable in 1 click
THEME_PRESETS: Dict[str, Dict[str, Any]] = {
    "fluent_dark": {
        "label": "Fluent Dark (Default)",
        "is_light": False,
        "accent": (88, 188, 255),
        "panel_rgb": (33, 33, 33),
        "edge_rgba": (64, 64, 64, 160),
        "tile_bg": (37, 41, 50, 255),
        "tile_bg_inactive": (31, 34, 42, 255),
        "tile_bg_hover": (46, 52, 66, 255),
        "tile_edge": (58, 64, 76, 255),
        "track_bg": (52, 55, 64, 255),
        "divider": (46, 49, 58, 255),
        "text_primary": (245, 247, 252, 255),
        "text_secondary": (182, 189, 199, 255),
        "text_muted": (145, 152, 168, 255),
        "role_overrides": {},
    },
    "fluent_light": {
        "label": "Fluent Light (Frosted White)",
        "is_light": True,
        "accent": (0, 114, 210),
        "panel_rgb": (242, 245, 250),
        "edge_rgba": (196, 204, 218, 210),
        "tile_bg": (229, 234, 243, 255),
        "tile_bg_inactive": (236, 240, 247, 255),
        "tile_bg_hover": (214, 223, 238, 255),
        "tile_edge": (190, 199, 214, 255),
        "track_bg": (204, 211, 224, 255),
        "divider": (208, 215, 226, 255),
        "text_primary": (22, 27, 38, 255),
        "text_secondary": (66, 75, 92, 255),
        "text_muted": (102, 112, 130, 255),
        "role_overrides": {
            "primary": (0, 114, 210),
            "monitor_normal": (14, 116, 178),
            "audio": (29, 108, 216),
            "storage": (2, 122, 188),
            "network_down": (20, 142, 68),
            "network_up": (124, 58, 206),
            "focus_work": (206, 86, 14),
            "focus_break": (18, 144, 96),
            "quick_actions": (68, 76, 204),
            "mouse": (16, 114, 208),
            "keyboard": (14, 134, 144),
            "gamepad": (118, 66, 212),
            "handheld": (18, 146, 88),
            "bluetooth": (28, 98, 214),
            "phone_screen": (28, 98, 214),
            "phone_shot": (12, 142, 96),
            "phone_sms": (28, 104, 212),
            "media": (20, 146, 74),
            "media_heart": (20, 152, 70),
            "hue": (186, 112, 12),
            "ecoflow_soc": (20, 148, 68),
            "ecoflow_out": (196, 110, 10),
            "ecoflow_backup": (20, 144, 74),
            "phone_otp": (18, 140, 66),
            "todoist": (208, 48, 38),
            "custom_0": (18, 112, 206),
            "custom_1": (198, 84, 42),
            "custom_2": (14, 144, 128),
            "weather": (24, 112, 216),
            "calendar": (29, 108, 216),
        },
    },
    "amoled_black": {
        "label": "AMOLED Pure Black",
        "is_light": False,
        "accent": (88, 188, 255),
        "panel_rgb": (10, 11, 14),
        "edge_rgba": (46, 50, 62, 210),
        "tile_bg": (18, 20, 26, 255),
        "tile_bg_inactive": (14, 16, 20, 255),
        "tile_bg_hover": (28, 32, 42, 255),
        "tile_edge": (42, 46, 58, 255),
        "track_bg": (32, 35, 44, 255),
        "divider": (30, 33, 42, 255),
        "text_primary": (248, 250, 255, 255),
        "text_secondary": (176, 184, 198, 255),
        "text_muted": (128, 136, 154, 255),
        "role_overrides": {},
    },
    "catppuccin_mocha": {
        "label": "Catppuccin Mocha",
        "is_light": False,
        "accent": (137, 180, 250),
        "panel_rgb": (30, 30, 46),
        "edge_rgba": (69, 71, 90, 210),
        "tile_bg": (41, 42, 62, 255),
        "tile_bg_inactive": (35, 36, 54, 255),
        "tile_bg_hover": (54, 56, 80, 255),
        "tile_edge": (69, 71, 90, 255),
        "track_bg": (56, 58, 78, 255),
        "divider": (54, 56, 76, 255),
        "text_primary": (205, 214, 244, 255),
        "text_secondary": (186, 194, 222, 255),
        "text_muted": (147, 153, 178, 255),
        "role_overrides": {
            "primary": (137, 180, 250),
            "audio": (137, 220, 235),
            "media": (166, 227, 161),
            "media_heart": (166, 227, 161),
            "hue": (249, 226, 175),
            "gamepad": (203, 166, 247),
            "focus_work": (250, 179, 135),
            "todoist": (243, 139, 168),
            "quick_actions": (180, 190, 254),
            "ecoflow_soc": (166, 227, 161),
            "ecoflow_out": (250, 179, 135),
        },
    },
    "nord": {
        "label": "Nord Frost",
        "is_light": False,
        "accent": (136, 192, 208),
        "panel_rgb": (46, 52, 64),
        "edge_rgba": (76, 86, 106, 200),
        "tile_bg": (55, 63, 78, 255),
        "tile_bg_inactive": (50, 57, 71, 255),
        "tile_bg_hover": (67, 76, 94, 255),
        "tile_edge": (76, 86, 106, 255),
        "track_bg": (67, 76, 94, 255),
        "divider": (67, 76, 94, 255),
        "text_primary": (236, 239, 244, 255),
        "text_secondary": (216, 222, 233, 255),
        "text_muted": (165, 177, 196, 255),
        "role_overrides": {
            "primary": (136, 192, 208),
            "audio": (129, 161, 193),
            "media": (163, 190, 140),
            "hue": (235, 203, 139),
            "gamepad": (180, 142, 173),
            "focus_work": (208, 135, 112),
            "todoist": (191, 97, 106),
            "ecoflow_soc": (163, 190, 140),
        },
    },
    "tokyo_night": {
        "label": "Tokyo Night",
        "is_light": False,
        "accent": (122, 162, 247),
        "panel_rgb": (26, 27, 38),
        "edge_rgba": (65, 72, 104, 205),
        "tile_bg": (36, 40, 59, 255),
        "tile_bg_inactive": (30, 33, 49, 255),
        "tile_bg_hover": (48, 54, 80, 255),
        "tile_edge": (65, 72, 104, 255),
        "track_bg": (52, 58, 84, 255),
        "divider": (46, 51, 74, 255),
        "text_primary": (192, 202, 245, 255),
        "text_secondary": (169, 177, 214, 255),
        "text_muted": (120, 128, 164, 255),
        "role_overrides": {
            "primary": (122, 162, 247),
            "audio": (125, 207, 255),
            "media": (158, 206, 106),
            "hue": (224, 175, 104),
            "gamepad": (187, 154, 247),
            "focus_work": (255, 158, 100),
            "todoist": (247, 118, 142),
            "ecoflow_soc": (115, 218, 202),
        },
    },
}

_SINGLE_TONE_FACTORS: Dict[str, Tuple[float, float]] = {
    "ecoflow_out": (0.85, 1.05),
    "ecoflow_backup": (0.92, 1.08),
    "custom_1": (0.82, 1.04),
    "custom_2": (0.72, 0.96),
    "keyboard": (0.88, 1.02),
    "gamepad": (0.80, 0.98),
    "handheld": (0.90, 1.05),
    "phone_shot": (0.86, 1.04),
    "network_up": (0.82, 1.06),
    "focus_break": (0.88, 1.08),
}


def parse_hex_color(value: str, default: RGB = DEFAULT_ACCENT) -> RGB:
    cleaned = str(value or "").strip().lstrip("#")
    if len(cleaned) != 6:
        return default
    try:
        return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))
    except ValueError:
        return default


def parse_optional_hex(value: Any) -> Optional[RGB]:
    cleaned = str(value or "").strip().lstrip("#")
    if len(cleaned) != 6:
        return None
    try:
        return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))
    except ValueError:
        return None


def rgb_to_hex(rgb: RGB) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def read_windows_accent_color(default: RGB = DEFAULT_ACCENT, *, for_light: bool = False) -> RGB:
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
            h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
            if for_light and l > 0.52:
                l = 0.42
                nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
                return (int(round(nr * 255)), int(round(ng * 255)), int(round(nb * 255)))
            if not for_light and l < 0.45:
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


def _is_rgb_light(rgb: RGB) -> bool:
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) >= 155.0


@dataclass(frozen=True)
class Theme:
    preset: str = "fluent_dark"
    mode: str = "multi_accent"
    accent: RGB = DEFAULT_ACCENT
    panel_alpha: int = 180
    blur: bool = True
    corner_radius: int = 14
    is_light: bool = False

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

    # Critical alerts — ALWAYS preserved in every preset & single_accent mode
    alert_danger: RGB = (239, 96, 86)
    alert_warn: RGB = (245, 179, 66)
    alert_ok: RGB = (74, 222, 128)

    # Optional per-widget role overrides (from preset + user theme.role_overrides)
    role_overrides: Mapping[str, RGB] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "Theme":
        t = cfg.get("theme", {})
        preset_key = str(t.get("preset", "fluent_dark")).strip().lower()
        if preset_key not in THEME_PRESETS:
            preset_key = "fluent_dark"
        p = THEME_PRESETS[preset_key]

        mode = str(t.get("mode", "multi_accent")).lower()
        if mode not in ("multi_accent", "single_accent"):
            mode = "multi_accent"

        custom = t.get("custom_colors") if isinstance(t.get("custom_colors"), dict) else {}
        panel_rgb: RGB = parse_optional_hex(custom.get("panel_bg")) or p["panel_rgb"]
        is_light = _is_rgb_light(panel_rgb) if custom.get("panel_bg") else bool(p["is_light"])

        raw_accent = str(t.get("accent_color", "")).strip()
        if raw_accent.lower() == "windows":
            accent = read_windows_accent_color(default=p["accent"], for_light=is_light)
        elif raw_accent:
            # When using a non-default preset and accent is left at default blue, keep preset's signature accent
            if preset_key != "fluent_dark" and raw_accent.upper() == "#58BCFF" and not t.get("accent_explicit"):
                accent = p["accent"]
            else:
                accent = parse_hex_color(raw_accent, default=p["accent"])
        else:
            accent = p["accent"]

        tile_custom = parse_optional_hex(custom.get("tile_bg"))
        if tile_custom:
            tile_bg: RGBA = (*tile_custom, 255)
            tile_bg_inactive: RGBA = (*mix_rgb(tile_custom, panel_rgb, 0.65), 255)
            hover_mix = (255, 255, 255) if not is_light else (0, 0, 0)
            tile_bg_hover: RGBA = (*mix_rgb(hover_mix, tile_custom, 0.12), 255)
        else:
            tile_bg = p["tile_bg"]
            tile_bg_inactive = p["tile_bg_inactive"]
            tile_bg_hover = p["tile_bg_hover"]

        border_custom = parse_optional_hex(custom.get("border"))
        if border_custom:
            edge_rgba: RGBA = (*border_custom, 190)
            tile_edge: RGBA = (*border_custom, 255)
            divider: RGBA = (*mix_rgb(border_custom, panel_rgb, 0.6), 255)
        else:
            edge_rgba = p["edge_rgba"]
            tile_edge = p["tile_edge"]
            divider = p["divider"]

        txt_p = parse_optional_hex(custom.get("text_primary"))
        txt_s = parse_optional_hex(custom.get("text_secondary"))
        text_primary: RGBA = (*txt_p, 255) if txt_p else p["text_primary"]
        text_secondary: RGBA = (*txt_s, 255) if txt_s else p["text_secondary"]
        text_muted: RGBA = (*mix_rgb(text_secondary[:3], panel_rgb, 0.72), 255) if txt_s else p["text_muted"]

        # Merge preset role overrides with explicit user role_overrides
        merged_roles: Dict[str, RGB] = dict(p.get("role_overrides") or {})
        user_roles = t.get("role_overrides") if isinstance(t.get("role_overrides"), dict) else {}
        for rk, rv in user_roles.items():
            parsed = parse_optional_hex(rv)
            if parsed is not None:
                merged_roles[str(rk)] = parsed

        alert_danger = (212, 50, 44) if is_light else (239, 96, 86)
        alert_warn = (196, 120, 12) if is_light else (245, 179, 66)
        alert_ok = (22, 154, 72) if is_light else (74, 222, 128)

        return cls(
            preset=preset_key,
            mode=mode,
            accent=accent,
            panel_alpha=max(80, min(255, int(t.get("panel_alpha", 180)))),
            blur=bool(t.get("blur", True)),
            corner_radius=max(0, min(24, int(t.get("corner_radius", 14)))),
            is_light=is_light,
            panel_rgb=panel_rgb,
            edge_rgba=edge_rgba,
            tile_bg=tile_bg,
            tile_bg_inactive=tile_bg_inactive,
            tile_bg_hover=tile_bg_hover,
            tile_edge=tile_edge,
            track_bg=p["track_bg"],
            divider=divider,
            text_primary=text_primary,
            text_secondary=text_secondary,
            text_muted=text_muted,
            alert_danger=alert_danger,
            alert_warn=alert_warn,
            alert_ok=alert_ok,
            role_overrides=merged_roles,
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
        """Resolve a semantic UI role color respecting user overrides, presets, and single_accent."""
        if not self.is_single_accent:
            if name in self.role_overrides:
                return self.role_overrides[name]
            return MULTI_ACCENT_ROLES.get(name, self.accent)
        if name in _SINGLE_TONE_FACTORS:
            sat_s, light_s = _SINGLE_TONE_FACTORS[name]
            return adjust_tone(self.accent, sat_s, light_s)
        return self.accent

    def role_rgba(self, name: str, alpha: int = 255) -> RGBA:
        return (*self.role(name), alpha)

    def tint_dark(self, rgb: RGB, ratio: float = 0.20, alpha: int = 255) -> RGBA:
        """Return a surface-matched subtle pill/button background tinted by rgb (works in both Dark & Light themes!)."""
        anchor = (232, 237, 246) if self.is_light else (24, 27, 34)
        eff_ratio = min(0.32, ratio * 0.85) if self.is_light else ratio
        base = mix_rgb(rgb, anchor, eff_ratio)
        return (*base, alpha)

    def tint_hover(self, rgb: RGB, ratio: float = 0.30, alpha: int = 255) -> RGBA:
        anchor = (218, 226, 239) if self.is_light else (34, 38, 48)
        eff_ratio = min(0.42, ratio * 0.90) if self.is_light else ratio
        base = mix_rgb(rgb, anchor, eff_ratio)
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
