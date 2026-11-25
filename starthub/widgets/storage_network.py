"""Storage drives usage + live network download/upload throughput card renderer."""
from __future__ import annotations

from typing import Any, Dict, List

from . import Box, RenderContext, draw_card_surface, draw_progress_bar


def draw_storage_network_card(ctx: RenderContext, box: Box, state: Dict[str, Any]) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    drives: List[Dict[str, Any]] = list(state.get("drives") or [])[:3]
    down_txt = str(state.get("down_text") or "0 KB/s")
    up_txt = str(state.get("up_text") or "0 KB/s")

    # Top half: drive columns (1 to 3)
    if drives:
        n = len(drives)
        col_w = (x2 - x1 - 24) / float(n)
        for idx, drv in enumerate(drives):
            cx = x1 + 12 + idx * col_w
            cw = max(40.0, col_w - 10)
            pct = max(0, min(100, int(drv.get("percent", 0))))
            label = str(drv.get("label") or "C:")
            free_txt = str(drv.get("free_text") or "")

            # Critical storage alerts (>90% red, >80% amber) preserved even in single_accent
            if pct >= 90:
                bar_rgb = ctx.theme.alert_danger
            elif pct >= 80:
                bar_rgb = ctx.theme.alert_warn
            else:
                bar_rgb = ctx.theme.role("storage")

            ctx.draw.text((cx * S, (y1 + 10) * S), label, font=ctx.font(13, "bold"), fill=ctx.theme.text_primary)
            f_free = ctx.font(11, "semibold")
            free_fit = ctx.fit_text(free_txt, cw - 28, 11, "semibold")
            fw = int(round(ctx.draw.textlength(free_fit, font=f_free) / S))
            ctx.draw.text(((cx + cw - fw) * S, (y1 + 11) * S), free_fit, font=f_free, fill=ctx.theme.text_muted)

            draw_progress_bar(ctx, cx, y1 + 31, cx + cw, y1 + 37, pct, bar_rgb, radius=3)
    else:
        ctx.draw.text(((x1 + 14) * S, (y1 + 14) * S), ctx.i18n.t("storage.loading"), font=ctx.font(13), fill=ctx.theme.text_muted)

    # Subtle divider + bottom network speed row
    div_y = y2 - 34
    ctx.draw.line([((x1 + 12) * S, div_y * S), ((x2 - 12) * S, div_y * S)], fill=ctx.theme.divider, width=S)

    mid_x = (x1 + x2) // 2
    row_y = div_y + 8
    dn_col = ctx.theme.role("network_down")
    up_col = ctx.theme.role("network_up")

    # Download arrow + rate (left half)
    ax, ay = (x1 + 20) * S, (row_y + 9) * S
    ctx.draw.line([(ax, ay - 6 * S), (ax, ay + 5 * S)], fill=(*dn_col, 255), width=max(1, round(1.8 * S)))
    ctx.draw.line([(ax - 4 * S, ay + 1 * S), (ax, ay + 5 * S), (ax + 4 * S, ay + 1 * S)], fill=(*dn_col, 255), width=max(1, round(1.8 * S)))
    ctx.draw.text(((x1 + 32) * S, row_y * S), ctx.i18n.t("storage.down"), font=ctx.font(12, "semibold"), fill=ctx.theme.text_muted)
    ctx.draw.text(((x1 + 66) * S, (row_y - 1) * S), down_txt, font=ctx.font(13, "bold"), fill=ctx.theme.text_primary)

    # Upload arrow + rate (right half)
    ux, uy = (mid_x + 12) * S, (row_y + 9) * S
    ctx.draw.line([(ux, uy + 5 * S), (ux, uy - 6 * S)], fill=(*up_col, 255), width=max(1, round(1.8 * S)))
    ctx.draw.line([(ux - 4 * S, uy - 2 * S), (ux, uy - 6 * S), (ux + 4 * S, uy - 2 * S)], fill=(*up_col, 255), width=max(1, round(1.8 * S)))
    ctx.draw.text(((mid_x + 24) * S, row_y * S), ctx.i18n.t("storage.up"), font=ctx.font(12, "semibold"), fill=ctx.theme.text_muted)
    ctx.draw.text(((mid_x + 54) * S, (row_y - 1) * S), up_txt, font=ctx.font(13, "bold"), fill=ctx.theme.text_primary)
