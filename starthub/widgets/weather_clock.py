"""Weather & Clock center transparent overlays, compact wing cards, and optional outer columns."""
from __future__ import annotations

import calendar
import datetime
import math
import time
from typing import Any, Callable, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter

from ..i18n import I18n
from ..surface import FontBank
from ..theme import Theme
from . import Box, RenderContext, draw_card_surface


def format_degree(val: Any) -> str:
    if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val):
        return f"{val:+.0f}°" if round(val) > 0 else f"{val:.0f}°"
    return "—"


def draw_weather_icon(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    code: Any,
    scale_px: float,
    icon_scale: float = 1.0,
    *,
    light_bg: bool = False,
) -> None:
    S = scale_px * icon_scale
    px, py = x * scale_px, y * scale_px
    gold = (232, 166, 24, 255) if light_bg else (255, 205, 91, 255)
    cloud = (126, 140, 160, 255) if light_bg else (190, 201, 215, 255)
    if code in (0, 1, 2):
        sx, sy = (px - 9 * S, py - 9 * S) if code else (px, py)
        draw.ellipse((sx - 8 * S, sy - 8 * S, sx + 8 * S, sy + 8 * S), fill=gold)
        for i in range(8):
            a = i * math.pi / 4.0
            if code and i in (0, 1, 2):
                continue
            draw.line(
                (sx + 11 * S * math.cos(a), sy + 11 * S * math.sin(a), sx + 14 * S * math.cos(a), sy + 14 * S * math.sin(a)),
                fill=gold,
                width=max(1, int(2 * S)),
            )
    if code != 0:
        for cx, cy, r in ((-9, 5, 8), (1, 0, 10), (12, 5, 8)):
            draw.ellipse((px + (cx - r) * S, py + (cy - r) * S, px + (cx + r) * S, py + (cy + r) * S), fill=cloud)
        draw.rectangle((px - 9 * S, py + 5 * S, px + 12 * S, py + 13 * S), fill=cloud)
    if code in (45, 48):
        for dy, half in ((18, 17), (23, 12)):
            draw.line((px - half * S, py + dy * S, px + half * S, py + dy * S), fill=cloud, width=max(1, int(2 * S)))
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
        for dx in (-9, 2, 13):
            draw.line((px + dx * S, py + 16 * S, px + (dx - 3) * S, py + 22 * S), fill=(104, 183, 255, 255), width=max(1, int(2 * S)))
    if code in (71, 73, 75, 77, 85, 86):
        for dx in (-9, 2, 13):
            draw.ellipse((px + dx * S, py + 16 * S, px + (dx + 3) * S, py + 19 * S), fill=cloud)
    if code in (95, 96, 99):
        draw.polygon(
            [(px + 3 * S, py + 10 * S), (px - 3 * S, py + 20 * S), (px + 2 * S, py + 20 * S), (px - 1 * S, py + 28 * S), (px + 10 * S, py + 16 * S), (px + 4 * S, py + 16 * S)],
            fill=gold,
        )


