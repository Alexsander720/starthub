"""Todoist tasks card with project switcher, 1-click completion, and optional Tile Switcher pill."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from . import Box, RenderContext, draw_card_surface


def draw_todoist_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_cycle_project: Callable[[], None],
    on_complete_task: Callable[[int], None],
    on_open_app: Callable[[], None],
    tile_pack_label: Optional[str] = None,
    tile_busy: bool = False,
    on_cycle_tiles: Optional[Callable[[], None]] = None,
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box, radius=min(16, ctx.theme.corner_radius + 2))

    accent = ctx.theme.role("todoist")
    projs = list(state.get("projects") or [{"id": "__all__", "name": ctx.i18n.t("todoist.default_project")}])
    p_idx = int(state.get("proj_idx", 0)) % len(projs)
    proj_name = str(projs[p_idx].get("name") or ctx.i18n.t("todoist.default_project"))
    tasks = list(state.get("tasks") or [])

    show_tile_btn = on_cycle_tiles is not None
    proj_max_w = (x2 - x1 - 184) if show_tile_btn else (x2 - x1 - 80)

    f_pn = ctx.font(17, "bold")
    fit_proj = ctx.fit_text(proj_name, proj_max_w, 17, "bold")
    ctx.draw.text(((x1 + 18) * S, (y1 + 12) * S), fit_proj, font=f_pn, fill=(*accent, 255))
    ptb = ctx.draw.textbbox((0, 0), fit_proj, font=f_pn)
    ch_x = (x1 + 18) * S + (ptb[2] - ptb[0]) + 11 * S
    ch_y = (y1 + 24) * S
    ctx.draw.line([(ch_x - 4 * S, ch_y - 2 * S), (ch_x, ch_y + 2 * S), (ch_x + 4 * S, ch_y - 2 * S)], fill=(*accent, 255), width=2 * S)
    ctx.add_spot(x1 + 12, y1 + 8, x1 + 12 + int(proj_max_w), y1 + 40, on_cycle_project, None, "td_proj")

    # Open Todoist '+' circle button
    pcx, pcy = (x2 - 26) * S, (y1 + 23) * S
    pr = 12 * S
    ctx.draw.ellipse((pcx - pr, pcy - pr, pcx + pr, pcy + pr), fill=(*accent, 255))
    ctx.draw.line([(pcx - 5 * S, pcy), (pcx + 5 * S, pcy)], fill=(255, 255, 255, 255), width=2 * S)
    ctx.draw.line([(pcx, pcy - 5 * S), (pcx, pcy + 5 * S)], fill=(255, 255, 255, 255), width=2 * S)
    ctx.add_spot(x2 - 42, y1 + 8, x2 - 10, y1 + 38, on_open_app, None, "td_open")

    # Optional compact Start11 Tile Pack Switcher pill
    if show_tile_btn:
        bx, by = x2 - 144, y1 + 9
        hov_t = ctx.hover == "tile_set"
        ctx.draw.rounded_rectangle(
            (bx * S, by * S, (bx + 98) * S, (by + 28) * S),
            radius=7 * S,
            fill=ctx.theme.tile_bg_hover if hov_t else ctx.theme.tile_bg,
            outline=(*ctx.theme.role("primary"), 220) if hov_t else ctx.theme.tile_edge,
            width=S,
        )
        for dx in (0, 7):
            for dy in (0, 7):
                ctx.draw.rectangle(((bx + 9 + dx) * S, (by + 8 + dy) * S, (bx + 13 + dx) * S, (by + 12 + dy) * S), fill=ctx.theme.text_secondary)
        t_lbl = "…" if tile_busy else ctx.fit_text(tile_pack_label or ctx.i18n.t("tiles.pack_fallback"), 64, 13, "semibold")
        ctx.draw.text(((bx + 28) * S, (by + 5) * S), t_lbl, font=ctx.font(13, "semibold"), fill=ctx.theme.text_primary)
        ctx.add_spot(bx, by, bx + 98, by + 28, on_cycle_tiles, None, "tile_set")

    if not state.get("configured", True):
        ctx.draw.text(((x1 + 18) * S, (y1 + 64) * S), ctx.fit_text(ctx.i18n.t("todoist.no_token"), x2 - x1 - 36, 14), font=ctx.font(14), fill=ctx.theme.text_muted)
        return

    if not tasks:
        ctx.draw.text(((x1 + 18) * S, (y1 + 64) * S), ctx.i18n.t("todoist.all_done"), font=ctx.font(15, "semibold"), fill=ctx.theme.text_muted)
        return

    ty0 = y1 + 44
    rh = 34
    capacity = max(0, (y2 - ty0 - 8) // rh)
    done_rgb = ctx.theme.status_color("ok", "primary")
    for idx, t in enumerate(tasks[:capacity]):
        ry1 = ty0 + idx * rh
        ry2 = ry1 + rh - 2
        hov = ctx.hover == f"task_{idx}"
        if idx > 0:
            ctx.draw.line([((x1 + 16) * S, ry1 * S), ((x2 - 16) * S, ry1 * S)], fill=ctx.theme.divider, width=S)

        ccx, ccy = (x1 + 28) * S, (ry1 + 16) * S
        cr = 8 * S
        c_col = (*done_rgb, 255) if hov else (165, 172, 186, 255)
        ctx.draw.ellipse((ccx - cr, ccy - cr, ccx + cr, ccy + cr), outline=c_col, width=2 * S)
        if hov:
            ctx.draw.line([(ccx - 4 * S, ccy), (ccx - 1 * S, ccy + 3 * S), (ccx + 5 * S, ccy - 4 * S)], fill=c_col, width=2 * S)

        content = ctx.fit_text(str(t.get("content", "")), x2 - x1 - 64, 14, "semibold")
        ctx.draw.text(((x1 + 46) * S, (ry1 + 6) * S), content, font=ctx.font(14, "semibold"), fill=ctx.theme.text_primary)
        ctx.add_spot(x1 + 14, ry1, x2 - 14, ry2, lambda i=idx: on_complete_task(i), None, f"task_{idx}")
