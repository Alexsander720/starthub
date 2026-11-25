"""EcoFlow portable power station telemetry & controls card (clean vector chassis or user PNG)."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict

from . import Box, RenderContext, draw_card_surface, get_cached_image


def _draw_vector_power_station(
    ctx: RenderContext,
    x: int,
    y: int,
    w: int,
    h: int,
    *,
    soc: int,
    is_grid: bool,
    stale: bool,
) -> None:
    """Clean, original vector portable power station graphic (zero trademarked brand PNGs)."""
    S = ctx.scale
    accent = ctx.theme.alert_warn if stale else (ctx.theme.role("ecoflow_soc") if is_grid else ctx.theme.alert_danger)

    # Top carry handle arch
    hx1, hx2 = x + 14, x + w - 14
    ctx.draw.rounded_rectangle(
        (hx1 * S, (y + 6) * S, hx2 * S, (y + 28) * S),
        radius=8 * S,
        outline=(110, 118, 134, 255),
        width=4 * S,
    )
    # Main rugged matte body
    by1, by2 = y + 20, y + h - 6
    ctx.draw.rounded_rectangle(
        ((x + 6) * S, by1 * S, (x + w - 6) * S, by2 * S),
        radius=11 * S,
        fill=(32, 36, 44, 255),
        outline=(86, 94, 110, 255),
        width=2 * S,
    )
    # Upper metallic fascia strip
    ctx.draw.rounded_rectangle(
        ((x + 12) * S, (by1 + 7) * S, (x + w - 12) * S, (by1 + 21) * S),
        radius=4 * S,
        fill=(44, 49, 60, 255),
    )
    # Digital LCD display screen
    lx1, ly1, lx2, ly2 = x + 16, by1 + 27, x + w - 16, by1 + 63
    ctx.draw.rounded_rectangle(
        (lx1 * S, ly1 * S, lx2 * S, ly2 * S),
        radius=6 * S,
        fill=(14, 18, 24, 255),
        outline=(*accent, 210),
        width=S,
    )
    lcd_txt = "—" if stale else f"{soc}%"
    ctx.draw.text(
        (((lx1 + lx2) * S) // 2, ((ly1 + ly2) * S) // 2 - 2 * S),
        lcd_txt,
        anchor="mm",
        font=ctx.font(14, "bold"),
        fill=(*accent, 255),
    )
    # Mini SoC bar inside LCD
    bar_x1, bar_x2 = lx1 + 6, lx2 - 6
    bar_y = ly2 - 7
    ctx.draw.rounded_rectangle((bar_x1 * S, bar_y * S, bar_x2 * S, (bar_y + 3) * S), radius=S, fill=(40, 46, 56, 255))
    if not stale and soc > 0:
        fw = max(3, int((bar_x2 - bar_x1) * min(100, soc) / 100.0))
        ctx.draw.rounded_rectangle((bar_x1 * S, bar_y * S, (bar_x1 + fw) * S, (bar_y + 3) * S), radius=S, fill=(*accent, 255))

    # Front USB / AC port indicators at bottom of chassis
    py = by2 - 20
    for dx in (18, 30, 42):
        ctx.draw.rounded_rectangle(((x + dx) * S, py * S, (x + dx + 7) * S, (py + 9) * S), radius=2 * S, fill=(64, 72, 86, 255))
    ctx.draw.ellipse(((x + w - 28) * S, (py + 1) * S, (x + w - 18) * S, (py + 11) * S), outline=(*accent, 220), width=2 * S)


def draw_ecoflow_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_cycle_charge: Callable[[], None],
    on_toggle_usb: Callable[[], None],
    on_toggle_dc12v: Callable[[], None],
    on_toggle_beep: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box, radius=min(16, ctx.theme.corner_radius + 2))

    stale = bool(state.get("stale", True))
    soc = max(0, min(100, int(state.get("soc", 0) or 0)))
    in_w = int(round(float(state.get("in_watts", 0) or 0)))
    out_w = int(round(float(state.get("out_watts", 0) or 0)))
    is_grid = bool(state.get("is_grid", True))
    est_min = int(state.get("est_dsg_min", 0) or 0)
    rem_wh = int(state.get("remain_wh", 0) or 0)
    chg_max = int(state.get("chg_pow_max", 200) or 200)
    chg_label = ctx.i18n.t("ecoflow.limit", w=chg_max) if state.get("chg_pow_max_reported") else ctx.i18n.t("ecoflow.limit_empty")
    usb_open = bool(state.get("usb_open", False))
    dc_open = bool(state.get("dc_out_open", False))
    beep_on = bool(state.get("beep_on", True))
    dev_name = str(state.get("device_name") or "EcoFlow Station")

    # Station artwork on top-right
    custom_img = get_cached_image(ctx.img_cache, str(state.get("image_path") or ""), (92 * S, 122 * S))
    if custom_img is not None:
        ctx.img.paste(custom_img, ((x2 - 106) * S, (y1 + 10) * S), custom_img)
    else:
        _draw_vector_power_station(ctx, x2 - 104, y1 + 12, 88, 118, soc=soc, is_grid=is_grid, stale=stale)

    lx = x1 + 16
    ctx.draw.text((lx * S, (y1 + 13) * S), ctx.fit_text(dev_name, x2 - lx - 114, 17, "bold"), font=ctx.font(17, "bold"), fill=ctx.theme.text_primary)

    # Grid status row — CRITICAL alerts (BLACKOUT red, STALE amber) ALWAYS keep alert color!
    if stale:
        grid_txt = ctx.i18n.t("ecoflow.stale")
        grid_col = (*ctx.theme.alert_warn, 255)
    elif not is_grid:
        grid_txt = ctx.i18n.t("ecoflow.battery_blackout")
        grid_col = (*ctx.theme.alert_danger, 255)
    elif in_w > out_w + 25:
        grid_txt = ctx.i18n.t("ecoflow.grid_charging")
        grid_col = (*ctx.theme.role("ecoflow_soc"), 255)
    else:
        grid_txt = ctx.i18n.t("ecoflow.grid_bypass")
        grid_col = (*ctx.theme.role("ecoflow_soc"), 255)

    ctx.draw.ellipse((lx * S, (y1 + 43) * S, (lx + 8) * S, (y1 + 51) * S), fill=grid_col)
    ctx.draw.text(((lx + 14) * S, (y1 + 38) * S), ctx.fit_text(grid_txt, x2 - lx - 128, 13, "bold"), font=ctx.font(13, "bold"), fill=grid_col)

    # 5 slanted SoC segments + SoC % + Wh
    seg_y = (y1 + 66) * S
    seg_h = 18 * S
    seg_w = 7 * S
    slant = 4 * S
    active_segs = 0 if stale else (max(1, int(math.ceil(soc / 20.0))) if soc > 0 else 0)
    soc_rgb = ctx.theme.alert_danger if (not stale and (not is_grid or soc <= 15)) else ctx.theme.role("ecoflow_soc")
    for i in range(5):
        sx = (lx + i * 11) * S
        pts = [(sx + slant, seg_y), (sx + slant + seg_w, seg_y), (sx + seg_w, seg_y + seg_h), (sx, seg_y + seg_h)]
        col = (*soc_rgb, 255) if i < active_segs else (58, 62, 70, 255)
        ctx.draw.polygon(pts, fill=col)

    ctx.draw.text(((lx + 64) * S, (y1 + 57) * S), "—" if stale else f"{soc}%", font=ctx.font(24, "bold"), fill=ctx.theme.text_primary)
    wh_str = ctx.i18n.t("ecoflow.wh_empty") if stale else ctx.i18n.t("ecoflow.wh", wh=rem_wh)
    ctx.draw.text(((lx + 138) * S, (y1 + 65) * S), wh_str, font=ctx.font(13, "semibold"), fill=ctx.theme.text_secondary)

    # 3 Telemetry boxes (Input / Output / Backup)
    dur_h, dur_m = est_min // 60, est_min % 60
    dur_str = ctx.i18n.t("ecoflow.duration", h=dur_h, m=dur_m) if est_min > 0 else "—"
    metrics = [
        (ctx.i18n.t("ecoflow.in_label"), ctx.i18n.t("ecoflow.watts", w=in_w), ctx.theme.role("ecoflow_in")),
        (ctx.i18n.t("ecoflow.out_label"), ctx.i18n.t("ecoflow.watts", w=out_w), ctx.theme.role("ecoflow_out")),
        (ctx.i18n.t("ecoflow.backup_label"), dur_str, ctx.theme.role("ecoflow_backup")),
    ]
    if stale:
        metrics = [(lbl, "—", col) for lbl, _, col in metrics]

    mw = 88
    my1, my2 = y1 + 98, y1 + 154
    for i, (m_lbl, m_val, m_rgb) in enumerate(metrics):
        mx1 = lx + i * (mw + 6)
        mx2 = mx1 + mw
        ctx.draw.rounded_rectangle((mx1 * S, my1 * S, mx2 * S, my2 * S), radius=10 * S, fill=ctx.theme.tile_bg, outline=ctx.theme.tile_edge, width=S)
        ctx.draw.text(((mx1 + 9) * S, (my1 + 6) * S), m_lbl, font=ctx.font(12, "bold"), fill=(*m_rgb, 255))
        ctx.draw.text(((mx1 + 9) * S, (my1 + 24) * S), m_val, font=ctx.font(15, "bold"), fill=ctx.theme.text_primary)

    # Bottom hardware controls row (Limit | USB | 12V | Beep)
    cy1, cy2 = y2 - 44, y2 - 10
    on_s = ctx.i18n.t("peripherals.bt_on")
    off_s = ctx.i18n.t("peripherals.bt_off")
    controls = [
        (chg_label, "ef_chg", True, ctx.theme.role("ecoflow_limit"), on_cycle_charge, 1.32),
        (ctx.i18n.t("ecoflow.usb", state=on_s if usb_open else off_s), "ef_usb", usb_open, ctx.theme.role("ecoflow_usb"), on_toggle_usb, 1.0),
        (ctx.i18n.t("ecoflow.dc", state=on_s if dc_open else off_s), "ef_dc", dc_open, ctx.theme.role("ecoflow_dc"), on_toggle_dc12v, 1.0),
        (ctx.i18n.t("ecoflow.beep"), "ef_beep", beep_on, ctx.theme.role("ecoflow_beep"), on_toggle_beep, 0.72),
    ]
    total_weight = sum(c[5] for c in controls)
    avail_w = (x2 - x1 - 32) - 6 * (len(controls) - 1)
    cx_cur = float(lx)

    for c_lbl, c_key, c_on, c_rgb, c_cb, weight in controls:
        cw = avail_w * (weight / total_weight)
        enabled = not stale
        if stale:
            c_on = False
            if c_key == "ef_chg":
                c_lbl = ctx.i18n.t("ecoflow.limit_empty")
            elif c_key == "ef_usb":
                c_lbl = ctx.i18n.t("ecoflow.usb", state="—")
            elif c_key == "ef_dc":
                c_lbl = ctx.i18n.t("ecoflow.dc", state="—")
        cx1, cx2 = round(cx_cur), round(cx_cur + cw)
        cx_cur += cw + 6
        hov = enabled and ctx.hover == c_key
        bg = ctx.theme.tint_hover(c_rgb, 0.34) if (hov and c_on) else (ctx.theme.tint_dark(c_rgb, 0.24) if c_on else (ctx.theme.tile_bg_hover if hov else ctx.theme.tile_bg))
        bd = (*c_rgb, 255) if (c_on or hov) else ctx.theme.tile_edge
        ctx.draw.rounded_rectangle((cx1 * S, cy1 * S, cx2 * S, cy2 * S), radius=9 * S, fill=bg, outline=bd, width=S)
        if enabled:
            ctx.add_spot(cx1, cy1, cx2, cy2, c_cb, None, c_key)
        f_c = ctx.font(13, "bold")
        fit_c = ctx.fit_text(c_lbl, cw - 8, 13, "bold")
        ctx.draw.text((((cx1 + cx2) * S) // 2, ((cy1 + cy2) * S) // 2), fit_c, anchor="mm", font=f_c, fill=(*c_rgb, 255) if c_on else ctx.theme.text_muted)
