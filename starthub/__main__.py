"""CLI entrypoint for `python -m starthub`."""
from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from . import __version__
from .config import DEFAULT_CACHE_DIR, DEFAULT_CONFIG_PATH, load_config
from .doctor import format_diagnostics, run_diagnostics
from .i18n import I18n
from .providers import ProviderHub
from .renderer import HubRenderer
from .surface import SingleInstanceGuard, ensure_interactive_desktop
from .theme import Theme


def configure_logging(cache_dir: Path) -> None:
    log_dir = cache_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "starthub.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(str(log_file), maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"),
        ],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m starthub",
        description="StartHub — Modular Windows 11 & Start11 acrylic companion panels.",
    )
    parser.add_argument("--version", action="version", version=f"StartHub {__version__}")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to config.json")
    parser.add_argument("--demo", action="store_true", help="Launch with rich synthetic demo data (no devices/keys needed)")
    parser.add_argument("--preview", action="store_true", help="Keep wings visible on screen without waiting for Start11")
    parser.add_argument("--settings", action="store_true", help="Open the GUI Settings window immediately on startup")
    parser.add_argument("--doctor", action="store_true", help="Print a sanitized environment diagnostics report and exit")
    parser.add_argument("--trigger", choices=("auto", "start11", "windows11", "hotkey"), default=None, help="Override trigger mode")
    parser.add_argument(
        "--preset",
        choices=("fluent_dark", "fluent_light", "amoled_black", "catppuccin_mocha", "nord", "tokyo_night"),
        default=None,
        help="Override theme visual preset",
    )
    parser.add_argument("--theme", choices=("multi_accent", "single_accent"), default=None, help="Override theme mode")
    parser.add_argument("--accent", default=None, help="Override accent color (#RRGGBB or 'windows')")
    parser.add_argument("--lang", choices=("en", "ru", "uk"), default=None, help="Override UI language")
    parser.add_argument("--render-test", type=Path, default=None, metavar="DIR", help="Render PNG snapshots headlessly into DIR and exit")
    parser.add_argument("--on-default", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.doctor:
        print(format_diagnostics(run_diagnostics(args.config)))
        return 0

    overrides = {}
    if args.lang:
        overrides["language"] = args.lang
    if args.theme or args.accent or args.preset:
        overrides["theme"] = {}
        if args.preset:
            overrides["theme"]["preset"] = args.preset
        if args.theme:
            overrides["theme"]["mode"] = args.theme
        if args.accent:
            overrides["theme"]["accent_color"] = args.accent
            overrides["theme"]["accent_explicit"] = True
    if args.trigger:
        overrides.setdefault("window", {})["trigger_mode"] = args.trigger

    if args.render_test is not None:
        out_dir: Path = args.render_test
        out_dir.mkdir(parents=True, exist_ok=True)
        cfg = load_config(args.config, demo=args.demo, overrides=overrides)
        i18n = I18n(cfg["language"])
        theme = Theme.from_config(cfg)
        renderer = HubRenderer(cfg, theme, i18n)
        hub = ProviderHub(cfg, i18n, demo=args.demo)
        snap = hub.snapshot()
        w_cfg = cfg["window"]
        if renderer.has_widgets("left", snap):
            im_l, _, _ = renderer.render_wing("left", w_cfg["left_width"], w_cfg["fallback_height"], snap, tile_pack_label="Minimal")
            im_l.save(out_dir / "left_wing.png")
        if renderer.has_widgets("right", snap):
            im_r, _, _ = renderer.render_wing("right", w_cfg["right_width"], w_cfg["fallback_height"], snap, tile_pack_label="Minimal")
            im_r.save(out_dir / "right_wing.png")
        renderer.render_center_strip_preview(snap).save(out_dir / "center_overlay.png")
        print(f"Rendered StartHub previews to {out_dir}")
        return 0

    ensure_interactive_desktop()

    guard: SingleInstanceGuard | None = None
    if not args.preview:
        guard = SingleInstanceGuard()
        if not guard.acquire():
            print("StartHub is already running (check your system tray).", file=sys.stderr)
            return 0

    configure_logging(DEFAULT_CACHE_DIR)

    from .app import StartHubApp

    try:
        app = StartHubApp(
            config_path=args.config,
            demo=args.demo,
            preview=args.preview,
            open_settings_on_start=args.settings,
            overrides=overrides,
        )
        app.run()
    finally:
        if guard is not None:
            guard.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