def render_center_part(
    side: str,
    size: Tuple[int, int],
    *,
    weather: Dict[str, Any],
    now: datetime.datetime,
    theme: Theme,
    fonts: FontBank,
    i18n: I18n,
    scale: int = 2,
) -> Image.Image:
    """Render one transparent center overlay (weather OR clock) with a crisp dark text halo."""
    w, h = size
    S = scale
    sc = w / 308.0
    image = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    text_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ink, outline = ImageDraw.Draw(text_layer), ImageDraw.Draw(shadow)

    white = (245, 247, 250, 255)
    muted = (225, 230, 238, 255)
    accent = (*theme.role("weather"), 255)

    def draw_txt(x: float, y: float, value: str, points: float, color=white, weight: str = "regular", anchor: str = "lt"):
        f = fonts.get(max(14 * S, round(points * S * sc)), weight)
        pt = (round(x * S), round(y * S))
        outline.text(pt, value, font=f, anchor=anchor, fill=(0, 0, 0, 210), stroke_width=max(1, round(0.65 * S * sc)), stroke_fill=(0, 0, 0, 210))
        ink.text(pt, value, font=f, anchor=anchor, fill=color)

    inset = 12 * sc
    expanded = h >= 150 and w >= 290
    middle = h >= 124 and w >= 290
    main_pt = 50 if expanded else min(72, (h / sc) - 58)

    current = weather.get("current") or {}
    daily = weather.get("daily") or {}
    wind_unit = "mph" if weather.get("units") == "imperial" else "m/s"

    def at(field: str, idx: int):
        vals = daily.get(field) or []
        return vals[idx] if idx < len(vals) else None

    def fit(value: str, points: int = 14) -> str:
        f = fonts.get(max(14 * S, round(points * S * sc)))
        while f.getlength(value) > (w - 2 * inset) * S and len(value) > 1:
            value = value[:-2] + "…"
        return value

    if side == "center_weather":
        temp = current.get("temperature_2m")
        code = current.get("weather_code", 3)
        label = format_degree(temp)
        while fonts.get(round(main_pt * S * sc), "light").getlength(label) > w * S * 0.67 and main_pt > 30:
            main_pt -= 1
        draw_txt(inset, 6 if expanded else 8 * sc, label, main_pt, weight="light")
        icon_y = 29 if expanded else min(50 * sc, max(28, (h - 52 * sc) / 2 + 10 * sc))
        icon_sc = 0.95 if expanded else min(1.4, (h / sc - 45) / 36.0) * sc
        icon_y = max(icon_y, 24 * icon_sc + 5)
        draw_weather_icon(ImageDraw.Draw(image), w - 53 * sc, icon_y, code, S, icon_sc)

        desc = i18n.weather_description(code) if current else i18n.t("weather.loading")
        feels = i18n.t("weather.feels_like", temp=format_degree(current.get("apparent_temperature")))
        detail = f"{desc} · {feels}" if current else desc
        stamp = weather.get("updated_at", 0)
        if current and (weather.get("offline") or (stamp and (time.time() - float(stamp) > 7200))):
            detail = f"{i18n.t('weather.cached')} · {detail}"
        draw_txt(inset, 60 if expanded else h - 43 * sc, fit(detail), 14, muted)
        draw_txt(inset, 79 if expanded else h - 22 * sc, str(weather.get("city") or "Kyiv"), 14, accent)

        if expanded:
            dates = daily.get("time") or []
            indices = []
            for idx, ds in enumerate(dates):
                try:
                    day = datetime.date.fromisoformat(ds)
                except (ValueError, TypeError):
                    continue
                if day > now.date():
                    indices.append((idx, day))
            wshort = i18n.weekdays_short()
            for col, (idx, day) in enumerate(indices[:3]):
                cx = inset + (w - 2 * inset) * (col + 0.5) / 3.0
                draw_txt(cx - 13, 99, wshort[day.weekday()], 14, muted, anchor="mt")
                draw_weather_icon(ImageDraw.Draw(image), cx + 21, 106, at("weather_code", idx), S, 0.32)
                draw_txt(cx, 119, f"{format_degree(at('temperature_2m_max', idx))} / {format_degree(at('temperature_2m_min', idx))}", 14, anchor="mt")
            wind = current.get("wind_speed_10m")
            hum = current.get("relative_humidity_2m")
            wind_s = f"{wind:.1f}" if isinstance(wind, (int, float)) and math.isfinite(wind) else "—"
            hum_s = f"{hum:.0f}%" if isinstance(hum, (int, float)) and math.isfinite(hum) else "—"
            w_str = i18n.t("weather.wind", speed=wind_s, unit=wind_unit)
            h_str = i18n.t("weather.humidity", pct=hum_s)
            draw_txt(inset, h - 21, fit(f"{w_str} · {h_str}"), 14, muted)
    else:
        draw_txt(w / 2.0, 6 if middle else 8 * sc, now.strftime("%H:%M"), 60 if middle else min(78, h / sc - 48), weight="light", anchor="mt")
        date_str = f"{i18n.weekday_name(now.weekday())} · {i18n.format_date_short(now)}"
        draw_txt(w / 2.0, 76 if middle else h - 28, fit(date_str), 14, accent, anchor="mt")
        if middle:
            dates = daily.get("time") or []
            idx = dates.index(now.date().isoformat()) if now.date().isoformat() in dates else None

            def solar(field: str) -> str:
                val = at(field, idx) if idx is not None else None
                try:
                    return datetime.datetime.fromisoformat(val).strftime("%H:%M")
                except (ValueError, TypeError):
                    return "—"

            solar_line = f"{i18n.t('weather.sunrise')} {solar('sunrise')} · {i18n.t('weather.sunset')} {solar('sunset')}"
            draw_txt(w / 2.0, 104 if expanded else h - 18, fit(solar_line), 14, muted, anchor="mt")
        if expanded:
            for col, label in enumerate(i18n.weekdays_short()):
                is_today = col == now.weekday()
                draw_txt(
                    inset + (w - 2 * inset) * (col + 0.5) / 7.0,
                    h - 21,
                    label,
                    14,
                    accent if is_today else muted,
                    "semibold" if is_today else "regular",
                    anchor="mt",
                )

    image = Image.alpha_composite(image, shadow.filter(ImageFilter.GaussianBlur(0.45 * S * sc)))
    image = Image.alpha_composite(image, text_layer)
    return image.resize(size, Image.Resampling.LANCZOS)


