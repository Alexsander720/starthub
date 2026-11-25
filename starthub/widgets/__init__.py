"""Shared 2x-supersampled PIL drawing primitives and RenderContext for all StartHub widgets."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw

from ..i18n import I18n
from ..surface import FontBank
from ..theme import RGB, RGBA, Theme

Hotspot = Tuple[int, int, int, int, Optional[Callable[[], None]], Optional[Callable[[], None]], str]
Box = Tuple[int, int, int, int]


@dataclass
class RenderContext:
    img: Image.Image
    draw: ImageDraw.ImageDraw
    scale: int
    theme: Theme
    fonts: FontBank
    i18n: I18n
    hover: Optional[str]
    hotspots: List[Hotspot]
    img_cache: Dict[Any, Any]
    side: str = "left"

    def add_spot(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        left_cb: Optional[Callable[[], None]],
        right_cb: Optional[Callable[[], None]] = None,
        hid: str = "",
    ) -> None:
        self.hotspots.append((int(x1), int(y1), int(x2), int(y2), left_cb, right_cb, hid))

    def font(self, size: int, weight: str = "regular"):
        return self.fonts.get(int(round(size * self.scale)), weight)

    def fit_text(self, text: str, max_width: float, size: int = 15, weight: str = "regular") -> str:
        f = self.font(size, weight)
        limit = max(8.0, max_width * self.scale)
        if f.getlength(text) <= limit:
            return text
        trimmed = text
        while trimmed and f.getlength(trimmed + "…") > limit:
            trimmed = trimmed[:-1]
        return (trimmed + "…") if trimmed else "…"


def draw_card_surface(ctx: RenderContext, box: Box, radius: Optional[int] = None) -> None:
    S = ctx.scale
    r = ctx.theme.corner_radius if radius is None else radius
    x1, y1, x2, y2 = box
    ctx.draw.rounded_rectangle(
        (x1 * S, y1 * S, x2 * S, y2 * S),
        radius=r * S,
        fill=ctx.theme.card_bg,
        outline=ctx.theme.card_edge,
        width=S,
    )


def draw_progress_bar(
    ctx: RenderContext,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    percent: Optional[float],
    fill_rgb: RGB,
    radius: int = 3,
) -> None:
    S = ctx.scale
    ctx.draw.rounded_rectangle(
        (x1 * S, y1 * S, x2 * S, y2 * S),
        radius=radius * S,
        fill=ctx.theme.track_bg,
    )
    if percent is not None and percent > 0:
        clamped = max(0.0, min(100.0, float(percent)))
        w = max(4.0, (x2 - x1) * clamped / 100.0)
        ctx.draw.rounded_rectangle(
            (x1 * S, y1 * S, min(x2, x1 + w) * S, y2 * S),
            radius=radius * S,
            fill=(*fill_rgb, 255),
        )


def draw_panel_icon(ctx: RenderContext, kind: str, x: float, y: float, ink: RGBA, lit: bool = False) -> None:
    """Flat 24px vector symbols drawn directly at supersampled resolution."""
    S = ctx.scale
    d = ctx.draw

    def line(points, width: float = 1.5):
        d.line([(int((x + a) * S), int((y + b) * S)) for a, b in points], fill=ink, width=max(1, round(width * S)), joint="curve")

    def rect(box, fill=None, radius: int = 2):
        d.rounded_rectangle(
            tuple(int(v * S) for v in (x + box[0], y + box[1], x + box[2], y + box[3])),
            radius=radius * S,
            outline=ink,
            fill=fill,
            width=max(1, round(1.5 * S)),
        )

    if kind == "cpu":
        rect((5, 5, 19, 19))
        rect((9, 9, 15, 15), radius=1)
        for p in (8, 12, 16):
            line([(p, 1), (p, 4)])
            line([(p, 20), (p, 23)])
            line([(1, p), (4, p)])
            line([(20, p), (23, p)])
    elif kind == "gpu":
        rect((2, 5, 22, 18))
        line([(0, 3), (0, 21), (4, 21)])
        d.ellipse(((x + 6) * S, (y + 8) * S, (x + 14) * S, (y + 16) * S), outline=ink, width=max(1, round(1.5 * S)))
        line([(10, 8), (10, 16)])
        line([(6, 12), (14, 12)])
        line([(17, 9), (20, 9)])
        line([(17, 13), (20, 13)])
        for p in (7, 10, 13, 16):
            line([(p, 19), (p, 22)])
    elif kind == "ram":
        rect((1, 6, 23, 17), radius=1)
        for p in (4, 10, 16):
            rect((p, 9, p + 4, 14), radius=0)
        for p in (4, 7, 10, 16, 19, 22):
            line([(p, 18), (p, 21)])
    elif kind in ("bulb", "office"):
        d.ellipse(
            ((x + 5) * S, (y + 2) * S, (x + 19) * S, (y + 16) * S),
            outline=ink,
            fill=ink if lit else None,
            width=max(1, round(1.5 * S)),
        )
        line([(8, 16), (8, 19), (16, 19), (16, 16)])
        line([(9, 22), (15, 22)])
    else:
        # Monitor / lamp bar icon
        rect((2, 6, 22, 19))
        line([(8, 23), (16, 23)])
        line([(12, 19), (12, 23)])
        line([(4, 2), (20, 2)], 2.5 if lit else 1.5)
        line([(0, 5), (0, 1), (4, 1)])
        line([(20, 1), (24, 1), (24, 5)])


def finish_panel_image(img: Image.Image, width: int, height: int, scale: int, theme: Theme) -> Image.Image:
    """Apply smooth rounded corner alpha mask, subtle panel border, and LANCZOS 2x downsample."""
    S = scale
    mask = Image.new("L", img.size, 0)
    corner = min(10, max(0, theme.corner_radius - 4))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width * S - 1, height * S - 1), radius=corner * S, fill=255)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    ImageDraw.Draw(img).rounded_rectangle(
        (0, 0, width * S - 1, height * S - 1), radius=corner * S, outline=theme.panel_edge, width=S
    )
    return img.resize((width, height), Image.Resampling.LANCZOS)


def draw_toast(ctx: RenderContext, win_w: int, win_h: int, msg: str) -> None:
    if not msg:
        return
    S = ctx.scale
    f = ctx.font(14, "bold")
    lines: List[str] = []
    line = ""
    for word in msg.split():
        cand = f"{line} {word}".strip()
        if line and f.getlength(cand) > (win_w - 52) * S:
            lines.append(line)
            line = word
        else:
            line = cand
    if line:
        lines.append(line)
    lines = lines or [""]
    tw = min((win_w - 20) * S, round(max(f.getlength(ln) for ln in lines)) + 32 * S)
    th = max(36, 18 * len(lines) + 16) * S
    cx = (win_w * S) // 2
    by = (win_h - 12) * S - th // 2
    toast_rgb = ctx.theme.role("toast")
    ctx.draw.rounded_rectangle(
        (cx - tw // 2, by - th // 2, cx + tw // 2, by + th // 2),
        radius=18 * S,
        fill=(*toast_rgb, 248),
        outline=(210, 232, 255, 255),
        width=2 * S,
    )
    for i, ln in enumerate(lines):
        ctx.draw.text((cx, by - th // 2 + (8 + i * 18) * S), ln, anchor="mt", font=f, fill=(255, 255, 255, 255))


def get_cached_image(cache: Dict[Any, Any], path: str, size: Tuple[int, int]) -> Optional[Image.Image]:
    if not path or not os.path.isfile(path):
        return None
    key = ("img", path, size, os.path.getmtime(path))
    if key in cache:
        return cache[key]
    try:
        im = Image.open(path).convert("RGBA").resize(size, Image.Resampling.LANCZOS)
        cache[key] = im
        return im
    except Exception:
        return None


def get_photo_thumb(cache: Dict[Any, Any], path: str, tw: int, th: int, radius: int) -> Optional[Image.Image]:
    if not path or not os.path.isfile(path):
        return None
    key = ("thumb", path, tw, th, radius, os.path.getmtime(path))
    if key in cache:
        return cache[key]
    try:
        with Image.open(path) as source:
            source.draft("RGB", (tw * 2, th * 2))
            im = source.convert("RGBA")
        iw, ih = im.size
        target_r = tw / max(1, th)
        cur_r = iw / max(1, ih)
        if cur_r > target_r:
            nw = int(ih * target_r)
            left = (iw - nw) // 2
            im = im.crop((left, 0, left + nw, ih))
        else:
            nh = int(iw / target_r)
            top = (ih - nh) // 2
            im = im.crop((0, top, iw, top + nh))
        im = im.resize((tw, th), Image.Resampling.LANCZOS)
        mask = Image.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw - 1, th - 1), radius=radius, fill=255)
        out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        out.paste(im, (0, 0), mask)
        cache[key] = out
        return out
    except Exception:
        return None
