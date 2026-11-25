"""Zero-key Pomodoro / Focus Timer provider (Tier 1)."""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from ..i18n import I18n
from ..surface import IS_WINDOWS


class FocusTimerProvider:
    """Lightweight 25/5 Pomodoro focus timer with zero idle CPU usage when paused."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: I18n,
        on_change: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self.work_sec = max(60, int(config.get("work_minutes", 25)) * 60)
        self.break_sec = max(60, int(config.get("break_minutes", 5)) * 60)
        self.sound_on_done = bool(config.get("sound_on_done", True))

        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._wake = threading.Event()
        self._phase = "work"  # "work" | "break"
        self._running = False
        self._remaining = float(self.work_sec)
        self._last_tick = 0.0
        self._sessions_done = 0

    def _phase_total(self, phase: str) -> int:
        return self.work_sec if phase == "work" else self.break_sec

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            rem = self._remaining
            if self._running and self._last_tick > 0:
                rem = max(0.0, rem - (time.monotonic() - self._last_tick))
            total = self._phase_total(self._phase)
            pct = max(0.0, min(100.0, (1.0 - rem / max(1, total)) * 100.0))
            secs = int(round(rem))
            return {
                "phase": self._phase,
                "running": self._running,
                "remaining_sec": secs,
                "total_sec": total,
                "percent": pct,
                "display": f"{secs // 60:02d}:{secs % 60:02d}",
                "sessions_done": self._sessions_done,
            }

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=self._loop, name="starthub-focus", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()
        self._wake.set()

    def toggle(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._running:
                self._remaining = max(0.0, self._remaining - (now - self._last_tick))
                self._running = False
            else:
                if self._remaining <= 0.5:
                    self._remaining = float(self._phase_total(self._phase))
                self._running = True
                self._last_tick = now
                self._wake.set()
        if self.on_change:
            self.on_change()

    def reset(self) -> None:
        with self._lock:
            self._running = False
            self._remaining = float(self._phase_total(self._phase))
            self._last_tick = 0.0
        if self.on_change:
            self.on_change()

    def switch_phase(self) -> None:
        with self._lock:
            self._phase = "break" if self._phase == "work" else "work"
            self._running = False
            self._remaining = float(self._phase_total(self._phase))
            self._last_tick = 0.0
        if self.on_change:
            self.on_change()

    def _play_chime(self) -> None:
        if not self.sound_on_done or not IS_WINDOWS:
            return
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stopped.is_set():
            with self._lock:
                running = self._running
            if not running:
                self._wake.wait(timeout=2.0)
                self._wake.clear()
                continue

            if self._stopped.wait(0.5):
                break

            finished_phase: Optional[str] = None
            with self._lock:
                if self._running:
                    now = time.monotonic()
                    self._remaining = max(0.0, self._remaining - (now - self._last_tick))
                    self._last_tick = now
                    if self._remaining <= 0.0:
                        finished_phase = self._phase
                        self._running = False
                        if finished_phase == "work":
                            self._sessions_done += 1
                            self._phase = "break"
                        else:
                            self._phase = "work"
                        self._remaining = float(self._phase_total(self._phase))
                        self._last_tick = 0.0

            if finished_phase:
                self._play_chime()
                if self.on_toast:
                    key = "focus.done_work" if finished_phase == "work" else "focus.done_break"
                    self.on_toast(self.i18n.t(key))
            if self.on_change:
                self.on_change()
