"""Visibility-gated CPU, GPU (NVIDIA NVML / AMD & Intel Windows PDH), and RAM monitor (Tier 1)."""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional

from ..surface import CREATE_NO_WINDOW, IS_WINDOWS

logger = logging.getLogger("starthub.providers.system_monitor")


class _WindowsPdhGpuReader:
    """Universal Windows 10/11 GPU utilization reader (AMD / Intel / NVIDIA) via PDH GPU Engine counters."""

    def __init__(self) -> None:
        self._pdh = None
        self._hq = None
        self._counter = None
        self._primed = False
        self._failed = False

    def read_percent(self) -> Optional[int]:
        if not IS_WINDOWS or self._failed:
            return None
        try:
            if self._pdh is None:
                import win32pdh

                self._pdh = win32pdh
                self._hq = win32pdh.OpenQuery()
                self._counter = win32pdh.AddEnglishCounter(
                    self._hq, r"\GPU Engine(*engtype_3D)\Utilization Percentage"
                )
                win32pdh.CollectQueryData(self._hq)
                self._primed = True
                return None
            self._pdh.CollectQueryData(self._hq)
            vals = self._pdh.GetFormattedCounterArray(self._counter, self._pdh.PDH_FMT_DOUBLE)
            total = sum(float(v) for v in vals.values() if isinstance(v, (int, float)) and v >= 0)
            return max(0, min(100, int(round(total))))
        except Exception:
            self._failed = True
            self.close()
            return None

    def close(self) -> None:
        if self._pdh is not None and self._hq is not None:
            try:
                self._pdh.CloseQuery(self._hq)
            except Exception:
                pass
        self._hq = None
        self._counter = None


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
        self._nvidia_smi_missing = False
        self._pdh_gpu = _WindowsPdhGpuReader()
        self._gpu_backend = "none"
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
            self._due = 0.0
        else:
            self._visible.clear()

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        # Prime psutil CPU baseline immediately so first visible frame never shows "—"
        try:
            import psutil

            self._psutil = psutil
            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        threading.Thread(target=self._loop, name="starthub-monitor", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()
        self._pdh_gpu.close()

    def _loop(self) -> None:
        # One initial background sample so the very first open already displays live numbers
        time.sleep(0.25)
        if not self._stopped.is_set():
            self.poll_once()
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
                result["cpu"] = round(psutil.cpu_percent(interval=0.05))
            else:
                result["cpu"] = round(self._psutil.cpu_percent(interval=None))
            result["ram"] = round(self._psutil.virtual_memory().percent)
        except Exception:
            pass

        # 1) NVIDIA NVML (fast, zero subprocesses, includes GPU temperature)
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
                self._gpu_backend = "nvml"
            except Exception:
                self._nvml_failed = True

        # 2) NVIDIA nvidia-smi fallback (cached permanently if missing so AMD/Intel never spam CreateProcess)
        if result["gpu"] is None and not self._nvidia_smi_missing:
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
                self._gpu_backend = "nvidia-smi"
            except FileNotFoundError:
                self._nvidia_smi_missing = True
            except Exception:
                self._nvidia_smi_missing = True

        # 3) Universal Windows PDH GPU Engine counter fallback (AMD Radeon / Intel Arc / iGPU)
        if result["gpu"] is None:
            pdh_pct = self._pdh_gpu.read_percent()
            if pdh_pct is not None:
                result["gpu"] = pdh_pct
                self._gpu_backend = "windows-pdh"

        with self._lock:
            changed = self._state != result
            self._state = result
        if changed and self.on_change:
            self.on_change()
        return result
