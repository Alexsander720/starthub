"""Open-Meteo weather provider (Tier 1, free, zero API keys)."""
from __future__ import annotations

import datetime
import logging
import math
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode

import requests

from ..config import read_json_safe, write_json_atomic

logger = logging.getLogger("starthub.providers.weather")


def build_open_meteo_url(config: Dict[str, Any]) -> str:
    units = str(config.get("units", "metric")).lower()
    params = {
        "latitude": f"{float(config.get('latitude', 50.4501)):.4f}",
        "longitude": f"{float(config.get('longitude', 30.5234)):.4f}",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day,relative_humidity_2m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,sunrise,sunset",
        "timezone": str(config.get("timezone") or "auto"),
        "wind_speed_unit": "mph" if units == "imperial" else "ms",
        "forecast_days": "5",
    }
    if units == "imperial":
        params["temperature_unit"] = "fahrenheit"
    return "https://api.open-meteo.com/v1/forecast?" + urlencode(params)


def validate_open_meteo_payload(payload: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Weather payload must be a JSON object")
    current = payload.get("current")
    daily = payload.get("daily")
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise ValueError("Missing current/daily weather sections")

    def is_num(v: Any) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

    for key in ("temperature_2m", "apparent_temperature", "wind_speed_10m", "weather_code"):
        if not is_num(current.get(key)):
            raise ValueError(f"Invalid weather field: {key}")

    dates = daily.get("time")
    if not isinstance(dates, list) or not (3 <= len(dates) <= 7) or not all(isinstance(d, str) for d in dates):
        raise ValueError("Invalid forecast dates")
    for day in dates:
        datetime.date.fromisoformat(day)
    for field in ("temperature_2m_max", "temperature_2m_min", "weather_code"):
        vals = daily.get(field)
        if not isinstance(vals, list) or len(vals) != len(dates) or not all(is_num(x) for x in vals):
            raise ValueError(f"Invalid forecast field: {field}")
    return current, daily


class WeatherProvider:
    def __init__(
        self,
        config: Dict[str, Any],
        cache_dir: Path,
        on_change: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.cache_file = Path(cache_dir) / "weather_cache.json"
        self.on_change = on_change
        self.interval = max(300, int(config.get("refresh_minutes", 20)) * 60)
        self._lock = threading.Lock()
        self._stopped = threading.Event()

        cached = read_json_safe(self.cache_file, {})
        if not isinstance(cached, dict):
            cached = {}
        # Drop cached data if user switched city/units
        if cached.get("city") and cached.get("city") != config.get("city"):
            cached = {}
        self._state: Dict[str, Any] = cached or {
            "city": str(config.get("city") or "Kyiv"),
            "units": str(config.get("units") or "metric"),
            "current": {},
            "daily": {},
            "updated_at": 0,
            "offline": False,
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=self._loop, name="starthub-weather", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _loop(self) -> None:
        try:
            age = time.time() - float(self._state.get("updated_at", 0))
            delay = max(0.0, min(float(self.interval), float(self.interval) - age))
        except (TypeError, ValueError):
            delay = 0.0
        if self._stopped.wait(delay):
            return
        while not self._stopped.is_set():
            self.poll_once()
            if self._stopped.wait(self.interval):
                break

    def poll_once(self, session: Optional[requests.Session] = None) -> Dict[str, Any]:
        url = build_open_meteo_url(self.config)
        http = session or requests
        try:
            resp = http.get(url, timeout=(4, 8))
            resp.raise_for_status()
            current, daily = validate_open_meteo_payload(resp.json())
            value = {
                "city": str(self.config.get("city") or "Kyiv"),
                "units": str(self.config.get("units") or "metric"),
                "current": current,
                "daily": daily,
                "updated_at": time.time(),
                "offline": False,
            }
            write_json_atomic(self.cache_file, value)
            with self._lock:
                self._state = value
        except Exception as exc:
            with self._lock:
                self._state = {**self._state, "offline": True}
            logger.debug("Weather refresh failed: %s", type(exc).__name__)
        if self.on_change:
            self.on_change()
        return self.snapshot()
