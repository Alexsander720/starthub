# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building standalone StartHub.exe (no Python required on user PC)."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "locales"), "locales"),
    (str(ROOT / "packs"), "packs"),
    (str(ROOT / "config.example.json"), "."),
]

binaries = []
for _pkg in ("winrt", "hid"):
    try:
        binaries += collect_dynamic_libs(_pkg)
    except Exception:
        pass

hiddenimports = [
    "tools.tile_switcher",
    "pystray._win32",
    "PIL._tkinter_finder",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "win32event",
    "win32clipboard",
    "win32pdh",
    "win32file",
    "win32security",
    "ntsecuritycon",
    "pywintypes",
    "winrt.runtime",
    "winrt.system",
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.media",
    "winrt.windows.media.control",
    "winrt.windows.storage.streams",
    "pynvml",
    "hid",
    "paho.mqtt.client",
    "google.protobuf",
    "google.protobuf.json_format",
]

for _pkg in ("starthub", "winrt"):
    try:
        hiddenimports += collect_submodules(_pkg)
    except Exception:
        pass

hiddenimports = sorted(set(hiddenimports))

a = Analysis(
    [str(ROOT / "starthub_launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "scipy", "pandas", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StartHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="StartHub",
)
