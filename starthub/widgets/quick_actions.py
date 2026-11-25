"""Customizable Quick Actions bar & standalone Start11 Tile Pack Switcher bar."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

from . import Box, RenderContext, draw_card_surface


def _draw_action_glyph(ctx: RenderContext, icon: str, cx: float, cy: float, ink: tuple[int, int, int, int]) -> None:
    S = ctx.scale
    d = ctx.draw
    w = max(1, round(1.7 * S))
    if icon == "camera" or icon == "snip":
        d.rounded_rectangle(((cx - 9) * S, (cy - 6) * S, (cx + 9) * S, (cy + 7) * S), radius=3 * S, outline=ink, width=w)
        d.ellipse(((cx - 3.5) * S, (cy - 3) * S, (cx + 3.5) * S, (cy + 4) * S), outline=ink, width=w)
    elif icon == "terminal":
        d.rounded_rectangle(((cx - 9) * S, (cy - 7) * S, (cx + 9) * S, (cy + 7) * S), radius=3 * S, outline=ink, width=w)
        d.line([((cx - 5) * S, (cy - 2) * S), ((cx - 1) * S, (cy + 1) * S), ((cx - 5) * S, (cy + 4) * S)], fill=ink, width=w)
        d.line([((cx + 1) * S, (cy + 4) * S), ((cx + 5) * S, (cy + 4) * S)], fill=ink, width=w)
    elif icon == "lock":
        d.rounded_rectangle(((cx - 7) * S, (cy - 1) * S, (cx + 7) * S, (cy + 8) * S), radius=2 * S, outline=ink, width=w)
        d.arc(((cx - 4.5) * S, (cy - 8) * S, (cx + 4.5) * S, (cy + 2) * S), start=180, end=360, fill=ink, width=w)
    elif icon == "gear" or icon == "settings":
        d.ellipse(((cx - 3.5) * S, (cy - 3.5) * S, (cx + 3.5) * S, (cy + 3.5) * S), outline=ink, width=w)
        for i in range(6):
            a = i * math.pi / 3.0
            d.line(
                [
                    ((cx + 4.5 * math.cos(a)) * S, (cy + 4.5 * math.sin(a)) * S),
                    ((cx + 8.0 * math.cos(a)) * S, (cy + 8.0 * math.sin(a)) * S),
                ],
                fill=ink,
                width=w,
            )
    elif icon == "sleep" or icon == "moon":
        d.arc(((cx - 7) * S, (cy - 7) * S, (cx + 7) * S, (cy + 7) * S), start=40, end=270, fill=ink, width=w)
    elif icon == "folder":
        d.rounded_rectangle(((cx - 9) * S, (cy - 5) * S, (cx + 9) * S, (cy + 7) * S), radius=2 * S, outline=ink, width=w)
        d.line([((cx - 9) * S, (cy - 5) * S), ((cx - 5) * S, (cy - 8) * S), ((cx - 1) * S, (cy - 5) * S)], fill=ink, width=w)
    else:
        # Generic bolt / launch glyph
        d.polygon(
            [
                ((cx + 1) * S, (cy - 8) * S),
                ((cx - 5) * S, (cy + 1) * S),
                ((cx) * S, (cy + 1) * S),
                ((cx - 1) * S, (cy + 8) * S),
                ((cx + 5) * S, (cy - 1) * S),
                ((cx) * S, (cy - 1) * S),
            ],
            fill=ink,
        )


def draw_quick_actions_card(
    ctx: RenderContext,
    box: Box,
    items: List[Dict[str, Any]],
    *,
    on_trigger: Callable[[Dict[str, Any]], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    valid = [it for it in (items or []) if isinstance(it, dict)][:5]
    if not valid:
        return

    accent = ctx.theme.role("quick_actions")
    n = len(valid)
    gap = 6
    btn_w = (x2 - x1 - 20 - gap * (n - 1)) / float(n)
    by1, by2 = y1 + 8, y2 - 8

    for idx, item in enumerate(valid):
        bx1 = round(x1 + 10 + idx * (btn_w + gap))
        bx2 = round(x1 + 10 + idx * (btn_w + gap) + btn_w)
        aid = str(item.get("id") or f"act_{idx}")
        hid = f"qa_{aid}"
        hov = ctx.hover == hid
        ctx.draw.rounded_rectangle(
            (bx1 * S, by1 * S, bx2 * S, by2 * S),
            radius=9 * S,
            fill=ctx.theme.tile_bg_hover if hov else ctx.theme.tile_bg,
            outline=(*accent, 235) if hov else ctx.theme.tile_edge,
            width=S,
        )
        cx = (bx1 + bx2) / 2.0
        _draw_action_glyph(ctx, str(item.get("icon") or "bolt"), cx, by1 + 15, (*accent, 255) if hov else ctx.theme.text_primary)
        raw_lbl = str(item.get("label") or aid.title())
        # Allow built-in i18n lookup for standard action labels
        i18n_key = f"quick_actions.{aid}"
        translated = ctx.i18n.t(i18n_key)
        lbl = translated if translated != i18n_key else raw_lbl
        fit = ctx.fit_text(lbl, btn_w - 8, 11, "semibold")
        ctx.draw.text((cx * S, (by2 - 11) * S), fit, anchor="mm", font=ctx.font(11, "semibold"), fill=ctx.theme.text_secondary)
        ctx.add_spot(bx1, by1, bx2, by2, lambda it=item: on_trigger(it), None, hid)


def draw_tile_switcher_bar(
    ctx: RenderContext,
    box: Box,
    *,
    pack_label: Optional[str],
    busy: bool,
    on_cycle: Callable[[], None],
) -> None:
    """Standalone Start11 Tile Pack Switcher bar shown when Todoist/Tasks card is disabled."""
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    accent = ctx.theme.role("tile_bar")
    hov = ctx.hover == "tile_bar_btn"

    # 2x2 tile icon on left
    ix, iy = x1 + 16, (y1 + y2) // 2 - 6
    for dx in (0, 7):
        for dy in (0, 7):
            ctx.draw.rectangle(((ix + dx) * S, (iy + dy) * S, (ix + 5 + dx) * S, (iy + 5 + dy) * S), fill=(*accent, 255))

    ctx.draw.text(((x1 + 36) * S, (y1 + 13) * S), ctx.i18n.t("tiles.bar_title"), font=ctx.font(14, "bold"), fill=ctx.theme.text_primary)

    px1, py1, px2, py2 = x2 - 122, y1 + 9, x2 - 12, y2 - 9
    ctx.draw.rounded_rectangle(
        (px1 * S, py1 * S, px2 * S, py2 * S),
        radius=8 * S,
        fill=ctx.theme.tint_hover(accent, 0.32) if hov else ctx.theme.tint_dark(accent, 0.22),
        outline=(*accent, 235 if hov else 170),
        width=S,
    )
    lbl = "…" if busy else ctx.fit_text(pack_label or ctx.i18n.t("tiles.pack_fallback"), 96, 13, "bold")
    ctx.draw.text((((px1 + px2) * S) // 2, ((py1 + py2) * S) // 2), lbl, anchor="mm", font=ctx.font(13, "bold"), fill=(*accent, 255))
    ctx.add_spot(x1 + 8, y1 + 4, x2 - 8, y2 - 4, on_cycle, None, "tile_bar_btn")
