"""Safe Start11 Custom Tile Pack Switcher.

Discovers user tile packs under `packs/<pack_name>/pack.json`, backs up the Start11
registry branch before writing, validates all PNG paths inside the pack directory,
atomically updates CustomTiles with full rollback on error, and broadcasts START8_REFRESH.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKS_DIR = REPO_ROOT / "packs"
CACHE_DIR = REPO_ROOT / "cache"
STATE_FILE = CACHE_DIR / "tile_pack.txt"
REG_BASE = r"Software\Stardock\Start8\Start8.ini"
REG_TILES = REG_BASE + r"\Start8\CustomTiles"


def discover_packs(packs_dir: Path = DEFAULT_PACKS_DIR) -> List[Tuple[str, Path, Dict[str, object]]]:
    """Return sorted list of (pack_id, pack_folder, manifest_dict) for valid packs."""
    root = Path(packs_dir)
    if not root.is_dir():
        return []
    found = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "pack.json"
        if not manifest_path.is_file():
            continue
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tiles"), dict):
                found.append((child.name, child, data))
        except Exception:
            continue
    return found


def resolve_pack_tiles(pack_dir: Path, manifest: Dict[str, object]) -> Dict[str, str]:
    """Validate and resolve Start11 target -> absolute PNG path mapping inside pack_dir."""
    pack_root = pack_dir.resolve()
    raw_tiles = manifest.get("tiles")
    if not isinstance(raw_tiles, dict) or not raw_tiles:
        raise ValueError(f"Pack {pack_root.name!r} has no tiles defined in pack.json")
    resolved: Dict[str, str] = {}
    for target, filename in raw_tiles.items():
        if not isinstance(target, str) or not target.strip():
            raise ValueError("Invalid empty target key in pack.json")
        if not isinstance(filename, str) or not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            raise ValueError(f"Unsupported tile image filename: {filename!r}")
        candidate = (pack_root / filename).resolve()
        try:
            candidate.relative_to(pack_root)
        except ValueError as exc:
            raise ValueError(f"Path traversal blocked for tile {filename!r}") from exc
        if not candidate.is_file():
            raise FileNotFoundError(f"Tile image not found: {candidate}")
        resolved[target] = str(candidate)
    return resolved


def get_current_pack(state_file: Path = STATE_FILE) -> Optional[str]:
    try:
        if state_file.is_file():
            val = state_file.read_text(encoding="utf-8-sig").strip()
            return val or None
    except OSError:
        pass
    return None


def _write_state_atomic(state_file: Path, value: str) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(value + "\n", encoding="utf-8")
    os.replace(tmp, state_file)


@contextmanager
def _switch_lock(cache_dir: Path = CACHE_DIR):
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / "tile_switcher.lock"
    if sys.platform != "win32":
        yield
        return
    import msvcrt

    with lock_path.open("a+b") as handle:
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + 15.0
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if time.monotonic() > deadline:
                    raise RuntimeError("Another tile switch operation is in progress") from exc
                time.sleep(0.1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def broadcast_start11_refresh() -> int:
    if sys.platform != "win32":
        return 0
    user32 = ctypes.windll.user32
    msg = user32.RegisterWindowMessageW("START8_REFRESH")
    if not msg:
        raise OSError("Could not register START8_REFRESH message")
    user32.PostMessageW(0xFFFF, msg, 0, 0)
    for cls in ("Shell_TrayWnd", "DV2ControlHost"):
        hwnd = user32.FindWindowW(cls, None)
        if hwnd:
            user32.PostMessageW(hwnd, msg, 0, 0)
    return int(msg)


def apply_pack(pack_id: str, packs_dir: Path = DEFAULT_PACKS_DIR, state_file: Path = STATE_FILE, dry_run: bool = False) -> Dict[str, object]:
    packs = {pid: (folder, manifest) for pid, folder, manifest in discover_packs(packs_dir)}
    if pack_id not in packs:
        raise KeyError(f"Unknown pack {pack_id!r}. Available: {sorted(packs)}")
    folder, manifest = packs[pack_id]
    tiles = resolve_pack_tiles(folder, manifest)
    display_name = str(manifest.get("name") or pack_id)

    updates: Dict[str, str] = {}
    for target, img_path in tiles.items():
        updates[target] = img_path
        updates[target.replace("\\", "_")] = img_path

    if dry_run:
        return {"pack": pack_id, "name": display_name, "tiles": len(tiles), "updates": updates, "dry_run": True}

    if sys.platform != "win32":
        raise RuntimeError("Applying tile packs to Start11 registry is only supported on Windows.")

    import winreg

    with _switch_lock(state_file.parent):
        backup_dir = state_file.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_file = backup_dir / f"start11_backup_{stamp}.reg"
        subprocess.run(["reg", "export", f"HKCU\\{REG_BASE}", str(backup_file), "/y"], check=True, capture_output=True)
        if not backup_file.is_file() or backup_file.stat().st_size < 100:
            raise OSError("Start11 registry backup failed or was empty")

        previous: Dict[str, Optional[Tuple[object, int]]] = {}
        prev_state = get_current_pack(state_file)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_TILES, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as handle:
            for key in updates:
                try:
                    previous[key] = winreg.QueryValueEx(handle, key)
                except OSError:
                    previous[key] = None
            try:
                for key, path in updates.items():
                    winreg.SetValueEx(handle, key, 0, winreg.REG_SZ, path)
                for key, path in updates.items():
                    if winreg.QueryValueEx(handle, key) != (path, winreg.REG_SZ):
                        raise OSError(f"Registry readback mismatch for {key}")
                for sub_name, sub_val in (("CustomTilesPainting", "1"), ("CustomTilesText", "1"), ("CustomTilesIcon", "0")):
                    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{REG_BASE}\\Start8\\{sub_name}") as sub_k:
                        for key in updates:
                            winreg.SetValueEx(sub_k, key, 0, winreg.REG_SZ, sub_val)
                msg_id = broadcast_start11_refresh()
                _write_state_atomic(state_file, display_name)
            except BaseException:
                for key, prev in previous.items():
                    if prev is not None:
                        winreg.SetValueEx(handle, key, 0, prev[1], prev[0])
                    else:
                        try:
                            winreg.DeleteValue(handle, key)
                        except OSError:
                            pass
                if prev_state is not None:
                    _write_state_atomic(state_file, prev_state)
                try:
                    broadcast_start11_refresh()
                except OSError:
                    pass
                raise

        return {
            "pack": pack_id,
            "name": display_name,
            "tiles": len(tiles),
            "values_written": len(updates),
            "backup": str(backup_file),
            "refresh_msg": msg_id,
        }


def read_current_custom_tiles() -> Dict[str, str]:
    """Read current Start11 CustomTiles entries (target -> image path) from HKCU registry."""
    if sys.platform != "win32":
        raise RuntimeError("Reading Start11 registry is only supported on Windows.")
    import winreg

    entries: Dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_TILES, 0, winreg.KEY_READ) as handle:
            idx = 0
            while True:
                try:
                    name, val, reg_type = winreg.EnumValue(handle, idx)
                except OSError:
                    break
                idx += 1
                if reg_type == winreg.REG_SZ and isinstance(val, str) and name.strip() and val.strip():
                    entries[name.strip()] = val.strip()
    except FileNotFoundError:
        return {}
    return entries


def _safe_filename(stem: str, suffix: str, used: set[str]) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "tile"
    ext = suffix.lower() if suffix.lower() in (".png", ".jpg", ".jpeg") else ".png"
    cand = f"{cleaned}{ext}"
    n = 2
    while cand.lower() in used:
        cand = f"{cleaned}_{n}{ext}"
        n += 1
    used.add(cand.lower())
    return cand


def export_current_tiles(
    pack_id: str,
    *,
    display_name: Optional[str] = None,
    packs_dir: Path = DEFAULT_PACKS_DIR,
    entries: Optional[Dict[str, str]] = None,
    overwrite: bool = False,
) -> Dict[str, object]:
    """Snapshot current Start11 CustomTiles into a self-contained `packs/<pack_id>/pack.json` + images."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(pack_id or "").strip()).strip("_-")
    if not slug or slug in (".", ".."):
        raise ValueError(f"Invalid pack_id: {pack_id!r}")

    packs_root = Path(packs_dir).resolve()
    dest_dir = (packs_root / slug).resolve()
    dest_dir.relative_to(packs_root)  # guarantees no traversal

    manifest_path = dest_dir / "pack.json"
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(f"Pack {slug!r} already exists at {dest_dir} (pass --overwrite to replace)")

    raw = read_current_custom_tiles() if entries is None else dict(entries)

    # Deduplicate Start11's twin keys (`C:\Path\App.lnk` and `C:_Path_App.lnk`) keeping canonical backslash keys
    canonical_underscored = {k.replace("\\", "_") for k in raw if "\\" in k}
    filtered: Dict[str, str] = {}
    for target, img_str in sorted(raw.items()):
        if "\\" not in target and target in canonical_underscored:
            continue
        filtered[target] = img_str

    dest_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    copied_by_src: Dict[Path, str] = {}
    tiles_map: Dict[str, str] = {}
    skipped: List[str] = []

    for target, img_str in filtered.items():
        src = Path(img_str)
        if not src.is_file() or src.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            skipped.append(target)
            continue
        src_resolved = src.resolve()
        if src_resolved in copied_by_src:
            tiles_map[target] = copied_by_src[src_resolved]
            continue
        fname = _safe_filename(src.stem, src.suffix, used_names)
        dest_img = dest_dir / fname
        if src_resolved != dest_img.resolve():
            shutil.copy2(src_resolved, dest_img)
        copied_by_src[src_resolved] = fname
        tiles_map[target] = fname

    if not tiles_map:
        raise ValueError("No valid Start11 custom tile image files were found to export.")

    manifest = {
        "name": (display_name or slug.replace("_", " ").title()).strip(),
        "description": f"Exported from Start11 CustomTiles on {datetime.now():%Y-%m-%d}",
        "tiles": tiles_map,
    }
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, manifest_path)

    return {
        "pack": slug,
        "name": manifest["name"],
        "dir": str(dest_dir),
        "tiles_exported": len(tiles_map),
        "images_copied": len(copied_by_src),
        "skipped": len(skipped),
    }


