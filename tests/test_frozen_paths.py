"""Tests for PyInstaller frozen-EXE entrypoint, BUNDLE_DIR/APP_DIR separation, and console=False safety."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

import starthub.config as cfg_mod
from starthub.__main__ import _ensure_stdio_streams
from starthub.surface import build_interactive_respawn_cmd


def test_entrypoint_and_launcher_have_zero_relative_imports():
    root = Path(__file__).resolve().parents[1]
    launcher = root / "starthub_launcher.py"
    main_py = root / "starthub" / "__main__.py"
    assert launcher.is_file()
    for path in (launcher, main_py):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"Relative import found in {path.name}:{node.lineno}"


def test_resolve_app_dirs_separates_bundle_and_app_dir_when_frozen(monkeypatch, tmp_path: Path):
    fake_install = tmp_path / "StartHubPortable"
    fake_internal = fake_install / "_internal"
    fake_internal.mkdir(parents=True)
    fake_exe = fake_install / "StartHub.exe"
    fake_exe.write_bytes(b"")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_internal), raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))

    is_frozen, bundle_dir, app_dir = cfg_mod.resolve_app_dirs()
    assert is_frozen is True
    assert bundle_dir == fake_internal.resolve()
    assert app_dir == fake_install.resolve()
    assert bundle_dir != app_dir


def test_find_bundled_file_prefers_app_dir_over_bundle_dir(monkeypatch, tmp_path: Path):
    app_dir = tmp_path / "app"
    bundle_dir = app_dir / "_internal"
    app_dir.mkdir()
    bundle_dir.mkdir()
    (bundle_dir / "config.example.json").write_text('{"from": "bundle"}', encoding="utf-8")

    monkeypatch.setattr(cfg_mod, "APP_DIR", app_dir)
    monkeypatch.setattr(cfg_mod, "BUNDLE_DIR", bundle_dir)

    # Falls back to BUNDLE_DIR when absent in APP_DIR
    assert cfg_mod.find_bundled_file("config.example.json") == bundle_dir / "config.example.json"

    # Prefers user APP_DIR when present
    (app_dir / "config.example.json").write_text('{"from": "app"}', encoding="utf-8")
    assert cfg_mod.find_bundled_file("config.example.json") == app_dir / "config.example.json"


def test_respawn_cmd_in_frozen_mode_never_passes_dash_m_starthub(tmp_path: Path):
    fake_exe = str(tmp_path / "My StartHub" / "StartHub.exe")
    cmd, cwd = build_interactive_respawn_cmd(
        ["--demo", "--preview"],
        is_frozen=True,
        executable=fake_exe,
    )
    assert "-m" not in cmd
    assert "pythonw" not in cmd.lower()
    assert "StartHub.exe" in cmd
    assert "--on-default" in cmd and "--demo" in cmd and "--preview" in cmd
    assert Path(cwd) == Path(fake_exe).parent


def test_ensure_stdio_streams_recovers_from_none_in_gui_subsystem(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _ensure_stdio_streams([])
    assert sys.stdout is not None and sys.stderr is not None
    # Writable without raising AttributeError
    sys.stdout.write("")
    sys.stderr.write("")
    sys.stdout.close()
    sys.stderr.close()
