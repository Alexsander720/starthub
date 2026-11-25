"""Win32 layered rendering surface, DWM acrylic blur, rounded corners, triggers, hotkeys, and OS helpers."""
from __future__ import annotations

import ctypes
import io
import logging
import os
import subprocess
import sys
import threading
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageFont

logger = logging.getLogger("starthub.surface")

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

if IS_WINDOWS:
    from ctypes import wintypes
    try:
        import win32api
        import win32clipboard
        import win32con
        import win32gui
        import win32process
    except ImportError:  # pragma: no cover - headless Windows without pywin32
        win32api = win32clipboard = win32con = win32gui = win32process = None  # type: ignore
else:  # pragma: no cover - non-Windows CI
    wintypes = None  # type: ignore
    win32api = win32clipboard = win32con = win32gui = win32process = None  # type: ignore


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        # Per-Monitor V2 DPI awareness on Windows 10/11 when available
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


class SingleInstanceGuard:
    """Windows named mutex guard preventing duplicate StartHub tray/window instances."""

    def __init__(self, name: str = "Local\\StartHub_SingleInstance"):
        self.name = name
        self._handle: Optional[int] = None
        self.already_running: bool = False

    def acquire(self) -> bool:
        if not IS_WINDOWS:
            return True
        try:
            k32 = ctypes.windll.kernel32
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            k32.CreateMutexW.restype = wintypes.HANDLE
            handle = k32.CreateMutexW(None, False, self.name)
            last_err = k32.GetLastError()
            if not handle:
                return True
            self._handle = int(handle)
            # ERROR_ALREADY_EXISTS = 183
            if last_err == 183:
                self.already_running = True
                return False
            return True
        except Exception:
            return True

    def release(self) -> None:
        if self._handle and IS_WINDOWS:
            try:
                ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(self._handle))
            except Exception:
                pass
            self._handle = None


def ensure_interactive_desktop() -> None:
    """If launched from a non-interactive desktop session, respawn onto WinSta0\\Default."""
    if not IS_WINDOWS or win32process is None or win32con is None:
        return
    if any(flag in sys.argv for flag in ("--render-test", "--on-default", "--doctor")):
        return
    try:
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hdesk = u32.GetThreadDesktop(k32.GetCurrentThreadId())
        buf = ctypes.create_unicode_buffer(256)
        u32.GetUserObjectInformationW(hdesk, 2, buf, 512, None)
        desk_name = buf.value
        if desk_name.lower() != "default":
            si = win32process.STARTUPINFO()
            si.lpDesktop = "WinSta0\\Default"
            si.dwFlags = win32con.STARTF_USESHOWWINDOW
            si.wShowWindow = win32con.SW_SHOW
            py_exe = sys.executable
            pyw_exe = os.path.join(os.path.dirname(py_exe), "pythonw.exe")
            if not os.path.exists(pyw_exe):
                pyw_exe = py_exe
            extra = " ".join(a for a in sys.argv[1:] if a != "--on-default")
            cmd_line = f'"{pyw_exe}" -m starthub --on-default {extra}'.strip()
            win32process.CreateProcess(
                None, cmd_line, None, None, False, 0, None, os.getcwd(), si
            )
            sys.exit(0)
    except Exception:
        pass


def popen_on_default_desktop(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    no_window: bool = False,
):
    """Launch a child process bound to WinSta0\\Default when running on Windows."""
    flags = CREATE_NO_WINDOW if no_window else 0
    if IS_WINDOWS and win32process is not None and win32con is not None:
        try:
            si = win32process.STARTUPINFO()
            si.lpDesktop = "WinSta0\\Default"
            si.dwFlags = win32con.STARTF_USESHOWWINDOW
            si.wShowWindow = win32con.SW_SHOWNORMAL
            cmd_line = subprocess.list2cmdline(cmd)
            win32process.CreateProcess(None, cmd_line, None, None, False, flags, env, cwd, si)
            return True
        except Exception:
            pass
    return subprocess.Popen(cmd, cwd=cwd, env=env, creationflags=flags)


