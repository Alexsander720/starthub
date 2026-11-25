"""System tray icon for StartHub (Reload config, Open config, Demo mode, Theme toggle, Pause, Quit)."""
from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

from PIL import Image, ImageDraw

from . import __version__

logger = logging.getLogger("starthub.tray")


def render_tray_icon(accent: Tuple[int, int, int] = (88, 188, 255), paused: bool = False) -> Image.Image:
    """Render a crisp 64x64 3-panel StartHub icon badge."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg = (58, 62, 72, 245) if paused else (26, 30, 38, 250)
    col = (150, 158, 172, 255) if paused else (*accent, 255)
    wing_col = (120, 128, 142, 220) if paused else (*accent, 195)

    draw.rounded_rectangle((2, 2, 61, 61), radius=14, fill=bg, outline=col, width=3)
    # Left wing
    draw.rounded_rectangle((10, 15, 20, 49), radius=3, fill=wing_col)
    # Center Start menu square
    draw.rounded_rectangle((24, 13, 40, 51), radius=4, fill=(242, 246, 252, 245))
    # Right wing
    draw.rounded_rectangle((44, 15, 54, 49), radius=3, fill=wing_col)
    return img


class StartHubTray:
    """Optional pystray integration running cleanly in a detached thread."""

    def __init__(
        self,
        *,
        t: Callable[[str], str],
        accent: Tuple[int, int, int] = (88, 188, 255),
        is_demo: Callable[[], bool],
        is_paused: Callable[[], bool],
        is_single_accent: Callable[[], bool],
        on_toggle_demo: Callable[[], None],
        on_toggle_theme: Callable[[], None],
        on_reload_config: Callable[[], None],
        on_open_config: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_quit: Callable[[], None],
    ):
        self._t = t
        self._accent = accent
        self._is_demo = is_demo
        self._is_paused = is_paused
        self._is_single_accent = is_single_accent
        self._on_toggle_demo = on_toggle_demo
        self._on_toggle_theme = on_toggle_theme
        self._on_reload_config = on_reload_config
        self._on_open_config = on_open_config
        self._on_toggle_pause = on_toggle_pause
        self._on_quit = on_quit
        self._icon = None

    def start(self) -> bool:
        try:
            import pystray
            from pystray import MenuItem as Item
        except ImportError:
            logger.info("pystray not installed; system tray icon disabled")
            return False

        menu = pystray.Menu(
            Item(lambda _: f"StartHub v{__version__}", action=None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item(lambda _: self._t("tray.demo_mode"), lambda _i, _m: self._on_toggle_demo(), checked=lambda _: self._is_demo()),
            Item(
                lambda _: self._t("tray.theme_multi") if self._is_single_accent() else self._t("tray.theme_single"),
                lambda _i, _m: self._on_toggle_theme(),
            ),
            pystray.Menu.SEPARATOR,
            Item(lambda _: self._t("tray.reload_config"), lambda _i, _m: self._on_reload_config()),
            Item(lambda _: self._t("tray.open_config"), lambda _i, _m: self._on_open_config()),
            Item(lambda _: self._t("tray.pause"), lambda _i, _m: self._on_toggle_pause(), checked=lambda _: self._is_paused()),
            pystray.Menu.SEPARATOR,
            Item(lambda _: self._t("tray.quit"), self._handle_quit),
        )
        self._icon = pystray.Icon(
            "StartHub",
            icon=render_tray_icon(self._accent, paused=self._is_paused()),
            title=f"StartHub v{__version__}",
            menu=menu,
        )
        try:
            self._icon.run_detached()
            self._icon.visible = True
            return True
        except Exception as exc:
            logger.warning("Could not start tray icon: %s", exc)
            return False

    def refresh(self, accent: Optional[Tuple[int, int, int]] = None) -> None:
        if accent is not None:
            self._accent = accent
        if self._icon is None:
            return
        try:
            self._icon.icon = render_tray_icon(self._accent, paused=self._is_paused())
            self._icon.update_menu()
        except Exception:
            pass

    def _handle_quit(self, icon, _item) -> None:
        try:
            icon.stop()
        except Exception:
            pass
        self._on_quit()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
