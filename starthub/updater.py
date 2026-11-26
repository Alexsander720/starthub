"""Non-intrusive GitHub Releases update checker (checks at most once per 24h, never auto-executes code)."""
from __future__ import annotations

import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests

from . import __version__
from .config import DEFAULT_CACHE_DIR, read_json_safe, write_json_atomic

logger = logging.getLogger("starthub.updater")

REPO_SLUG = "Alexsander720/starthub"
RELEASES_API_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{REPO_SLUG}/releases"
CHECK_TTL_SEC = 24 * 3600


def parse_semver(version: str) -> Tuple[int, int, int]:
    cleaned = str(version or "").strip().lstrip("vV")
    nums = [int(x) for x in re.findall(r"\d+", cleaned)[:3]]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def is_newer_version(latest: str, current: str = __version__) -> bool:
    return parse_semver(latest) > parse_semver(current)


def check_for_updates(
    *,
    cache_dir: Optional[Path] = None,
    force: bool = False,
    session: Optional[requests.Session] = None,
    timeout: float = 4.0,
) -> Dict[str, Any]:
    """Check GitHub Releases API for a newer StartHub version (cached 24h unless force=True)."""
    cdir = Path(cache_dir or DEFAULT_CACHE_DIR)
    cache_file = cdir / "update_check.json"

    if not force:
        cached = read_json_safe(cache_file, {})
        if isinstance(cached, dict) and (time.time() - float(cached.get("checked_at", 0) or 0)) < CHECK_TTL_SEC:
            latest = str(cached.get("latest_version") or __version__)
            return {
                "checked": True,
                "current_version": __version__,
                "latest_version": latest,
                "update_available": is_newer_version(latest, __version__),
                "url": str(cached.get("url") or RELEASES_PAGE_URL),
                "from_cache": True,
                "error": "",
            }

    http = session or requests
    try:
        resp = http.get(
            RELEASES_API_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"StartHub/{__version__}"},
            timeout=timeout,
        )
        if resp.status_code == 404:
            # Repository has no published releases yet
            result = {
                "checked": True,
                "current_version": __version__,
                "latest_version": __version__,
                "update_available": False,
                "url": RELEASES_PAGE_URL,
                "checked_at": time.time(),
                "from_cache": False,
                "error": "",
            }
            write_json_atomic(cache_file, result)
            return result
        resp.raise_for_status()
        data = resp.json()
        tag = str(data.get("tag_name") or __version__).lstrip("vV")
        html_url = str(data.get("html_url") or RELEASES_PAGE_URL)
        result = {
            "checked": True,
            "current_version": __version__,
            "latest_version": tag,
            "update_available": is_newer_version(tag, __version__),
            "url": html_url,
            "checked_at": time.time(),
            "from_cache": False,
            "error": "",
        }
        write_json_atomic(cache_file, result)
        return result
    except Exception as exc:
        logger.debug("Update check skipped: %s", type(exc).__name__)
        return {
            "checked": False,
            "current_version": __version__,
            "latest_version": __version__,
            "update_available": False,
            "url": RELEASES_PAGE_URL,
            "from_cache": False,
            "error": type(exc).__name__,
        }
