"""Win32 layered rendering surface, DWM acrylic blur, rounded corners, fonts, and OS helpers."""
from __future__ import annotations

import ctypes
import io
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageFont

IS_WINDOWS = sys.platform == "win32"
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

if IS_WINDOWS:
    from ctypes import wintypes
    try:
        import win32clipboard
        import win32con
        import win32gui
        import win32process
    except ImportError:  # pragma: no cover - headless Windows without pywin32
        win32clipboard = win32con = win32gui = win32process = None  # type: ignore
else:  # pragma: no cover - non-Windows CI
    wintypes = None  # type: ignore
    win32clipboard = win32con = win32gui = win32process = None  # type: ignore


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def ensure_interactive_desktop() -> None:
    """If launched from a non-interactive desktop session, respawn onto WinSta0\\Default."""
    if not IS_WINDOWS or win32process is None or win32con is None:
        return
    if any(flag in sys.argv for flag in ("--render-test", "--on-default")):
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


def apply_panel_blur(hwnd: int) -> None:
    """Enable native Windows blur-behind on a layered top-level HWND."""
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

    accent = Accent(3, 0, 0, 0)  # ACCENT_ENABLE_BLURBEHIND; tint comes from PIL surface alpha
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


class LayeredSurface:
    """Top-down premultiplied 32-bit DIB presented via UpdateLayeredWindow."""

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

    def present(self, image: Image.Image) -> None:
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
        self.represent()

    def represent(self) -> None:
        if not self.dc or not IS_WINDOWS:
            return
        size, source = wintypes.SIZE(*self.size), wintypes.POINT(0, 0)
        blend = self.Blend(0, 0, 255, 1)
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
