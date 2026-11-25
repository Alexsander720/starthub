"""Visibility-gated Disk Storage & Live Network Throughput provider (Tier 1, zero API keys)."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("starthub.providers.storage_network")


def format_bytes_rate(bps: float) -> str:
    val = max(0.0, float(bps))
    if val < 1024.0:
        return f"{val:.0f} B/s"
    kb = val / 1024.0
    if kb < 1024.0:
        return f"{kb:.0f} KB/s" if kb >= 100 else f"{kb:.1f} KB/s"
    mb = kb / 1024.0
    if mb < 1024.0:
        return f"{mb:.1f} MB/s"
    return f"{mb / 1024.0:.2f} GB/s"


def format_gb(num_bytes: int) -> str:
    gb = max(0.0, float(num_bytes) / (1024.0 ** 3))
    if gb >= 1024.0:
        return f"{gb / 1024.0:.1f} TB"
    if gb >= 100.0:
        return f"{gb:.0f} GB"
    return f"{gb:.1f} GB"


class StorageNetworkProvider:
    """Monitors fixed drive usage and real-time network upload/download rates while StartHub is visible."""

    def __init__(
        self,
        config: Dict[str, Any],
        on_change: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.on_change = on_change
        self.interval = max(0.75, float(config.get("poll_interval_sec", 2.0)))
        self.max_drives = max(1, min(4, int(config.get("max_drives", 3))))
        self.drives_cfg = list(config.get("drives") or ["auto"])

        self._lock = threading.Lock()
        self._visible = threading.Event()
        self._stopped = threading.Event()
        self._due = 0.0
        self._last_net: Optional[tuple[int, int, float]] = None
        self._state: Dict[str, Any] = {
            "drives": [],
            "down_bps": 0.0,
            "up_bps": 0.0,
            "down_text": "0 KB/s",
            "up_text": "0 KB/s",
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._state,
                "drives": [dict(d) for d in self._state.get("drives", [])],
            }

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._visible.set()
            self._due = 0.0
        else:
            self._visible.clear()
            self._last_net = None

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=self._loop, name="starthub-storage-net", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _collect_drives(self, psutil) -> List[Dict[str, Any]]:
        targets: List[str] = []
        if not self.drives_cfg or self.drives_cfg == ["auto"]:
            try:
                for p in psutil.disk_partitions(all=False):
                    opts = (p.opts or "").lower()
                    if "cdrom" in opts or not p.fstype:
                        continue
                    mp = p.mountpoint
                    if mp and mp not in targets:
                        targets.append(mp)
            except Exception:
                pass
        else:
            for item in self.drives_cfg:
                s = str(item or "").strip()
                if not s:
                    continue
                if len(s) == 1 and s.isalpha():
                    s = f"{s.upper()}:\\"
                elif len(s) == 2 and s[1] == ":":
                    s = f"{s.upper()}\\"
                if os.path.exists(s):
                    targets.append(s)

        out: List[Dict[str, Any]] = []
        for mp in targets[: self.max_drives]:
            try:
                u = psutil.disk_usage(mp)
                label = mp.rstrip("\\/")
                if not label:
                    label = "/"
                out.append(
                    {
                        "label": label,
                        "percent": int(round(u.percent)),
                        "free_bytes": int(u.free),
                        "total_bytes": int(u.total),
                        "free_text": format_gb(u.free),
                        "total_text": format_gb(u.total),
                    }
                )
            except Exception:
                continue
        return out

    def poll_once(self) -> Dict[str, Any]:
        try:
            import psutil
        except Exception:
            return self.snapshot()

        drives = self._collect_drives(psutil)
        down_bps = 0.0
        up_bps = 0.0
        try:
            io = psutil.net_io_counters()
            now = time.monotonic()
            if io is not None:
                if self._last_net is not None:
                    prev_rx, prev_tx, prev_t = self._last_net
                    dt = max(0.1, now - prev_t)
                    down_bps = max(0.0, (io.bytes_recv - prev_rx) / dt)
                    up_bps = max(0.0, (io.bytes_sent - prev_tx) / dt)
                self._last_net = (int(io.bytes_recv), int(io.bytes_sent), now)
        except Exception:
            pass

        result = {
            "drives": drives,
            "down_bps": down_bps,
            "up_bps": up_bps,
            "down_text": format_bytes_rate(down_bps),
            "up_text": format_bytes_rate(up_bps),
        }
        with self._lock:
            changed = self._state != result
            self._state = result
        if changed and self.on_change:
            self.on_change()
        return result

    def _loop(self) -> None:
        # Initial read so disks show immediately when first opened
        self.poll_once()
        while not self._stopped.wait(0.25):
            if not self._visible.is_set():
                continue
            now = time.monotonic()
            if now >= self._due:
                self._due = now + self.interval
                self.poll_once()
