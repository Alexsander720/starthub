"""Localization loader and date/weather formatting for EN, RU, and UK."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import LOCALES_DIR

SUPPORTED_LANGUAGES = ("en", "ru", "uk")


class I18n:
    def __init__(self, lang: str = "en", locales_dir: Optional[Path] = None):
        self.locales_dir = locales_dir or LOCALES_DIR
        self._fallback = self._load_file("en")
        self.lang = lang.lower() if lang and lang.lower() in SUPPORTED_LANGUAGES else "en"
        self._strings = self._load_file(self.lang) if self.lang != "en" else dict(self._fallback)

    def _load_file(self, lang: str) -> Dict[str, Any]:
        path = self.locales_dir / f"{lang}.json"
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def t(self, key: str, **kwargs: Any) -> str:
        val = self._strings.get(key)
        if val is None:
            val = self._fallback.get(key, key)
        if not isinstance(val, str):
            return str(val)
        if kwargs:
            try:
                return val.format(**kwargs)
            except Exception:
                return val
        return val

    def list_value(self, key: str) -> List[str]:
        val = self._strings.get(key)
        if not isinstance(val, list):
            val = self._fallback.get(key, [])
        return list(val) if isinstance(val, list) else []

    def month_name(self, month: int) -> str:
        names = self.list_value("months")
        return names[month] if 1 <= month < len(names) else ""

    def month_genitive(self, month: int) -> str:
        names = self.list_value("months_genitive")
        return names[month] if 1 <= month < len(names) else self.month_name(month)

    def weekday_name(self, weekday: int) -> str:
        names = self.list_value("weekdays")
        return names[weekday] if 0 <= weekday < len(names) else ""

    def weekdays_short(self) -> List[str]:
        names = self.list_value("weekdays_short")
        return names if len(names) == 7 else ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

    def format_date_long(self, dt: datetime.date | datetime.datetime) -> str:
        if self.lang == "en":
            return f"{self.month_genitive(dt.month)} {dt.day}, {dt.year}"
        return f"{dt.day} {self.month_genitive(dt.month)} {dt.year}"

    def format_date_short(self, dt: datetime.date | datetime.datetime) -> str:
        if self.lang == "en":
            return f"{self.month_genitive(dt.month)} {dt.day}"
        return f"{dt.day} {self.month_genitive(dt.month)}"

    def format_relative_time(self, ts: float, now: Optional[datetime.datetime] = None) -> str:
        ref = now or datetime.datetime.now()
        dt = datetime.datetime.fromtimestamp(ts)
        if dt.date() == ref.date():
            return self.t("time.today", hm=dt.strftime("%H:%M"))
        if dt.date() == (ref.date() - datetime.timedelta(days=1)):
            return self.t("time.yesterday", hm=dt.strftime("%H:%M"))
        return f"{self.format_date_short(dt)} {dt:%H:%M}"

    def weather_description(self, code: Any) -> str:
        if code == 0:
            return self.t("weather.clear")
        if code in (1, 2):
            return self.t("weather.partly_cloudy")
        if code == 3:
            return self.t("weather.overcast")
        if code in (45, 48):
            return self.t("weather.fog")
        if code in (51, 53, 55, 56, 57):
            return self.t("weather.drizzle")
        if code in (61, 63, 65, 66, 67, 80, 81, 82):
            return self.t("weather.rain")
        if code in (71, 73, 75, 77, 85, 86):
            return self.t("weather.snow")
        if code in (95, 96, 99):
            return self.t("weather.thunderstorm")
        return self.t("weather.unknown")
