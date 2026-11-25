"""Peripherals battery tiles (Mouse, Keyboard, DualSense, Handheld, Bluetooth) + BT Drawer."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from . import Box, RenderContext, draw_card_surface


def _render_dualsense_glyph(
    cache: Dict[Any, Any],
    target_w: int,
    target_h: int,
    col: Tuple[int, int, int, int],
    bg_rgb: Tuple[int, int, int],
) -> Image.Image:
    key = ("ds_glyph", target_w, target_h, col, bg_rgb)
    if key in cache:
        return cache[key]
    W, H = 240, 170
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    shell_fill = (
        col[0] // 4 + bg_rgb[0] * 3 // 4,
        col[1] // 4 + bg_rgb[1] * 3 // 4,
        col[2] // 4 + bg_rgb[2] * 3 // 4,
        235,
    )
    grip_dark = (max(0, shell_fill[0] - 14), max(0, shell_fill[1] - 14), max(0, shell_fill[2] - 14), 255)

    d.chord((36, 10, 96, 52), start=180, end=360, fill=grip_dark, outline=col, width=6)
    d.chord((144, 10, 204, 52), start=180, end=360, fill=grip_dark, outline=col, width=6)

    left_grip = [(32, 42), (84, 42), (78, 114), (54, 152), (28, 156), (14, 140), (18, 86)]
    right_grip = [(W - x, y) for (x, y) in left_grip]
    d.polygon(left_grip, fill=shell_fill)
    d.polygon(right_grip, fill=shell_fill)
    d.ellipse((14, 124, 56, 160), fill=shell_fill)
    d.ellipse((W - 56, 124, W - 14, 160), fill=shell_fill)
    d.rounded_rectangle((42, 24, W - 42, 110), radius=24, fill=shell_fill)

    inner_arch = [(54, 110), (82, 86), (158, 86), (186, 110), (168, 132), (72, 132)]
    d.polygon(inner_arch, fill=grip_dark)
    d.ellipse((68, 98, W - 68, 182), fill=(0, 0, 0, 0))

    outer = [
        (46, 24), (194, 24), (212, 38), (224, 88), (224, 140), (204, 158), (182, 148),
        (164, 108), (76, 108), (58, 148), (36, 158), (16, 140), (16, 88), (28, 38),
    ]
    d.line(outer + [outer[0]], fill=col, width=7, joint="curve")

    tp = [(82, 26), (158, 26), (150, 64), (90, 64)]
    d.polygon(tp, fill=grip_dark, outline=col, width=5)
    d.line([(76, 30), (85, 64)], fill=col, width=4)
    d.line([(164, 30), (155, 64)], fill=col, width=4)

    dx, dy = 56, 62
    d.rounded_rectangle((dx - 15, dy - 5, dx + 15, dy + 5), radius=2, fill=col)
    d.rounded_rectangle((dx - 5, dy - 15, dx + 5, dy + 15), radius=2, fill=col)

    bx, by = W - 56, 62
    for ox, oy in ((0, -12), (12, 0), (0, 12), (-12, 0)):
        d.ellipse((bx + ox - 5, by + oy - 5, bx + ox + 5, by + oy + 5), fill=col)

    for sx in (88, W - 88):
        sy = 88
        d.ellipse((sx - 15, sy - 15, sx + 15, sy + 15), fill=grip_dark, outline=col, width=6)
        d.ellipse((sx - 6, sy - 6, sx + 6, sy + 6), fill=col)

    out = im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    cache[key] = out
    return out


def draw_peripherals_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    cfg: Dict[str, Any],
    *,
    bt_drawer_open: bool,
    on_refresh_gamepad: Callable[[], None],
    on_toggle_bt_drawer: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    mouse = state.get("mouse") or {}
    keyboard = state.get("keyboard") or {}
    gp = state.get("gamepad") or {}
    handheld = state.get("handheld") or {}
    bt_on = bool(state.get("bt_on", True))
    bt_devs = list(state.get("bt_devices") or [])
    bt_conn_cnt = sum(1 for d in bt_devs if d.get("connected"))

    auto_hide = bool(cfg.get("auto_hide_offline", False))
    tiles: List[Tuple[str, str, int, bool, Tuple[int, int, int], Optional[Callable[[], None]]]] = []
    if cfg.get("show_mouse", True):
        mb = mouse.get("battery")
        if not auto_hide or mb is not None:
            tiles.append(("mouse", f"{mb}%" if mb is not None else "—", int(mb or 0), mb is not None, ctx.theme.role("mouse"), None))
    if cfg.get("show_keyboard", True):
        kb = keyboard.get("battery")
        if not auto_hide or kb is not None:
            tiles.append(("keyboard", f"{kb}%" if kb is not None else "—", int(kb or 0), kb is not None, ctx.theme.role("keyboard"), None))
    if cfg.get("show_gamepad", True):
        gb = gp.get("battery")
        g_on = bool(gp.get("online"))
        if not auto_hide or (g_on and gb is not None):
            tiles.append(("gamepad", f"{gb}%" if g_on and gb is not None else "—", int(gb or 0), g_on, ctx.theme.role("gamepad"), on_refresh_gamepad))
    if cfg.get("show_handheld", False):
        hb = handheld.get("battery")
        h_ok = not handheld.get("stale", True)
        if not auto_hide or (h_ok and hb is not None):
            tiles.append(("handheld", f"{hb}%" if hb is not None else "—", int(hb or 0), h_ok, ctx.theme.role("handheld"), None))
    if cfg.get("show_bluetooth", True):
        bt_txt = str(bt_conn_cnt) if bt_conn_cnt > 0 else ctx.i18n.t("peripherals.bt_on" if bt_on else "peripherals.bt_off")
        tiles.append(("bt", bt_txt, 100 if bt_on else 0, bt_on, ctx.theme.role("bluetooth"), on_toggle_bt_drawer))

    if not tiles:
        return

    n = len(tiles)
    gap = 6
    tw = (x2 - x1 - 24 - gap * (n - 1)) / float(n)
    tx0 = x1 + 12
    ty1, ty2 = y1 + 10, y2 - 10

    for i, (kind, val_txt, pct, active, col, cb) in enumerate(tiles):
        # Critical low battery alert (<15%) always turns red even in single_accent
        if kind != "bt" and active and 0 < pct <= 15:
            col = ctx.theme.alert_danger
        bx1 = round(tx0 + i * (tw + gap))
        bx2 = round(tx0 + i * (tw + gap) + tw)
        hov = ctx.hover == f"dev_{kind}"
        bg = ctx.theme.tile_bg_hover if hov else (ctx.theme.tile_bg if active else ctx.theme.tile_bg_inactive)
        bd = (*col, 255) if (hov or (kind == "bt" and bt_drawer_open)) else ctx.theme.tile_edge
        ctx.draw.rounded_rectangle(
            (bx1 * S, ty1 * S, bx2 * S, ty2 * S),
            radius=11 * S,
            fill=bg,
            outline=bd,
            width=2 * S if hov else S,
        )

        icx = (bx1 + (bx2 - bx1) // 2) * S
        icy = (ty1 + 25) * S
        ic_col = (*col, 255) if active else (120, 126, 140, 255)

        if kind == "mouse":
            ctx.draw.rounded_rectangle((icx - 11 * S, icy - 15 * S, icx + 11 * S, icy + 15 * S), radius=10 * S, outline=ic_col, width=2 * S)
            ctx.draw.line([(icx, icy - 14 * S), (icx, icy - 3 * S)], fill=ic_col, width=2 * S)
            ctx.draw.rounded_rectangle((icx - 2 * S, icy - 10 * S, icx + 2 * S, icy - 4 * S), radius=1 * S, fill=ic_col)
        elif kind == "keyboard":
            ctx.draw.rounded_rectangle((icx - 19 * S, icy - 10 * S, icx + 19 * S, icy + 10 * S), radius=3 * S, outline=ic_col, width=2 * S)
            for row in range(2):
                for c in range(6):
                    a = icx + (-15 + c * 6) * S
                    b = icy + (-5 + row * 5) * S
                    ctx.draw.rectangle((a, b, a + 2 * S, b + 2 * S), fill=ic_col)
            ctx.draw.line((icx - 10 * S, icy + 6 * S, icx + 10 * S, icy + 6 * S), fill=ic_col, width=2 * S)
        elif kind == "gamepad":
            ds = _render_dualsense_glyph(ctx.img_cache, 46 * S, 32 * S, ic_col, bg[:3])
            ctx.img.alpha_composite(ds, (icx - 23 * S, icy - 16 * S))
        elif kind == "handheld":
            ctx.draw.rounded_rectangle((icx - 18 * S, icy - 10 * S, icx + 18 * S, icy + 10 * S), radius=6 * S, outline=ic_col, width=2 * S)
            ctx.draw.rectangle((icx - 9 * S, icy - 7 * S, icx + 9 * S, icy + 7 * S), outline=ic_col, width=2 * S)
            ctx.draw.ellipse((icx - 15 * S, icy - 3 * S, icx - 11 * S, icy + 1 * S), fill=ic_col)
            ctx.draw.ellipse((icx + 11 * S, icy - 3 * S, icx + 15 * S, icy + 1 * S), fill=ic_col)
        elif kind == "bt":
            bx = icx - 3 * S
            ctx.draw.line([(bx, icy - 12 * S), (bx, icy + 12 * S)], fill=ic_col, width=2 * S)
            ctx.draw.line([(bx, icy - 12 * S), (bx + 8 * S, icy - 5 * S), (bx - 7 * S, icy + 6 * S)], fill=ic_col, width=2 * S)
            ctx.draw.line([(bx, icy + 12 * S), (bx + 8 * S, icy + 5 * S), (bx - 7 * S, icy - 6 * S)], fill=ic_col, width=2 * S)
            ax = icx + 12 * S
            ctx.draw.line([(ax - 3 * S, icy - 2 * S), (ax, icy + 2 * S), (ax + 3 * S, icy - 2 * S)], fill=(200, 210, 230, 255), width=2 * S)

        f_v = ctx.font(14 if kind == "bt" else 16, "bold")
        tb = ctx.draw.textbbox((0, 0), val_txt, font=f_v)
        ctx.draw.text(
            (icx - (tb[2] - tb[0]) // 2, (ty1 + 46) * S),
            val_txt,
            font=f_v,
            fill=ctx.theme.text_primary if active else (130, 136, 150, 255),
        )

        if kind == "handheld" and handheld.get("stale", True):
            f_old = ctx.font(12, "regular")
            stale_lbl = ctx.i18n.t("peripherals.stale")
            ob = ctx.draw.textbbox((0, 0), stale_lbl, font=f_old)
            ctx.draw.text((icx - (ob[2] - ob[0]) // 2, (ty2 - 18) * S), stale_lbl, font=f_old, fill=(130, 136, 150, 255))
            continue

        bar_x1 = (bx1 + 10) * S
        bar_y1 = (ty2 - 8) * S
        bar_w = max(8 * S, (bx2 - bx1 - 20) * S)
        ctx.draw.rounded_rectangle((bar_x1, bar_y1, bar_x1 + bar_w, bar_y1 + 4 * S), radius=2 * S, fill=(22, 24, 30, 255))
        if active and pct > 0:
            fw = max(4 * S, int(bar_w * min(100, pct) / 100.0))
            ctx.draw.rounded_rectangle((bar_x1, bar_y1, bar_x1 + fw, bar_y1 + 4 * S), radius=2 * S, fill=(*col, 255))

        if cb:
            ctx.add_spot(bx1, ty1, bx2, ty2, cb, None, f"dev_{kind}")


def draw_bt_drawer(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_toggle_radio: Callable[[], None],
    on_close: Callable[[], None],
    on_open_settings: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    ctx.hotspots[:] = [s for s in ctx.hotspots if s[2] <= x1 or s[0] >= x2 or s[3] <= y1 or s[1] >= y2]

    bt_col = ctx.theme.role("bluetooth")
    ctx.draw.rounded_rectangle(
        (x1 * S, y1 * S, x2 * S, y2 * S),
        radius=16 * S,
        fill=(22, 25, 34, 252),
        outline=(*bt_col, 255),
        width=2 * S,
    )
    bt_on = bool(state.get("bt_on", True))
    bt_devs = list(state.get("bt_devices") or [])

    ctx.draw.text(((x1 + 16) * S, (y1 + 14) * S), ctx.i18n.t("peripherals.bt_title"), font=ctx.font(16, "bold"), fill=ctx.theme.text_primary)

    tx1, ty1 = x2 - 110, y1 + 12
    ctx.draw.rounded_rectangle(
        (tx1 * S, ty1 * S, (x2 - 44) * S, (ty1 + 28) * S),
        radius=8 * S,
        fill=(*bt_col, 255) if bt_on else (55, 60, 72, 255),
    )
    rad_txt = ctx.i18n.t("peripherals.bt_on" if bt_on else "peripherals.bt_off")
    ctx.draw.text(((tx1 + 12) * S, (ty1 + 5) * S), rad_txt, font=ctx.font(13, "bold"), fill=(255, 255, 255, 255))
    ctx.add_spot(tx1, ty1, x2 - 44, ty1 + 28, on_toggle_radio, None, "bt_toggle_rad")

    cx_x, cy_x = (x2 - 24) * S, (y1 + 25) * S
    ctx.draw.line([(cx_x - 5 * S, cy_x - 5 * S), (cx_x + 5 * S, cy_x + 5 * S)], fill=(190, 198, 215, 255), width=2 * S)
    ctx.draw.line([(cx_x - 5 * S, cy_x + 5 * S), (cx_x + 5 * S, cy_x - 5 * S)], fill=(190, 198, 215, 255), width=2 * S)
    ctx.add_spot(x2 - 38, y1 + 10, x2 - 10, y1 + 40, on_close, None, "bt_close")

    ry = y1 + 52
    rh = 44
    if not bt_devs:
        ctx.draw.text(((x1 + 16) * S, (ry + 12) * S), ctx.i18n.t("peripherals.bt_loading"), font=ctx.font(14), fill=ctx.theme.text_muted)
    else:
        for idx, d in enumerate(bt_devs[:4]):
            dy1 = ry + idx * (rh + 6)
            dy2 = dy1 + rh
            conn = bool(d.get("connected"))
            ctx.draw.rounded_rectangle(
                ((x1 + 12) * S, dy1 * S, (x2 - 12) * S, dy2 * S),
                radius=10 * S,
                fill=ctx.theme.tint_dark(bt_col, 0.25) if conn else ctx.theme.tile_bg_inactive,
                outline=(*bt_col, 255) if conn else ctx.theme.tile_edge,
                width=S,
            )
            dot_c = (*ctx.theme.status_color("ok", "bluetooth"), 255) if conn else (120, 126, 140, 255)
            ctx.draw.ellipse(((x1 + 24) * S, (dy1 + 17) * S, (x1 + 34) * S, (dy1 + 27) * S), fill=dot_c)
            ctx.draw.text(
                ((x1 + 44) * S, (dy1 + 11) * S),
                ctx.fit_text(str(d.get("name", "Device")), x2 - x1 - 170, 14, "bold"),
                font=ctx.font(14, "bold"),
                fill=ctx.theme.text_primary,
            )
            batt = d.get("battery")
            st_lbl = f"{batt}%" if isinstance(batt, int) else ctx.i18n.t("peripherals.bt_connected" if conn else "peripherals.bt_paired")
            ctx.draw.text(
                ((x2 - 112) * S, (dy1 + 12) * S),
                st_lbl,
                font=ctx.font(13, "semibold"),
                fill=dot_c if conn else ctx.theme.text_muted,
            )
            ctx.add_spot(x1 + 12, dy1, x2 - 12, dy2, on_open_settings, None, f"bt_dev_{idx}")

    by1, by2 = y2 - 48, y2 - 12
    bhov = ctx.hover == "bt_settings_btn"
    ctx.draw.rounded_rectangle(
        ((x1 + 14) * S, by1 * S, (x2 - 14) * S, by2 * S),
        radius=10 * S,
        fill=ctx.theme.tint_hover(bt_col, 0.72) if bhov else (*bt_col, 255),
    )
    btn_txt = ctx.i18n.t("peripherals.bt_settings")
    f_bt = ctx.font(14, "bold")
    tb = ctx.draw.textbbox((0, 0), btn_txt, font=f_bt)
    ctx.draw.text((((x1 + x2) * S - (tb[2] - tb[0])) // 2, (by1 + 8) * S), btn_txt, font=f_bt, fill=(255, 255, 255, 255))
    ctx.add_spot(x1 + 14, by1, x2 - 14, by2, on_open_settings, None, "bt_settings_btn")
