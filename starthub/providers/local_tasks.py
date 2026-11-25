"""Zero-key local checklist task provider (Tier 1 default fallback when Todoist is not configured)."""
from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from ..config import read_json_safe, write_json_atomic
from ..i18n import I18n

logger = logging.getLogger("starthub.providers.local_tasks")


class LocalTasksProvider:
    """Offline JSON-backed quick checklist so every user gets a working Tasks card out of the box."""

    def __init__(
        self,
        config: Dict[str, Any],
        cache_dir: Path,
        i18n: I18n,
        on_change: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self.store_path = Path(cache_dir) / "local_tasks.json"
        self._lock = threading.Lock()
        self._last_completed: Optional[Dict[str, Any]] = None

        self._lists: List[Dict[str, Any]] = self._load_or_seed()
        self._list_idx = 0

    def _seed_defaults(self) -> List[Dict[str, Any]]:
        title = str(self.config.get("title") or "").strip() or self.i18n.t("tasks.local_list")
        return [
            {
                "id": "local_today",
                "name": title,
                "tasks": [
                    {"id": "welcome_1", "content": self.i18n.t("tasks.welcome_1"), "priority": 2},
                    {"id": "welcome_2", "content": self.i18n.t("tasks.welcome_2"), "priority": 1},
                    {"id": "welcome_3", "content": self.i18n.t("tasks.welcome_3"), "priority": 1},
                ],
            }
        ]

    def _load_or_seed(self) -> List[Dict[str, Any]]:
        raw = read_json_safe(self.store_path, None)
        if isinstance(raw, dict) and isinstance(raw.get("lists"), list) and raw["lists"]:
            return raw["lists"]
        seeded = self._seed_defaults()
        write_json_atomic(self.store_path, {"lists": seeded, "updated_at": time.time()})
        return seeded

    def _persist_locked(self) -> None:
        write_json_atomic(self.store_path, {"lists": self._lists, "updated_at": time.time()})

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            idx = self._list_idx % max(1, len(self._lists))
            cur = self._lists[idx]
            projects = [{"id": lst["id"], "name": lst["name"]} for lst in self._lists]
            tasks = [dict(t) for t in cur.get("tasks", [])]
            return {
                "configured": True,
                "is_local": True,
                "projects": projects,
                "proj_idx": idx,
                "tasks": tasks,
                "all_tasks": tasks,
            }

    def add_task(self, content: str) -> bool:
        cleaned = str(content or "").strip()
        if not cleaned:
            return False
        with self._lock:
            idx = self._list_idx % max(1, len(self._lists))
            self._lists[idx].setdefault("tasks", []).insert(
                0,
                {"id": uuid.uuid4().hex[:10], "content": cleaned[:160], "priority": 1},
            )
            self._persist_locked()
        if self.on_toast:
            self.on_toast(self.i18n.t("tasks.toast_added", title=cleaned[:28]))
        if self.on_change:
            self.on_change()
        return True

    def complete_task(self, idx: int) -> None:
        with self._lock:
            lst = self._lists[self._list_idx % max(1, len(self._lists))]
            tasks = lst.get("tasks", [])
            if idx < 0 or idx >= len(tasks):
                return
            task = tasks.pop(idx)
            self._last_completed = task
            self._persist_locked()
        if self.on_toast:
            self.on_toast(self.i18n.t("todoist.toast_done", title=str(task.get("content", ""))[:30]))
        if self.on_change:
            self.on_change()

    def cycle_project(self) -> None:
        with self._lock:
            if len(self._lists) <= 1:
                return
            self._list_idx = (self._list_idx + 1) % len(self._lists)
        if self.on_change:
            self.on_change()
