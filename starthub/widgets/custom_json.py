"""Universal Custom JSON card renderer supporting 'columns', 'hero', and 'list' layouts."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import Box, RenderContext, draw_card_surface, draw_progress_bar


def draw_custom_json_card(
    ctx: RenderContext,
    box: Box,
    card: Dict[str, Any],
    *,
    on_open_url: Callable[[str], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box, radius=min(15, ctx.theme.corner_radius + 1))

    card_id = str(card.get("id") or "custom")
    title = str(card.get("title") or "Custom Metrics")
    subtitle = str(card.get("subtitle") or "")
    badge = str(card.get("badge") or "")
    url = str(card.get("url") or "")
    layout = str(card.get("layout") or "columns").lower()
    ok = bool(card.get("ok", False))
    metrics: List[Dict[str, Any]] = list(card.get("metrics") or [])[:3]
    items: List[Dict[str, Any]] = list(card.get("items") or [])[:5]

    header_accent = ctx.theme.role("custom_0")

    # Small geometric icon dot in header
    icx, icy = (x1 + 19) * S, (y1 + 20) * S
    ctx.draw.rounded_rectangle((icx - 7 * S, icy - 7 * S, icx + 7 * S, icy + 7 * S), radius=4 * S, outline=(*header_accent, 255), width=2 * S)
    ctx.draw.ellipse((icx - 2 * S, icy - 2 * S, icx + 2 * S, icy + 2 * S), fill=(*header_accent, 255))

    f_title = ctx.font(15, "bold")
    title_x = x1 + 34
    fit_t = ctx.fit_text(title, 180, 15, "bold")
    ctx.draw.text((title_x * S, (y1 + 10) * S), fit_t, font=f_title, fill=ctx.theme.text_primary)
    title_w = int(round(ctx.draw.textlength(fit_t, font=f_title) / S))

    # Right badge pill (clickable if url configured)
    badge_txt = badge if ok else ctx.i18n.t("custom.offline")
    badge_x1 = x2 - 12
    if badge_txt:
        f_b = ctx.font(13, "bold")
        btw = int(round(ctx.draw.textlength(badge_txt, font=f_b) / S))
        arrow_w = 10 if url else 0
        badge_x2 = x2 - 12
        badge_x1 = badge_x2 - (btw + arrow_w + 14)
        by1, by2 = y1 + 10, y1 + 30
        hid = f"custom_url_{card_id}"
        hov = bool(url) and ctx.hover == hid
        b_rgb = header_accent if ok else (130, 136, 150)
        ctx.draw.rounded_rectangle(
            (badge_x1 * S, by1 * S, badge_x2 * S, by2 * S),
            radius=6 * S,
            fill=ctx.theme.tint_dark(b_rgb, 0.30) if hov else None,
            outline=(*b_rgb, 235),
            width=S,
        )
        ctx.draw.text(((badge_x1 + 7) * S, (by1 + 2) * S), badge_txt, font=f_b, fill=(*b_rgb, 255))
        if url:
            ax1, ay1 = badge_x2 - 12, by1 + 6
            ax2, ay2 = badge_x2 - 6, by1 + 12
            ctx.draw.line([(ax1 * S, ay2 * S), (ax2 * S, ay1 * S)], fill=(*b_rgb, 255), width=max(1, round(1.5 * S)))
            ctx.draw.line([((ax2 - 4) * S, ay1 * S), (ax2 * S, ay1 * S), (ax2 * S, (ay1 + 4) * S)], fill=(*b_rgb, 255), width=max(1, round(1.5 * S)))
            ctx.add_spot(badge_x1 - 2, by1 - 2, badge_x2 + 2, by2 + 2, lambda u=url: on_open_url(u), None, hid)

    if subtitle:
        sub_x = title_x + title_w + 8
        sub_max = max(0, badge_x1 - sub_x - 8)
        if sub_max >= 42:
            ctx.draw.text((sub_x * S, (y1 + 12) * S), ctx.fit_text(f"· {subtitle}", sub_max, 12, "semibold"), font=ctx.font(12, "semibold"), fill=ctx.theme.text_muted)

    # Header divider
    ctx.draw.line([((x1 + 12) * S, (y1 + 37) * S), ((x2 - 12) * S, (y1 + 37) * S)], fill=ctx.theme.divider, width=S)

    if not ok:
        ctx.draw.text(((x1 + 16) * S, (y1 + 58) * S), ctx.i18n.t("custom.no_data"), font=ctx.font(14), fill=ctx.theme.text_muted)
        return

    if layout == "hero":
        _draw_hero_body(ctx, box, card, metrics)
        return
    if layout == "list":
        _draw_list_body(ctx, box, items or metrics)
        return

    # Default 'columns' layout (1..3 metrics with optional progress bars)
    if not metrics:
        ctx.draw.text(((x1 + 16) * S, (y1 + 58) * S), ctx.i18n.t("custom.no_data"), font=ctx.font(14), fill=ctx.theme.text_muted)
        return

    n = len(metrics)
    total_w = x2 - x1
    roles = ("custom_0", "custom_1", "custom_2")

    for i in range(1, n):
        dx = x1 + (total_w * i) // n
        ctx.draw.line([(dx * S, (y1 + 44) * S), (dx * S, (y2 - 10) * S)], fill=ctx.theme.divider, width=S)

    for idx, m in enumerate(metrics):
        cx1 = x1 + (total_w * idx) // n + 12
        cx2 = x1 + (total_w * (idx + 1)) // n - 10
        col_w = max(24, cx2 - cx1)
        role_name = roles[idx % len(roles)]
        col_rgb = ctx.theme.status_color(str(m.get("status") or "info"), role_name)

        dot_x, dot_y = (cx1 + 3) * S, (y1 + 52) * S
        ctx.draw.ellipse((dot_x - 3 * S, dot_y - 3 * S, dot_x + 3 * S, dot_y + 3 * S), fill=(*col_rgb, 255))
        tag = str(m.get("tag") or "")
        tag_w = int(round(ctx.draw.textlength(tag, font=ctx.font(12, "bold")) / S)) if tag else 0
        lbl_max = max(24, col_w - 14 - (tag_w + 4 if tag else 0))
        ctx.draw.text(((cx1 + 10) * S, (y1 + 44) * S), ctx.fit_text(str(m.get("label") or ""), lbl_max, 13, "semibold"), font=ctx.font(13, "semibold"), fill=ctx.theme.text_secondary)
        if tag:
            ctx.draw.text(((cx2 - tag_w) * S, (y1 + 44) * S), tag, font=ctx.font(12, "bold"), fill=(*col_rgb, 255))

        val_s = ctx.fit_text(str(m.get("value") or "—"), col_w, 22, "bold")
        ctx.draw.text((cx1 * S, (y1 + 64) * S), val_s, font=ctx.font(22, "bold"), fill=(*col_rgb, 255))

        pct = m.get("percent")
        bar_y = y1 + 100
        if pct is not None:
            draw_progress_bar(ctx, cx1, bar_y, cx2, bar_y + 7, pct, col_rgb, radius=3)

        sub = str(m.get("sublabel") or "")
        if sub:
            ctx.draw.text((cx1 * S, (y1 + 114) * S), ctx.fit_text(sub, col_w, 12, "semibold"), font=ctx.font(12, "semibold"), fill=ctx.theme.text_muted)


def _draw_hero_body(ctx: RenderContext, box: Box, card: Dict[str, Any], metrics: List[Dict[str, Any]]) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    hero_val = str(card.get("hero_value") or (metrics[0].get("value") if metrics else "—"))
    hero_sub = str(card.get("hero_sub") or (metrics[0].get("sublabel") if metrics else ""))
    hero_rgb = ctx.theme.status_color(str(card.get("hero_status") or "info"), "custom_0")

    f_hero = ctx.font(28, "bold")
    fit_v = ctx.fit_text(hero_val, (x2 - x1) * 0.62, 28, "bold")
    ctx.draw.text(((x1 + 16) * S, (y1 + 45) * S), fit_v, font=f_hero, fill=ctx.theme.text_primary)
    vw = int(round(ctx.draw.textlength(fit_v, font=f_hero) / S))
    if hero_sub:
        sub_max = max(32, (x2 - 14) - (x1 + 24 + vw))
        ctx.draw.text(
            ((x1 + 24 + vw) * S, (y1 + 56) * S),
            ctx.fit_text(hero_sub, sub_max, 14, "bold"),
            font=ctx.font(14, "bold"),
            fill=(*hero_rgb, 255),
        )

    sub_metrics = metrics[:2]
    if sub_metrics:
        n = len(sub_metrics)
        gap = 8
        bw = (x2 - x1 - 28 - gap * (n - 1)) / float(n)
        by1, by2 = y2 - 52, y2 - 10
        for idx, m in enumerate(sub_metrics):
            bx1 = round(x1 + 14 + idx * (bw + gap))
            bx2 = round(bx1 + bw)
            col_rgb = ctx.theme.status_color(str(m.get("status") or "info"), f"custom_{idx}")
            ctx.draw.rounded_rectangle((bx1 * S, by1 * S, bx2 * S, by2 * S), radius=9 * S, fill=ctx.theme.tile_bg, outline=ctx.theme.tile_edge, width=S)
            ctx.draw.text(((bx1 + 10) * S, (by1 + 5) * S), ctx.fit_text(str(m.get("label") or ""), bw - 18, 11, "semibold"), font=ctx.font(11, "semibold"), fill=ctx.theme.text_muted)
            ctx.draw.text(((bx1 + 10) * S, (by1 + 20) * S), ctx.fit_text(str(m.get("value") or "—"), bw - 18, 15, "bold"), font=ctx.font(15, "bold"), fill=(*col_rgb, 255))


def _draw_list_body(ctx: RenderContext, box: Box, rows: List[Dict[str, Any]]) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    if not rows:
        ctx.draw.text(((x1 + 16) * S, (y1 + 58) * S), ctx.i18n.t("custom.no_data"), font=ctx.font(14), fill=ctx.theme.text_muted)
        return
    ry0 = y1 + 44
    avail = max(40, y2 - ry0 - 8)
    max_rows = min(4, len(rows))
    rh = max(22, avail // max(1, max_rows))
    for idx, item in enumerate(rows[:max_rows]):
        ry = ry0 + idx * rh
        col_rgb = ctx.theme.status_color(str(item.get("status") or "info"), f"custom_{idx % 3}")
        if idx > 0:
            ctx.draw.line([((x1 + 14) * S, ry * S), ((x2 - 14) * S, ry * S)], fill=ctx.theme.divider, width=S)
        cy = ry + rh // 2
        ctx.draw.ellipse(((x1 + 16) * S, (cy - 3) * S, (x1 + 22) * S, (cy + 3) * S), fill=(*col_rgb, 255))
        val_s = str(item.get("value") or "—")
        f_val = ctx.font(13, "bold")
        vw = int(round(ctx.draw.textlength(val_s, font=f_val) / S))
        lbl_max = max(40, (x2 - x1) - 46 - vw)
        ctx.draw.text(((x1 + 28) * S, (cy - 8) * S), ctx.fit_text(str(item.get("label") or ""), lbl_max, 13, "semibold"), font=ctx.font(13, "semibold"), fill=ctx.theme.text_secondary)
        ctx.draw.text(((x2 - 14 - vw) * S, (cy - 8) * S), val_s, font=f_val, fill=(*col_rgb, 255))