def apply_panel_blur(hwnd: int, enabled: bool = True) -> None:
    """Enable or disable native Windows blur-behind on a layered top-level HWND."""
    if not IS_WINDOWS:
        return

    class Accent(ctypes.Structure):
        _fields_ = [
            ("state", ctypes.c_int),
            ("flags", ctypes.c_int),
            ("color", ctypes.c_uint),
            ("animation", ctypes.c_int),
        ]

    class Attribute(ctypes.Structure):
        _fields_ = [
            ("attribute", ctypes.c_int),
            ("data", ctypes.c_void_p),
            ("size", ctypes.c_size_t),
        ]

    # 3 = ACCENT_ENABLE_BLURBEHIND, 0 = ACCENT_DISABLED
    accent = Accent(3 if enabled else 0, 0, 0, 0)
    attribute = Attribute(19, ctypes.addressof(accent), ctypes.sizeof(accent))
    setter = ctypes.windll.user32.SetWindowCompositionAttribute
    setter.argtypes = [wintypes.HWND, ctypes.POINTER(Attribute)]
    if not setter(hwnd, ctypes.byref(attribute)):
        raise ctypes.WinError()


def apply_win11_rounded(
    hwnd: int,
    round_mode: int = 2,
    border_rgb: Optional[Tuple[int, int, int]] = None,
) -> None:
    """Apply Windows 11 DWM rounded corners and optional native border color."""
    if not IS_WINDOWS:
        return
    try:
        pref = ctypes.c_int(round_mode)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_int(33), ctypes.byref(pref), ctypes.sizeof(pref)
        )
    except Exception:
        pass
    try:
        if border_rgb is None:
            colorref = 0xFFFFFFFE  # DWMWA_COLOR_NONE
        else:
            r, g, b = border_rgb
            colorref = r | (g << 8) | (b << 16)
        cval = ctypes.c_uint(colorref)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_int(34), ctypes.byref(cval), ctypes.sizeof(cval)
        )
    except Exception:
        pass


def is_window_cloaked(hwnd: int) -> bool:
    """Check DWMWA_CLOAKED (14) — Windows 11 cloaks the native Start Menu instead of hiding it."""
    if not IS_WINDOWS:
        return False
    try:
        cloaked = ctypes.c_int(0)
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_int(14), ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        return hr == 0 and cloaked.value != 0
    except Exception:
        return False


