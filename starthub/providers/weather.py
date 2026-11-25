"""Open-Meteo weather provider with free city geocoding (Tier 1, zero API keys)."""
from __future__ import annotations

import datetime
import logging
import math
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

import requests

from ..config import read_json_safe, write_json_atomic

logger = logging.getLogger("starthub.providers.weather")


def geocode_city(
    city_name: str,
    *,
    count: int = 5,
    language: str = "en",
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """Look up city coordinates & timezone via Open-Meteo's free zero-key Geocoding API."""
    query = str(city_name or "").strip()
    if len(query) < 2:
        return []
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urlencode(
        {"name": query, "count": str(max(1, min(10, count))), "language": language, "format": "json"}
    )
    http = session or requests
    try:
        resp = http.get(url, timeout=(4, 6))
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        out: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            lat = item.get("latitude")
            lon = item.get("longitude")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue
            parts = [str(item.get("name") or query)]
            if item.get("admin1"):
                parts.append(str(item["admin1"]))
            if item.get("country"):
                parts.append(str(item["country"]))
            out.append(
                {
                    "name": str(item.get("name") or query),
                    "display": ", ".join(parts),
                    "latitude": round(float(lat), 4),
                    "longitude": round(float(lon), 4),
                    "timezone": str(item.get("timezone") or "auto"),
                }
            )
        return out
    except Exception as exc:
        logger.debug("City geocode failed for %s: %s", query, type(exc).__name__)
        return []


def build_open_meteo_url(config: Dict[str, Any]) -> str:
    units = str(config.get("units", "metric")).lower()
    lat = config.get("latitude")
    lon = config.get("longitude")
    lat_val = float(lat) if lat is not None else 50.4501
    lon_val = float(lon) if lon is not None else 30.5234
    params = {
        "latitude": f"{lat_val:.4f}",
        "longitude": f"{lon_val:.4f}",
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
        self.config = dict(config)
        self.cache_file = Path(cache_dir) / "weather_cache.json"
        self.on_change = on_change
        self.interval = max(300, int(config.get("refresh_minutes", 20)) * 60)
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._geocoded_city: Optional[str] = None

        cached = read_json_safe(self.cache_file, {})
        if not isinstance(cached, dict):
            cached = {}
        # Drop cached data if user switched city or units
        if (cached.get("city") and cached.get("city") != config.get("city")) or (
            cached.get("units") and cached.get("units") != config.get("units")
        ):
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

    def _maybe_resolve_city_coords(self, session: Optional[requests.Session] = None) -> None:
        city = str(self.config.get("city") or "").strip()
        if not city or not self.config.get("auto_geocode", True):
            return
        lat = self.config.get("latitude")
        lon = self.config.get("longitude")
        # Auto-geocode when coords are omitted OR user changed city name while leaving default Kyiv coords
        is_default_kyiv_coords = (
            lat is not None
            and lon is not None
            and abs(float(lat) - 50.4501) < 0.001
            and abs(float(lon) - 30.5234) < 0.001
            and city.lower() not in ("kyiv", "kiev", "киев", "київ")
        )
        if (lat is None or lon is None or is_default_kyiv_coords) and self._geocoded_city != city.lower():
            matches = geocode_city(city, count=1, session=session)
            if matches:
                self.config["latitude"] = matches[0]["latitude"]
                self.config["longitude"] = matches[0]["longitude"]
                if self.config.get("timezone") in (None, "", "auto"):
                    self.config["timezone"] = matches[0].get("timezone") or "auto"
                self._geocoded_city = city.lower()

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
        http = session or requests
        try:
            self._maybe_resolve_city_coords(session=session)
            url = build_open_meteo_url(self.config)
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
