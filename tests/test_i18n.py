"""Tests for EN, RU, and UK localization completeness and formatting."""
from __future__ import annotations

import datetime
import json

from starthub.config import LOCALES_DIR
from starthub.i18n import SUPPORTED_LANGUAGES, I18n


def test_all_locales_have_complete_key_parity():
    en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    en_keys = set(en.keys())
    for lang in SUPPORTED_LANGUAGES:
        data = json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))
        missing = en_keys - set(data.keys())
        assert not missing, f"Locale {lang} missing keys: {sorted(missing)}"
        assert len(data["months"]) == 13
        assert len(data["months_genitive"]) == 13
        assert len(data["weekdays"]) == 7
        assert len(data["weekdays_short"]) == 7


def test_i18n_fallback_and_formatting():
    unknown = I18n("zz")
    assert unknown.lang == "en"
    assert unknown.t("media.nothing_playing") == "Nothing playing"

    ru = I18n("ru")
    assert ru.t("ecoflow.watts", w=250) == "250 Вт"
    assert ru.weather_description(0) == "Ясно"
    assert ru.weather_description(95) == "Гроза"

    uk = I18n("uk")
    assert uk.t("ecoflow.battery_blackout") == "БАТАРЕЯ · БЛЕКАУТ"
    assert uk.format_date_long(datetime.date(2026, 11, 25)) == "25 листопада 2026"

    en = I18n("en")
    assert en.format_date_long(datetime.date(2026, 11, 25)) == "Nov 25, 2026"
