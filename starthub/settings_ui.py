"""Full-featured dark GUI Settings & Customizer for StartHub (zero raw JSON editing required).

Lets users customize:
- 6 visual theme presets (Fluent Dark/Light, AMOLED, Catppuccin Mocha, Nord, Tokyo Night)
- Custom surface colors (panel, tile, border, text) + per-widget accent role overrides
- Export / Import shareable theme & layout profiles (zero secrets)
- Drag-free Left/Right wing widget toggling, reordering, and clearing
- Full Quick Actions button builder and Custom JSON card builder
- City geocoding search, 1-click Philips Hue discovery/pairing/room picker, and update checks
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, ttk
from typing import Any, Callable, Dict, List, Optional
import webbrowser

from . import __version__
from .config import (
    ALL_WIDGET_IDS,
    DEFAULT_CONFIG,
    LAYOUT_PRESETS,
    REPO_ROOT,
    deep_merge,
    export_profile_data,
    load_raw_user_config,
    migrate_config,
    save_config_patch,
)
from .doctor import format_diagnostics, run_diagnostics
from .providers.hue import discover_hue_bridges, fetch_hue_catalog, pair_hue_bridge
from .providers.weather import geocode_city
from .surface import IS_WINDOWS, copy_text_to_clipboard
from .theme import MULTI_ACCENT_ROLES, THEME_PRESETS
from .updater import RELEASES_PAGE_URL, check_for_updates

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

EDITABLE_ROLE_KEYS = (
    "primary",
    "audio",
    "media",
    "monitor_normal",
    "storage",
    "focus_work",
    "quick_actions",
    "hue",
    "todoist",
    "ecoflow_soc",
    "weather",
    "calendar",
    "custom_0",
)

ACCENT_SWATCHES = ("#58BCFF", "#4ADE80", "#A78BFA", "#F97316", "#F43F5E", "#38BDF8")

BG_MAIN = "#12151C"
BG_CARD = "#1B1F2A"
BG_INPUT = "#252B39"
FG_MAIN = "#F1F5F9"
FG_MUTED = "#94A3B8"
ACCENT_HEX = "#58BCFF"


class SettingsWindow:
    """Tabbed dark GUI settings modal with complete widget, color, action, and integration editors."""

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

        raw_user = migrate_config(load_raw_user_config(self.config_path))
        self.draft: Dict[str, Any] = deep_merge(DEFAULT_CONFIG, raw_user)
        self._role_overrides: Dict[str, str] = dict(self.draft["theme"].get("role_overrides") or {})
        self._qa_items: List[Dict[str, Any]] = [
            dict(it) for it in (self.draft["widgets"]["quick_actions"].get("items") or []) if isinstance(it, dict)
        ]
        self._custom_cards: List[Dict[str, Any]] = [
            dict(c) for c in (self.draft["widgets"]["custom_json"].get("cards") or []) if isinstance(c, dict)
        ]
        self._hue_catalog: List[Dict[str, Any]] = []
        self._hue_selected_vars: List[tuple[Dict[str, Any], tk.BooleanVar]] = []

        self.win = tk.Toplevel(parent)
        self.win.title(f"StartHub Settings — v{__version__}")
        self.win.configure(bg=BG_MAIN)
        self.win.geometry("880x700")
        self.win.minsize(800, 610)
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
            padding=(12, 8),
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_INPUT)],
            foreground=[("selected", FG_MAIN)],
        )

    def _scrollable_tab(self, parent: tk.Misc) -> tk.Frame:
        canvas = tk.Canvas(parent, bg=BG_MAIN, highlightthickness=0)
        sb = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG_MAIN)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return inner

    def _build_ui(self) -> None:
        hdr = tk.Frame(self.win, bg=BG_CARD, height=52)
        hdr.pack(fill="x", side="top")
        tk.Label(hdr, text="StartHub Customizer & Settings", font=("Segoe UI", 13, "bold"), fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=16, pady=12)
        self.status_var = tk.StringVar(value="All changes apply live — ${ENV_VAR} secrets stay untouched")
        tk.Label(hdr, textvariable=self.status_var, font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_CARD).pack(side="right", padx=16)

        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(10, 6))

        t1 = tk.Frame(self.nb, bg=BG_MAIN)
        t2 = tk.Frame(self.nb, bg=BG_MAIN)
        t3 = tk.Frame(self.nb, bg=BG_MAIN)
        t4 = tk.Frame(self.nb, bg=BG_MAIN)
        t5 = tk.Frame(self.nb, bg=BG_MAIN)
        t6 = tk.Frame(self.nb, bg=BG_MAIN)

        self.nb.add(t1, text="Themes & Triggers")
        self.nb.add(t2, text="Widgets & Layout")
        self.nb.add(t3, text="Custom Cards & Actions")
        self.nb.add(t4, text="Weather & Peripherals")
        self.nb.add(t5, text="Integrations (Tier 2)")
        self.nb.add(t6, text="Diagnostics & Updates")

        self.tab_appearance = self._scrollable_tab(t1)
        self.tab_widgets = t2
        self.tab_custom = self._scrollable_tab(t3)
        self.tab_weather = self._scrollable_tab(t4)
        self.tab_integrations = self._scrollable_tab(t5)
        self.tab_doctor = t6

        self._build_appearance_tab()
        self._build_widgets_tab()
        self._build_custom_tab()
        self._build_weather_tab()
        self._build_integrations_tab()
        self._build_doctor_tab()

        # Bottom action bar
        bar = tk.Frame(self.win, bg=BG_CARD, height=52)
        bar.pack(fill="x", side="bottom")
        tk.Button(bar, text="Reset Defaults", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=12, pady=6, font=("Segoe UI", 9, "bold"), command=self._reset_defaults).pack(side="left", padx=(12, 4), pady=10)
        tk.Button(bar, text="Export Profile...", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=10, pady=6, font=("Segoe UI", 9), command=self._export_profile).pack(side="left", padx=4, pady=10)
        tk.Button(bar, text="Import Profile...", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=10, pady=6, font=("Segoe UI", 9), command=self._import_profile).pack(side="left", padx=4, pady=10)
        tk.Button(bar, text="Open config.json", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=10, pady=6, font=("Segoe UI", 9), command=self._open_raw_config).pack(side="left", padx=4, pady=10)

        tk.Button(bar, text="Close", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=14, pady=6, font=("Segoe UI", 9, "bold"), command=self.win.destroy).pack(side="right", padx=(4, 12), pady=10)
        tk.Button(bar, text="Apply & Save", bg="#2563EB", fg="#FFFFFF", relief="flat", padx=20, pady=6, font=("Segoe UI", 10, "bold"), command=self._save_and_apply).pack(side="right", padx=6, pady=10)

    def _section(self, parent: tk.Misc, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BG_CARD, padx=14, pady=10)
        outer.pack(fill="x", padx=8, pady=5)
        tk.Label(outer, text=title, font=("Segoe UI", 10, "bold"), fg=ACCENT_HEX, bg=BG_CARD).pack(anchor="w", pady=(0, 6))
        return outer

    def _row(self, parent: tk.Misc) -> tk.Frame:
        r = tk.Frame(parent, bg=BG_CARD)
        r.pack(fill="x", pady=3)
        return r

    def _entry(self, parent: tk.Misc, var: tk.Variable, width: int = 20, show: str = "") -> tk.Entry:
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
            font=("Segoe UI", 9),
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
            font=("Segoe UI", 9),
        )

    # ------------------------------------------------------------------
    # Tab 1: Themes, Custom Colors & Triggers
    # ------------------------------------------------------------------

    def _build_appearance_tab(self) -> None:
        t = self.draft["theme"]
        w = self.draft["window"]
        cc = t.get("custom_colors") if isinstance(t.get("custom_colors"), dict) else {}

        # Theme Presets & Color Mode
        sec_t = self._section(self.tab_appearance, "Theme Preset, Accent & Surface Colors")
        self.var_preset = tk.StringVar(value=str(t.get("preset", "fluent_dark")))
        self.var_lang = tk.StringVar(value=str(self.draft.get("language", "en")))
        self.var_theme_mode = tk.StringVar(value=str(t.get("mode", "multi_accent")))
        raw_acc = str(t.get("accent_color", "#58BCFF"))
        self.var_win_accent = tk.BooleanVar(value=raw_acc.lower() == "windows")
        self.var_accent_hex = tk.StringVar(value="#58BCFF" if raw_acc.lower() == "windows" else raw_acc)
        self.var_alpha = tk.IntVar(value=int(t.get("panel_alpha", 180)))
        self.var_radius = tk.IntVar(value=int(t.get("corner_radius", 14)))
        self.var_blur = tk.BooleanVar(value=bool(t.get("blur", True)))
        self.var_fade = tk.BooleanVar(value=bool(w.get("fade_animation", True)))

        r0 = self._row(sec_t)
        tk.Label(r0, text="Theme Preset:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        ttk.Combobox(r0, textvariable=self.var_preset, values=tuple(THEME_PRESETS.keys()), width=18, state="readonly").pack(side="left", padx=(0, 14))
        tk.Label(r0, text="Color Style:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(0, 6))
        for val, lbl in (("multi_accent", "Multi-Accent"), ("single_accent", "Single-Accent")):
            tk.Radiobutton(
                r0, text=lbl, value=val, variable=self.var_theme_mode,
                bg=BG_CARD, fg=FG_MAIN, selectcolor=BG_INPUT, activebackground=BG_CARD, activeforeground=FG_MAIN,
            ).pack(side="left", padx=4)
        tk.Label(r0, text="Lang:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(14, 4))
        ttk.Combobox(r0, textvariable=self.var_lang, values=("en", "ru", "uk"), width=5, state="readonly").pack(side="left")

        r2 = self._row(sec_t)
        tk.Label(r2, text="Accent Color:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        self._entry(r2, self.var_accent_hex, width=10).pack(side="left", padx=(0, 6))
        tk.Button(r2, text="Pick...", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=lambda: self._pick_into(self.var_accent_hex, clear_win=True)).pack(side="left", padx=(0, 8))
        for sw in ACCENT_SWATCHES:
            tk.Button(r2, bg=sw, width=2, relief="flat", command=lambda c=sw: (self.var_win_accent.set(False), self.var_accent_hex.set(c))).pack(side="left", padx=2)
        self._check(r2, "Sync Windows Accent", self.var_win_accent).pack(side="left", padx=10)

        r3 = self._row(sec_t)
        tk.Label(r3, text="Panel Opacity:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        tk.Scale(r3, from_=80, to=255, orient="horizontal", variable=self.var_alpha, bg=BG_CARD, fg=FG_MAIN, highlightthickness=0, troughcolor=BG_INPUT, length=160).pack(side="left", padx=(0, 14))
        tk.Label(r3, text="Radius:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(4, 4))
        tk.Scale(r3, from_=0, to=24, orient="horizontal", variable=self.var_radius, bg=BG_CARD, fg=FG_MAIN, highlightthickness=0, troughcolor=BG_INPUT, length=110).pack(side="left", padx=(0, 10))
        self._check(r3, "Acrylic Blur", self.var_blur).pack(side="left", padx=6)
        self._check(r3, "120ms Fade", self.var_fade).pack(side="left", padx=6)

        # Custom Surface & Per-Widget Role Colors
        sec_c = self._section(self.tab_appearance, "Custom Surface & Per-Widget Colors (Optional Overrides)")
        self.var_cc_panel = tk.StringVar(value=str(cc.get("panel_bg", "")))
        self.var_cc_tile = tk.StringVar(value=str(cc.get("tile_bg", "")))
        self.var_cc_border = tk.StringVar(value=str(cc.get("border", "")))
        self.var_cc_text = tk.StringVar(value=str(cc.get("text_primary", "")))
        self.var_cc_text2 = tk.StringVar(value=str(cc.get("text_secondary", "")))

        rc1 = self._row(sec_c)
        for lbl, var in (("Panel BG:", self.var_cc_panel), ("Tile BG:", self.var_cc_tile), ("Border:", self.var_cc_border)):
            tk.Label(rc1, text=lbl, fg=FG_MUTED, bg=BG_CARD).pack(side="left", padx=(0, 4))
            self._entry(rc1, var, width=9).pack(side="left")
            tk.Button(rc1, text="Pick", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=5, command=lambda v=var: self._pick_into(v)).pack(side="left", padx=(2, 10))

        rc2 = self._row(sec_c)
        for lbl, var in (("Text:", self.var_cc_text), ("Subtext:", self.var_cc_text2)):
            tk.Label(rc2, text=lbl, fg=FG_MUTED, bg=BG_CARD).pack(side="left", padx=(0, 4))
            self._entry(rc2, var, width=9).pack(side="left")
            tk.Button(rc2, text="Pick", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=5, command=lambda v=var: self._pick_into(v)).pack(side="left", padx=(2, 10))
        tk.Button(rc2, text="Clear Surface Overrides", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=8, command=self._clear_surface_overrides).pack(side="right")

        rc3 = self._row(sec_c)
        tk.Label(rc3, text="Per-Widget Color:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(0, 6))
        self.var_role_pick = tk.StringVar(value=EDITABLE_ROLE_KEYS[0])
        ttk.Combobox(rc3, textvariable=self.var_role_pick, values=EDITABLE_ROLE_KEYS, width=15, state="readonly").pack(side="left", padx=(0, 6))
        tk.Button(rc3, text="Set Widget Color...", bg="#2563EB", fg="white", relief="flat", padx=8, command=self._pick_role_override).pack(side="left", padx=3)
        tk.Button(rc3, text="Reset Widget Colors", bg="#2D3343", fg=FG_MAIN, relief="flat", padx=8, command=self._clear_role_overrides).pack(side="left", padx=3)
        self.var_roles_summary = tk.StringVar(value=self._format_roles_summary())
        tk.Label(rc3, textvariable=self.var_roles_summary, fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 8)).pack(side="left", padx=8)

        # Trigger, Hotkey & Zero-Overlap Start11 Guard
        sec_w = self._section(self.tab_appearance, "Start Menu Trigger, DPI Fit & Start11 Zero-Overlap Guard")
        self.var_trigger = tk.StringVar(value=str(w.get("trigger_mode", "auto")))
        self.var_hk_en = tk.BooleanVar(value=bool(w.get("hotkey_enabled", True)))
        self.var_hotkey = tk.StringVar(value=str(w.get("hotkey", "Alt+Space")))
        self.var_adaptive = tk.BooleanVar(value=bool(w.get("adaptive_width", True)))
        self.var_center = tk.BooleanVar(value=bool(w.get("center_overlay", True)))
        self.var_center_margin = tk.IntVar(value=int(w.get("center_overlay_safety_margin", 14)))
        self.var_lw = tk.IntVar(value=int(w.get("left_width", 416)))
        self.var_rw = tk.IntVar(value=int(w.get("right_width", 430)))

        rw1 = self._row(sec_w)
        tk.Label(rw1, text="Trigger Mode:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        ttk.Combobox(rw1, textvariable=self.var_trigger, values=("auto", "start11", "windows11", "hotkey"), width=12, state="readonly").pack(side="left", padx=(0, 12))
        self._check(rw1, "Global Hotkey:", self.var_hk_en).pack(side="left")
        self._entry(rw1, self.var_hotkey, width=14).pack(side="left", padx=6)

        rw2 = self._row(sec_w)
        self._check(rw2, "Adaptive DPI/1080p Width", self.var_adaptive).pack(side="left", padx=(0, 12))
        self._check(rw2, "Start11 Center Weather/Clock (click-through, zero-overlap)", self.var_center).pack(side="left")

        rw3 = self._row(sec_w)
        tk.Label(rw3, text="Wing Widths:", fg=FG_MAIN, bg=BG_CARD, width=14, anchor="w").pack(side="left")
        tk.Label(rw3, text="Left:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rw3, from_=300, to=560, increment=8, textvariable=self.var_lw, width=5, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=(4, 12))
        tk.Label(rw3, text="Right:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rw3, from_=300, to=560, increment=8, textvariable=self.var_rw, width=5, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=(4, 18))
        tk.Label(rw3, text="Tile Safety Margin (px):", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        tk.Spinbox(rw3, from_=0, to=48, increment=2, textvariable=self.var_center_margin, width=4, bg=BG_INPUT, fg=FG_MAIN, relief="flat").pack(side="left", padx=4)

    def _pick_into(self, target_var: tk.StringVar, *, clear_win: bool = False) -> None:
        init = target_var.get().strip() or "#58BCFF"
        _, hex_col = colorchooser.askcolor(color=init, parent=self.win)
        if hex_col:
            if clear_win:
                self.var_win_accent.set(False)
            target_var.set(hex_col.upper())

    def _clear_surface_overrides(self) -> None:
        for v in (self.var_cc_panel, self.var_cc_tile, self.var_cc_border, self.var_cc_text, self.var_cc_text2):
            v.set("")
        self.status_var.set("Cleared custom surface color overrides")

    def _format_roles_summary(self) -> str:
        if not self._role_overrides:
            return "(preset defaults)"
        return f"Custom: {', '.join(f'{k}={v}' for k, v in list(self._role_overrides.items())[:3])}" + (
            f" (+{len(self._role_overrides) - 3})" if len(self._role_overrides) > 3 else ""
        )

    def _pick_role_override(self) -> None:
        key = self.var_role_pick.get()
        cur = self._role_overrides.get(key) or "#58BCFF"
        _, hex_col = colorchooser.askcolor(color=cur, parent=self.win)
        if hex_col:
            self._role_overrides[key] = hex_col.upper()
            self.var_roles_summary.set(self._format_roles_summary())

    def _clear_role_overrides(self) -> None:
        self._role_overrides.clear()
        self.var_roles_summary.set(self._format_roles_summary())

    # ------------------------------------------------------------------
    # Tab 2: Widgets & Layout Customizer
    # ------------------------------------------------------------------

    def _build_widgets_tab(self) -> None:
        top = tk.Frame(self.tab_widgets, bg=BG_MAIN)
        top.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(top, text="Layout Presets:", fg=FG_MUTED, bg=BG_MAIN, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        for key, lbl in (("balanced", "Balanced (Default)"), ("minimal", "Minimal"), ("productivity", "Productivity")):
            tk.Button(
                top, text=lbl, bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=10, pady=4, font=("Segoe UI", 9, "bold"),
                command=lambda k=key: self._apply_preset(k),
            ).pack(side="left", padx=3)

        self.left_order: List[str] = [("tasks" if w == "todoist" else w) for w in self.draft["layout"]["left_widgets"]]
        self.right_order: List[str] = [("tasks" if w == "todoist" else w) for w in self.draft["layout"]["right_widgets"]]
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

    def _apply_preset(self, name: str) -> None:
        preset = LAYOUT_PRESETS.get(name)
        if not preset:
            return
        self.left_order = list(preset["left_widgets"])
        self.right_order = list(preset["right_widgets"])
        for wkey, state in preset["enabled"].items():
            if wkey in self.draft["widgets"]:
                self.draft["widgets"][wkey]["enabled"] = state
        present = set(self.left_order) | set(self.right_order)
        for wid in ALL_WIDGET_IDS:
            if wid not in present and wid in WIDGET_META:
                self.right_order.append(wid)
        self._sync_widget_vars_from_draft()
        self._rebuild_widget_columns()
        self.status_var.set(f"Applied '{name}' layout preset — click Apply & Save")

    def _sync_widget_vars_from_draft(self) -> None:
        widgets = self.draft["widgets"]
        for wid, (_title, _tier, cfg_key) in WIDGET_META.items():
            val = bool(widgets.get(cfg_key, {}).get("enabled", False))
            if wid in self.widget_enabled_vars:
                self.widget_enabled_vars[wid].set(val)
            else:
                self.widget_enabled_vars[wid] = tk.BooleanVar(value=val)

    def _disable_wing(self, side: str) -> None:
        order = self.left_order if side == "left" else self.right_order
        for wid in order:
            self.widget_enabled_vars[wid].set(False)
        self.status_var.set(f"Disabled all widgets on {side} wing (wing will hide automatically)")

    def _rebuild_widget_columns(self) -> None:
        for frame, title, side, order in (
            (self.left_col_frame, "Left Wing", "left", self.left_order),
            (self.right_col_frame, "Right Wing", "right", self.right_order),
        ):
            for child in frame.winfo_children():
                child.destroy()
            hdr = tk.Frame(frame, bg=BG_CARD)
            hdr.pack(fill="x", pady=(0, 6))
            tk.Label(hdr, text=title, font=("Segoe UI", 10, "bold"), fg=ACCENT_HEX, bg=BG_CARD).pack(side="left")
            tk.Button(hdr, text="Disable All", bg=BG_INPUT, fg=FG_MUTED, relief="flat", padx=6, font=("Segoe UI", 8), command=lambda s=side: self._disable_wing(s)).pack(side="right")

            for idx, wid in enumerate(order):
                label, tier, _ = WIDGET_META[wid]
                row = tk.Frame(frame, bg=BG_INPUT, padx=6, pady=3)
                row.pack(fill="x", pady=2)
                tk.Checkbutton(
                    row, text=label, variable=self.widget_enabled_vars[wid],
                    bg=BG_INPUT, fg=FG_MAIN, selectcolor=BG_CARD, activebackground=BG_INPUT, activeforeground=FG_MAIN,
                    font=("Segoe UI", 9, "bold"),
                ).pack(side="left")
                tk.Label(row, text=tier, fg="#4ADE80" if tier == "Tier 1" else "#F59E0B", bg=BG_INPUT, font=("Segoe UI", 8, "bold")).pack(side="left", padx=4)
                move_arrow = "→" if side == "left" else "←"
                tk.Button(row, text=move_arrow, width=2, bg=BG_CARD, fg=ACCENT_HEX, relief="flat", command=lambda s=side, w=wid: self._move_widget_side(s, w)).pack(side="right", padx=1)
                tk.Button(row, text="↓", width=2, bg=BG_CARD, fg=FG_MAIN, relief="flat", command=lambda s=side, i=idx: self._move_widget_order(s, i, 1)).pack(side="right", padx=1)
                tk.Button(row, text="↑", width=2, bg=BG_CARD, fg=FG_MAIN, relief="flat", command=lambda s=side, i=idx: self._move_widget_order(s, i, -1)).pack(side="right", padx=1)

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
    # Tab 3: Full Quick Actions & Custom JSON Card Builders
    # ------------------------------------------------------------------

    def _build_custom_tab(self) -> None:
        # 1) Quick Actions Builder
        sec_qa = self._section(self.tab_custom, "Quick Actions Bar Builder (Up to 5 Custom Buttons)")
        self.qa_list_frame = tk.Frame(sec_qa, bg=BG_CARD)
        self.qa_list_frame.pack(fill="x", pady=(0, 6))
        self._rebuild_qa_list()

        add_qa = self._row(sec_qa)
        self.var_qa_label = tk.StringVar(value="")
        self.var_qa_icon = tk.StringVar(value="bolt")
        self.var_qa_action = tk.StringVar(value="https://github.com")
        tk.Label(add_qa, text="Label:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(add_qa, self.var_qa_label, width=11).pack(side="left", padx=(3, 8))
        tk.Label(add_qa, text="Icon:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        ttk.Combobox(add_qa, textvariable=self.var_qa_icon, values=("bolt", "camera", "terminal", "lock", "gear", "sleep", "folder"), width=9, state="readonly").pack(side="left", padx=(3, 8))
        tk.Label(add_qa, text="Action/URL/Cmd:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(add_qa, self.var_qa_action, width=26).pack(side="left", padx=(3, 8))
        tk.Button(add_qa, text="+ Add Button", bg="#2563EB", fg="white", relief="flat", padx=10, command=self._add_qa_item).pack(side="left")

        # 2) Custom JSON Cards Builder
        sec_cj = self._section(self.tab_custom, "Custom JSON Cards Builder (columns / hero / list)")
        self.var_cj_remote = tk.BooleanVar(value=bool(self.draft["widgets"]["custom_json"].get("allow_remote_urls", False)))
        rcj0 = self._row(sec_cj)
        self._check(rcj0, "Allow non-localhost HTTP/HTTPS URLs", self.var_cj_remote).pack(side="left")
        tk.Button(rcj0, text="Open examples/custom_json/", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=self._open_examples_dir).pack(side="right")

        self.cj_list_frame = tk.Frame(sec_cj, bg=BG_CARD)
        self.cj_list_frame.pack(fill="x", pady=(4, 6))
        self._rebuild_cj_list()

        add_cj = self._row(sec_cj)
        self.var_cj_title = tk.StringVar(value="")
        self.var_cj_source = tk.StringVar(value="cache/custom_homelab.json")
        self.var_cj_layout = tk.StringVar(value="columns")
        self.var_cj_url = tk.StringVar(value="")
        tk.Label(add_cj, text="Title:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(add_cj, self.var_cj_title, width=12).pack(side="left", padx=(3, 6))
        tk.Label(add_cj, text="Layout:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        ttk.Combobox(add_cj, textvariable=self.var_cj_layout, values=("columns", "hero", "list"), width=8, state="readonly").pack(side="left", padx=(3, 6))
        tk.Label(add_cj, text="Source:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(add_cj, self.var_cj_source, width=24).pack(side="left", padx=(3, 6))
        tk.Button(add_cj, text="+ Add Card", bg="#2563EB", fg="white", relief="flat", padx=10, command=self._add_cj_card).pack(side="left")

    def _rebuild_qa_list(self) -> None:
        for w in self.qa_list_frame.winfo_children():
            w.destroy()
        for idx, item in enumerate(self._qa_items):
            r = tk.Frame(self.qa_list_frame, bg=BG_INPUT, padx=8, pady=4)
            r.pack(fill="x", pady=2)
            act = item.get("action") or item.get("command") or ""
            tk.Label(r, text=f"{item.get('label', item.get('id'))}  [{item.get('icon', 'bolt')}]  →  {act}", fg=FG_MAIN, bg=BG_INPUT, font=("Segoe UI", 9)).pack(side="left")
            tk.Button(r, text="✕", width=3, bg=BG_CARD, fg="#F87171", relief="flat", command=lambda i=idx: self._del_qa_item(i)).pack(side="right", padx=2)

    def _add_qa_item(self) -> None:
        lbl = self.var_qa_label.get().strip()
        act = self.var_qa_action.get().strip()
        if not lbl or not act:
            return
        if len(self._qa_items) >= 5:
            self.status_var.set("Quick Actions bar supports up to 5 buttons — remove one first")
            return
        builtin = {"snip", "terminal", "lock", "sleep", "explorer", "starthub_settings"}
        entry: Dict[str, Any] = {
            "id": lbl.lower().replace(" ", "_")[:16],
            "label": lbl[:16],
            "icon": self.var_qa_icon.get(),
        }
        if act.lower() in builtin or act.startswith(("http://", "https://")):
            entry["action"] = act
        else:
            entry["action"] = "custom"
            entry["command"] = act
        self._qa_items.append(entry)
        self.var_qa_label.set("")
        self.widget_enabled_vars["quick_actions"].set(True)
        self._rebuild_qa_list()

    def _del_qa_item(self, idx: int) -> None:
        if 0 <= idx < len(self._qa_items):
            self._qa_items.pop(idx)
            self._rebuild_qa_list()

    def _rebuild_cj_list(self) -> None:
        for w in self.cj_list_frame.winfo_children():
            w.destroy()
        if not self._custom_cards:
            tk.Label(self.cj_list_frame, text="No custom cards yet — add one below.", fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(anchor="w")
            return
        for idx, c in enumerate(self._custom_cards):
            r = tk.Frame(self.cj_list_frame, bg=BG_INPUT, padx=8, pady=4)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=f"{c.get('title', c.get('id'))}  [{c.get('layout', 'columns')}]  →  {c.get('source', '')}", fg=FG_MAIN, bg=BG_INPUT, font=("Segoe UI", 9)).pack(side="left")
            tk.Button(r, text="✕", width=3, bg=BG_CARD, fg="#F87171", relief="flat", command=lambda i=idx: self._del_cj_card(i)).pack(side="right", padx=2)

    def _add_cj_card(self) -> None:
        title = self.var_cj_title.get().strip()
        src = self.var_cj_source.get().strip()
        if not title or not src:
            return
        cid = title.lower().replace(" ", "_")[:20]
        self._custom_cards.append(
            {
                "id": cid,
                "title": title,
                "source": src,
                "layout": self.var_cj_layout.get(),
                "refresh_sec": 15,
                "click_url": self.var_cj_url.get().strip(),
            }
        )
        self.var_cj_title.set("")
        self.widget_enabled_vars["custom_json"].set(True)
        self._rebuild_cj_list()

    def _del_cj_card(self, idx: int) -> None:
        if 0 <= idx < len(self._custom_cards):
            self._custom_cards.pop(idx)
            self._rebuild_cj_list()

    def _open_examples_dir(self) -> None:
        ex_dir = REPO_ROOT / "examples" / "custom_json"
        if IS_WINDOWS and ex_dir.is_dir():
            os.startfile(str(ex_dir))

    # ------------------------------------------------------------------
    # Tab 4: Weather & Peripherals
    # ------------------------------------------------------------------

    def _build_weather_tab(self) -> None:
        w = self.draft["widgets"]["weather"]
        p = self.draft["widgets"]["peripherals"]
        f = self.draft["widgets"]["focus_timer"]

        sec_w = self._section(self.tab_weather, "Weather (Free Open-Meteo — Search City by Name)")
        self.var_city = tk.StringVar(value=str(w.get("city", "Kyiv")))
        self.var_lat = tk.StringVar(value="" if w.get("latitude") is None else str(w.get("latitude")))
        self.var_lon = tk.StringVar(value="" if w.get("longitude") is None else str(w.get("longitude")))
        self.var_units = tk.StringVar(value=str(w.get("units", "metric")))
        sc = w.get("show_card", "auto")
        self.var_wcard = tk.StringVar(value="auto" if sc == "auto" else ("always" if sc else "hidden"))

        r1 = self._row(sec_w)
        tk.Label(r1, text="City:", fg=FG_MAIN, bg=BG_CARD, width=12, anchor="w").pack(side="left")
        self._entry(r1, self.var_city, width=22).pack(side="left", padx=(0, 8))
        tk.Button(r1, text="Search City", bg="#2563EB", fg="white", relief="flat", padx=12, command=self._search_city).pack(side="left", padx=(0, 10))
        self.city_status = tk.StringVar(value="")
        tk.Label(r1, textvariable=self.city_status, fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")

        r2 = self._row(sec_w)
        tk.Label(r2, text="Coords:", fg=FG_MAIN, bg=BG_CARD, width=12, anchor="w").pack(side="left")
        tk.Label(r2, text="Lat:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(r2, self.var_lat, width=10).pack(side="left", padx=(4, 12))
        tk.Label(r2, text="Lon:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        self._entry(r2, self.var_lon, width=10).pack(side="left", padx=(4, 18))
        tk.Label(r2, text="Units:", fg=FG_MUTED, bg=BG_CARD).pack(side="left")
        ttk.Combobox(r2, textvariable=self.var_units, values=("metric", "imperial"), width=9, state="readonly").pack(side="left", padx=4)

        r3 = self._row(sec_w)
        tk.Label(r3, text="Wing Weather Card:", fg=FG_MAIN, bg=BG_CARD, width=18, anchor="w").pack(side="left")
        ttk.Combobox(r3, textvariable=self.var_wcard, values=("auto", "always", "hidden"), width=10, state="readonly").pack(side="left", padx=4)
        tk.Label(r3, text="auto automatically moves Weather to side wing if tiles fill Start11 center", fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 8)).pack(side="left", padx=8)

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
        self._check(rp2, "Auto-hide offline tiles", self.var_p_autohide).pack(side="left", padx=(0, 14))
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
                    self.city_status.set("City not found (check spelling / internet)")
            self._safe_ui(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _safe_ui(self, fn: Callable[[], None]) -> None:
        """Schedule a Tk callback safely from a worker thread without crashing if Settings closed."""
        def _wrapped():
            try:
                if self.win.winfo_exists():
                    fn()
            except Exception:
                pass
        try:
            self.win.after(0, _wrapped)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Tab 5: Integrations (Tier 2) — with live Hue Room Picker!
    # ------------------------------------------------------------------

    def _build_integrations_tab(self) -> None:
        widgets = self.draft["widgets"]
        hue = widgets["philips_hue"]
        td = widgets["todoist"]
        tasks = widgets["tasks"]
        ef = widgets["ecoflow"]
        ph = widgets["phone_adb"]

        sec_h = self._section(self.tab_integrations, "Philips Hue (1-Click Discovery, Pair & Room Picker)")
        self.var_hue_ip = tk.StringVar(value=str(hue.get("bridge_ip", "")))
        self.var_hue_key = tk.StringVar(value=str(hue.get("app_key", "")))
        self.hue_status = tk.StringVar(value="")

        rh1 = self._row(sec_h)
        tk.Label(rh1, text="Bridge IP:", fg=FG_MAIN, bg=BG_CARD, width=11, anchor="w").pack(side="left")
        self._entry(rh1, self.var_hue_ip, width=16).pack(side="left", padx=(0, 6))
        tk.Button(rh1, text="Find Bridge", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=self._hue_discover).pack(side="left", padx=3)
        tk.Button(rh1, text="Press Link & Pair", bg="#2563EB", fg="white", relief="flat", padx=8, command=self._hue_pair).pack(side="left", padx=3)
        tk.Button(rh1, text="Load Rooms & Lights", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=8, command=self._hue_load_rooms).pack(side="left", padx=3)

        rh2 = self._row(sec_h)
        tk.Label(rh2, text="App Key:", fg=FG_MAIN, bg=BG_CARD, width=11, anchor="w").pack(side="left")
        self._entry(rh2, self.var_hue_key, width=30).pack(side="left", padx=(0, 8))
        tk.Label(rh2, textvariable=self.hue_status, fg=FG_MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")

        self.hue_picker_frame = tk.Frame(sec_h, bg=BG_CARD)
        self.hue_picker_frame.pack(fill="x", pady=(4, 0))

        # Tasks & Todoist
        sec_t = self._section(self.tab_integrations, "Tasks & Todoist")
        self.var_task_mode = tk.StringVar(value=str(tasks.get("mode", "auto")))
        self.var_td_token = tk.StringVar(value=str(td.get("api_token", "")))
        rt = self._row(sec_t)
        tk.Label(rt, text="Backend:", fg=FG_MAIN, bg=BG_CARD, width=11, anchor="w").pack(side="left")
        ttk.Combobox(rt, textvariable=self.var_task_mode, values=("auto", "local", "todoist"), width=10, state="readonly").pack(side="left", padx=(0, 12))
        tk.Label(rt, text="Todoist Token:", fg=FG_MAIN, bg=BG_CARD).pack(side="left", padx=(0, 6))
        self._entry(rt, self.var_td_token, width=32).pack(side="left")

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
            self._safe_ui(_done)

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
                    self.hue_status.set("Paired! Click Load Rooms & Lights.")
                else:
                    self.hue_status.set(res)
            self._safe_ui(_done)

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
                self._hue_catalog = cat
                self._render_hue_picker()
                self.hue_status.set(f"Loaded {len(cat)} items — check up to 4 to display" if cat else "No rooms/lights returned")
            self._safe_ui(_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _render_hue_picker(self) -> None:
        for w in self.hue_picker_frame.winfo_children():
            w.destroy()
        self._hue_selected_vars.clear()
        existing = {(t.get("kind"), str(t.get("id"))) for t in (self.draft["widgets"]["philips_hue"].get("targets") or [])}
        row = self._row(self.hue_picker_frame)
        for idx, item in enumerate(self._hue_catalog[:8]):
            if idx > 0 and idx % 4 == 0:
                row = self._row(self.hue_picker_frame)
            checked = (item["kind"], str(item["id"])) in existing or (not existing and idx < 2)
            v = tk.BooleanVar(value=checked)
            self._hue_selected_vars.append((item, v))
            self._check(row, f"{item['label']} ({item['kind'][:-1]})", v).pack(side="left", padx=(0, 10))

    # ------------------------------------------------------------------
    # Tab 6: Diagnostics & Updates
    # ------------------------------------------------------------------

    def _build_doctor_tab(self) -> None:
        upd = self.draft.get("updates", {})
        self.var_upd_check = tk.BooleanVar(value=bool(upd.get("check_enabled", True)))
        self.upd_status = tk.StringVar(value=f"Installed: StartHub v{__version__}")

        top_u = tk.Frame(self.tab_doctor, bg=BG_CARD, padx=12, pady=8)
        top_u.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(top_u, textvariable=self.upd_status, fg=FG_MAIN, bg=BG_CARD, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Button(top_u, text="Open Releases", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=10, command=lambda: webbrowser.open(RELEASES_PAGE_URL)).pack(side="right", padx=3)
        tk.Button(top_u, text="Check for Updates", bg="#2563EB", fg="white", relief="flat", padx=10, command=self._check_updates).pack(side="right", padx=3)
        self._check(top_u, "Auto-check (24h)", self.var_upd_check).pack(side="right", padx=10)

        top = tk.Frame(self.tab_doctor, bg=BG_MAIN)
        top.pack(fill="x", padx=8, pady=6)
        tk.Button(top, text="Refresh Diagnostics", bg=BG_INPUT, fg=FG_MAIN, relief="flat", padx=12, command=self._refresh_doctor).pack(side="left", padx=(0, 6))
        tk.Button(top, text="Copy Report for GitHub Issue", bg="#2563EB", fg="white", relief="flat", padx=12, command=self._copy_doctor).pack(side="left")

        self.doctor_txt = tk.Text(self.tab_doctor, bg=BG_CARD, fg=FG_MAIN, font=("Consolas", 10), relief="flat", padx=12, pady=10)
        self.doctor_txt.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._refresh_doctor()

    def _check_updates(self) -> None:
        self.upd_status.set("Checking GitHub Releases...")

        def _worker():
            res = check_for_updates(force=True)
            def _done():
                if not self.win.winfo_exists():
                    return
                if not res.get("checked"):
                    self.upd_status.set(f"Update check failed ({res.get('error', 'offline')})")
                elif res.get("update_available"):
                    self.upd_status.set(f"New version available: v{res['latest_version']} (you have v{__version__})")
                else:
                    self.upd_status.set(f"You are up to date (v{__version__})")
            self._safe_ui(_done)

        threading.Thread(target=_worker, daemon=True).start()

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
            self._safe_ui(_done)

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
    # Profile Export / Import + Save / Reset
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

        hue_targets = self.draft["widgets"]["philips_hue"].get("targets", [])
        if self._hue_selected_vars:
            picked = [item for item, var in self._hue_selected_vars if var.get()]
            if picked:
                hue_targets = picked[:4]

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
        w_patch["quick_actions"]["items"] = list(self._qa_items)
        w_patch["custom_json"]["allow_remote_urls"] = bool(self.var_cj_remote.get())
        w_patch["custom_json"]["cards"] = list(self._custom_cards)
        w_patch["philips_hue"].update(
            {
                "bridge_ip": self.var_hue_ip.get().strip(),
                "app_key": self.var_hue_key.get().strip(),
                "targets": hue_targets,
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
            "updates": {"check_enabled": bool(self.var_upd_check.get())},
            "theme": {
                "preset": self.var_preset.get(),
                "mode": self.var_theme_mode.get(),
                "accent_color": "windows" if self.var_win_accent.get() else self.var_accent_hex.get().strip(),
                "accent_explicit": not self.var_win_accent.get() and self.var_accent_hex.get().strip().upper() != "#58BCFF",
                "panel_alpha": int(self.var_alpha.get()),
                "blur": bool(self.var_blur.get()),
                "corner_radius": int(self.var_radius.get()),
                "custom_colors": {
                    "panel_bg": self.var_cc_panel.get().strip(),
                    "tile_bg": self.var_cc_tile.get().strip(),
                    "border": self.var_cc_border.get().strip(),
                    "text_primary": self.var_cc_text.get().strip(),
                    "text_secondary": self.var_cc_text2.get().strip(),
                },
                "role_overrides": dict(self._role_overrides),
            },
            "window": {
                "trigger_mode": self.var_trigger.get(),
                "hotkey_enabled": bool(self.var_hk_en.get()),
                "hotkey": self.var_hotkey.get().strip() or "Alt+Space",
                "adaptive_width": bool(self.var_adaptive.get()),
                "center_overlay": bool(self.var_center.get()),
                "center_overlay_safety_margin": int(self.var_center_margin.get()),
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

    def _export_profile(self) -> None:
        out = filedialog.asksaveasfilename(
            parent=self.win,
            title="Export Shareable StartHub Profile (Zero Secrets)",
            defaultextension=".json",
            filetypes=[("JSON Profile", "*.json")],
            initialfile="starthub_profile.json",
        )
        if not out:
            return
        prof = export_profile_data(self._collect_patch())
        Path(out).write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_var.set(f"Exported shareable profile (no secrets) -> {os.path.basename(out)}")

    def _import_profile(self) -> None:
        src = filedialog.askopenfilename(
            parent=self.win,
            title="Import StartHub Profile",
            filetypes=[("JSON Profile", "*.json")],
        )
        if not src:
            return
        try:
            data = json.loads(Path(src).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Invalid JSON")
            patch: Dict[str, Any] = {}
            for section in ("theme", "window", "layout"):
                if isinstance(data.get(section), dict):
                    patch[section] = data[section]
            if patch and save_config_patch(self.config_path, patch):
                self.status_var.set("Imported profile & applied live! Reopen Settings to inspect.")
                self.on_apply()
        except Exception as exc:
            self.status_var.set(f"Import failed: {type(exc).__name__}")

    def _save_and_apply(self) -> None:
        patch = self._collect_patch()
        if save_config_patch(self.config_path, patch):
            self.status_var.set("Saved to config.json and applied live!")
            try:
                self.on_apply()
            except Exception:
                pass
        else:
            self.status_var.set("Could not write config.json")

    def _reset_defaults(self) -> None:
        self.draft = copy.deepcopy(DEFAULT_CONFIG)
        self._role_overrides.clear()
        self._qa_items = [dict(it) for it in DEFAULT_CONFIG["widgets"]["quick_actions"]["items"]]
        self._custom_cards = []
        self._apply_preset("balanced")
        self.var_preset.set("fluent_dark")
        self.var_theme_mode.set("multi_accent")
        self.var_win_accent.set(False)
        self.var_accent_hex.set("#58BCFF")
        self.var_alpha.set(180)
        self.var_radius.set(14)
        self.var_blur.set(True)
        self.var_fade.set(True)
        self.var_trigger.set("auto")
        self.var_center_margin.set(14)
        self._clear_surface_overrides()
        self.var_roles_summary.set(self._format_roles_summary())
        self._rebuild_qa_list()
        self._rebuild_cj_list()
        self.status_var.set("Defaults restored — click Apply & Save to persist")

    def _open_raw_config(self) -> None:
        if not self.config_path.is_file():
            save_config_patch(self.config_path, {})
        if IS_WINDOWS and self.config_path.is_file():
            os.startfile(str(self.config_path))
