"""Universal Smart Lights (Philips Hue / Home Assistant / WLED) 1–4 tile toggle + dimmer card renderer."""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from . import Box, RenderContext, draw_card_surface, draw_panel_icon


def draw_hue_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    on_command: Callable[[str, Any], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    if not state.get("ready"):
        ctx.draw.text(((x1 + 16) * S, (y1 + 16) * S), ctx.i18n.t("hue.title"), font=ctx.font(18, "semibold"), fill=ctx.theme.text_primary)
        msg = str(state.get("message") or ctx.i18n.t("hue.need_key"))
        ctx.draw.text(((x1 + 16) * S, (y1 + 48) * S), ctx.fit_text(msg, x2 - x1 - 32, 14), font=ctx.font(14), fill=ctx.theme.text_muted)
        return

    targets: List[Dict[str, Any]] = list(state.get("targets") or [])[:4]
    if not targets:
        return

    hue_rgb = ctx.theme.role("hue")
    two_rows = len(targets) > 2
    cols = 2 if len(targets) >= 2 else 1
    rows = 2 if two_rows else 1
    tile_w = (x2 - x1 - 20 - 8 * (cols - 1)) / float(cols)
    top = y1 + 10
    dimmer_area_h = 40
    avail_h = max(54, (y2 - y1) - 10 - dimmer_area_h)
    row_gap = 8 if two_rows else 0
    tile_h = min(74 if not two_rows else 58, max(44, (avail_h - row_gap) // rows))

    dimmer_key = state.get("dimmer_key")
    dimmer_target = next((t for t in targets if t["key"] == dimmer_key), None)
    if dimmer_target is None:
        dimmer_target = next((t for t in targets if t.get("dimmer")), targets[0])

    for i, target in enumerate(targets):
        key = target["key"]
        reachable = bool(target.get("reachable", True))
        on = bool(target.get("on")) and reachable
        col_i = i % cols
        row_i = i // cols
        tx = x1 + 10 + col_i * (tile_w + 8)
        ty = top + row_i * (tile_h + row_gap)
        hid = f"hue_{key}"
        hov = ctx.hover == hid and reachable

        ink = (*hue_rgb, 255) if on else (ctx.theme.text_secondary if reachable else ctx.theme.text_muted)
        fill = ctx.theme.tint_dark(hue_rgb, 0.24) if on else (ctx.theme.tile_bg if reachable else ctx.theme.tile_bg_inactive)
        if hov:
            fill = ctx.theme.tint_hover(hue_rgb, 0.30) if on else ctx.theme.tile_bg_hover
        outline = (*hue_rgb, 185) if on else ctx.theme.tile_edge

        ctx.draw.rounded_rectangle((tx * S, ty * S, (tx + tile_w) * S, (ty + tile_h) * S), radius=10 * S, fill=fill, outline=outline, width=S)
        draw_panel_icon(ctx, str(target.get("icon") or "bulb"), tx + 11, ty + (tile_h - 24) // 2, ink, lit=on)

        label_w = tile_w - 50
        label = str(target.get("label") or "Light")
        lbl_y = ty + (8 if two_rows else 12)
        st_y = ty + (28 if two_rows else 36)
        ctx.draw.text(((tx + 42) * S, lbl_y * S), ctx.fit_text(label, label_w, 13 if two_rows else 14, "semibold"), font=ctx.font(13 if two_rows else 14, "semibold"), fill=ink)
        status = ctx.i18n.t("hue.on" if on else ("hue.off" if reachable else "hue.offline"))
        ctx.draw.text(((tx + 42) * S, st_y * S), status, font=ctx.font(12 if two_rows else 13), fill=ink)

        if reachable:
            # Left-click toggles light; Right-click selects this light for the bottom dimmer bar
            ctx.add_spot(
                int(tx),
                int(ty),
                int(tx + tile_w),
                int(ty + tile_h),
                lambda k=key: on_command(k, "toggle"),
                lambda k=key: on_command(k, "select_dimmer"),
                hid,
            )

    # Bottom 10-step dimmer row for selected/primary dimmable target
    enabled = bool(dimmer_target.get("reachable", True))
    pct = round(int(dimmer_target.get("bri", 0)) * 100 / 254.0)
    d_label = ctx.fit_text(str(dimmer_target.get("label") or "Light").split()[0], 72, 13, "semibold")
    val_txt = f"{d_label} {pct}%" if enabled else f"{d_label} —"
    ctx.draw.text(
        ((x1 + 14) * S, (y2 - 30) * S),
        val_txt,
        font=ctx.font(13, "semibold"),
        fill=(*hue_rgb, 255) if enabled else ctx.theme.text_muted,
    )
    left = x1 + 128
    step = (x2 - 12 - left) / 10.0
    for i in range(10):
        a = round(left + i * step)
        end = round(left + (i + 1) * step)
        b = max(a + 2, end - 4)
        hid = f"hue_bri_{(i + 1) * 10}"
        filled = enabled and pct >= i * 10 + 5
        col = (*hue_rgb, 255) if filled else ctx.theme.track_bg
        if enabled and ctx.hover == hid:
            col = (min(255, hue_rgb[0] + 25), min(255, hue_rgb[1] + 25), min(255, hue_rgb[2] + 25), 255)
        ctx.draw.rounded_rectangle((a * S, (y2 - 26) * S, b * S, (y2 - 14) * S), radius=3 * S, fill=col)
        if enabled:
            tkey = dimmer_target["key"]
            ctx.add_spot(a, y2 - 36, end, y2 - 4, lambda k=tkey, p=(i + 1) * 10: on_command(k, p), None, hid)
