"""Windows Core Audio volume slider, mute toggle, and 1-click output device switcher card."""
from __future__ import annotations

from typing import Any, Callable, Dict

from . import Box, RenderContext, draw_card_surface


def _draw_speaker_icon(
    ctx: RenderContext,
    cx: float,
    cy: float,
    muted: bool,
    volume: int,
    ink: tuple[int, int, int, int],
) -> None:
    S = ctx.scale
    d = ctx.draw
    # Speaker body
    d.polygon(
        [
            ((cx - 9) * S, (cy - 4) * S),
            ((cx - 4) * S, (cy - 4) * S),
            ((cx + 1) * S, (cy - 9) * S),
            ((cx + 1) * S, (cy + 9) * S),
            ((cx - 4) * S, (cy + 4) * S),
            ((cx - 9) * S, (cy + 4) * S),
        ],
        fill=ink,
    )
    if muted or volume <= 0:
        d.line([((cx + 4) * S, (cy - 4) * S), ((cx + 11) * S, (cy + 4) * S)], fill=ink, width=max(1, round(2 * S)))
        d.line([((cx + 11) * S, (cy - 4) * S), ((cx + 4) * S, (cy + 4) * S)], fill=ink, width=max(1, round(2 * S)))
    else:
        if volume > 5:
            d.arc(((cx + 1) * S, (cy - 5) * S, (cx + 8) * S, (cy + 5) * S), start=-55, end=55, fill=ink, width=max(1, round(1.8 * S)))
        if volume >= 45:
            d.arc(((cx + 2) * S, (cy - 9) * S, (cx + 12) * S, (cy + 9) * S), start=-55, end=55, fill=ink, width=max(1, round(1.8 * S)))


def draw_audio_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_toggle_mute: Callable[[], None],
    on_set_volume: Callable[[int], None],
    on_cycle_output: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    accent = ctx.theme.role("audio")
    muted = bool(state.get("muted", False))
    vol = max(0, min(100, int(state.get("volume", 0) or 0)))
    devices = list(state.get("devices") or [])
    dev_name = str(state.get("device_name") or ctx.i18n.t("audio.default_device"))
    can_switch = len(devices) >= 2

    # Mute button (left)
    mx1, my1, mx2, my2 = x1 + 12, y1 + 10, x1 + 48, y1 + 42
    mhov = ctx.hover == "audio_mute"
    m_rgb = ctx.theme.alert_danger if muted else accent
    m_bg = ctx.theme.tint_hover(m_rgb, 0.34) if mhov else ctx.theme.tint_dark(m_rgb, 0.22 if muted else 0.16)
    ctx.draw.rounded_rectangle(
        (mx1 * S, my1 * S, mx2 * S, my2 * S),
        radius=9 * S,
        fill=m_bg,
        outline=(*m_rgb, 235) if (muted or mhov) else ctx.theme.tile_edge,
        width=S,
    )
    _draw_speaker_icon(ctx, (mx1 + mx2) / 2.0, (my1 + my2) / 2.0, muted, vol, (*m_rgb, 255))
    ctx.add_spot(mx1, my1, mx2, my2, on_toggle_mute, None, "audio_mute")

    # Volume percentage badge (right)
    pct_str = ctx.i18n.t("audio.muted") if muted else f"{vol}%"
    f_pct = ctx.font(15, "bold")
    pct_w = int(round(ctx.draw.textlength(pct_str, font=f_pct) / S))
    ctx.draw.text(
        ((x2 - 14 - pct_w) * S, (y1 + 16) * S),
        pct_str,
        font=f_pct,
        fill=(*ctx.theme.alert_danger, 255) if muted else ctx.theme.text_primary,
    )

    # Output device switcher pill (center)
    ox1, oy1, ox2, oy2 = x1 + 56, y1 + 10, x2 - 26 - pct_w, y1 + 42
    ohov = ctx.hover == "audio_output"
    if ox2 - ox1 >= 60:
        ctx.draw.rounded_rectangle(
            (ox1 * S, oy1 * S, ox2 * S, oy2 * S),
            radius=9 * S,
            fill=ctx.theme.tile_bg_hover if ohov else ctx.theme.tile_bg,
            outline=(*accent, 220) if ohov else ctx.theme.tile_edge,
            width=S,
        )
        switch_icon_w = 18 if can_switch else 0
        lbl = ctx.fit_text(dev_name, ox2 - ox1 - 18 - switch_icon_w, 13, "semibold")
        ctx.draw.text(((ox1 + 10) * S, (oy1 + 7) * S), lbl, font=ctx.font(13, "semibold"), fill=ctx.theme.text_primary)
        if can_switch:
            # Subtle bidirectional switch arrows '⇄'
            ax = (ox2 - 14) * S
            ay = ((oy1 + oy2) // 2) * S
            a_col = (*accent, 235) if ohov else ctx.theme.text_muted
            ctx.draw.line([(ax - 5 * S, ay - 3 * S), (ax + 5 * S, ay - 3 * S)], fill=a_col, width=max(1, round(1.5 * S)))
            ctx.draw.line([(ax + 2 * S, ay - 6 * S), (ax + 5 * S, ay - 3 * S), (ax + 2 * S, ay)], fill=a_col, width=max(1, round(1.5 * S)))
            ctx.draw.line([(ax + 5 * S, ay + 3 * S), (ax - 5 * S, ay + 3 * S)], fill=a_col, width=max(1, round(1.5 * S)))
            ctx.draw.line([(ax - 2 * S, ay), (ax - 5 * S, ay + 3 * S), (ax - 2 * S, ay + 6 * S)], fill=a_col, width=max(1, round(1.5 * S)))
        ctx.add_spot(ox1, oy1, ox2, oy2, on_cycle_output, None, "audio_output")

    # 10-step clickable volume bar (10% .. 100%)
    bar_x1, bar_x2 = x1 + 14, x2 - 14
    bar_y1, bar_y2 = y2 - 22, y2 - 10
    steps = 10
    gap = 4
    seg_w = (bar_x2 - bar_x1 - gap * (steps - 1)) / float(steps)
    filled_steps = 0 if muted else round(vol / 10.0)
    bar_col = (120, 126, 140) if muted else accent

    for idx in range(steps):
        sx1 = round(bar_x1 + idx * (seg_w + gap))
        sx2 = round(bar_x1 + idx * (seg_w + gap) + seg_w)
        step_pct = (idx + 1) * 10
        hid = f"audio_vol_{step_pct}"
        shov = ctx.hover == hid
        active = idx < filled_steps
        fill = (*bar_col, 255) if (active or shov) else ctx.theme.track_bg
        ctx.draw.rounded_rectangle((sx1 * S, bar_y1 * S, sx2 * S, bar_y2 * S), radius=4 * S, fill=fill)
        ctx.add_spot(sx1 - 1, bar_y1 - 4, sx2 + 1, bar_y2 + 4, lambda p=step_pct: on_set_volume(p), None, hid)
