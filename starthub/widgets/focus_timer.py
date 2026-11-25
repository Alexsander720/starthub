"""Compact Pomodoro / Focus Timer card renderer (Tier 1, zero API keys)."""
from __future__ import annotations

from typing import Any, Callable, Dict

from . import Box, RenderContext, draw_card_surface, draw_progress_bar


def draw_focus_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_toggle: Callable[[], None],
    on_reset: Callable[[], None],
    on_switch_phase: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    phase = str(state.get("phase") or "work")
    running = bool(state.get("running", False))
    display = str(state.get("display") or "25:00")
    pct = float(state.get("percent", 0.0) or 0.0)
    sessions = int(state.get("sessions_done", 0) or 0)

    accent = ctx.theme.role("focus_work" if phase == "work" else "focus_break")
    phase_lbl = ctx.i18n.t("focus.work" if phase == "work" else "focus.break")

    # Clickable phase pill (left)
    px1, py1, px2, py2 = x1 + 12, y1 + 12, x1 + 106, y1 + 42
    phov = ctx.hover == "focus_phase"
    ctx.draw.rounded_rectangle(
        (px1 * S, py1 * S, px2 * S, py2 * S),
        radius=9 * S,
        fill=ctx.theme.tint_hover(accent, 0.30) if phov else ctx.theme.tint_dark(accent, 0.22),
        outline=(*accent, 235 if (running or phov) else 155),
        width=S,
    )
    ctx.draw.ellipse(((px1 + 10) * S, (py1 + 11) * S, (px1 + 18) * S, (py1 + 19) * S), fill=(*accent, 255))
    ctx.draw.text(((px1 + 24) * S, (py1 + 6) * S), ctx.fit_text(phase_lbl, 72, 13, "bold"), font=ctx.font(13, "bold"), fill=(*accent, 255))
    ctx.add_spot(px1, py1, px2, py2, on_switch_phase, None, "focus_phase")

    # Session counter badge aligned cleanly with phase pill and clock
    if sessions > 0:
        ctx.draw.text(
            ((px2 + 10) * S, (y1 + 27) * S),
            f"×{sessions}",
            anchor="lm",
            font=ctx.font(12, "semibold"),
            fill=ctx.theme.text_muted,
        )

    # Big countdown readout (center)
    center_x = (x1 + x2) // 2 + 12
    ctx.draw.text(
        (center_x * S, (y1 + 27) * S),
        display,
        anchor="mm",
        font=ctx.font(24, "bold"),
        fill=ctx.theme.text_primary if running else ctx.theme.text_secondary,
    )

    # Reset button (right-2)
    rx1, ry1, rx2, ry2 = x2 - 86, y1 + 12, x2 - 54, y1 + 42
    rhov = ctx.hover == "focus_reset"
    ctx.draw.rounded_rectangle(
        (rx1 * S, ry1 * S, rx2 * S, ry2 * S),
        radius=9 * S,
        fill=ctx.theme.tile_bg_hover if rhov else ctx.theme.tile_bg,
        outline=ctx.theme.tile_edge,
        width=S,
    )
    rcx, rcy = ((rx1 + rx2) / 2.0) * S, ((ry1 + ry2) / 2.0) * S
    r_ink = ctx.theme.text_primary if rhov else ctx.theme.text_secondary
    ctx.draw.arc((rcx - 6 * S, rcy - 6 * S, rcx + 6 * S, rcy + 6 * S), start=40, end=320, fill=r_ink, width=max(1, round(1.8 * S)))
    ctx.draw.polygon([(rcx + 3 * S, rcy - 8 * S), (rcx + 7 * S, rcy - 3 * S), (rcx + 1 * S, rcy - 3 * S)], fill=r_ink)
    ctx.add_spot(rx1, ry1, rx2, ry2, on_reset, None, "focus_reset")

    # Play / Pause primary button (right-1)
    bx1, by1, bx2, by2 = x2 - 46, y1 + 12, x2 - 12, y1 + 42
    bhov = ctx.hover == "focus_toggle"
    ctx.draw.rounded_rectangle(
        (bx1 * S, by1 * S, bx2 * S, by2 * S),
        radius=9 * S,
        fill=ctx.theme.tint_hover(accent, 0.72) if bhov else (*accent, 235 if running else 210),
    )
    bcx, bcy = ((bx1 + bx2) / 2.0) * S, ((by1 + by2) / 2.0) * S
    if running:
        for dx in (-4, 2):
            ctx.draw.rectangle((bcx + dx * S, bcy - 6 * S, bcx + (dx + 2.5) * S, bcy + 6 * S), fill=(255, 255, 255, 255))
    else:
        ctx.draw.polygon(
            [(bcx - 4 * S, bcy - 6 * S), (bcx - 4 * S, bcy + 6 * S), (bcx + 6 * S, bcy)],
            fill=(255, 255, 255, 255),
        )
    ctx.add_spot(bx1, by1, bx2, by2, on_toggle, None, "focus_toggle")

    # Slim progress bar along bottom
    draw_progress_bar(ctx, x1 + 12, y2 - 10, x2 - 12, y2 - 5, pct, accent, radius=2)
