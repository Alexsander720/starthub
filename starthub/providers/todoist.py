"""Todoist REST API v1 provider (Tier 2, opt-in)."""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional

import requests

from ..config import read_json_safe, write_json_atomic
from ..i18n import I18n
from ..surface import IS_WINDOWS, popen_on_default_desktop

logger = logging.getLogger("starthub.providers.todoist")


class TodoistProvider:
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
        self.interval = max(10.0, float(config.get("poll_interval_sec", 30.0)))
        self._prefs_file = Path(cache_dir) / "todoist_prefs.json"
        self._lock = threading.Lock()
        self._stopped = threading.Event()

        prefs = read_json_safe(self._prefs_file, {})
        configured_projects = [
            {"id": str(p["id"]), "name": str(p["name"])}
            for p in (config.get("projects") or [])
            if isinstance(p, dict) and p.get("id") and p.get("name")
        ]
        self._auto_discover_projects = len(configured_projects) == 0
        default_projects = configured_projects or [{"id": "__all__", "name": self.i18n.t("todoist.default_project")}]

        self._state: Dict[str, Any] = {
            "configured": bool(str(config.get("api_token") or "").strip()),
            "projects": default_projects,
            "proj_idx": int(prefs.get("proj_idx", 0)) if isinstance(prefs, dict) else 0,
            "all_tasks": [],
            "tasks": [],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "configured": self._state["configured"],
                "projects": [dict(p) for p in self._state["projects"]],
                "proj_idx": self._state["proj_idx"],
                "tasks": [dict(t) for t in self._state["tasks"]],
                "all_tasks": [dict(t) for t in self._state["all_tasks"]],
            }

    def start(self) -> None:
        if not self.config.get("enabled", False):
            return
        threading.Thread(target=self._loop, name="starthub-todoist", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {str(self.config.get('api_token') or '').strip()}"}

    def _loop(self) -> None:
        while not self._stopped.is_set():
            self.poll_once()
            if self._stopped.wait(self.interval):
                break

    def poll_once(self) -> None:
        token = str(self.config.get("api_token") or "").strip()
        if not token:
            with self._lock:
                self._state["configured"] = False
            return
        try:
            headers = self._headers()
            if self._auto_discover_projects:
                pr = requests.get("https://api.todoist.com/api/v1/projects", headers=headers, timeout=5.0)
                if pr.status_code == 200:
                    pdata = pr.json()
                    plist = pdata.get("results", pdata) if isinstance(pdata, dict) else pdata
                    discovered = [
                        {"id": str(p["id"]), "name": str(p.get("name", "Project"))}
                        for p in plist
                        if isinstance(p, dict) and p.get("id")
                    ]
                    if discovered:
                        with self._lock:
                            self._state["projects"] = discovered
            r = requests.get("https://api.todoist.com/api/v1/tasks", headers=headers, timeout=5.0)
            if r.status_code == 200:
                data = r.json()
                all_tasks = data.get("results", data) if isinstance(data, dict) else data
                if not isinstance(all_tasks, list):
                    all_tasks = []
                with self._lock:
                    self._state["configured"] = True
                    self._state["all_tasks"] = all_tasks
                    self._filter_locked()
                if self.on_change:
                    self.on_change()
        except Exception as exc:
            logger.debug("Todoist refresh failed: %s", type(exc).__name__)

    def _filter_locked(self) -> None:
        projs = self._state["projects"]
        if not projs:
            self._state["tasks"] = []
            return
        idx = self._state["proj_idx"] % len(projs)
        self._state["proj_idx"] = idx
        target_pid = projs[idx]["id"]
        all_tasks = self._state["all_tasks"]
        if target_pid == "__all__":
            filtered = [t for t in all_tasks if not t.get("checked") and not t.get("is_completed")]
        else:
            filtered = [
                t
                for t in all_tasks
                if str(t.get("project_id", "")) == target_pid and not t.get("checked") and not t.get("is_completed")
            ]
        filtered.sort(key=lambda x: (-int(x.get("priority", 1)), int(x.get("child_order", 0))))
        self._state["tasks"] = filtered

    def cycle_project(self) -> None:
        with self._lock:
            if not self._state["projects"]:
                return
            self._state["proj_idx"] = (self._state["proj_idx"] + 1) % len(self._state["projects"])
            self._filter_locked()
            idx = self._state["proj_idx"]
        write_json_atomic(self._prefs_file, {"proj_idx": idx})
        if self.on_change:
            self.on_change()

    def complete_task(self, idx: int) -> None:
        with self._lock:
            tasks = self._state["tasks"]
            if idx < 0 or idx >= len(tasks):
                return
            task = tasks.pop(idx)
            tid = task.get("id")
            self._state["all_tasks"] = [t for t in self._state["all_tasks"] if t.get("id") != tid]
        if self.on_toast:
            self.on_toast(self.i18n.t("todoist.toast_done", title=str(task.get("content", ""))[:30]))
        if self.on_change:
            self.on_change()

        token = str(self.config.get("api_token") or "").strip()
        if not token or not tid:
            return

        def _worker():
            try:
                requests.post(
                    f"https://api.todoist.com/api/v1/tasks/{tid}/close",
                    headers=self._headers(),
                    timeout=5.0,
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def upcoming_tasks(self, today: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
        today = today or datetime.date.today()
        valid_dates = {today.isoformat(), (today + datetime.timedelta(days=1)).isoformat()}
        with self._lock:
            tasks = [
                dict(t)
                for t in self._state.get("all_tasks", [])
                if not t.get("checked")
                and not t.get("is_completed")
                and isinstance(t.get("due"), dict)
                and str(t["due"].get("date", ""))[:10] in valid_dates
            ]
        return sorted(tasks, key=lambda t: (t["due"]["date"], -int(t.get("priority", 1))))

    @staticmethod
    def open_app() -> None:
        if IS_WINDOWS:
            popen_on_default_desktop(["cmd.exe", "/c", "start", "", "todoist://"], no_window=True)
