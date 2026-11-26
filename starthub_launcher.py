"""Top-level PyInstaller entrypoint for StartHub.exe (avoids relative-import errors in frozen builds)."""
from __future__ import annotations

from starthub.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
