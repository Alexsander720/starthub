"""Universal Custom JSON metrics provider (Tier 2, opt-in).

Reads any local JSON file or localhost HTTP endpoint (e.g. Home Assistant, Pi-hole,
AI quota tracker, custom scripts) and exposes up to 3 structured metrics per card.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

import requests

from ..config import REPO_ROOT
from ..surface import IS_WINDOWS, popen_on_default_desktop

logger = logging.getLogger("starthub.providers.custom_json")

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_allowed_source_url(url: str, allow_remote: bool = False) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if allow_remote:
        return bool(parsed.hostname)
    return (parsed.hostname or "").lower() in LOCAL_HOSTS


def normalize_custom_card(card_cfg: Dict[str, Any], payload: Any) -> Dict[str, Any]:
    """Validate and normalize a custom JSON payload into a predictable card snapshot."""
    fallback_title = str(card_cfg.get("title") or "Custom Metrics")
    card_id = str(card_cfg.get("id") or fallback_title.lower().replace(" ", "_"))
    click_url = str(card_cfg.get("click_url") or "")

    if not isinstance(payload, dict):
        return {
            "id": card_id,
            "title": fallback_title,
            "badge": "",
            "subtitle": "",
            "url": click_url,
            "ok": False,
            "metrics": [],
        }

    raw_metrics = payload.get("metrics") or []
    metrics: List[Dict[str, Any]] = []
    if isinstance(raw_metrics, list):
        for item in raw_metrics[:3]:
            if not isinstance(item, dict):
                continue
            pct = item.get("percent")
            if isinstance(pct, (int, float)) and not isinstance(pct, bool):
                pct_val: Optional[int] = max(0, min(100, int(round(pct))))
            else:
                pct_val = None
            metrics.append(
                {
                    "label": str(item.get("label") or ""),
                    "value": str(item.get("value") if item.get("value") is not None else "—"),
                    "percent": pct_val,
                    "sublabel": str(item.get("sublabel") or ""),
                    "tag": str(item.get("tag") or ""),
                    "status": str(item.get("status") or "info").lower(),
                }
            )

    return {
        "id": card_id,
        "title": str(payload.get("title") or fallback_title),
        "badge": str(payload.get("badge") or ""),
        "subtitle": str(payload.get("subtitle") or ""),
        "url": str(payload.get("url") or click_url),
        "ok": True,
        "metrics": metrics,
    }


class CustomJsonProvider:
    def __init__(
        self,
        config: Dict[str, Any],
        on_change: Optional[Callable[[], None]] = None,
        base_dir: Optional[Path] = None,
    ):
        self.config = config
        self.on_change = on_change
        self.base_dir = Path(base_dir) if base_dir else REPO_ROOT
        self.allow_remote = bool(config.get("allow_remote_urls", False))
        self.cards_cfg: List[Dict[str, Any]] = [
            c for c in (config.get("cards") or []) if isinstance(c, dict)
        ]

        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._next_due: Dict[str, float] = {}
        self._cards: Dict[str, Dict[str, Any]] = {}
        for idx, c in enumerate(self.cards_cfg):
            cid = str(c.get("id") or f"custom_{idx}")
            self._cards[cid] = normalize_custom_card(c, None)

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for idx, c in enumerate(self.cards_cfg):
                cid = str(c.get("id") or f"custom_{idx}")
                if cid in self._cards:
                    card = dict(self._cards[cid])
                    card["metrics"] = [dict(m) for m in card.get("metrics", [])]
                    out.append(card)
            return out

    def start(self) -> None:
        if not self.config.get("enabled", False) or not self.cards_cfg:
            return
        threading.Thread(target=self._loop, name="starthub-custom-json", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _read_source(self, source: str) -> Any:
        src = source.strip()
        if not src:
            return None
        if src.startswith(("http://", "https://")):
            if not is_allowed_source_url(src, allow_remote=self.allow_remote):
                logger.warning("Blocked non-local custom_json URL (set allow_remote_urls=true to enable)")
                return None
            resp = requests.get(src, timeout=3.0)
            resp.raise_for_status()
            return resp.json()
        path = Path(src)
        if not path.is_absolute():
            path = self.base_dir / path
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def poll_card(self, card_cfg: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
        cid = str(card_cfg.get("id") or f"custom_{idx}")
        source = str(card_cfg.get("source") or "")
        try:
            raw = self._read_source(source)
            normalized = normalize_custom_card(card_cfg, raw)
        except Exception as exc:
            logger.debug("Custom JSON %s refresh failed: %s", cid, type(exc).__name__)
            normalized = normalize_custom_card(card_cfg, None)
        with self._lock:
            changed = self._cards.get(cid) != normalized
            self._cards[cid] = normalized
        if changed and self.on_change:
            self.on_change()
        return normalized

    def poll_all(self) -> List[Dict[str, Any]]:
        for idx, c in enumerate(self.cards_cfg):
            self.poll_card(c, idx)
        return self.snapshot()

    def _loop(self) -> None:
        while not self._stopped.is_set():
            now = time.monotonic()
            for idx, c in enumerate(self.cards_cfg):
                cid = str(c.get("id") or f"custom_{idx}")
                interval = max(2.0, float(c.get("refresh_sec", 15.0)))
                if now >= self._next_due.get(cid, 0.0):
                    self._next_due[cid] = now + interval
                    self.poll_card(c, idx)
            if self._stopped.wait(1.0):
                break

    @staticmethod
    def open_url(url: str) -> None:
        if not url or not url.startswith(("http://", "https://")):
            return
        if IS_WINDOWS:
            popen_on_default_desktop(["cmd.exe", "/c", "start", "", url], no_window=True)
