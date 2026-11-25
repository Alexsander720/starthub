"""Build a clean, verified StartHub release ZIP and SHA-256 checksum inside dist/."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starthub import __version__

EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "cache",
    "logs",
    "dist",
    "build",
}
EXCLUDED_FILES = {"config.json", ".env", "hue_config.json", "spotify_token.json"}


def build_zip(version: str = __version__, out_dir: Path = REPO_ROOT / "dist") -> tuple[Path, Path]:
    # Enforce privacy scan gate before packaging
    scan = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "scan_private.py")], cwd=str(REPO_ROOT))
    if scan.returncode != 0:
        raise RuntimeError("Privacy scan failed; aborting release package build")

    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"starthub-{version}.zip"
    sha_path = out_dir / f"starthub-{version}.zip.sha256"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(REPO_ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT)
            if any(part in EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.name.lower() in EXCLUDED_FILES or path.suffix.lower() in {".pyc", ".pyo", ".log", ".reg"}:
                continue
            zf.write(path, arcname=f"starthub-{version}/{rel.as_posix()}")

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return zip_path, sha_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build StartHub release ZIP + SHA-256")
    parser.add_argument("--version", default=__version__)
    args = parser.parse_args()
    zip_path, sha_path = build_zip(args.version)
    print(f"Built: {zip_path} ({zip_path.stat().st_size:,} bytes)")
    print(f"SHA256: {sha_path.read_text(encoding='utf-8').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
