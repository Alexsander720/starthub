"""StartHub Windows 11 / Start11 live companion shell (Win32 HWND tracker + Acrylic layered wings)."""
from __future__ import annotations

import ctypes
import datetime
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageTk

from .config import DEFAULT_CACHE_DIR, DEFAULT_CONFIG_PATH, REPO_ROOT, load_config
from .i18n import I18n
from .layout import CENTER_H, CENTER_SIDES, CENTER_W, calibrated_tile_grid, center_layouts, panel_layout
from .providers import ProviderHub
from .renderer import HubRenderer
from .surface import (
    CREATE_NO_WINDOW,
    FontBank,
    IS_WINDOWS,
    LayeredSurface,
    apply_panel_blur,
    apply_win11_rounded,
    copy_image_and_file_to_clipboard,
    enable_dpi_awareness,
    popen_on_default_desktop,
)
from .theme import Theme
from .tray import StartHubTray
from .widgets import Hotspot, get_photo_thumb

if IS_WINDOWS:
    from ctypes import wintypes
    import win32api
    import win32con
    import win32event
    import win32gui
    import win32process
    import winreg
else:  # pragma: no cover
    wintypes = win32api = win32con = win32event = win32gui = win32process = winreg = None  # type: ignore

logger = logging.getLogger("starthub.app")


