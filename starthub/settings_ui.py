"""Modern dark GUI Settings & Widget Customizer for StartHub (zero raw JSON editing needed)."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import colorchooser, ttk
from typing import Any, Callable, Dict, List, Optional

from . import __version__
from .config import (
    ALL_WIDGET_IDS,
    DEFAULT_CONFIG,
    LAYOUT_PRESETS,
    REPO_ROOT,
    deep_merge,
    load_raw_user_config,
    save_config_patch,
)
from .doctor import format_diagnostics, run_diagnostics
from .providers.hue import discover_hue_bridges, fetch_hue_catalog, pair_hue_bridge
from .providers.weather import geocode_city
from .surface import IS_WINDOWS, copy_text_to_clipboard

WIDGET_META: Dict[str, tuple[str, str, str]] = {
    "peripherals": ("Peripherals & Bluetooth", "Tier 1", "peripherals"),
    "audio_control": ("Audio Volume & Switcher", "Tier 1", "audio_control"),
    "media_player": ("Media Player (SMTC)", "Tier 1", "media_player"),
    "system_monitor": ("System Monitor (CPU/GPU/RAM)", "Tier 1", "system_monitor"),
    "storage_network": ("Storage & Network Speed", "Tier 1", "storage_network"),
    "weather_card": ("Weather Forecast Card", "Tier 1", "weather"),
    "tasks": ("Tasks (Local / Todoist)", "Tier 1", "tasks"),
    "focus_timer": ("Focus / Pomodoro Timer", "Tier 1", "focus_timer"),
    "calendar_card": ("Monthly Calendar", "Tier 1", "calendar"),
    "quick_actions": ("Quick Actions Bar", "Tier 1", "quick_actions"),
    "philips_hue": ("Philips Hue Lights", "Tier 2", "philips_hue"),
    "phone_adb": ("Android Phone Hub (ADB)", "Tier 2", "phone_adb"),
    "ecoflow": ("EcoFlow Power Station", "Tier 2", "ecoflow"),
    "custom_json": ("Custom JSON Cards", "Tier 2", "custom_json"),
    "tile_switcher": ("Start11 Tile Switcher", "Tier 2", "tile_switcher"),
}

ACCENT_SWATCHES = ("#58BCFF", "#4ADE80", "#A78BFA", "#F97316", "#F43F5E", "#38BDF8")

BG_MAIN = "#12151C"
BG_CARD = "#1B1F2A"
BG_INPUT = "#252B39"
FG_MAIN = "#F1F5F9"
FG_MUTED = "#94A3B8"
ACCENT_HEX = "#58BCFF"


class SettingsWindow:
    """Tabbed dark GUI settings modal with live widget layout reordering, city search, and 1-click Hue pairing."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        config_path: Path,
        on_apply: Callable[[], None],
    ):
        self.parent = parent
        self.config_path = Path(config_path)
        self.on_apply = on_apply

        # Merge raw user config over defaults WITHOUT expanding ${ENV_VAR} placeholders!
        raw_user = load_raw_user_config(self.config_path)
        self.draft: Dict[str, Any] = deep_merge(DEFAULT_CONFIG, raw_user)

        self.win = tk.Toplevel(parent)
        self.win.title(f"StartHub Settings — v{__version__}")
        self.win.configure(bg=BG_MAIN)
        self.win.geometry("820x660")
        self.win.minsize(760, 580)
        self.win.attributes("-topmost", True)

        self._style_ttk()
        self._build_ui()

    def _style_ttk(self) -> None:
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG_CARD,
            foreground=FG_MUTED,
            padding=(14, 8),
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_INPUT)],
            foreground=[("selected", FG_MAIN)],
        )
        style.configure("Dark.TFrame", background=BG_MAIN)
        style.configure("Card.TFrame", background=BG_CARD)

    def _build_ui(self) -> None:
        # Top Header
        hdr = tk.Frame(self.win, bg=BG_CARD, height=54)
        hdr.pack(fill="x", side="top")
        tk.Label(
            hdr,
            text="StartHub Settings",
            font=("Segoe UI", 14, "bold"),
            fg=FG_MAIN,
            bg=BG_CARD,
        ).pack(side="left", padx=18, pady=12)
        self.status_var = tk.StringVar(value="Changes apply immediately on Save — ${ENV_VAR} secrets are preserved")
        tk.Label(
            hdr,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            fg=FG_MUTED,
            bg=BG_CARD,
        ).pack(side="right", padx=18)

        # Notebook tabs
        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(12, 6))

        self.tab_appearance = tk.Frame(self.nb, bg=BG_MAIN)
        self.tab_widgets = tk.Frame(self.nb, bg=BG_MAIN)
        self.tab_weather = tk.Frame(self.nb, bg=BG_MAIN)
        self.tab_integrations = tk.Frame(self.nb, bg=BG_MAIN)
        self.tab_doctor = tk.Frame(self.nb, bg=BG_MAIN)

        self.nb.add(self.tab_appearance, text="Appearance & Triggers")
        self.nb.add(self.tab_widgets, text="Widgets & Layout")
        self.nb.add(self.tab_weather, text="Weather & Peripherals")
        self.nb.add(self.tab_integrations, text="Integrations (Tier 2)")
        self.nb.add(self.tab_doctor, text="Diagnostics")

        self._build_appearance_tab()
        self._build_widgets_tab()
        self._build_weather_tab()
        self._build_integrations_tab()
        self._build_doctor_tab()

        # Bottom action bar
        bar = tk.Frame(self.win, bg=BG_CARD, height=52)
        bar.pack(fill="x", side="bottom")
        tk.Button(
            bar,
            text="Reset Defaults",
            bg="#2D3343",
            fg=FG_MAIN,
            relief="flat",
            padx=14,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            command=self._reset_defaults,
        ).pack(side="left", padx=14, pady=10)
        tk.Button(
            bar,
            text="Open config.json",
            bg="#2D3343",
            fg=FG_MAIN,
            relief="flat",
            padx=14,
            pady=6,
            font=("Segoe UI", 9),
            command=self._open_raw_config,
        ).pack(side="left", padx=4, pady=10)
        tk.Button(
            bar,
            text="Close",
            bg="#2D3343",
            fg=FG_MAIN,
            relief="flat",
            padx=16,
            pady=6,
            font=("Segoe UI", 9, "bold"),
            command=self.win.destroy,
        ).pack(side="right", padx=(6, 14), pady=10)
        tk.Button(
            bar,
            text="Apply & Save",
            bg="#2563EB",
            fg="#FFFFFF",
            relief="flat",
            padx=20,
            pady=6,
            font=("Segoe UI", 10, "bold"),
            command=self._save_and_apply,
        ).pack(side="right", padx=6, pady=10)

    def _section(self, parent: tk.Misc, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG_CARD, padx=14, pady=10)
        outer.pack(fill="x", padx=8, pady=6)
        tk.Label(outer, text=title, font=("Segoe UI", 11, "bold"), fg=ACCENT_HEX, bg=BG_CARD).pack(anchor="w", pady=(0, 6))
        return outer

    def _row(self, parent: tk.Misc) -> tk.Frame:
        r = tk.Frame(parent, bg=BG_CARD)
        r.pack(fill="x", pady=3)
        return r

    def _entry(self, parent: tk.Misc, var: tk.Variable, width: int = 22, show: str = "") -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=var,
            width=width,
            bg=BG_INPUT,
            fg=FG_MAIN,
            insertbackground=FG_MAIN,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#3B4254",
            font=("Segoe UI", 10),
            show=show,
        )

    def _check(self, parent: tk.Misc, text: str, var: tk.BooleanVar) -> tk.Checkbutton:
        return tk.Checkbutton(
            parent,
            text=text,
            variable=var,
            bg=BG_CARD,
            fg=FG_MAIN,
            selectcolor=BG_INPUT,
            activebackground=BG_CARD,
            activeforeground=FG_MAIN,
            font=("Segoe UI", 10),
        )

    # ------------------------------------------------------------------
    # Tab 1: Appearance & Triggers
    # ------------------------------------------------------------------

    def _build_appearance_tab(self) -> None:
        t = self.draft["theme"]
        w = self.draft["window"]

        # Quick layout presets
        sec_p = self._section(self.tab_appearance, "Quick Layout Presets")
        rp = self._row(sec_p)
        for key, lbl in (("balanced", "Balanced (Recommended)"), ("minimal", "Minimal Clean"), ("productivity", "Productivity Focus")):
            tk.Button(
                rp,
                text=lbl,
                bg=BG_INPUT,
                fg=FG_MAIN,
                relief="flat",
                padx=12,
                pady=5,
                font=("Segoe UI", 9, "bold"),
                command=lambda k=key: self._apply_preset(k),
            ).pack(side="left", padx=(0, 8))

        # Theme & Language
        sec_t = self._section(self.tab_appearance, "Theme & Visuals")
        self.var_lang = tk.StringVar(value=str(self.draft.get("language", "en")))
        self.var_theme_mode = tk.StringVar(value=str(t.get("mode", "multi_accent")))
        raw_acc = str(t.get("accent_color", "#58BCFF"))
        self.var_win_accent = tk.BooleanVar(value=raw_acc.lower() == "windows")
        self.var_accent_hex = tk.StringVar(value="#58BCFF" if raw_acc.lower() == "windows" else raw_acc)
        self.var_alpha = tk.IntVar(value=int(t.get("panel_alpha", 180)))
        self.var_radius = tk.IntVar(value=int(t.get("corner_radius", 14)))
        self.var_blur = tk.BooleanVar(value=bool(t.get("blur", True)))
        self.var_fade = tk.BooleanVar(value=bool(w.get("fade_animation", True)))

        r1 = self._row(sec_t)
        tk.Label(r1, text="Theme Mode:", fg=FG_MAIN, bg=BG_CARD, width=16, anchor="w").pack(side="left")
        for val, lbl in (("multi_accent", "Multi-Accent"), ("single_accent", "Single-Accent")):
            tk.Radiobutton(
                r1, text=lbl, value=val, variable=self.var_theme_mode,
                bg=BG_CARD, fg=FG_MAIN, selectcolor=BG_INPUT, activebackground=BG_CARD, activeforeground=FG_MAIN,
            ).pack(side="left", padx=6)
        tk.Label(r1, text="Language:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(24, 6))
        ttk.Combobox(r1, textvariable=self.var_lang, values=("en", "ru", "uk"), width=6, state="readonly").pack(side="left")

        r2 = self._row(sec_t)
        tk.Label(r2, text="Accent Color:", fg=FG_MAIN, bg=BG_CARD, width=16, anchor="w").pack(side="left")
        self._entry(r2, self.var_accent_hex, width=10).pack(side="left", padx=(0, 6))
        tk.Button(
            r2, text="Pick...", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=self._pick_accent
        ).pack(side="left", padx=(0, 8))
        for sw in ACCENT_SWATCHES:
            tk.Button(
                r2, bg=sw, width=2, relief="flat", command=lambda c=sw: (self.var_win_accent.set(False), self.var_accent_hex.set(c))
            ).pack(side="left", padx=2)
        self._check(r2, "Sync Windows Accent", self.var_win_accent).pack(side="left", padx=10)

        r3 = self._row(sec_t)
        tk.Label(r3, text="Panel Opacity:", fg=FG_MAIN, bg=BG_CARD, width=16, anchor="w").pack(side="left")
        tk.Scale(
            r3, from_=80, to=255, orient="horizontal", variable=self.var_alpha,
            bg=BG_CARD, fg=FG_MAIN, highlightthickness=0, troughcolor=BG_INPUT, length=180,
        ).pack(side="left", padx=(0, 18))
        tk.Label(r3, text="Corner Radius:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(4, 6))
        tk.Scale(
            r3, from_=0, to=24, orient="horizontal", variable=self.var_radius,
            bg=BG_CARD, fg=FG_MAIN, highlightthickness=0, troughcolor=BG_INPUT, length=120,
        ).pack(side="left")

        r4 = self._row(sec_t)
        self._check(r4, "Native Acrylic Blur-Behind", self.var_blur).pack(side="left", padx=(0, 16))
        self._check(r4, "Smooth 120ms Fade Animation", self.var_fade).pack(side="left")

        # Trigger & Window Geometry
        sec_w = self._section(self.tab_appearance, "Start Menu Trigger & Multi-Monitor Fit")
        self.var_trigger = tk.StringVar(value=str(w.get("trigger_mode", "auto")))
        self.var_hk_en = tk.BooleanVar(value=bool(w.get("hotkey_enabled", True)))
        self.var_hotkey = tk.StringVar(value=str(w.get("hotkey", "Alt+Space")))
        self.var_adaptive = tk.BooleanVar(value=bool(w.get("adaptive_width", True)))
        self.var_center = tk.BooleanVar(value=bool(w.get("center_overlay", True)))
        self.var_lw = tk.IntVar(value=int(w.get("left_width", 416)))
        self.var_rw = tk.IntVar(value=int(w.get("right_width", 430)))

        rw1 = self._row(sec_w)
        tk.Label(rw1, text="Trigger Mode:", fg=FG_MAIN, bg=BG_CARD, width=16, anchor="w").pack(side="left")
        ttk.Combobox(
            rw1,
            textvariable=self.var_trigger,
            values=("auto", "start11", "windows11", "hotkey"),
            width=14,
            state="readonly",
        ).pack(side="left", padx=(0, 12))
        tk.Label(
            rw1,
            text="auto = Start11 -> Native Windows 11 Start",
            fg=FG_MUTED,
            bg=BG_CARD,
            font=("Segoe UI", 9),
        ).pack(side="left")

        rw2 = self._row(sec_w)
        self._check(rw2, "Global Toggle Hotkey:", self.var_hk_en).pack(side="left")
        self._entry(rw2, self.var_hotkey, width=16).pack(side="left", padx=8)
        tk.Label(rw2, text="(e.g. Alt+Space, Ctrl+Shift+H)", fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")

        rw3 = self._row(sec_w)
        self._check(rw3, "Adaptive DPI/1080p Width (never overlaps Start)", self.var_adaptive).pack(side="left", padx=(0, 14))
        self._check(rw3, "Start11 Center Weather/Clock Overlay", self.var_center).pack(side="left")

        rw4 = self._row(sec_w)
        tk.Label(rw4, text="Wing Widths (px):", fg=FG_MAIN, bg=BG_CARD, width=16, anchor="w").pack(side="left")
        tk.Label(rw4, text="Left:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rw4, from_=300, to=560, increment=8, textvariable=self.var_lw, width=6, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=(4, 16))
        tk.Label(rw4, text="Right:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rw4, from_=300, to=560, increment=8, textvariable=self.var_rw, width=6, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=4)

    def _pick_accent(self) -> None:
        _, hex_col = colorchooser.askcolor(color=self.var_accent_hex.get(), parent=self.win)
        if hex_col:
            self.var_win_accent.set(False)
            self.var_accent_hex.set(hex_col.upper())

    def _apply_preset(self, name: str) -> None:
        preset = LAYOUT_PRESETS.get(name)
        if not preset:
            return
        self.left_order = list(preset["left_widgets"])
        self.right_order = list(preset["right_widgets"])
        for wkey, state in preset["enabled"].items():
            if wkey in self.draft["widgets"]:
                self.draft["widgets"][wkey]["enabled"] = state
        # Ensure all known widgets exist in one of the lists
        present = set(self.left_order) | set(self.right_order)
        for wid in ALL_WIDGET_IDS:
            if wid not in present:
                self.right_order.append(wid)
        self._sync_widget_vars_from_draft()
        self._rebuild_widget_columns()
        self.status_var.set(f"Applied '{name}' preset — click Apply & Save to activate")

    # ------------------------------------------------------------------
    # Tab 2: Widgets & Layout Customizer
    # ------------------------------------------------------------------

    def _build_widgets_tab(self) -> None:
        info = tk.Label(
            self.tab_widgets,
            text="Enable, disable, reorder (↑ ↓), or move any widget between Left and Right wings (← →).",
            fg=FG_MUTED,
            bg=BG_MAIN,
            font=("Segoe UI", 9),
        )
        info.pack(anchor="w", padx=10, pady=(8, 4))

        self.left_order: List[str] = [
            ("tasks" if w == "todoist" else w) for w in self.draft["layout"]["left_widgets"]
        ]
        self.right_order: List[str] = [
            ("tasks" if w == "todoist" else w) for w in self.draft["layout"]["right_widgets"]
        ]
        # Deduplicate and append any newly added widgets so every widget is configurable in UI
        seen = set()
        clean_l, clean_r = [], []
        for w in self.left_order:
            if w in WIDGET_META and w not in seen:
                clean_l.append(w)
                seen.add(w)
        for w in self.right_order:
            if w in WIDGET_META and w not in seen:
                clean_r.append(w)
                seen.add(w)
        for w in ALL_WIDGET_IDS:
            if w in WIDGET_META and w not in seen:
                clean_r.append(w)
                seen.add(w)
        self.left_order, self.right_order = clean_l, clean_r

        self.widget_enabled_vars: Dict[str, tk.BooleanVar] = {}
        self._sync_widget_vars_from_draft()

        cols = tk.Frame(self.tab_widgets, bg=BG_MAIN)
        cols.pack(fill="both", expand=True, padx=8, pady=4)
        self.left_col_frame = tk.Frame(cols, bg=BG_CARD, padx=10, pady=8)
        self.left_col_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.right_col_frame = tk.Frame(cols, bg=BG_CARD, padx=10, pady=8)
        self.right_col_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self._rebuild_widget_columns()

    def _sync_widget_vars_from_draft(self) -> None:
        widgets = self.draft["widgets"]
        for wid, (_title, _tier, cfg_key) in WIDGET_META.items():
            val = bool(widgets.get(cfg_key, {}).get("enabled", False))
            if wid in self.widget_enabled_vars:
                self.widget_enabled_vars[wid].set(val)
            else:
                self.widget_enabled_vars[wid] = tk.BooleanVar(value=val)

    def _rebuild_widget_columns(self) -> None:
        for frame, title, side, order in (
            (self.left_col_frame, "Left Wing", "left", self.left_order),
            (self.right_col_frame, "Right Wing", "right", self.right_order),
        ):
            for child in frame.winfo_children():
                child.destroy()
            tk.Label(frame, text=title, font=("Segoe UI", 11, "bold"), fg=ACCENT_HEX, bg=BG_CARD).pack(anchor="w", pady=(0, 6))
            for idx, wid in enumerate(order):
                label, tier, _ = WIDGET_META[wid]
                row = tk.Frame(frame, bg=BG_INPUT, padx=6, pady=4)
                row.pack(fill="x", pady=2)
                tk.Checkbutton(
                    row,
                    text=label,
                    variable=self.widget_enabled_vars[wid],
                    bg=BG_INPUT,
                    fg=FG_MAIN,
                    selectcolor=BG_CARD,
                    activebackground=BG_INPUT,
                    activeforeground=FG_MAIN,
                    font=("Segoe UI", 9, "bold"),
                ).pack(side="left")
                tk.Label(
                    row,
                    text=tier,
                    fg="#4ADE80" if tier == "Tier 1" else "#F59E0B",
                    bg=BG_INPUT,
                    font=("Segoe UI", 8, "bold"),
                ).pack(side="left", padx=4)
                move_arrow = "→" if side == "left" else "←"
                tk.Button(
                    row, text=move_arrow, width=2, bg=BG_CARD, fg=ACCENT_HEX, relief="flat",
                    command=lambda s=side, w=wid: self._move_widget_side(s, w),
                ).pack(side="right", padx=1)
                tk.Button(
                    row, text="↓", width=2, bg=BG_CARD, fg=FG_MAIN, relief="flat",
                    command=lambda s=side, i=idx: self._move_widget_order(s, i, 1),
                ).pack(side="right", padx=1)
                tk.Button(
                    row, text="↑", width=2, bg=BG_CARD, fg=FG_MAIN, relief="flat",
                    command=lambda s=side, i=idx: self._move_widget_order(s, i, -1),
                ).pack(side="right", padx=1)

    def _move_widget_order(self, side: str, idx: int, delta: int) -> None:
        lst = self.left_order if side == "left" else self.right_order
        nxt = idx + delta
        if 0 <= nxt < len(lst):
            lst[idx], lst[nxt] = lst[nxt], lst[idx]
            self._rebuild_widget_columns()

    def _move_widget_side(self, side: str, wid: str) -> None:
        src = self.left_order if side == "left" else self.right_order
        dst = self.right_order if side == "left" else self.left_order
        if wid in src:
            src.remove(wid)
            dst.append(wid)
            self._rebuild_widget_columns()

    # ------------------------------------------------------------------
    # Tab 3: Weather & Peripherals
    # ------------------------------------------------------------------

    def _build_weather_tab(self) -> None:
        w = self.draft["widgets"]["weather"]
        p = self.draft["widgets"]["peripherals"]
        f = self.draft["widgets"]["focus_timer"]

        sec_w = self._section(self.tab_weather, "Weather (Free Open-Meteo — Zero API Keys)")
        self.var_city = tk.StringVar(value=str(w.get("city", "Kyiv")))
        self.var_lat = tk.StringVar(value="" if w.get("latitude") is None else str(w.get("latitude")))
        self.var_lon = tk.StringVar(value="" if w.get("longitude") is None else str(w.get("longitude")))
        self.var_units = tk.StringVar(value=str(w.get("units", "metric")))
        sc = w.get("show_card", "auto")
        self.var_wcard = tk.StringVar(value="auto" if sc == "auto" else ("always" if sc else "hidden"))

        r1 = self._row(sec_w)
        tk.Label(r1, text="City:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        self._entry(r1, self.var_city, width=22).pack(side="left", padx=(0, 8))
        tk.Button(
            r1, text="Search City", bg="#2563EB", fg="white", relief="flat", padx=12, command=self._search_city
        ).pack(side="left", padx=(0, 10))
        self.city_status = tk.StringVar(value="")
        tk.Label(r1, textvariable=self.city_status, fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")

        r2 = self._row(sec_w)
        tk.Label(r2, text="Coordinates:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        tk.Label(r2, text="Lat:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(r2, self.var_lat, width=10).pack(side="left", padx=(4, 12))
        tk.Label(r2, text="Lon:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(r2, self.var_lon, width=10).pack(side="left", padx=(4, 18))
        tk.Label(r2, text="Units:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        ttk.Combobox(r2, textvariable=self.var_units, values=("metric", "imperial"), width=9, state="readonly").pack(side="left", padx=4)

        r3 = self._row(sec_w)
        tk.Label(r3, text="Wing Weather Card:", fg=FG_MAIN, bg=BG_CARD, width=18, anchor="w").pack(side="left")
        ttk.Combobox(r3, textvariable=self.var_wcard, values=("auto", "always", "hidden"), width=10, state="readonly").pack(side="left", padx=4)
        tk.Label(r3, text="auto hides wing duplicate when Start11 center overlay is active", fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=8)

        sec_p = self._section(self.tab_weather, "Peripherals & Bluetooth Batteries")
        self.var_p_mouse = tk.BooleanVar(value=bool(p.get("show_mouse", True)))
        self.var_p_kb = tk.BooleanVar(value=bool(p.get("show_keyboard", True)))
        self.var_p_gp = tk.BooleanVar(value=bool(p.get("show_gamepad", True)))
        self.var_p_hh = tk.BooleanVar(value=bool(p.get("show_handheld", False)))
        self.var_p_bt = tk.BooleanVar(value=bool(p.get("show_bluetooth", True)))
        self.var_p_autohide = tk.BooleanVar(value=bool(p.get("auto_hide_offline", False)))
        self.var_p_dsx = tk.BooleanVar(value=bool(p.get("dsx_udp_enabled", False)))

        rp1 = self._row(sec_p)
        for lbl, var in (("Mouse", self.var_p_mouse), ("Keyboard", self.var_p_kb), ("Gamepad (Xbox/DualSense)", self.var_p_gp), ("Bluetooth", self.var_p_bt)):
            self._check(rp1, lbl, var).pack(side="left", padx=(0, 12))
        rp2 = self._row(sec_p)
        self._check(rp2, "Auto-hide offline device tiles", self.var_p_autohide).pack(side="left", padx=(0, 14))
        self._check(rp2, "Handheld JSON slot", self.var_p_hh).pack(side="left", padx=(0, 14))
        self._check(rp2, "DualSense DSX UDP", self.var_p_dsx).pack(side="left")

        sec_f = self._section(self.tab_weather, "Focus / Pomodoro Timer")
        self.var_f_work = tk.IntVar(value=int(f.get("work_minutes", 25)))
        self.var_f_break = tk.IntVar(value=int(f.get("break_minutes", 5)))
        self.var_f_sound = tk.BooleanVar(value=bool(f.get("sound_on_done", True)))
        rf = self._row(sec_f)
        tk.Label(rf, text="Work (min):", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rf, from_=1, to=180, textvariable=self.var_f_work, width=5, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=(4, 16))
        tk.Label(rf, text="Break (min):", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rf, from_=1, to=60, textvariable=self.var_f_break, width=5, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=(4, 16))
        self._check(rf, "Play chime on completion", self.var_f_sound).pack(side="left")

    def _search_city(self) -> None:
        query = self.var_city.get().strip()
        if not query:
            return
        self.city_status.set("Searching...")

        def _worker():
            matches = geocode_city(query, count=1, language=self.var_lang.get())
            def _done():
                if not self.win.winfo_exists():
                    return
                if matches:
                    m = matches[0]
                    self.var_city.set(m["name"])
                    self.var_lat.set(str(m["latitude"]))
                    self.var_lon.set(str(m["longitude"]))
                    self.city_status.set(f"Found: {m['display']}")
                else:
                    self.city_status.set("City not found (check spelling / network)")
            self.win.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Tab 4: Integrations (Tier 2)
    # ------------------------------------------------------------------

    def _build_integrations_tab(self) -> None:
        widgets = self.draft["widgets"]
        hue = widgets["philips_hue"]
        td = widgets["todoist"]
        tasks = widgets["tasks"]
        ef = widgets["ecoflow"]
        ph = widgets["phone_adb"]

        # Philips Hue with 1-click Discovery & Pair
        sec_h = self._section(self.tab_integrations, "Philips Hue (Local LAN HTTPS)")
        self.var_hue_ip = tk.StringVar(value=str(hue.get("bridge_ip", "")))
        self.var_hue_key = tk.StringVar(value=str(hue.get("app_key", "")))
        self.hue_status = tk.StringVar(value="")

        rh1 = self._row(sec_h)
        tk.Label(rh1, text="Bridge IP:", fg=FG_MAIN, bg=BG_CARD, width=12, anchor="w").pack(side="left")
        self._entry(rh1, self.var_hue_ip, width=16).pack(side="left", padx=(0, 6))
        tk.Button(rh1, text="Find Bridge", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=self._hue_discover).pack(side="left", padx=3)
        tk.Button(rh1, text="Press Link & Pair", bg="#2563EB", fg="white", relief="flat", padx=8, command=self._hue_pair).pack(side="left", padx=3)
        tk.Button(rh1, text="Load Rooms", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=self._hue_load_rooms).pack(side="left", padx=3)

        rh2 = self._row(sec_h)
        tk.Label(rh2, text="App Key:", fg=FG_MAIN, bg=BG_CARD, width=12, anchor="w").pack(side="left")
        self._entry(rh2, self.var_hue_key, width=30).pack(side="left", padx=(0, 8))
        tk.Label(rh2, textvariable=self.hue_status, fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")

        # Tasks & Todoist
        sec_t = self._section(self.tab_integrations, "Tasks & Todoist")
        self.var_task_mode = tk.StringVar(value=str(tasks.get("mode", "auto")))
        self.var_td_token = tk.StringVar(value=str(td.get("api_token", "")))
        rt = self._row(sec_t)
        tk.Label(rt, text="Backend:", fg=FG_MAIN, bg=BG_CARD, width=12, anchor="w").pack(side="left")
        ttk.Combobox(rt, textvariable=self.var_task_mode, values=("auto", "local", "todoist"), width=10, state="readonly").pack(side="left", padx=(0, 12))
        tk.Label(rt, text="Todoist Token:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(0, 6))
        self._entry(rt, self.var_td_token, width=30).pack(side="left")

        # EcoFlow
        sec_e = self._section(self.tab_integrations, "EcoFlow DELTA 3 / DELTA 2 (MQTT or State File)")
        self.var_ef_mode = tk.StringVar(value=str(ef.get("mode", "mqtt")))
        self.var_ef_region = tk.StringVar(value=str(ef.get("region", "europe")))
        self.var_ef_name = tk.StringVar(value=str(ef.get("device_name", "EcoFlow Station")))
        self.var_ef_email = tk.StringVar(value=str(ef.get("email", "")))
        self.var_ef_pass = tk.StringVar(value=str(ef.get("password", "")))
        self.var_ef_sn = tk.StringVar(value=str(ef.get("device_sn", "")))

        re1 = self._row(sec_e)
        tk.Label(re1, text="Mode:", fg=FG_MAIN, bg=BG_CARD, width=10, anchor="w").pack(side="left")
        ttk.Combobox(re1, textvariable=self.var_ef_mode, values=("mqtt", "state_file"), width=10, state="readonly").pack(side="left", padx=(0, 10))
        tk.Label(re1, text="Region:", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        ttk.Combobox(re1, textvariable=self.var_ef_region, values=("europe", "us"), width=8, state="readonly").pack(side="left", padx=(4, 10))
        tk.Label(re1, text="Name:", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        self._entry(re1, self.var_ef_name, width=18).pack(side="left", padx=4)

        re2 = self._row(sec_e)
        tk.Label(re2, text="Email:", fg=FG_MAIN, bg=BG_CARD, width=10, anchor="w").pack(side="left")
        self._entry(re2, self.var_ef_email, width=20).pack(side="left", padx=(0, 8))
        tk.Label(re2, text="Password:", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        self._entry(re2, self.var_ef_pass, width=16).pack(side="left", padx=(4, 8))
        tk.Label(re2, text="SN (opt):", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        self._entry(re2, self.var_ef_sn, width=14).pack(side="left", padx=4)

        # Android ADB
        sec_a = self._section(self.tab_integrations, "Android Phone Hub (ADB + scrcpy)")
        self.var_ph_name = tk.StringVar(value=str(ph.get("device_name", "Android Phone")))
        self.var_ph_wifi = tk.StringVar(value=str(ph.get("wifi_address", "")))
        self.var_ph_sms = tk.BooleanVar(value=bool(ph.get("enable_sms_otp", False)))
        ra = self._row(sec_a)
        tk.Label(ra, text="Phone Name:", fg=FG_MAIN, bg=BG_CARD, width=12, anchor="w").pack(side="left")
        self._entry(ra, self.var_ph_name, width=18).pack(side="left", padx=(0, 10))
        tk.Label(ra, text="Wi-Fi ADB:", fg=FG_MAIN, bg=BG_CARD).pack(side="left")
        self._entry(ra, self.var_ph_wifi, width=18).pack(side="left", padx=(4, 10))
        self._check(ra, "SMS / 2FA Bar", self.var_ph_sms).pack(side="left")

    def _hue_discover(self) -> None:
        self.hue_status.set("Discovering...")

        def _worker():
            ips = discover_hue_bridges()
            def _done():
                if not self.win.winfo_exists():
                    return
                if ips:
                    self.var_hue_ip.set(ips[0])
                    self.hue_status.set(f"Found bridge: {ips[0]}")
                else:
                    self.hue_status.set("No bridge found automatically; enter LAN IP")
            self.win.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _hue_pair(self) -> None:
        ip = self.var_hue_ip.get().strip()
        if not ip:
            self.hue_status.set("Enter Bridge IP first")
            return
        self.hue_status.set("Pairing (press Bridge Link button first)...")

        def _worker():
            ok, res = pair_hue_bridge(ip)
            def _done():
                if not self.win.winfo_exists():
                    return
                if ok:
                    self.var_hue_key.set(res)
                    self.widget_enabled_vars["philips_hue"].set(True)
                    self.hue_status.set("Paired! Click Load Rooms or Apply.")
                else:
                    self.hue_status.set(res)
            self.win.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _hue_load_rooms(self) -> None:
        ip = self.var_hue_ip.get().strip()
        key = self.var_hue_key.get().strip()
        if not ip or not key:
            self.hue_status.set("Need Bridge IP and App Key")
            return
        self.hue_status.set("Loading rooms & lights...")

        def _worker():
            cat = fetch_hue_catalog(ip, key)
            def _done():
                if not self.win.winfo_exists():
                    return
                if cat:
                    self.draft["widgets"]["philips_hue"]["targets"] = cat[:2]
                    self.hue_status.set(f"Loaded {len(cat)} items (selected top {min(2, len(cat))})")
                else:
                    self.hue_status.set("No rooms/lights returned")
            self.win.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Tab 5: Diagnostics (--doctor)
    # ------------------------------------------------------------------

    def _build_doctor_tab(self) -> None:
        top = tk.Frame(self.tab_doctor, bg=BG_MAIN)
        top.pack(fill="x", padx=8, pady=8)
        tk.Button(top, text="Refresh", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=12, command=self._refresh_doctor).pack(side="left", padx=(0, 6))
        tk.Button(top, text="Copy Report for GitHub Issue", bg="#2563EB", fg="white", relief="flat", padx=12, command=self._copy_doctor).pack(side="left")

        self.doctor_txt = tk.Text(
            self.tab_doctor,
            bg=BG_CARD,
            fg=FG_MAIN,
            font=("Consolas", 10),
            relief="flat",
            padx=12,
            pady=10,
        )
        self.doctor_txt.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._refresh_doctor()

    def _refresh_doctor(self) -> None:
        self.doctor_txt.configure(state="normal")
        self.doctor_txt.delete("1.0", "end")
        self.doctor_txt.insert("1.0", "Running diagnostics...")
        self.doctor_txt.configure(state="disabled")

        def _worker():
            text = format_diagnostics(run_diagnostics(self.config_path))
            def _done():
                if not self.win.winfo_exists():
                    return
                self.doctor_txt.configure(state="normal")
                self.doctor_txt.delete("1.0", "end")
                self.doctor_txt.insert("1.0", text)
                self.doctor_txt.configure(state="disabled")
            self.win.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _copy_doctor(self) -> None:
        txt = self.doctor_txt.get("1.0", "end").strip()
        if copy_text_to_clipboard(txt):
            self.status_var.set("Sanitized diagnostics copied to clipboard")
        else:
            self.win.clipboard_clear()
            self.win.clipboard_append(txt)
            self.status_var.set("Diagnostics copied to clipboard")

    # ------------------------------------------------------------------
    # Save / Reset / Open
    # ------------------------------------------------------------------

    def _collect_patch(self) -> Dict[str, Any]:
        sc_map = {"auto": "auto", "always": True, "hidden": False}
        lat_s = self.var_lat.get().strip()
        lon_s = self.var_lon.get().strip()
        try:
            lat_v: Optional[float] = float(lat_s) if lat_s else None
        except ValueError:
            lat_v = None
        try:
            lon_v: Optional[float] = float(lon_s) if lon_s else None
        except ValueError:
            lon_v = None

        w_patch: Dict[str, Any] = {}
        for wid, (_title, _tier, cfg_key) in WIDGET_META.items():
            w_patch.setdefault(cfg_key, {})["enabled"] = bool(self.widget_enabled_vars[wid].get())

        w_patch["weather"].update(
            {
                "city": self.var_city.get().strip() or "Kyiv",
                "latitude": lat_v,
                "longitude": lon_v,
                "units": self.var_units.get(),
                "show_card": sc_map.get(self.var_wcard.get(), "auto"),
            }
        )
        w_patch["peripherals"].update(
            {
                "show_mouse": bool(self.var_p_mouse.get()),
                "show_keyboard": bool(self.var_p_kb.get()),
                "show_gamepad": bool(self.var_p_gp.get()),
                "show_handheld": bool(self.var_p_hh.get()),
                "show_bluetooth": bool(self.var_p_bt.get()),
                "auto_hide_offline": bool(self.var_p_autohide.get()),
                "dsx_udp_enabled": bool(self.var_p_dsx.get()),
            }
        )
        w_patch["focus_timer"].update(
            {
                "work_minutes": int(self.var_f_work.get()),
                "break_minutes": int(self.var_f_break.get()),
                "sound_on_done": bool(self.var_f_sound.get()),
            }
        )
        w_patch["philips_hue"].update(
            {
                "bridge_ip": self.var_hue_ip.get().strip(),
                "app_key": self.var_hue_key.get().strip(),
                "targets": self.draft["widgets"]["philips_hue"].get("targets", []),
            }
        )
        w_patch["tasks"]["mode"] = self.var_task_mode.get()
        w_patch["todoist"] = {
            "enabled": self.var_task_mode.get() == "todoist" or bool(self.var_td_token.get().strip()),
            "api_token": self.var_td_token.get().strip(),
        }
        w_patch["ecoflow"].update(
            {
                "mode": self.var_ef_mode.get(),
                "region": self.var_ef_region.get(),
                "device_name": self.var_ef_name.get().strip() or "EcoFlow Station",
                "email": self.var_ef_email.get().strip(),
                "password": self.var_ef_pass.get().strip(),
                "device_sn": self.var_ef_sn.get().strip(),
            }
        )
        w_patch["phone_adb"].update(
            {
                "device_name": self.var_ph_name.get().strip() or "Android Phone",
                "wifi_address": self.var_ph_wifi.get().strip(),
                "enable_sms_otp": bool(self.var_ph_sms.get()),
            }
        )

        return {
            "language": self.var_lang.get(),
            "theme": {
                "mode": self.var_theme_mode.get(),
                "accent_color": "windows" if self.var_win_accent.get() else self.var_accent_hex.get().strip(),
                "panel_alpha": int(self.var_alpha.get()),
                "blur": bool(self.var_blur.get()),
                "corner_radius": int(self.var_radius.get()),
            },
            "window": {
                "trigger_mode": self.var_trigger.get(),
                "hotkey_enabled": bool(self.var_hk_en.get()),
                "hotkey": self.var_hotkey.get().strip() or "Alt+Space",
                "adaptive_width": bool(self.var_adaptive.get()),
                "center_overlay": bool(self.var_center.get()),
                "fade_animation": bool(self.var_fade.get()),
                "left_width": int(self.var_lw.get()),
                "right_width": int(self.var_rw.get()),
            },
            "layout": {
                "left_widgets": list(self.left_order),
                "right_widgets": list(self.right_order),
            },
            "widgets": w_patch,
        }

    def _save_and_apply(self) -> None:
        patch = self._collect_patch()
        if save_config_patch(self.config_path, patch):
            self.status_var.set("Saved to config.json and reloaded live!")
            try:
                self.on_apply()
            except Exception:
                pass
        else:
            self.status_var.set("Could not write config.json")

    def _reset_defaults(self) -> None:
        self.draft = copy.deepcopy(DEFAULT_CONFIG)
        self._apply_preset("balanced")
        self.var_theme_mode.set("multi_accent")
        self.var_win_accent.set(False)
        self.var_accent_hex.set("#58BCFF")
        self.var_alpha.set(180)
        self.var_radius.set(14)
        self.var_blur.set(True)
        self.var_fade.set(True)
        self.var_trigger.set("auto")
        self.status_var.set("Defaults restored — click Apply & Save to persist")

    def _open_raw_config(self) -> None:
        if not self.config_path.is_file():
            save_config_patch(self.config_path, {})
        if IS_WINDOWS and self.config_path.is_file():
            os.startfile(str(self.config_path))
