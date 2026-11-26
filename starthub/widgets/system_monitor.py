"""CPU / GPU (+ temperature) / RAM system monitor card renderer."""
from __future__ import annotations

from typing import Any, Dict

from . import Box, RenderContext, draw_card_surface, draw_panel_icon, draw_progress_bar


def draw_system_monitor(ctx: RenderContext, box: Box, state: Dict[str, Any]) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    col_w = (x2 - x1 - 24) / 3.0
    keys = (
        ("cpu", ctx.i18n.t("monitor.cpu")),
        ("gpu", ctx.i18n.t("monitor.gpu")),
        ("ram", ctx.i18n.t("monitor.ram")),
    )
    icon_ink = ctx.theme.text_secondary
    for i, (key, label) in enumerate(keys):
        x = x1 + 12 + i * col_w
        draw_panel_icon(ctx, key, x, y1 + 9, icon_ink)
        ctx.draw.text(((x + 30) * S, (y1 + 11) * S), label, font=ctx.font(13, "semibold"), fill=ctx.theme.text_secondary)

        val = state.get(key)
        text = "—" if val is None else f"{int(val)}%"
        bar_rgb = ctx.theme.monitor_bar_color(val)
        f_val = ctx.font(23, "semibold")
        ctx.draw.text((x * S, (y1 + 35) * S), text, font=f_val, fill=ctx.theme.text_primary)

        if key == "gpu" and state.get("temperature") is not None:
            tw = ctx.draw.textlength(text, font=f_val) / S
            ctx.draw.text(
                ((x + tw + 5) * S, (y1 + 42) * S),
                f"{state['temperature']}°",
                font=ctx.font(13, "regular"),
                fill=ctx.theme.text_muted,
            )

        draw_progress_bar(ctx, x, y2 - 13, x + col_w - 12, y2 - 7, val, bar_rgb, radius=3)