class StartHubApp:
    """Tracks Start11 (DV2ControlHost) and floats layered acrylic wings + center overlays beside it."""

    def __init__(
        self,
        *,
        config_path: Optional[Path] = None,
        demo: bool = False,
        preview: bool = False,
        overrides: Optional[Dict[str, Any]] = None,
    ):
        enable_dpi_awareness()
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.demo = demo
        self.preview_mode = preview
        self._overrides = overrides or {}
        self._paused = False

        self.config = load_config(self.config_path, demo=self.demo, overrides=self._overrides)
        self.i18n = I18n(self.config["language"])
        self.theme = Theme.from_config(self.config)
        self.fonts = FontBank()
        self.renderer = HubRenderer(self.config, self.theme, self.i18n, self.fonts)
        self.hub = ProviderHub(
            self.config,
            self.i18n,
            demo=self.demo,
            cache_dir=DEFAULT_CACHE_DIR,
            on_change=self._request_redraw,
        )

        win_cfg = self.config["window"]
        self.lw: int = int(win_cfg["left_width"])
        self.rw: int = int(win_cfg["right_width"])
        self.gap: int = int(win_cfg["gap"])
        self.wing_h: int = int(win_cfg["fallback_height"])
        self.hide_delay: float = float(win_cfg["hide_delay_sec"])
        self.center_overlay: bool = bool(win_cfg["center_overlay"])
        self.start_menu_class: str = str(win_cfg["start_menu_class"])

        self._dirty = True
        self._visible = False
        self._last_interact_ts = 0.0
        self._next_hidden_render = 0.0
        self._left_hotspots: List[Hotspot] = []
        self._right_hotspots: List[Hotspot] = []
        self._left_hover: Optional[str] = None
        self._right_hover: Optional[str] = None
        self._left_scroll = 0
        self._right_scroll = 0
        self._left_max_scroll = 0
        self._right_max_scroll = 0
        self._bt_drawer_open = False
        self._calendar_month = (datetime.date.today().year, datetime.date.today().month)
        self._calendar_follow_today = True
        self._clock_now = datetime.datetime.now()
        self._clock_minute = self._clock_now.strftime("%Y-%m-%d %H:%M")

        # Start11 center overlay state
        self._center_view = None
        self._center_menu = None
        self._center_grid = None
        self._center_grid_valid = False
        self._center_sizes = {side: (CENTER_W, CENTER_H) for side in CENTER_SIDES}
        self._center_registry_watch = None
        self._center_registry_snapshot = None
        self._center_probe_result = None
        self._center_result_used = None
        self._center_probe_pending = False
        self._center_probe_until = 0.0
        self._center_epoch = 0
        self._center_dragging = False
        self._center_refresh_required = False
        self._center_work = (0, 0, 1920, 1080)

        # Tile switcher state
        self._tile_pack_label: Optional[str] = self._read_current_tile_pack()
        self._tile_busy = False

        self._panel_geometry: Dict[str, Tuple[int, int, int, int]] = {}
        self._last_start_rect: Optional[Tuple[int, int, int, int]] = None
        self._frame_cache: Dict[str, Any] = {}
        self._gallery_win: Optional[tk.Toplevel] = None
        self._pending_ui_actions: List[Callable[[], None]] = []
        self._ui_lock = threading.Lock()

        # Detect live Start11 height before creating windows
        if IS_WINDOWS and win32gui is not None and not self.preview_mode:
            menu = win32gui.FindWindow(self.start_menu_class, None)
            if menu:
                r = win32gui.GetWindowRect(menu)
                if r[3] - r[1] > 200:
                    work = win32api.GetMonitorInfo(win32api.MonitorFromRect(r, win32con.MONITOR_DEFAULTTONEAREST))["Work"]
                    lay = panel_layout(r, work, left_width=self.lw, right_width=self.rw, gap=self.gap)
                    self.wing_h = lay["left"][3]

        # Build Tkinter windows
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("StartHub Left Wing")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#14161B")
        self.left_canvas = tk.Canvas(self.root, width=self.lw, height=self.wing_h, bg="#14161B", highlightthickness=0, bd=0)
        self.left_canvas.pack(fill="both", expand=True)
        self._left_tk_img: Optional[ImageTk.PhotoImage] = None

        self.right_win = tk.Toplevel(self.root)
        self.right_win.withdraw()
        self.right_win.title("StartHub Right Wing")
        self.right_win.overrideredirect(True)
        self.right_win.attributes("-topmost", True)
        self.right_win.configure(bg="#14161B")
        self.right_canvas = tk.Canvas(self.right_win, width=self.rw, height=self.wing_h, bg="#14161B", highlightthickness=0, bd=0)
        self.right_canvas.pack(fill="both", expand=True)
        self._right_tk_img: Optional[ImageTk.PhotoImage] = None

        self._center_windows: Dict[str, tk.Toplevel] = {}
        self._center_hwnds: Dict[str, int] = {}
        self._center_old_procs: Dict[int, Any] = {}
        for side, title in zip(CENTER_SIDES, ("StartHub Weather Overlay", "StartHub Clock Overlay")):
            win = tk.Toplevel(self.root)
            win.withdraw()
            win.title(title)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.geometry(f"{CENTER_W}x{CENTER_H}")
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id() if IS_WINDOWS else win.winfo_id()
            self._center_windows[side] = win
            self._center_hwnds[side] = hwnd
            if IS_WINDOWS and win32gui is not None:
                self._center_old_procs[hwnd] = win32gui.SetWindowLong(hwnd, win32con.GWL_WNDPROC, self._center_window_proc)

        # Mouse & keyboard bindings
        self.left_canvas.bind("<Button-1>", lambda e: self._on_click(e, self._left_hotspots, False))
        self.left_canvas.bind("<Button-3>", lambda e: self._on_click(e, self._left_hotspots, True))
        self.left_canvas.bind("<Motion>", lambda e: self._on_motion(e, self._left_hotspots, True))
        self.left_canvas.bind("<Leave>", lambda _e: self._on_leave(True))
        self.left_canvas.bind("<MouseWheel>", lambda e: self._scroll_wing("left", e.delta))

        self.right_canvas.bind("<Button-1>", lambda e: self._on_click(e, self._right_hotspots, False))
        self.right_canvas.bind("<Button-3>", lambda e: self._on_click(e, self._right_hotspots, True))
        self.right_canvas.bind("<Motion>", lambda e: self._on_motion(e, self._right_hotspots, False))
        self.right_canvas.bind("<Leave>", lambda _e: self._on_leave(False))
        self.right_canvas.bind("<MouseWheel>", lambda e: self._scroll_wing("right", e.delta))

        self.root.bind("<Escape>", lambda _e: self._hide_windows())
        self.right_win.bind("<Escape>", lambda _e: self._hide_windows())
        self.root.bind("<Destroy>", self._on_destroy, add="+")

        self.root.update_idletasks()
        self.right_win.update_idletasks()
        if IS_WINDOWS:
            self.left_hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            self.right_hwnd = ctypes.windll.user32.GetParent(self.right_win.winfo_id()) or self.right_win.winfo_id()
        else:
            self.left_hwnd = self.root.winfo_id()
            self.right_hwnd = self.right_win.winfo_id()

        self._surfaces: Dict[str, LayeredSurface] = {}
        self._init_surfaces()

        # System tray
        self.tray = StartHubTray(
            t=self.i18n.t,
            accent=self.theme.accent,
            is_demo=lambda: self.demo,
            is_paused=lambda: self._paused,
            is_single_accent=lambda: self.theme.is_single_accent,
            on_toggle_demo=lambda: self._enqueue_ui(self._toggle_demo_mode),
            on_toggle_theme=lambda: self._enqueue_ui(self._toggle_theme_mode),
            on_reload_config=lambda: self._enqueue_ui(self._reload_config),
            on_open_config=self._open_config_file,
            on_toggle_pause=lambda: self._enqueue_ui(self._toggle_pause),
            on_quit=lambda: self._enqueue_ui(self.quit),
        )
        self.tray.start()

        # Pre-render initial frame before showing
        self._render_all()
        self._dirty = False

        if self.preview_mode:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            center_w = 640
            cx = max(self.lw + 20, (sw - center_w) // 2)
            cy = max(40, (sh - self.wing_h) // 2)
            fake_start = (cx, cy, cx + center_w, cy + self.wing_h)
            self._visible = True
            self._place_panels(fake_start, show=True)

        self.hub.start()
        if self.center_overlay and IS_WINDOWS and not self.preview_mode:
            self._prime_center_probe()
        self.root.after(40, self._tick)

    def _init_surfaces(self) -> None:
        for side, hwnd in self._all_hwnds().items():
            inset = side in CENTER_SIDES
            if IS_WINDOWS and win32gui is not None:
                apply_win11_rounded(hwnd, 1 if inset else 2, None)
                ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(
                    hwnd,
                    win32con.GWL_EXSTYLE,
                    (ex_style | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE) & ~win32con.WS_EX_APPWINDOW,
                )
            self._surfaces[side] = LayeredSurface(hwnd)
            if not inset and self.theme.blur and IS_WINDOWS:
                try:
                    apply_panel_blur(hwnd)
                except Exception:
                    pass

    def _enqueue_ui(self, fn: Callable[[], None]) -> None:
        with self._ui_lock:
            self._pending_ui_actions.append(fn)

    def _request_redraw(self) -> None:
        self._dirty = True

    def _all_hwnds(self) -> Dict[str, int]:
        return {"left": self.left_hwnd, "right": self.right_hwnd, **self._center_hwnds}

    def _all_windows(self) -> Dict[str, tk.Misc]:
        return {"left": self.root, "right": self.right_win, **self._center_windows}

    def _center_window_proc(self, hwnd, message, wparam, lparam):
        if message == win32con.WM_MOUSEACTIVATE:
            return win32con.MA_NOACTIVATE
        return win32gui.CallWindowProc(self._center_old_procs[hwnd], hwnd, message, wparam, lparam)

    # ------------------------------------------------------------------
    # Tray & Runtime Actions
    # ------------------------------------------------------------------

    def _rebuild_runtime(self) -> None:
        self.hub.stop()
        self.config = load_config(self.config_path, demo=self.demo, overrides=self._overrides)
        self.i18n = I18n(self.config["language"])
        self.theme = Theme.from_config(self.config)
        self.renderer = HubRenderer(self.config, self.theme, self.i18n, self.fonts)
        self.hub = ProviderHub(
            self.config,
            self.i18n,
            demo=self.demo,
            cache_dir=DEFAULT_CACHE_DIR,
            on_change=self._request_redraw,
        )
        self.hub.start()
        self._frame_cache.clear()
        self._left_scroll = self._right_scroll = 0
        self.tray.refresh(self.theme.accent)
        self._dirty = True

    def _toggle_demo_mode(self) -> None:
        self.demo = not self.demo
        self._rebuild_runtime()
        self.hub.show_toast(f"{self.i18n.t('tray.demo_mode')}: {'ON' if self.demo else 'OFF'}")

    def _toggle_theme_mode(self) -> None:
        next_mode = "multi_accent" if self.theme.is_single_accent else "single_accent"
        self._overrides.setdefault("theme", {})["mode"] = next_mode
        self.config["theme"]["mode"] = next_mode
        self.theme = Theme.from_config(self.config)
        self.renderer.theme = self.theme
        self._frame_cache.clear()
        self.tray.refresh(self.theme.accent)
        self._dirty = True

    def _reload_config(self) -> None:
        self._rebuild_runtime()
        self.hub.show_toast(self.i18n.t("tray.reloaded"))

    def _open_config_file(self) -> None:
        if not self.config_path.is_file():
            example = REPO_ROOT / "config.example.json"
            if example.is_file():
                self.config_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        if IS_WINDOWS and self.config_path.is_file():
            os.startfile(str(self.config_path))

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self._hide_windows()
        self.tray.refresh()

    def quit(self) -> None:
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            os._exit(0)

    def _on_destroy(self, event) -> None:
        if event.widget == self.root:
            self.hub.stop()
            self.tray.stop()
            if self._center_registry_watch:
                key, sig = self._center_registry_watch
                key.Close()
                sig.Close()
            for surface in self._surfaces.values():
                surface.close()

    # ------------------------------------------------------------------
    # Tile Switcher integration
    # ------------------------------------------------------------------

    def _read_current_tile_pack(self) -> Optional[str]:
        if self.demo:
            return "Minimal"
        state_file = DEFAULT_CACHE_DIR / "tile_pack.txt"
        try:
            if state_file.is_file():
                val = state_file.read_text(encoding="utf-8-sig").strip()
                if val:
                    return val
        except OSError:
            pass
        return None

    def _cycle_tile_pack(self) -> None:
        if self.demo:
            names = ("Minimal", "Classic", "Clean")
            nxt = names[(names.index(self._tile_pack_label) + 1) % len(names)] if self._tile_pack_label in names else names[0]
            self._tile_pack_label = nxt
            self.hub.show_toast(self.i18n.t("tiles.toast_switched", name=nxt))
            self._dirty = True
            return
        if self._tile_busy:
            return
        self._tile_busy = True
        self._dirty = True

        def _worker():
            try:
                script = REPO_ROOT / "tools" / "tile_switcher.py"
                packs_dir = str(self.config["widgets"]["tile_switcher"].get("packs_dir") or "packs")
                res = subprocess.run(
                    [sys.executable, str(script), "--packs-dir", packs_dir, "--cycle", "--apply"],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=CREATE_NO_WINDOW,
                )
                if res.returncode != 0:
                    self.hub.show_toast(self.i18n.t("tiles.toast_error"), 3.5)
                    return
                self._tile_pack_label = self._read_current_tile_pack()
                self.hub.show_toast(self.i18n.t("tiles.toast_switched", name=self._tile_pack_label or "OK"))
            except Exception:
                self.hub.show_toast(self.i18n.t("tiles.toast_error"), 3.5)
            finally:
                self._tile_busy = False
                self._dirty = True

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Start11 Center Overlay Probing
    # ------------------------------------------------------------------

    @staticmethod
    def _read_center_registry() -> Dict[str, Any]:
        base = r"Software\Stardock\Start8\Start8.ini\\"

        def read(sub: str) -> Dict[str, Any]:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + sub) as key:
                return {n: v for n, v, _ in (winreg.EnumValue(key, i) for i in range(winreg.QueryInfoKey(key)[1]))}

        registry = {sub: read(sub) for sub in ("Groups", "Start8")}
        for value in registry["Groups"].values():
            sub = "GroupContents\\" + value.split("|")[0]
            try:
                registry[sub] = read(sub)
            except FileNotFoundError:
                registry[sub] = {}
        return registry

    @staticmethod
    def _native_tile_items(view: int) -> List[Tuple[int, int, int, int]]:
        k = ctypes.windll.kernel32
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
        k.VirtualAllocEx.restype = ctypes.c_void_p
        k.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        k.WriteProcessMemory.argtypes = k.ReadProcessMemory.argtypes
        k.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        proc = k.OpenProcess(0x38, False, win32process.GetWindowThreadProcessId(view)[1])
        if not proc:
            raise ctypes.WinError()
        ptr = k.VirtualAllocEx(proc, None, 16, 0x3000, 4)
        try:
            if not ptr:
                raise ctypes.WinError()
            _, count = win32gui.SendMessageTimeout(view, 0x1004, 0, 0, win32con.SMTO_ABORTIFHUNG, 20)
            if not 0 <= count <= 4096:
                raise ValueError("native tile count")
            items = []
            for i in range(count):
                r = wintypes.RECT()
                if not k.WriteProcessMemory(proc, ptr, ctypes.byref(r), 16, None):
                    raise ctypes.WinError()
                _, ok = win32gui.SendMessageTimeout(view, 0x100E, i, ptr, win32con.SMTO_ABORTIFHUNG, 20)
                if not ok:
                    raise ValueError("native item")
                if not k.ReadProcessMemory(proc, ptr, ctypes.byref(r), 16, None):
                    raise ctypes.WinError()
                items.append((r.left, r.top, r.right, r.bottom))
            return items
        finally:
            if ptr:
                k.VirtualFreeEx(proc, ptr, 0, 0x8000)
            k.CloseHandle(proc)

    def _prime_center_probe(self) -> None:
        if not IS_WINDOWS or win32gui is None:
            return
        menu = win32gui.FindWindow(self.start_menu_class, None)
        if menu:
            rect = win32gui.GetWindowRect(menu)
            work = win32api.GetMonitorInfo(win32api.MonitorFromRect(rect, win32con.MONITOR_DEFAULTTONEAREST))["Work"]
            self._center_safe(rect, work, force=True)

    def _start_center_probe(self, view: int, registry: Dict[str, Any]) -> None:
        if self._center_probe_pending or self._center_dragging or not view:
            return
        self._center_probe_pending = True
        epoch = self._center_epoch

        def worker():
            try:
                nr = win32gui.GetWindowRect(view)
                native = dict(
                    rect=nr,
                    visible=True,
                    scroll=tuple(ctypes.windll.user32.GetScrollPos(view, b) for b in (0, 1)),
                    items=self._native_tile_items(view),
                    client=win32gui.GetClientRect(view)[2:],
                )
                grid = calibrated_tile_grid(registry, native) if registry == self._read_center_registry() else None
                self._center_probe_result = (epoch, registry, grid)
            except Exception:
                self._center_probe_result = (epoch, registry, None)
            finally:
                self._center_probe_pending = False

        threading.Thread(target=worker, name="starthub-center-geo", daemon=True).start()

    def _invalidate_center_geometry(self) -> None:
        self._center_epoch += 1
        self._center_grid = None
        self._center_grid_valid = False
        self._center_probe_result = None
        self._center_result_used = None
        self._center_refresh_required = True
        self._center_probe_until = 0.0

    def _center_drag_active(self) -> bool:
        pressed = bool(ctypes.windll.user32.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
        view = self._center_view
        over = False
        if pressed and view:
            target = win32gui.WindowFromPoint(win32gui.GetCursorPos())
            over = target == view or win32gui.IsChild(view, target)
        if pressed and (over or self._center_dragging):
            if not self._center_dragging:
                self._center_dragging = True
                self._invalidate_center_geometry()
            return True
        if self._center_dragging:
            self._center_dragging = False
            self._invalidate_center_geometry()
        return False

    def _center_safe(self, rect, work, force: bool = False) -> bool:
        if not IS_WINDOWS or win32gui is None:
            return False
        try:
            if self._center_drag_active():
                return False
            reg_changed = False
            if not self._center_registry_watch:
                key = win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER, r"Software\Stardock\Start8\Start8.ini", 0, win32con.KEY_NOTIFY)
                sig = win32event.CreateEvent(None, False, False, None)
                self._center_registry_watch = (key, sig)
                win32api.RegNotifyChangeKeyValue(key, True, 0x5, sig, True)
                force = reg_changed = True
            elif win32event.WaitForSingleObject(self._center_registry_watch[1], 0) == win32event.WAIT_OBJECT_0:
                key, sig = self._center_registry_watch
                win32api.RegNotifyChangeKeyValue(key, True, 0x5, sig, True)
                force = reg_changed = True
            now = time.monotonic()
            if (
                force
                and not reg_changed
                and not self._center_refresh_required
                and self._center_probe_result
                and self._center_probe_result[0] == self._center_epoch
                and self._center_view
                and self._center_menu == win32gui.FindWindow(self.start_menu_class, None)
                and win32gui.IsChild(self._center_menu, self._center_view)
            ):
                self._center_probe_until = now + 0.25
                force = False
            if force or now >= self._center_probe_until:
                menu = win32gui.FindWindow(self.start_menu_class, None)
                self._center_menu = menu
                views: List[int] = []
                if menu:
                    win32gui.EnumChildWindows(
                        menu,
                        lambda h, _: views.append(h)
                        if win32gui.GetClassName(h) == "SysListView32" and win32gui.GetWindowText(h) == "M"
                        else None,
                        None,
                    )
                self._center_view = views[0] if len(views) == 1 else None
                view = self._center_view
                if self._center_drag_active():
                    return False
                registry = self._read_center_registry()
                if registry != self._center_registry_snapshot:
                    self._invalidate_center_geometry()
                    self._center_registry_snapshot = registry
                cached = self._center_probe_result
                if not (
                    force
                    and not self._center_refresh_required
                    and cached
                    and cached[0] == self._center_epoch
                    and cached[1] == registry
                ):
                    self._start_center_probe(view, registry)
                self._center_probe_until = now + 0.25
            result = self._center_probe_result
            if result is not self._center_result_used:
                matching = bool(result and result[0] == self._center_epoch and result[1] == self._center_registry_snapshot)
                self._center_grid = result[2] if matching else None
                if matching and self._center_grid:
                    self._center_refresh_required = False
                self._center_result_used = result
            self._center_grid_valid = bool(self._center_grid)
            view = self._center_view
            native_visible = bool(view and win32gui.IsWindowVisible(view))
            native_rect = win32gui.GetWindowRect(view) if view else None
            scroll = (
                tuple(ctypes.windll.user32.GetScrollPos(wintypes.HWND(view), bar) for bar in (win32con.SB_VERT, win32con.SB_HORZ))
                if view
                else None
            )
            return bool(
                self._center_grid_valid
                and native_visible
                and scroll == (0, 0)
                and not self._center_refresh_required
                and not (win32gui.GetWindowLong(view, win32con.GWL_STYLE) & (win32con.WS_HSCROLL | win32con.WS_VSCROLL))
                and native_rect == self._center_grid["native_rect"]
                and center_layouts(rect, work, self._center_grid)
            )
        except Exception:
            self._center_grid_valid = False
            self._center_grid = None
            return False

    def _keep_center_above_start11(self) -> None:
        if not IS_WINDOWS or win32gui is None:
            return
        for side, win in self._center_windows.items():
            if not win.winfo_viewable():
                continue
            hwnd = self._center_hwnds[side]
            prev = win32gui.GetWindow(hwnd, win32con.GW_HWNDPREV)
            while prev:
                if prev == self._center_menu:
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_TOPMOST,
                        0,
                        0,
                        0,
                        0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                    )
                    break
                prev = win32gui.GetWindow(prev, win32con.GW_HWNDPREV)

    # ------------------------------------------------------------------
    # Window placement & lifecycle loop
    # ------------------------------------------------------------------

    def _find_start11_rect(self) -> Optional[Tuple[int, int, int, int]]:
        if not IS_WINDOWS or win32gui is None or self._paused:
            return None
        hwnd = win32gui.FindWindow(self.start_menu_class, None)
        if hwnd and win32gui.IsWindowVisible(hwnd):
            try:
                r = win32gui.GetWindowRect(hwnd)
                if (r[2] - r[0]) > 200 and (r[3] - r[1]) > 200:
                    return r
            except Exception:
                pass
        return None

    def _is_cursor_inside_wings(self) -> bool:
        if not IS_WINDOWS or win32gui is None:
            return False
        try:
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            for hwnd in self._all_hwnds().values():
                if not win32gui.IsWindowVisible(hwnd):
                    continue
                r = win32gui.GetWindowRect(hwnd)
                if (r[0] - 14 <= pt.x <= r[2] + 14) and (r[1] - 14 <= pt.y <= r[3] + 14):
                    return True
        except Exception:
            pass
        return False

    def _hide_windows(self) -> None:
        if self._visible and not self.preview_mode:
            for win in self._all_windows().values():
                win.withdraw()
            self._visible = False
            if self._bt_drawer_open:
                self._bt_drawer_open = False
                self._dirty = True

    def _set_wing_height(self, height: int) -> bool:
        height = int(height)
        if self.wing_h == height:
            return False
        self.wing_h = height
        self._left_scroll = self._right_scroll = 0
        self._frame_cache.clear()
        self.left_canvas.configure(height=height)
        self.right_canvas.configure(height=height)
        self._dirty = True
        return True

    def _place_panels(self, rect: Tuple[int, int, int, int], show: bool = False) -> None:
        if IS_WINDOWS and win32api is not None:
            mon = win32api.MonitorFromRect(rect, win32con.MONITOR_DEFAULTTONEAREST)
            work = win32api.GetMonitorInfo(mon)["Work"]
        else:
            work = (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        snap = self.hub.snapshot()
        has_left = self.renderer.has_widgets("left", snap)
        has_right = self.renderer.has_widgets("right", snap)

        layout = panel_layout(
            rect,
            work,
            left_width=self.lw,
            right_width=self.rw,
            gap=self.gap,
            has_left=has_left,
            has_right=has_right,
        )
        ref_panel = layout.get("left") or layout.get("right")
        if ref_panel and self._set_wing_height(ref_panel[3]):
            self._render_all()

        if self.center_overlay and not self.preview_mode and self._center_safe(rect, work, force=show):
            layout.update(center_layouts(rect, work, self._center_grid))
        self._center_work = work

        to_show = []
        for side, win in self._all_windows().items():
            geom = layout.get(side)
            if geom is None:
                win.withdraw()
                continue
            x, y, w, h = geom
            if self._panel_geometry.get(side) != geom:
                win.geometry(f"{w}x{h}+{x}+{y}")
                if IS_WINDOWS and win32gui is not None:
                    win32gui.SetWindowPos(self._all_hwnds()[side], win32con.HWND_TOPMOST, x, y, w, h, win32con.SWP_NOACTIVATE)
                self._panel_geometry[side] = geom
                if side in CENTER_SIDES and self._center_sizes[side] != (w, h):
                    self._center_sizes[side] = (w, h)
                    self._render_center(force=True)
            if show or not win.winfo_viewable():
                win.deiconify()
                to_show.append((side, x, y, w, h))

        if to_show:
            self.root.update_idletasks()
            for side, x, y, w, h in to_show:
                if IS_WINDOWS and win32gui is not None:
                    win32gui.SetWindowPos(
                        self._all_hwnds()[side],
                        win32con.HWND_TOPMOST,
                        x,
                        y,
                        w,
                        h,
                        win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
                    )
                self._surfaces[side].represent()
        self._last_start_rect = rect

    def _tick(self) -> None:
        # Drain any queued tray/UI callbacks on the Tk thread
        with self._ui_lock:
            pending = list(self._pending_ui_actions)
            self._pending_ui_actions.clear()
        for fn in pending:
            try:
                fn()
            except Exception as exc:
                logger.warning("UI callback error: %s", exc)

        just_shown = False
        s_rect = self._find_start11_rect()
        now = time.time()

        if s_rect is not None:
            if not self._visible:
                self._place_panels(s_rect, show=True)
                self._visible = True
                just_shown = True
                self.root.after(30, self._refresh_visible_frame)
            elif s_rect != self._last_start_rect:
                self._place_panels(s_rect)
            elif self.center_overlay:
                safe = self._center_safe(s_rect, self._center_work)
                desired = center_layouts(s_rect, self._center_work, self._center_grid) if safe else {}
                if any(
                    bool(desired.get(side)) != bool(win.winfo_viewable())
                    or (side in desired and desired[side] != self._panel_geometry.get(side))
                    for side, win in self._center_windows.items()
                ):
                    self._place_panels(s_rect)
            if self.center_overlay:
                self._keep_center_above_start11()
        else:
            for win in self._center_windows.values():
                win.withdraw()
            if not self.preview_mode and self._visible:
                if not self._is_cursor_inside_wings() and (now - self._last_interact_ts) > self.hide_delay:
                    self._hide_windows()

        self.hub.set_visible(self._visible)

        if not just_shown and self._dirty and (self._visible or now >= self._next_hidden_render):
            self._dirty = False
            self._render_all()
            self._next_hidden_render = now + 0.5

        if self._visible and not just_shown:
            self._update_clock()

        self.root.after(16 if self._visible else 10, self._tick)

    def _refresh_visible_frame(self) -> None:
        if self._dirty:
            self._dirty = False
            self._render_all()

    def _update_clock(self) -> None:
        now = datetime.datetime.now()
        minute = now.strftime("%Y-%m-%d %H:%M")
        if minute == self._clock_minute:
            return
        self._clock_now, self._clock_minute = now, minute
        if self._calendar_follow_today:
            self._calendar_month = (now.year, now.month)
        if any(w.winfo_viewable() for w in self._center_windows.values()):
            self._render_center()

    # ------------------------------------------------------------------
    # Mouse / Scroll / Actions wiring
    # ------------------------------------------------------------------

    def _build_actions(self) -> Dict[str, Callable[..., None]]:
        return {
            "phone_scrcpy": self.hub.phone.launch_scrcpy if not self.demo else lambda: self.hub.show_toast("Demo: scrcpy screen mirror"),
            "phone_screenshot": self.hub.phone.screenshot_to_clipboard if not self.demo else lambda: self.hub.show_toast("Demo: screenshot copied"),
            "phone_auto_clip": lambda: self.hub.toggle_demo_phone_flag("auto_clip_sync"),
            "phone_photos_toggle": lambda: self.hub.toggle_demo_phone_flag("photos_expanded"),
            "phone_open_gallery": self.open_full_gallery_modal,
            "phone_copy_photo": self.hub.phone.copy_photo,
            "phone_open_photo": self.hub.phone.open_photo,
            "phone_sms_toggle": lambda: self.hub.toggle_demo_phone_flag("sms_expanded"),
            "phone_copy_sms": self.hub.phone.copy_sms if not self.demo else lambda i: self.hub.show_toast("Demo: OTP copied"),
            "refresh_gamepad": self.hub.peripherals.refresh_gamepad_now if not self.demo else lambda: self.hub.show_toast("Demo: DualSense 80%"),
            "toggle_bt_drawer": self._toggle_bt_drawer,
            "bt_toggle_radio": self.hub.peripherals.toggle_bt_radio if not self.demo else lambda: self.hub.show_toast("Demo: Bluetooth toggled"),
            "bt_open_settings": self.hub.peripherals.open_bt_settings,
            "media_command": self.hub.toggle_demo_media,
            "media_like": self.hub.toggle_demo_media_like,
            "hue_command": self.hub.toggle_demo_hue,
            "ecoflow_charge": lambda: self.hub.toggle_demo_ecoflow("cycle_charge_watts"),
            "ecoflow_usb": lambda: self.hub.toggle_demo_ecoflow("toggle_usb"),
            "ecoflow_dc": lambda: self.hub.toggle_demo_ecoflow("toggle_dc12v"),
            "ecoflow_beep": lambda: self.hub.toggle_demo_ecoflow("toggle_beep"),
            "custom_open_url": self.hub.custom_json.open_url,
            "todoist_cycle": self.hub.todoist.cycle_project if not self.demo else lambda: None,
            "todoist_complete": self.hub.toggle_demo_todoist_complete,
            "todoist_open": self.hub.todoist.open_app,
            "tile_cycle": self._cycle_tile_pack,
            "calendar_change_month": self._change_month,
            "calendar_today": self._calendar_today,
        }

    def _toggle_bt_drawer(self) -> None:
        self._bt_drawer_open = not self._bt_drawer_open
        if self._bt_drawer_open and not self.demo:
            threading.Thread(target=self.hub.peripherals.refresh_bluetooth, daemon=True).start()
        self._dirty = True

    def _change_month(self, delta: int) -> None:
        y, m = self._calendar_month
        val = y * 12 + m - 1 + delta
        self._calendar_month = (val // 12, val % 12 + 1)
        self._calendar_follow_today = False
        self._dirty = True

    def _calendar_today(self) -> None:
        today = datetime.date.today()
        self._calendar_month = (today.year, today.month)
        self._calendar_follow_today = True
        self._dirty = True

    def _scroll_wing(self, side: str, delta: int) -> None:
        step = 48 if delta > 0 else -48
        if side == "left":
            nxt = max(0, min(self._left_max_scroll, self._left_scroll - step))
            if nxt != self._left_scroll:
                self._left_scroll = nxt
                self._dirty = True
        else:
            nxt = max(0, min(self._right_max_scroll, self._right_scroll - step))
            if nxt != self._right_scroll:
                self._right_scroll = nxt
                self._dirty = True

    def _on_click(self, event, hotspots: List[Hotspot], is_right: bool) -> None:
        self._last_interact_ts = time.time()
        x, y = event.x, event.y
        for x1, y1, x2, y2, lcb, rcb, _ in reversed(hotspots):
            if x1 <= x <= x2 and y1 <= y <= y2:
                cb = rcb if is_right else lcb
                if cb:
                    cb()
                return

    def _on_motion(self, event, hotspots: List[Hotspot], is_left: bool) -> None:
        x, y = event.x, event.y
        new_hover = None
        for x1, y1, x2, y2, _, _, hid in reversed(hotspots):
            if x1 <= x <= x2 and y1 <= y <= y2:
                new_hover = hid
                break
        cur = self._left_hover if is_left else self._right_hover
        if new_hover != cur:
            if is_left:
                self._left_hover = new_hover
                self.left_canvas.config(cursor="hand2" if new_hover else "")
            else:
                self._right_hover = new_hover
                self.right_canvas.config(cursor="hand2" if new_hover else "")
            self._dirty = True

    def _on_leave(self, is_left: bool) -> None:
        if is_left and self._left_hover is not None:
            self._left_hover = None
            self.left_canvas.config(cursor="")
            self._dirty = True
        elif not is_left and self._right_hover is not None:
            self._right_hover = None
            self.right_canvas.config(cursor="")
            self._dirty = True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_all(self) -> None:
        snap = self.hub.snapshot()
        toast = self.hub.current_toast()
        actions = self._build_actions()

        for side, w, scroll, hover, canvas in (
            ("left", self.lw, self._left_scroll, self._left_hover, self.left_canvas),
            ("right", self.rw, self._right_scroll, self._right_hover, self.right_canvas),
        ):
            if not self.renderer.has_widgets(side, snap):
                continue
            im, spots, lay = self.renderer.render_wing(
                side,
                w,
                self.wing_h,
                snap,
                scroll_offset=scroll,
                hover=hover,
                bt_drawer_open=self._bt_drawer_open,
                calendar_month=self._calendar_month,
                now=self._clock_now,
                toast_message=toast,
                tile_pack_label=self._tile_pack_label,
                tile_busy=self._tile_busy,
                actions=actions,
            )
            if side == "left":
                self._left_hotspots = spots
                self._left_max_scroll = lay.max_scroll
            else:
                self._right_hotspots = spots
                self._right_max_scroll = lay.max_scroll

            attr = f"_{side}_tk_img"
            photo = getattr(self, attr)
            if photo is None or (photo.width(), photo.height()) != im.size:
                canvas.delete("all")
                photo = ImageTk.PhotoImage(im, master=self.root)
                setattr(self, attr, photo)
                canvas.create_image(0, 0, anchor="nw", image=photo)
            else:
                photo.paste(im)
            self._surfaces[side].present(im)

        self._render_center()

    def _render_center(self, force: bool = False) -> None:
        if not self.center_overlay:
            return
        snap = self.hub.snapshot()
        w_key = repr(snap.get("weather"))
        for side in CENTER_SIDES:
            size = self._center_sizes[side]
            key = (w_key, self._clock_minute, size, self.theme.mode, self.theme.accent)
            if not force and self._frame_cache.get(side) == key:
                continue
            im = self.renderer.render_center_overlay(side, size, snap, now=self._clock_now)
            self._surfaces[side].present(im)
            self._frame_cache[side] = key

    # ------------------------------------------------------------------
    # Full Phone Gallery Modal (Tier 2 ADB)
    # ------------------------------------------------------------------

    def open_full_gallery_modal(self) -> None:
        if self.demo:
            self.hub.show_toast("Demo: Phone Gallery requires Android ADB")
            return
        self._last_interact_ts = time.time()
        if self._gallery_win is not None and self._gallery_win.winfo_exists():
            self._gallery_win.deiconify()
            self._gallery_win.lift()
            return

        win = tk.Toplevel(self.root)
        self._gallery_win = win
        dev_name = self.hub.phone.device_name
        win.title(f"{self.i18n.t('phone.gallery_btn')} — {dev_name}")
        win.configure(bg="#14161D")
        win.attributes("-topmost", True)
        gw, gh = 920, 680
        sx = (win.winfo_screenwidth() - gw) // 2
        sy = (win.winfo_screenheight() - gh) // 2
        win.geometry(f"{gw}x{gh}+{sx}+{sy}")

        hdr = tk.Frame(win, bg="#1C1F29", height=54)
        hdr.pack(fill="x", side="top")
        tk.Label(hdr, text=dev_name, font=("Segoe UI", 13, "bold"), fg="#F4F6FB", bg="#1C1F29").pack(side="left", padx=16, pady=12)

        status_var = tk.StringVar(value=self.i18n.t("phone.gallery_loading"))
        tk.Label(hdr, textvariable=status_var, font=("Segoe UI", 10), fg="#9AA4B8", bg="#1C1F29").pack(side="right", padx=16)

        cat_frame = tk.Frame(hdr, bg="#1C1F29")
        cat_frame.pack(side="left", padx=12)

        body = tk.Frame(win, bg="#14161D")
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(body, bg="#14161D", highlightthickness=0)
        scrollbar = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        grid_frame = tk.Frame(canvas, bg="#14161D")
        grid_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=grid_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=12, pady=10)
        scrollbar.pack(side="right", fill="y")
        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        thumb_refs: List[ImageTk.PhotoImage] = []

        def _copy_item(path: str) -> None:
            if copy_image_and_file_to_clipboard(path):
                status_var.set(self.i18n.t("phone.toast_copied", name=os.path.basename(path)))
                self.hub.show_toast(self.i18n.t("phone.toast_copied", name=os.path.basename(path)))

        def _add_card(idx: int, item: Dict[str, Any], pil_t: Image.Image) -> None:
            if not win.winfo_exists():
                return
            tk_t = ImageTk.PhotoImage(pil_t)
            thumb_refs.append(tk_t)
            card = tk.Frame(grid_frame, bg="#202430", bd=1, relief="solid", padx=6, pady=6)
            card.grid(row=idx // 4, column=idx % 4, padx=6, pady=6, sticky="nsew")
            lbl = tk.Label(card, image=tk_t, bg="#202430", cursor="hand2")
            lbl.pack()
            lbl.bind("<Button-1>", lambda _e, p=item["local_path"]: _copy_item(p))
            tk.Label(card, text=f"{item['name']} · {item['time_str']}", font=("Segoe UI", 9, "bold"), fg="#E2E8F0", bg="#202430").pack(pady=4)
            btn_row = tk.Frame(card, bg="#202430")
            btn_row.pack(fill="x")
            tk.Button(btn_row, text=self.i18n.t("phone.gallery_copy"), bg="#2563EB", fg="white", relief="flat", command=lambda p=item["local_path"]: _copy_item(p)).pack(side="left", fill="x", expand=True, padx=(0, 3))
            tk.Button(btn_row, text=self.i18n.t("phone.gallery_open"), bg="#334155", fg="white", relief="flat", command=lambda p=item["local_path"]: self.hub.phone.open_photo_file(p)).pack(side="right", padx=(3, 0))

        def load_category(cat_key: str) -> None:
            status_var.set(self.i18n.t("phone.gallery_loading"))
            for w in grid_frame.winfo_children():
                w.destroy()
            thumb_refs.clear()

            def _worker():
                items = self.hub.phone.fetch_gallery_items(category=cat_key, limit=28)
                for idx, item in enumerate(items):
                    if not win.winfo_exists() or not self.hub.phone.ensure_gallery_file(item):
                        continue
                    pil_t = get_photo_thumb(self.renderer.img_cache, item["local_path"], 200, 145, 10)
                    if pil_t:
                        win.after(0, lambda i=idx, it=item, pt=pil_t: _add_card(i, it, pt))
                if win.winfo_exists():
                    win.after(0, lambda: status_var.set(self.i18n.t("phone.gallery_loaded", count=len(items))))

            threading.Thread(target=_worker, daemon=True).start()

        for key, i18n_key in (
            ("all", "phone.gallery_all"),
            ("screenshots", "phone.gallery_screenshots"),
            ("camera", "phone.gallery_camera"),
            ("downloads", "phone.gallery_downloads"),
        ):
            tk.Button(
                cat_frame,
                text=self.i18n.t(i18n_key),
                font=("Segoe UI", 9, "bold"),
                bg="#2D3343",
                fg="#F1F5F9",
                relief="flat",
                padx=10,
                pady=4,
                command=lambda k=key: load_category(k),
            ).pack(side="left", padx=3)

        load_category("all")

    def run(self) -> None:
        self.root.mainloop()