def draw_weather_card(ctx: RenderContext, box: Box, weather: Dict[str, Any], now: datetime.datetime) -> None:
    """Compact Tier-1 Weather + 5-day forecast card for a wing."""
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    current = weather.get("current") or {}
    daily = weather.get("daily") or {}
    city = str(weather.get("city") or "Kyiv")
    wind_unit = "mph" if weather.get("units") == "imperial" else "m/s"

    ctx.draw.text(((x1 + 16) * S, (y1 + 12) * S), city, font=ctx.font(17, "bold"), fill=ctx.theme.text_primary)
    temp_str = format_degree(current.get("temperature_2m"))
    ctx.draw.text(((x1 + 16) * S, (y1 + 36) * S), temp_str, font=ctx.font(38, "light"), fill=ctx.theme.text_primary)
    draw_weather_icon(ctx.draw, x2 - 48, y1 + 52, current.get("weather_code", 3), S, 1.05, light_bg=ctx.theme.is_light)

    desc = ctx.i18n.weather_description(current.get("weather_code")) if current else ctx.i18n.t("weather.loading")
    feels = ctx.i18n.t("weather.feels_like", temp=format_degree(current.get("apparent_temperature")))
    ctx.draw.text(((x1 + 16) * S, (y1 + 86) * S), ctx.fit_text(f"{desc} · {feels}", x2 - x1 - 32, 13), font=ctx.font(13), fill=ctx.theme.text_secondary)

    wind = current.get("wind_speed_10m")
    wind_s = f"{wind:.1f}" if isinstance(wind, (int, float)) else "—"
    ctx.draw.text(((x1 + 16) * S, (y1 + 106) * S), ctx.i18n.t("weather.wind", speed=wind_s, unit=wind_unit), font=ctx.font(13), fill=ctx.theme.text_muted)

    if y2 - y1 >= 195:
        ctx.draw.line([((x1 + 14) * S, (y1 + 132) * S), ((x2 - 14) * S, (y1 + 132) * S)], fill=ctx.theme.divider, width=S)
        dates = daily.get("time") or []
        mins = daily.get("temperature_2m_min") or []
        maxs = daily.get("temperature_2m_max") or []
        codes = daily.get("weather_code") or []
        wshort = ctx.i18n.weekdays_short()
        max_rows = min(5, max(0, (y2 - y1 - 144) // 26))
        if not dates:
            # Clean loading skeleton rows instead of empty blank gap
            for i in range(min(4, max_rows)):
                ry = y1 + 142 + i * 26
                ctx.draw.rounded_rectangle(((x1 + 16) * S, ry * S, (x1 + 92) * S, (ry + 12) * S), radius=4 * S, fill=ctx.theme.track_bg)
                ctx.draw.rounded_rectangle(((x2 - 96) * S, ry * S, (x2 - 18) * S, (ry + 12) * S), radius=4 * S, fill=ctx.theme.track_bg)
        for i in range(min(max_rows, len(dates))):
            try:
                day = datetime.date.fromisoformat(dates[i])
            except ValueError:
                continue
            ry = y1 + 140 + i * 26
            lbl = ctx.i18n.t("calendar.today") if day == now.date() else f"{wshort[day.weekday()]} {day.day}"
            ctx.draw.text(((x1 + 16) * S, ry * S), lbl, font=ctx.font(13, "semibold"), fill=ctx.theme.text_primary)
            draw_weather_icon(ctx.draw, x2 - 120, ry + 8, codes[i] if i < len(codes) else 3, S, 0.42, light_bg=ctx.theme.is_light)
            lo = format_degree(mins[i] if i < len(mins) else None)
            hi = format_degree(maxs[i] if i < len(maxs) else None)
            ctx.draw.text(((x2 - 92) * S, ry * S), f"{lo} / {hi}", font=ctx.font(13), fill=ctx.theme.text_secondary)


def draw_calendar_card(
    ctx: RenderContext,
    box: Box,
    *,
    month_tuple: Tuple[int, int],
    today: datetime.date,
    on_change_month: Callable[[int], None],
    on_today: Callable[[], None],
) -> None:
    """Interactive Tier-1 monthly calendar card for a wing."""
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    year, month = month_tuple
    accent = ctx.theme.role("calendar")
    ctx.draw.text(((x1 + 16) * S, (y1 + 12) * S), f"{ctx.i18n.month_name(month)} {year}", font=ctx.font(17, "bold"), fill=ctx.theme.text_primary)

    for bx, glyph, delta, hid in ((x2 - 80, "‹", -1, "cal_prev"), (x2 - 44, "›", 1, "cal_next")):
        hov = ctx.hover == hid
        ctx.draw.rounded_rectangle(
            (bx * S, (y1 + 10) * S, (bx + 28) * S, (y1 + 38) * S),
            radius=7 * S,
            fill=ctx.theme.tile_bg_hover if hov else ctx.theme.tile_bg,
            outline=ctx.theme.tile_edge,
            width=S,
        )
        ctx.draw.text(((bx + 14) * S, (y1 + 22) * S), glyph, anchor="mm", font=ctx.font(20, "semibold"), fill=ctx.theme.text_primary)
        ctx.add_spot(bx, y1 + 10, bx + 28, y1 + 38, lambda d=delta: on_change_month(d), None, hid)

    step = (x2 - x1 - 28) / 7.0
    for i, wd in enumerate(ctx.i18n.weekdays_short()):
        ctx.draw.text(
            ((x1 + 14 + (i + 0.5) * step) * S, (y1 + 48) * S),
            wd,
            anchor="mt",
            font=ctx.font(12, "semibold"),
            fill=ctx.theme.text_muted,
        )

    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    avail_h = max(120, y2 - y1 - 108)
    row_h = min(34, avail_h // max(5, len(weeks)))
    for row_idx, week in enumerate(weeks):
        for col_idx, day in enumerate(week):
            if not day:
                continue
            dx = x1 + 14 + col_idx * step
            dy = y1 + 70 + row_idx * row_h
            is_today = (year, month, day) == (today.year, today.month, today.day)
            if is_today:
                ctx.draw.rounded_rectangle(
                    ((dx + 2) * S, dy * S, (dx + step - 2) * S, (dy + row_h - 4) * S),
                    radius=8 * S,
                    fill=(*accent, 255),
                )
            col = (255, 255, 255, 255) if is_today else (ctx.theme.text_muted if col_idx > 4 else ctx.theme.text_primary)
            ctx.draw.text(
                ((dx + step / 2.0) * S, (dy + (row_h - 4) / 2.0) * S),
                str(day),
                anchor="mm",
                font=ctx.font(14, "semibold"),
                fill=col,
            )

    btn_y1, btn_y2 = y2 - 36, y2 - 10
    ctx.draw.rounded_rectangle(
        ((x1 + 14) * S, btn_y1 * S, (x2 - 14) * S, btn_y2 * S),
        radius=8 * S,
        fill=ctx.theme.tint_dark(accent, 0.25),
        outline=(*accent, 140),
        width=S,
    )
    today_lbl = ctx.i18n.t("calendar.today_btn", date=ctx.i18n.format_date_short(today))
    ctx.draw.text(((x1 + x2) * S // 2, (btn_y1 + btn_y2) * S // 2), today_lbl, anchor="mm", font=ctx.font(13, "semibold"), fill=ctx.theme.text_primary)
    ctx.add_spot(x1 + 14, btn_y1, x2 - 14, btn_y2, on_today, None, "cal_today")