def cycle_pack(packs_dir: Path = DEFAULT_PACKS_DIR, state_file: Path = STATE_FILE, apply: bool = False) -> Dict[str, object]:
    packs = discover_packs(packs_dir)
    if not packs:
        raise FileNotFoundError(f"No valid tile packs found in {packs_dir}")
    current = get_current_pack(state_file)
    names = [str(m.get("name") or pid) for pid, _, m in packs]
    ids = [pid for pid, _, _ in packs]
    if current in names:
        nxt_idx = (names.index(current) + 1) % len(ids)
    elif current in ids:
        nxt_idx = (ids.index(current) + 1) % len(ids)
    else:
        nxt_idx = 0
    return apply_pack(ids[nxt_idx], packs_dir=packs_dir, state_file=state_file, dry_run=not apply)


def main() -> int:
    parser = argparse.ArgumentParser(description="StartHub Start11 Custom Tile Pack Switcher")
    parser.add_argument("--packs-dir", type=Path, default=DEFAULT_PACKS_DIR, help="Directory containing pack folders")
    parser.add_argument("--list", action="store_true", help="List available tile packs")
    parser.add_argument("--current", action="store_true", help="Print active pack name")
    parser.add_argument("--pack", default=None, help="Select a specific pack folder name")
    parser.add_argument("--cycle", action="store_true", help="Select the next available pack")
    parser.add_argument("--apply", action="store_true", help="Write Start11 registry (omit for dry-run)")
    parser.add_argument("--export", metavar="PACK_ID", default=None, help="Export current Start11 CustomTiles into packs/<PACK_ID>/")
    parser.add_argument("--name", default=None, help="Display name for --export pack.json")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting an existing pack on --export")
    args = parser.parse_args()

    if args.export:
        receipt = export_current_tiles(
            args.export,
            display_name=args.name,
            packs_dir=args.packs_dir,
            overwrite=args.overwrite,
        )
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    if args.list:
        packs = discover_packs(args.packs_dir)
        for pid, folder, manifest in packs:
            print(f"{pid}: {manifest.get('name', pid)} ({len(manifest.get('tiles', {}))} tiles) [{folder}]")
        return 0
    if args.current:
        print(get_current_pack() or "")
        return 0
    if args.cycle:
        receipt = cycle_pack(args.packs_dir, apply=args.apply)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0
    if args.pack:
        receipt = apply_pack(args.pack, packs_dir=args.packs_dir, dry_run=not args.apply)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
