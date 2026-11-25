"""Visibility-gated CPU, GPU (+ temperature), and RAM monitor (Tier 1, zero keys)."""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

from ..surface import CREATE_NO_WINDOW

logger = logging.getLogger("starthub.providers.system_monitor")


class SystemMonitorProvider:
    """Polls CPU/GPU/RAM only while StartHub panels are visible (0% idle background load)."""

    def __init__(
        self,
        config: Dict[str, Any],
        on_change: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.on_change = on_change
        self.interval = max(0.5, float(config.get("poll_interval_sec", 2.0)))
        self._lock = threading.Lock()
        self._visible = threading.Event()
        self._stopped = threading.Event()
        self._due = 0.0
        self._psutil = None
        self._nvml = None
        self._gpu_handle = None
        self._nvml_failed = False
        self._state: Dict[str, Any] = {
            "cpu": None,
            "gpu": None,
            "ram": None,
            "temperature": None,
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._visible.set()
        else:
            self._visible.clear()

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=self._loop, name="starthub-monitor", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _loop(self) -> None:
        while not self._stopped.wait(0.25):
            self.poll_if_due(time.monotonic())

    def poll_if_due(self, now: float) -> bool:
        if not self._visible.is_set() or now < self._due:
            return False
        self._due = now + self.interval
        self.poll_once()
        return True

    def poll_once(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"cpu": None, "ram": None, "gpu": None, "temperature": None}
        try:
            if self._psutil is None:
                import psutil

                self._psutil = psutil
                psutil.cpu_percent(interval=None)
            else:
                result["cpu"] = round(self._psutil.cpu_percent(interval=None))
            result["ram"] = round(self._psutil.virtual_memory().percent)
        except Exception:
            pass

        if not self._nvml_failed:
            try:
                if self._nvml is None:
                    import pynvml

                    pynvml.nvmlInit()
                    self._nvml = pynvml
                    self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                rates = self._nvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                result["gpu"] = int(rates.gpu)
                result["temperature"] = int(self._nvml.nvmlDeviceGetTemperature(self._gpu_handle, 0))
            except Exception:
                self._nvml_failed = True

        if result["gpu"] is None:
            try:
                output = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                    creationflags=CREATE_NO_WINDOW,
                    timeout=1.5,
                    text=True,
                )
                first = output.splitlines()[0].split(",")
                result["gpu"] = int(first[0].strip())
                result["temperature"] = int(first[1].strip())
            except Exception:
                pass

        with self._lock:
            changed = self._state != result
            self._state = result
        if changed and self.on_change:
            self.on_change()
        return result
