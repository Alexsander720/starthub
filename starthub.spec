# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building standalone StartHub.exe (no Python required on user PC)."""

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

datas = [
    (str(ROOT / "locales"), "locales"),
    (str(ROOT / "packs"), "packs"),
    (str(ROOT / "config.example.json"), "."),
]

hiddenimports = [
    "pystray._win32",
    "PIL._tkinter_finder",
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "win32event",
    "win32clipboard",
    "win32pdh",
    "winrt.windows.media.control",
    "winrt.windows.storage.streams",
    "pynvml",
    "hid",
    "paho.mqtt.client",
    "google.protobuf",
]

a = Analysis(
    [str(ROOT / "starthub" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
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
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="StartHub",
)
