"""Universal Windows SMTC media player card renderer with optional Spotify Like heart."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Optional

from PIL import Image, ImageDraw

from . import Box, RenderContext, draw_card_surface, draw_progress_bar


def _draw_media_button(
    ctx: RenderContext,
    box: Box,
    label: str,
    callback: Optional[Callable[[], None]],
    hid: str,
    *,
    active: bool = False,
    enabled: bool = True,
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    accent = ctx.theme.role("media_heart")
    bg = ctx.theme.tint_dark(accent, 0.25) if active else (47, 49, 54, 210)
    if ctx.hover == hid and enabled:
        bg = (65, 69, 76, 245)
    ctx.draw.rounded_rectangle(
        (x1 * S, y1 * S, x2 * S, y2 * S),
        radius=9 * S,
        fill=bg,
        outline=ctx.theme.card_edge,
        width=S,
    )
    ink = (240, 242, 246, 255) if (callback and enabled) else (135, 142, 151, 255)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    if label == "heart":
        pts = []
        for i in range(65):
            a = i * math.tau / 64.0
            hx = 16 * math.sin(a) ** 3
            hy = 13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)
            pts.append(((cx + hx * 0.54) * S, (cy - hy * 0.54) * S))
        if active:
            ctx.draw.polygon(pts, fill=(*accent, 255))
        else:
            ctx.draw.line(pts, fill=ink, width=2 * S, joint="curve")
    elif label == "pause":
        for dx in (-5, 3):
            ctx.draw.rectangle(((cx + dx) * S, (cy - 7) * S, (cx + dx + 3) * S, (cy + 7) * S), fill=ink)
    elif label in ("play", "previous", "next"):
        direction = -1 if label == "previous" else 1
        ctx.draw.polygon(
            [
                ((cx - 5 * direction) * S, (cy - 7) * S),
                ((cx - 5 * direction) * S, (cy + 7) * S),
                ((cx + 6 * direction) * S, cy * S),
            ],
            fill=ink,
        )
        if label != "play":
            bx = cx + 8 * direction
            ctx.draw.line((bx * S, (cy - 8) * S, bx * S, (cy + 8) * S), fill=ink, width=2 * S)
    if callback:
        ctx.add_spot(x1, y1, x2, y2, callback, None, hid)


def _draw_vector_album_art(ctx: RenderContext, x: int, y: int, size: int) -> None:
    """Clean vinyl/waveform vector artwork fallback when SMTC thumbnail is absent."""
    S = ctx.scale
    accent = ctx.theme.role("media")
    bg = ctx.theme.tint_dark(accent, 0.28)
    ctx.draw.rounded_rectangle(
        (x * S, y * S, (x + size) * S, (y + size) * S),
        radius=10 * S,
        fill=bg,
        outline=(*accent, 180),
        width=S,
    )
    cx, cy = (x + size // 2) * S, (y + size // 2) * S
    r_out = int(size * 0.34 * S)
    r_in = int(size * 0.12 * S)
    ctx.draw.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), outline=(*accent, 230), width=2 * S)
    ctx.draw.ellipse((cx - r_in, cy - r_in, cx + r_in, cy + r_in), fill=(*accent, 255))


def draw_media_card(
    ctx: RenderContext,
    box: Box,
    state: Dict[str, Any],
    on_command: Callable[[str], None],
    on_like: Callable[[], None],
) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)

    show_heart = bool(state.get("like_enabled") and state.get("is_spotify"))

    if not state.get("playing"):
        ctx.draw.text(
            ((x1 + 16) * S, (y1 + 13) * S),
            ctx.i18n.t("media.nothing_playing"),
            font=ctx.font(16, "semibold"),
            fill=ctx.theme.text_secondary,
        )
        if state.get("available"):
            _draw_media_button(
                ctx,
                (x2 - 52, y1 + 8, x2 - 12, y2 - 8),
                "play",
                lambda: on_command("toggle"),
                "media_toggle",
            )
            if show_heart:
                _draw_media_button(
                    ctx,
                    (x2 - 100, y1 + 8, x2 - 60, y2 - 8),
                    "heart",
                    on_like,
                    "media_like",
                    active=state.get("like_saved") is True,
                    enabled=bool(state.get("like_ready")) and not bool(state.get("like_busy")),
                )
        return

    # Cover artwork (cached by track identity)
    cover_path = state.get("cover")
    art = None
    if cover_path:
        cache_key = ("media_art", state.get("cover_track"), cover_path)
        if cache_key not in ctx.img_cache:
            try:
                with Image.open(cover_path) as src:
                    im = src.convert("RGBA").resize((52 * S, 52 * S), Image.Resampling.LANCZOS)
                mask = Image.new("L", (52 * S, 52 * S), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, 52 * S - 1, 52 * S - 1), radius=8 * S, fill=255)
                rounded = Image.new("RGBA", (52 * S, 52 * S), (0, 0, 0, 0))
                rounded.paste(im, (0, 0), mask)
                ctx.img_cache[cache_key] = rounded
            except Exception:
                ctx.img_cache[cache_key] = None
        art = ctx.img_cache[cache_key]

    if art is not None:
        ctx.img.paste(art, ((x1 + 14) * S, (y1 + 12) * S), art)
    else:
        _draw_vector_album_art(ctx, x1 + 14, y1 + 12, 52)

    text_max_w = x2 - x1 - 92
    title = state.get("title") or ctx.i18n.t("media.unknown_track")
    artist = state.get("artist") or ""
    ctx.draw.text(
        ((x1 + 78) * S, (y1 + 11) * S),
        ctx.fit_text(title, text_max_w, 18, "semibold"),
        font=ctx.font(18, "semibold"),
        fill=ctx.theme.text_primary,
    )
    ctx.draw.text(
        ((x1 + 78) * S, (y1 + 37) * S),
        ctx.fit_text(artist, text_max_w, 14, "regular"),
        font=ctx.font(14, "regular"),
        fill=ctx.theme.text_secondary,
    )

    btn_y1 = y2 - 44
    btn_y2 = y2 - 12
    controls_x = (x1 + 124) if show_heart else ((x1 + x2) // 2 - 68)
    for idx, (cmd, lbl) in enumerate((("previous", "previous"), ("toggle", "pause"), ("next", "next"))):
        bx = controls_x + idx * 48
        _draw_media_button(ctx, (bx, btn_y1, bx + 40, btn_y2), lbl, lambda c=cmd: on_command(c), f"media_{cmd}")

    if show_heart:
        _draw_media_button(
            ctx,
            (x2 - 52, btn_y1, x2 - 12, btn_y2),
            "heart",
            on_like,
            "media_like",
            active=state.get("like_saved") is True,
            enabled=bool(state.get("like_ready")) and not bool(state.get("like_busy")),
        )

    duration = float(state.get("duration") or 0.0)
    position = float(state.get("position") or 0.0)
    pct = (position / duration * 100.0) if duration > 0 else 0.0
    draw_progress_bar(ctx, x1 + 14, y2 - 7, x2 - 14, y2 - 4, pct, ctx.theme.role("media"), radius=1)