def get_dwm_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Return pixel-accurate visible frame bounds via DWMWA_EXTENDED_FRAME_BOUNDS, falling back to GetWindowRect."""
    if not IS_WINDOWS or win32gui is None:
        return None
    try:
        rect = wintypes.RECT()
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_int(9), ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if hr == 0 and (rect.right - rect.left) > 200 and (rect.bottom - rect.top) > 200:
            return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    except Exception:
        pass
    try:
        r = win32gui.GetWindowRect(hwnd)
        if (r[2] - r[0]) > 200 and (r[3] - r[1]) > 200:
            return (int(r[0]), int(r[1]), int(r[2]), int(r[3]))
    except Exception:
        pass
    return None


_PID_NAME_CACHE: Dict[int, str] = {}


def _process_basename(pid: int) -> str:
    if pid in _PID_NAME_CACHE:
        return _PID_NAME_CACHE[pid]
    if not IS_WINDOWS or pid <= 0:
        return ""
    name = ""
    try:
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            try:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value).lower()
            finally:
                k32.CloseHandle(handle)
    except Exception:
        pass
    if len(_PID_NAME_CACHE) > 256:
        _PID_NAME_CACHE.clear()
    _PID_NAME_CACHE[pid] = name
    return name


def find_native_win11_start_rect() -> Optional[Tuple[int, int, int, int]]:
    """Detect the native Windows 11 Start Menu (StartMenuExperienceHost.exe) when visibly open."""
    if not IS_WINDOWS or win32gui is None or win32process is None:
        return None
    found: List[Tuple[int, int, int, int]] = []

    def _cb(hwnd: int, _extra) -> bool:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.GetClassName(hwnd) != "Windows.UI.Core.CoreWindow":
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if _process_basename(pid) != "startmenuexperiencehost.exe":
                return True
            if is_window_cloaked(hwnd):
                return True
            rect = get_dwm_window_rect(hwnd)
            if rect and (rect[2] - rect[0]) >= 300 and (rect[3] - rect[1]) >= 300:
                found.append(rect)
                return False
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return found[0] if found else None


# ------------------------------------------------------------------
# Global Hotkey Listener (zero-CPU blocking Win32 message thread)
# ------------------------------------------------------------------

_MOD_MAP = {
    "alt": 0x0001,
    "ctrl": 0x0002,
    "control": 0x0002,
    "shift": 0x0004,
    "win": 0x0008,
    "super": 0x0008,
}

_VK_MAP: Dict[str, int] = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pgup": 0x21,
    "pgdn": 0x22,
    "`": 0xC0,
    "tilde": 0xC0,
}
for _i in range(1, 13):
    _VK_MAP[f"f{_i}"] = 0x6F + _i


def parse_hotkey_spec(spec: str) -> Optional[Tuple[int, int]]:
    """Parse a human-readable hotkey like 'Alt+Space' or 'Ctrl+Shift+H' into (modifiers, vk)."""
    if not spec or not isinstance(spec, str):
        return None
    parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0x4000  # MOD_NOREPEAT
    vk: Optional[int] = None
    for tok in parts:
        if tok in _MOD_MAP:
            mods |= _MOD_MAP[tok]
        elif tok in _VK_MAP:
            vk = _VK_MAP[tok]
        elif len(tok) == 1 and tok.isalnum():
            vk = ord(tok.upper())
        else:
            return None
    if vk is None or mods == 0x4000:
        return None
    return (mods, vk)


class GlobalHotkey:
    """Registers one Win32 system hotkey on a lightweight thread and invokes on_trigger()."""

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    HOTKEY_ID = 0x5748  # 'SH'

    def __init__(self, spec: str, on_trigger: Callable[[], None]):
        self.spec = spec
        self.on_trigger = on_trigger
        self._thread: Optional[threading.Thread] = None
        self._tid: Optional[int] = None
        self._ready = threading.Event()
        self.registered = False

    def start(self) -> bool:
        if not IS_WINDOWS:
            return False
        parsed = parse_hotkey_spec(self.spec)
        if not parsed:
            return False
        mods, vk = parsed

        def _worker():
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            self._tid = int(k32.GetCurrentThreadId())
            ok = bool(u32.RegisterHotKey(None, self.HOTKEY_ID, mods, vk))
            self.registered = ok
            self._ready.set()
            if not ok:
                logger.info("Could not register global hotkey %s (already in use)", self.spec)
                return
            try:
                msg = wintypes.MSG()
                while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                        try:
                            self.on_trigger()
                        except Exception:
                            pass
            finally:
                try:
                    u32.UnregisterHotKey(None, self.HOTKEY_ID)
                except Exception:
                    pass
                self.registered = False

        self._thread = threading.Thread(target=_worker, name="starthub-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=1.0)
        return self.registered

    def stop(self) -> None:
        if self._tid and IS_WINDOWS:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._tid, self.WM_QUIT, 0, 0)
            except Exception:
                pass
        self._tid = None
        self.registered = False


class LayeredSurface:
    """Top-down premultiplied 32-bit DIB presented via UpdateLayeredWindow with fade alpha."""

    if IS_WINDOWS:
        class BitmapInfo(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("width", wintypes.LONG),
                ("height", wintypes.LONG),
                ("planes", wintypes.WORD),
                ("bitcount", wintypes.WORD),
                ("compression", wintypes.DWORD),
                ("sizeimage", wintypes.DWORD),
                ("xppm", wintypes.LONG),
                ("yppm", wintypes.LONG),
                ("used", wintypes.DWORD),
                ("important", wintypes.DWORD),
            ]

        class Blend(ctypes.Structure):
            _fields_ = [
                ("op", ctypes.c_ubyte),
                ("flags", ctypes.c_ubyte),
                ("alpha", ctypes.c_ubyte),
                ("format", ctypes.c_ubyte),
            ]

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.dc = None
        self.bitmap = None
        self.old = None
        self.bits = None
        self.size: Optional[Tuple[int, int]] = None
        self.last_alpha: int = 255
        if not IS_WINDOWS or win32gui is None:
            return

        gdi = ctypes.windll.gdi32
        gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi.CreateCompatibleDC.restype = wintypes.HDC
        gdi.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(self.BitmapInfo),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        gdi.CreateDIBSection.restype = wintypes.HBITMAP
        gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi.SelectObject.restype = wintypes.HANDLE
        gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi.DeleteDC.argtypes = [wintypes.HDC]
        ctypes.windll.user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND,
            wintypes.HDC,
            ctypes.POINTER(wintypes.POINT),
            ctypes.POINTER(wintypes.SIZE),
            wintypes.HDC,
            ctypes.POINTER(wintypes.POINT),
            wintypes.DWORD,
            ctypes.POINTER(self.Blend),
            wintypes.DWORD,
        ]
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED)

    def close(self) -> None:
        if self.dc and IS_WINDOWS:
            gdi = ctypes.windll.gdi32
            gdi.SelectObject(self.dc, self.old)
            gdi.DeleteObject(self.bitmap)
            gdi.DeleteDC(self.dc)
            self.dc = None

    def present(self, image: Image.Image, alpha: Optional[int] = None) -> None:
        if not IS_WINDOWS or win32gui is None:
            return
        if self.size != image.size:
            self.close()
            width, height = image.size
            info = self.BitmapInfo(
                ctypes.sizeof(self.BitmapInfo),
                width,
                -height,
                1,
                32,
                0,
                width * height * 4,
                0,
                0,
                0,
                0,
            )
            self.dc = ctypes.windll.gdi32.CreateCompatibleDC(None)
            self.bits = ctypes.c_void_p()
            self.bitmap = ctypes.windll.gdi32.CreateDIBSection(
                self.dc, ctypes.byref(info), 0, ctypes.byref(self.bits), None, 0
            )
            if not self.bitmap or not self.bits:
                raise ctypes.WinError()
            self.old = ctypes.windll.gdi32.SelectObject(self.dc, self.bitmap)
            self.size = image.size
        pixels = image.convert("RGBa").tobytes("raw", "BGRa")
        ctypes.memmove(self.bits, pixels, len(pixels))
        self.represent(self.last_alpha if alpha is None else alpha)

    def represent(self, alpha: int = 255) -> None:
        if not self.dc or not IS_WINDOWS:
            return
        clamped = max(0, min(255, int(alpha)))
        self.last_alpha = clamped
        size, source = wintypes.SIZE(*self.size), wintypes.POINT(0, 0)
        blend = self.Blend(0, 0, clamped, 1)
        if not ctypes.windll.user32.UpdateLayeredWindow(
            self.hwnd, None, None, ctypes.byref(size), self.dc, ctypes.byref(source), 0, ctypes.byref(blend), 2
        ):
            raise ctypes.WinError()


class FontBank:
    """Cached TrueType font loader with cross-platform fallback for headless tests/CI."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[int, str], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}

    def get(self, size: int, weight: str = "regular"):
        key = (size, weight)
        if key in self._cache:
            return self._cache[key]
        if weight == "bold":
            candidates = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        elif weight == "semibold":
            candidates = ["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        elif weight == "light":
            candidates = ["segoeuil.ttf", "segoeui.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        else:
            candidates = ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        for name in candidates:
            try:
                font = ImageFont.truetype(name, size)
                self._cache[key] = font
                return font
            except Exception:
                continue
        font = ImageFont.load_default()
        self._cache[key] = font
        return font


def copy_image_and_file_to_clipboard(file_path: str) -> bool:
    """Copy an image to Windows clipboard as both CF_DIB and CF_HDROP."""
    if not IS_WINDOWS or win32clipboard is None or not os.path.exists(file_path):
        return False

    class DROPFILES(ctypes.Structure):
        _fields_ = [
            ("pFiles", ctypes.c_uint),
            ("x", ctypes.c_long),
            ("y", ctypes.c_long),
            ("fNC", ctypes.c_int),
            ("fWide", ctypes.c_int),
        ]

    try:
        img = Image.open(file_path).convert("RGB")
        out = io.BytesIO()
        img.save(out, "BMP")
        dib_data = out.getvalue()[14:]

        df = DROPFILES(ctypes.sizeof(DROPFILES), 0, 0, 0, 1)
        files_utf16 = (os.path.abspath(file_path) + "\0\0").encode("utf-16le")
        hdrop_data = bytes(df) + files_utf16

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, dib_data)
            win32clipboard.SetClipboardData(win32con.CF_HDROP, hdrop_data)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:
        return False


def copy_text_to_clipboard(text: str) -> bool:
    if not IS_WINDOWS or win32clipboard is None:
        return False
    try:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardUnicodeText(str(text))
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:
        return False
