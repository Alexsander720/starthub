"""Android Phone Hub card (clean vector chassis), collapsible Photos strip, and SMS/2FA bar."""
from __future__ import annotations

from typing import Any, Callable, Dict

from . import Box, RenderContext, draw_card_surface, get_cached_image, get_photo_thumb


def _draw_vector_phone_silhouette(ctx: RenderContext, x: int, y: int, w: int, h: int, online: bool) -> None:
    """Clean, copyright-free vector smartphone bezel with subtle theme gradient screen."""
    S = ctx.scale
    accent = ctx.theme.role("phone_screen")
    # Outer metallic bezel
    ctx.draw.rounded_rectangle(
        (x * S, y * S, (x + w) * S, (y + h) * S),
        radius=11 * S,
        fill=(24, 28, 36, 255),
        outline=(118, 126, 144, 255) if online else (74, 80, 92, 255),
        width=2 * S,
    )
    # Inner screen glass with accent ambient glow
    pad = 4
    ctx.draw.rounded_rectangle(
        ((x + pad) * S, (y + pad) * S, (x + w - pad) * S, (y + h - pad) * S),
        radius=8 * S,
        fill=ctx.theme.tint_dark(accent, 0.28) if online else (28, 31, 38, 255),
    )
    # Abstract wallpaper orbs
    if online:
        ctx.draw.ellipse(((x + 8) * S, (y + 24) * S, (x + w - 8) * S, (y + 62) * S), fill=(*accent, 90))
        ctx.draw.ellipse(((x + 14) * S, (y + 46) * S, (x + w - 6) * S, (y + 84) * S), fill=(*ctx.theme.role("phone_shot"), 70))
    # Camera punch-hole
    cx = (x + w // 2) * S
    ctx.draw.ellipse((cx - 3 * S, (y + 8) * S, cx + 3 * S, (y + 14) * S), fill=(12, 14, 18, 255))
    # Minimal home indicator pill
    ctx.draw.rounded_rectangle((cx - 10 * S, (y + h - 10) * S, cx + 10 * S, (y + h - 8) * S), radius=S, fill=(210, 218, 232, 180))


def draw_phone_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_scrcpy: Callable[[], None],
    on_screenshot: Callable[[], None],
    on_toggle_auto_clip: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    online = bool(state.get("online", False))
    custom_img = get_cached_image(ctx.img_cache, str(state.get("frame_image_path") or ""), (54 * S, 108 * S))
    if custom_img is not None:
        ctx.img.paste(custom_img, ((x1 + 14) * S, (y1 + 14) * S), custom_img)
    else:
        _draw_vector_phone_silhouette(ctx, x1 + 14, y1 + 14, 54, 108, online=online)
    ctx.add_spot(x1 + 14, y1 + 14, x1 + 68, y1 + 122, on_scrcpy, None, "ph_frame")

    tx = x1 + 80
    name = str(state.get("name") or "Android Phone")
    ctx.draw.text((tx * S, (y1 + 14) * S), ctx.fit_text(name, x2 - tx - 102, 17, "bold"), font=ctx.font(17, "bold"), fill=ctx.theme.text_primary)

    # Battery pill
    raw_batt = state.get("battery")
    pct = max(0, min(100, int(raw_batt))) if raw_batt is not None else None
    bat_str = f"{pct}%" if pct is not None else "—"
    if pct is not None and pct <= 15:
        bat_col = (*ctx.theme.alert_danger, 255)
    elif state.get("charging"):
        bat_col = (*ctx.theme.status_color("ok", "phone_sync"), 255)
    else:
        bat_col = ctx.theme.text_primary

    bx1, by1 = x2 - 90, y1 + 14
    ctx.draw.rounded_rectangle(
        (bx1 * S, by1 * S, (x2 - 14) * S, (by1 + 26) * S),
        radius=8 * S,
        fill=(38, 43, 54, 255),
        outline=ctx.theme.tile_edge,
        width=S,
    )
    dot_c = (*ctx.theme.status_color("ok", "phone_sync"), 255) if online else (130, 135, 148, 255)
    ctx.draw.ellipse(((bx1 + 9) * S, (by1 + 9) * S, (bx1 + 17) * S, (by1 + 17) * S), fill=dot_c)
    ctx.draw.text(((bx1 + 23) * S, (by1 + 3) * S), bat_str, font=ctx.font(14, "bold"), fill=bat_col)

    # Action buttons: Screen & Screenshot
    btn_y1, btn_y2 = y1 + 49, y1 + 115
    btns = [
        (ctx.i18n.t("phone.screen"), "scrcpy", on_scrcpy, ctx.theme.role("phone_screen")),
        (ctx.i18n.t("phone.screenshot"), "shot", on_screenshot, ctx.theme.role("phone_shot")),
    ]
    bw = (x2 - tx - 22) // 2
    for i, (lbl, key, cb, acc) in enumerate(btns):
        b1 = tx + i * (bw + 8)
        b2 = b1 + bw
        hov = ctx.hover == f"act_{key}"
        bg = ctx.theme.tile_bg_hover if hov else ctx.theme.tile_bg
        bd = (*acc, 255) if hov else ctx.theme.tile_edge
        ctx.draw.rounded_rectangle((b1 * S, btn_y1 * S, b2 * S, btn_y2 * S), radius=11 * S, fill=bg, outline=bd, width=2 * S if hov else S)

        icx = (b1 + bw // 2) * S
        icy = (btn_y1 + 21) * S
        ic_c = (*acc, 255)
        if key == "scrcpy":
            ctx.draw.rounded_rectangle((icx - 8 * S, icy - 11 * S, icx + 8 * S, icy + 11 * S), radius=3 * S, outline=ic_c, width=2 * S)
            ctx.draw.polygon([(icx - 3 * S, icy - 4 * S), (icx - 3 * S, icy + 4 * S), (icx + 4 * S, icy)], fill=ic_c)
        else:
            ctx.draw.rounded_rectangle((icx - 11 * S, icy - 8 * S, icx + 11 * S, icy + 8 * S), radius=3 * S, outline=ic_c, width=2 * S)
            ctx.draw.ellipse((icx - 4 * S, icy - 4 * S, icx + 4 * S, icy + 4 * S), outline=ic_c, width=2 * S)

        f_b = ctx.font(13, "bold")
        fit_lbl = ctx.fit_text(lbl, bw - 10, 13, "bold")
        tb = ctx.draw.textbbox((0, 0), fit_lbl, font=f_b)
        ctx.draw.text((icx - (tb[2] - tb[0]) // 2, (btn_y1 + 39) * S), fit_lbl, font=f_b, fill=ctx.theme.text_primary)
        ctx.add_spot(b1, btn_y1, b2, btn_y2, cb, None, f"act_{key}")

    # Bottom auto-clipboard toggle bar
    ay1, ay2 = y2 - 44, y2 - 10
    auto_on = bool(state.get("auto_clip_sync", True))
    ahov = ctx.hover == "auto_clip"
    sync_rgb = ctx.theme.role("phone_sync")
    ctx.draw.rounded_rectangle(
        ((x1 + 12) * S, ay1 * S, (x2 - 12) * S, ay2 * S),
        radius=10 * S,
        fill=ctx.theme.tile_bg_hover if ahov else ctx.theme.tile_bg_inactive,
        outline=(*sync_rgb, 180) if auto_on else ctx.theme.tile_edge,
        width=S,
    )
    ctx.draw.text(
        ((x1 + 22) * S, (ay1 + 8) * S),
        ctx.fit_text(ctx.i18n.t("phone.auto_clip"), x2 - x1 - 96, 13, "semibold"),
        font=ctx.font(13, "semibold"),
        fill=ctx.theme.text_primary,
    )
    sw_x1, sw_y1 = x2 - 62, ay1 + 6
    sw_w, sw_h = 40, 22
    sw_bg = (*sync_rgb, 255) if auto_on else (75, 82, 96, 255)
    ctx.draw.rounded_rectangle((sw_x1 * S, sw_y1 * S, (sw_x1 + sw_w) * S, (sw_y1 + sw_h) * S), radius=11 * S, fill=sw_bg)
    knob_x = (sw_x1 + sw_w - 19) * S if auto_on else (sw_x1 + 3) * S
    ctx.draw.ellipse((knob_x, (sw_y1 + 3) * S, knob_x + 16 * S, (sw_y1 + 19) * S), fill=(255, 255, 255, 255))
    ctx.add_spot(x1 + 12, ay1, x2 - 12, ay2, on_toggle_auto_clip, None, "auto_clip")


def draw_photos_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_toggle_expand: Callable[[], None],
    on_open_gallery: Callable[[], None],
    on_copy_photo: Callable[[int], None],
    on_open_photo: Callable[[int], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    ctx.draw.text(((x1 + 16) * S, (y1 + 12) * S), ctx.i18n.t("phone.photos_title"), font=ctx.font(16, "bold"), fill=ctx.theme.text_primary)

    accent = ctx.theme.role("phone_screen")
    gx1, gy1, gx2, gy2 = x2 - 124, y1 + 10, x2 - 12, y1 + 36
    ghov = ctx.hover == "open_gallery"
    ctx.draw.rounded_rectangle(
        (gx1 * S, gy1 * S, gx2 * S, gy2 * S),
        radius=8 * S,
        fill=ctx.theme.tint_hover(accent, 0.72) if ghov else ctx.theme.tint_dark(accent, 0.55),
        outline=(*accent, 220),
        width=S,
    )
    ctx.draw.text(((gx1 + 12) * S, (gy1 + 4) * S), ctx.i18n.t("phone.gallery_btn"), font=ctx.font(13, "bold"), fill=(255, 255, 255, 255))
    ax, ay = (gx2 - 16) * S, (gy1 + 13) * S
    ctx.draw.line([(ax - 4 * S, ay + 4 * S), (ax + 4 * S, ay - 4 * S)], fill=(255, 255, 255, 255), width=2 * S)
    ctx.draw.line([(ax - 1 * S, ay - 4 * S), (ax + 4 * S, ay - 4 * S), (ax + 4 * S, ay + 1 * S)], fill=(255, 255, 255, 255), width=2 * S)
    ctx.add_spot(gx1, gy1, gx2, gy2, on_open_gallery, None, "open_gallery")

    expanded = bool(state.get("photos_expanded", False))
    cx, cy = gx1 - 18, y1 + 23
    dy = -3 if expanded else 3
    ctx.draw.line([((cx - 4) * S, (cy - dy) * S), (cx * S, (cy + dy) * S), ((cx + 4) * S, (cy - dy) * S)], fill=(192, 201, 212, 255), width=2 * S)
    ctx.add_spot(x1, y1, gx1 - 4, y1 + 44, on_toggle_expand, None, "photos_toggle")
    if not expanded:
        return

    photos = list(state.get("photos") or [])
    if not photos:
        ctx.draw.text(((x1 + 16) * S, (y1 + 58) * S), ctx.i18n.t("phone.gallery_loading"), font=ctx.font(14), fill=ctx.theme.text_muted)
        return

    cw = (x2 - x1 - 32) // 2
    ch = max(48, (y2 - y1 - 68) // 2)
    gx0, gy0 = x1 + 12, y1 + 46
    for idx, p in enumerate(photos[:4]):
        col, row = idx % 2, idx // 2
        cx1 = gx0 + col * (cw + 8)
        cy1 = gy0 + row * (ch + 10)
        cx2, cy2 = cx1 + cw, cy1 + ch
        hov = ctx.hover == f"photo_{idx}"
        ctx.draw.rounded_rectangle(
            (cx1 * S, cy1 * S, cx2 * S, cy2 * S),
            radius=11 * S,
            fill=ctx.theme.tile_bg_hover if hov else (22, 24, 30, 255),
            outline=(*accent, 255) if hov else ctx.theme.tile_edge,
            width=2 * S if hov else S,
        )
        thumb = get_photo_thumb(ctx.img_cache, p.get("local_path", ""), (cw - 4) * S, (ch - 4) * S, 9 * S)
        if thumb:
            ctx.img.paste(thumb, ((cx1 + 2) * S, (cy1 + 2) * S), thumb)
        lbl = ctx.fit_text(f"{p.get('name', '')} · {p.get('time_str', '')}", cw - 24, 12, "bold")
        f_p = ctx.font(12, "bold")
        ptb = ctx.draw.textbbox((0, 0), lbl, font=f_p)
        pw = (ptb[2] - ptb[0]) // S + 14
        ctx.draw.rounded_rectangle(((cx1 + 6) * S, (cy2 - 26) * S, (cx1 + 6 + pw) * S, (cy2 - 6) * S), radius=6 * S, fill=(16, 18, 24, 240))
        ctx.draw.text(((cx1 + 13) * S, (cy2 - 23) * S), lbl, font=f_p, fill=ctx.theme.text_primary)
        ctx.add_spot(cx1, cy1, cx2, cy2, lambda i=idx: on_copy_photo(i), lambda i=idx: on_open_photo(i), f"photo_{idx}")


def draw_sms_bar_or_drawer(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    *,
    on_toggle_expand: Callable[[], None],
    on_copy_sms: Callable[[int], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    sms_list = list(state.get("sms") or [])
    expanded = bool(state.get("sms_expanded", False))
    sms_rgb = ctx.theme.role("phone_sms")
    otp_rgb = ctx.theme.role("phone_otp")

    latest_otp = None
    latest_otp_idx = 0
    for i, s in enumerate(sms_list):
        if s.get("otp"):
            latest_otp = s["otp"]
            latest_otp_idx = i
            break

    if expanded:
        dy1 = max(12, y2 - 332)
        ctx.hotspots[:] = [s for s in ctx.hotspots if s[3] <= dy1]
        ctx.draw.rounded_rectangle(
            (x1 * S, dy1 * S, x2 * S, y2 * S),
            radius=15 * S,
            fill=(24, 27, 35, 255),
            outline=(*sms_rgb, 255),
            width=2 * S,
        )
        ctx.draw.text(((x1 + 16) * S, (dy1 + 12) * S), ctx.i18n.t("phone.sms_title"), font=ctx.font(16, "bold"), fill=ctx.theme.text_primary)
        ctx.draw.text(((x2 - 102) * S, (dy1 + 14) * S), ctx.i18n.t("phone.sms_collapse"), font=ctx.font(13, "bold"), fill=(*sms_rgb, 255))
        chx, chy = (x2 - 22) * S, (dy1 + 24) * S
        ctx.draw.line([(chx - 4 * S, chy - 2 * S), (chx, chy + 2 * S), (chx + 4 * S, chy - 2 * S)], fill=(*sms_rgb, 255), width=2 * S)
        ctx.add_spot(x1, dy1, x2, dy1 + 42, on_toggle_expand, None, "sms_toggle")

        ry = dy1 + 46
        rh = 64
        for idx, s in enumerate(sms_list[:4]):
            sy1 = ry + idx * (rh + 6)
            sy2 = sy1 + rh
            hov = ctx.hover == f"sms_{idx}"
            ctx.draw.rounded_rectangle(
                ((x1 + 12) * S, sy1 * S, (x2 - 12) * S, sy2 * S),
                radius=10 * S,
                fill=ctx.theme.tile_bg_hover if hov else ctx.theme.tile_bg_inactive,
                outline=(*sms_rgb, 255) if hov else ctx.theme.tile_edge,
                width=S,
            )
            ctx.draw.text(((x1 + 22) * S, (sy1 + 8) * S), ctx.fit_text(str(s.get("sender", "SMS")), 140, 14, "bold"), font=ctx.font(14, "bold"), fill=ctx.theme.text_primary)
            otp = s.get("otp")
            if otp:
                otp_lbl = ctx.i18n.t("phone.otp_prefix", otp=otp)
                f_o = ctx.font(13, "bold")
                otb = ctx.draw.textbbox((0, 0), otp_lbl, font=f_o)
                ow = (otb[2] - otb[0]) // S + 18
                ctx.draw.rounded_rectangle(
                    ((x2 - 22 - ow) * S, (sy1 + 6) * S, (x2 - 22) * S, (sy1 + 30) * S),
                    radius=7 * S,
                    fill=ctx.theme.tint_dark(otp_rgb, 0.28),
                    outline=(*otp_rgb, 255),
                    width=S,
                )
                ctx.draw.text(((x2 - 13 - ow) * S, (sy1 + 9) * S), otp_lbl, font=f_o, fill=(*otp_rgb, 255))
            body = ctx.fit_text(str(s.get("body", "")), x2 - x1 - 44, 13)
            ctx.draw.text(((x1 + 22) * S, (sy1 + 34) * S), body, font=ctx.font(13), fill=ctx.theme.text_secondary)
            ctx.add_spot(x1 + 12, sy1, x2 - 12, sy2, lambda i=idx: on_copy_sms(i), None, f"sms_{idx}")
        return

    hov_bar = ctx.hover == "sms_toggle"
    ctx.draw.rounded_rectangle(
        (x1 * S, y1 * S, x2 * S, y2 * S),
        radius=ctx.theme.corner_radius * S,
        fill=ctx.theme.tile_bg_hover if hov_bar else ctx.theme.card_bg,
        outline=(*sms_rgb, 255) if hov_bar else ctx.theme.card_edge,
        width=S,
    )
    bx, by = (x1 + 24) * S, ((y1 + y2) // 2) * S
    ctx.draw.rounded_rectangle((bx - 9 * S, by - 7 * S, bx + 9 * S, by + 6 * S), radius=4 * S, outline=(*sms_rgb, 255), width=2 * S)
    ctx.draw.line([(bx - 4 * S, by - 1 * S), (bx + 4 * S, by - 1 * S)], fill=(*sms_rgb, 255), width=2 * S)
    ctx.draw.text(((x1 + 40) * S, (y1 + 16) * S), ctx.i18n.t("phone.sms_title"), font=ctx.font(15, "bold"), fill=ctx.theme.text_primary)

    ux, uy = (x2 - 24) * S, ((y1 + y2) // 2) * S
    ctx.draw.line([(ux - 5 * S, uy + 2 * S), (ux, uy - 3 * S), (ux + 5 * S, uy + 2 * S)], fill=(175, 185, 205, 255), width=2 * S)
    ctx.add_spot(x1, y1, x2, y2, on_toggle_expand, None, "sms_toggle")

    if latest_otp:
        ox1, oy1, ox2, oy2 = x1 + 148, y1 + 10, x2 - 44, y2 - 10
        ohov = ctx.hover == "sms_quick_otp"
        ctx.draw.rounded_rectangle(
            (ox1 * S, oy1 * S, ox2 * S, oy2 * S),
            radius=9 * S,
            fill=ctx.theme.tint_hover(otp_rgb, 0.36) if ohov else ctx.theme.tint_dark(otp_rgb, 0.28),
            outline=(*otp_rgb, 255),
            width=S,
        )
        otp_lbl = ctx.i18n.t("phone.otp_prefix", otp=latest_otp)
        f_o = ctx.font(13, "bold")
        ctx.draw.text((((ox1 + ox2) * S) // 2, ((oy1 + oy2) * S) // 2), otp_lbl, anchor="mm", font=f_o, fill=(*otp_rgb, 255))
        ctx.add_spot(ox1, oy1, ox2, oy2, lambda i=latest_otp_idx: on_copy_sms(i), None, "sms_quick_otp")
