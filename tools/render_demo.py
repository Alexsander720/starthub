"""Generate clean, copyright-free --demo showcase renders for README and docs.

Outputs into docs/assets/:
- demo_multi_accent.png     : Full 3-panel Windows 11 StartHub showcase (multi_accent)
- demo_single_accent.png    : Full 3-panel Windows 11 StartHub showcase (single_accent)
- theme_comparison.png      : Side-by-side multi_accent vs single_accent comparison
- ecoflow_focus.png         : EcoFlow DELTA 3 Grid Bypass vs Blackout card comparison
Also ensures packs/example_minimal/sample_tile.png exists (clean geometric tile).
"""
from __future__ import annotations

import datetime
from pathlib import Path
import sys
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starthub.config import load_config
from starthub.i18n import I18n
from starthub.providers import build_demo_snapshot
from starthub.renderer import HubRenderer
from starthub.surface import FontBank
from starthub.theme import Theme
from starthub.widgets import RenderContext
from starthub.widgets.ecoflow import draw_ecoflow_card


def _gradient_backdrop(width: int, height: int, top_rgb: Tuple[int, int, int], bot_rgb: Tuple[int, int, int], glow_rgb: Tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGBA", (width, height), (*top_rgb, 255))
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top_rgb[0] * (1 - t) + bot_rgb[0] * t)
        g = int(top_rgb[1] * (1 - t) + bot_rgb[1] * t)
        b = int(top_rgb[2] * (1 - t) + bot_rgb[2] * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((int(width * 0.12), int(height * 0.05), int(width * 0.62), int(height * 0.72)), fill=(*glow_rgb, 48))
    gd.ellipse((int(width * 0.45), int(height * 0.28), int(width * 0.94), int(height * 0.96)), fill=(94, 118, 224, 38))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(base, glow)


def _render_center_start11_mockup(width: int, height: int, center_overlay: Image.Image, theme: Theme, fonts: FontBank) -> Image.Image:
    """Clean, original Start11-inspired glass center panel with geometric app tiles + live overlay."""
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=10, fill=(30, 32, 38, 205), outline=(72, 76, 88, 180), width=1)

    # Search bar
    d.rounded_rectangle((20, 18, width - 20, 52), radius=16, fill=(22, 24, 30, 220), outline=(66, 72, 84, 200), width=1)
    d.ellipse((34, 28, 46, 40), outline=(160, 168, 184, 255), width=2)
    d.line([(45, 39), (50, 44)], fill=(160, 168, 184, 255), width=2)
    d.text((60, 26), "Search apps, settings, and files", font=fonts.get(13, "regular"), fill=(156, 164, 180, 255))

    # Two tile group headers
    d.text((24, 68), "Pinned", font=fonts.get(13, "semibold"), fill=(226, 232, 242, 255))
    d.text((width // 2 + 12, 68), "Workspace", font=fonts.get(13, "semibold"), fill=(226, 232, 242, 255))

    # Clean geometric tiles (3x4 per column) — zero third-party logos or copyrighted art
    palette_multi = [
        (56, 148, 246), (42, 184, 142), (142, 108, 244),
        (232, 118, 78), (64, 178, 212), (222, 164, 68),
        (82, 198, 134), (96, 132, 246), (218, 92, 114),
        (52, 176, 168), (168, 122, 236), (74, 158, 238),
    ]
    labels_l = ["Code", "Terminal", "Browser", "Notes", "Mail", "Files", "Music", "Chat", "Calendar", "Git", "Design", "Photos"]
    labels_r = ["Games", "Video", "Audio", "Cloud", "Docker", "Monitor", "Smart Home", "Backup", "Network", "SSH", "Calc", "Settings"]

    tile_sz = 88
    gap = 10
    for col_grp, (gx0, labels) in enumerate(((24, labels_l), (width // 2 + 12, labels_r))):
        for idx, lbl in enumerate(labels):
            r, c = idx // 3, idx % 3
            tx = gx0 + c * (tile_sz + gap)
            ty = 94 + r * (tile_sz + gap)
            acc = theme.accent if theme.is_single_accent else palette_multi[(idx + col_grp * 4) % len(palette_multi)]
            fill = theme.tint_dark(acc, 0.24, alpha=235)
            d.rounded_rectangle((tx, ty, tx + tile_sz, ty + tile_sz), radius=9, fill=fill, outline=(*acc, 120), width=1)
            # Clean minimal geometric glyph
            cx, cy = tx + tile_sz // 2, ty + 34
            shape = (idx + col_grp) % 4
            if shape == 0:
                d.rounded_rectangle((cx - 14, cy - 12, cx + 14, cy + 12), radius=5, outline=(*acc, 245), width=2)
                d.line([(cx - 6, cy - 2), (cx - 1, cy + 2), (cx - 6, cy + 6)], fill=(*acc, 245), width=2)
                d.line([(cx + 2, cy + 6), (cx + 8, cy + 6)], fill=(*acc, 245), width=2)
            elif shape == 1:
                d.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), outline=(*acc, 245), width=2)
                d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(*acc, 245))
            elif shape == 2:
                d.polygon([(cx, cy - 14), (cx + 14, cy), (cx, cy + 14), (cx - 14, cy)], outline=(*acc, 245), width=2)
            else:
                for ox in (-9, 3):
                    for oy in (-9, 3):
                        d.rounded_rectangle((cx + ox, cy + oy, cx + ox + 8, cy + oy + 8), radius=2, fill=(*acc, 225))
            d.text((tx + tile_sz // 2, ty + tile_sz - 14), lbl, anchor="mm", font=fonts.get(11, "semibold"), fill=(235, 240, 248, 255))

    # Paste transparent live Weather + Clock center overlay into the bottom open space
    ox = (width - center_overlay.width) // 2
    oy = height - center_overlay.height - 20
    panel.alpha_composite(center_overlay, (ox, oy))
    return panel


def render_three_panel_scene(mode: str, accent: str = "#58BCFF", lang: str = "en") -> Image.Image:
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    cfg = load_config(demo=True, overrides={"language": lang, "theme": {"mode": mode, "accent_color": accent}})
    i18n = I18n(lang)
    theme = Theme.from_config(cfg)
    fonts = FontBank()
    renderer = HubRenderer(cfg, theme, i18n, fonts)
    snap = build_demo_snapshot(i18n, now=fixed_now)

    wing_h = 774
    lw, rw = 416, 430
    cw = 626
    gap = 12
    pad_x, pad_y = 36, 36

    left_img, _, _ = renderer.render_wing("left", lw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal")
    right_img, _, _ = renderer.render_wing("right", rw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal")
    center_strip = renderer.render_center_strip_preview(snap, now=fixed_now)
    center_img = _render_center_start11_mockup(cw, wing_h, center_strip, theme, fonts)

    total_w = pad_x * 2 + lw + gap + cw + gap + rw
    total_h = pad_y * 2 + wing_h + 26

    scene = _gradient_backdrop(total_w, total_h, (13, 18, 29), (20, 28, 44), theme.accent)
    scene.alpha_composite(left_img, (pad_x, pad_y))
    scene.alpha_composite(center_img, (pad_x + lw + gap, pad_y))
    scene.alpha_composite(right_img, (pad_x + lw + gap + cw + gap, pad_y))

    # Minimal Windows 11 taskbar strip at very bottom for authentic framing
    d = ImageDraw.Draw(scene)
    tb_y = total_h - 32
    d.rectangle((0, tb_y, total_w, total_h), fill=(20, 22, 28, 225))
    d.line([(0, tb_y), (total_w, tb_y)], fill=(64, 68, 80, 180), width=1)
    # Minimal centered taskbar pill dots
    mid = total_w // 2
    for i in range(-3, 4):
        bx = mid + i * 26
        col = (*theme.accent, 255) if i == -3 else (150, 158, 174, 210)
        d.rounded_rectangle((bx - 7, tb_y + 9, bx + 7, tb_y + 23), radius=3, fill=col)

    return scene.convert("RGB")


def render_theme_comparison(lang: str = "en") -> Image.Image:
    """Side-by-side comparison of Multi-Accent vs Single-Accent wings."""
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    fonts = FontBank()
    wing_h = 774
    lw, rw = 416, 430
    gap = 12
    col_w = lw + gap + rw
    pad = 28
    hdr_h = 54
    sep = 34

    total_w = pad * 2 + col_w * 2 + sep
    total_h = pad * 2 + hdr_h + wing_h
    canvas = _gradient_backdrop(total_w, total_h, (12, 16, 26), (18, 24, 38), (88, 188, 255))
    d = ImageDraw.Draw(canvas)

    panels = [
        ("multi_accent", "Multi-Accent  (Default)", "Semantic colors per widget category"),
        ("single_accent", "Single-Accent  (#58BCFF / Windows Accent)", "Unified monochrome palette · Critical alerts preserved"),
    ]
    for idx, (mode, title, subtitle) in enumerate(panels):
        cfg = load_config(demo=True, overrides={"language": lang, "theme": {"mode": mode, "accent_color": "#58BCFF"}})
        i18n = I18n(lang)
        theme = Theme.from_config(cfg)
        renderer = HubRenderer(cfg, theme, i18n, fonts)
        snap = build_demo_snapshot(i18n, now=fixed_now)
        left_img, _, _ = renderer.render_wing("left", lw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal")
        right_img, _, _ = renderer.render_wing("right", rw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal")

        ox = pad + idx * (col_w + sep)
        d.text((ox + 4, pad), title, font=fonts.get(20, "bold"), fill=(246, 248, 252, 255))
        d.text((ox + 4, pad + 26), subtitle, font=fonts.get(13, "regular"), fill=(168, 178, 196, 255))
        canvas.alpha_composite(left_img, (ox, pad + hdr_h))
        canvas.alpha_composite(right_img, (ox + lw + gap, pad + hdr_h))

    return canvas.convert("RGB")


def render_ecoflow_focus(lang: str = "en") -> Image.Image:
    """Render EcoFlow card in both Grid Bypass and Battery Blackout states side by side."""
    fonts = FontBank()
    i18n = I18n(lang)
    cfg = load_config(demo=True, overrides={"language": lang, "theme": {"mode": "multi_accent"}})
    theme = Theme.from_config(cfg)
    base_ef = build_demo_snapshot(i18n)["ecoflow"]

    blackout_ef = dict(base_ef, is_grid=False, in_watts=0.0, out_watts=265.0, soc=78, remain_wh=1597, est_dsg_min=310)
    cw, ch = 406, 214
    pad = 24
    gap = 20
    S = 2

    out = _gradient_backdrop(pad * 2 + cw * 2 + gap, pad * 2 + ch + 34, (14, 18, 28), (22, 28, 42), (74, 222, 128))
    d = ImageDraw.Draw(out)
    for idx, (label, state) in enumerate((("Grid AC Bypass", base_ef), ("Battery Blackout Alert", blackout_ef))):
        card = Image.new("RGBA", (cw * S, ch * S), (0, 0, 0, 0))
        ctx = RenderContext(card, ImageDraw.Draw(card), S, theme, fonts, i18n, None, [], {}, "right")
        draw_ecoflow_card(ctx, (0, 0, cw, ch), state, on_cycle_charge=lambda: None, on_toggle_usb=lambda: None, on_toggle_dc12v=lambda: None, on_toggle_beep=lambda: None)
        small = card.resize((cw, ch), Image.Resampling.LANCZOS)
        ox = pad + idx * (cw + gap)
        d.text((ox + 4, pad), label, font=fonts.get(15, "bold"), fill=(235, 240, 248, 255))
        out.alpha_composite(small, (ox, pad + 28))
    return out.convert("RGB")


def generate_example_tile_pack() -> Path:
    """Create 1 clean original geometric tile in packs/example_minimal/ (no copyrighted art)."""
    pack_dir = REPO_ROOT / "packs" / "example_minimal"
    pack_dir.mkdir(parents=True, exist_ok=True)
    tile_path = pack_dir / "sample_terminal.png"
    size = 512
    im = Image.new("RGBA", (size, size), (22, 28, 40, 255))
    d = ImageDraw.Draw(im)
    for y in range(size):
        t = y / (size - 1)
        r = int(20 + 28 * t)
        g = int(34 + 48 * t)
        b = int(56 + 78 * t)
        d.line([(0, y), (size, y)], fill=(r, g, b, 255))
    # Minimal terminal prompt emblem
    accent = (88, 188, 255, 255)
    d.rounded_rectangle((72, 92, 440, 360), radius=36, fill=(16, 22, 32, 235), outline=accent, width=10)
    d.line([(132, 180), (192, 226), (132, 272)], fill=accent, width=18, joint="curve")
    d.line([(216, 272), (312, 272)], fill=(236, 242, 250, 255), width=18)
    fonts = FontBank()
    d.text((256, 424), "Terminal", anchor="mm", font=fonts.get(54, "bold"), fill=(244, 248, 255, 255))
    im.convert("RGB").save(tile_path, "PNG")
    return tile_path


def main() -> int:
    assets_dir = REPO_ROOT / "docs" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    p_multi = assets_dir / "demo_multi_accent.png"
    p_single = assets_dir / "demo_single_accent.png"
    p_comp = assets_dir / "theme_comparison.png"
    p_eco = assets_dir / "ecoflow_focus.png"

    render_three_panel_scene("multi_accent").save(p_multi, "PNG", optimize=True)
    render_three_panel_scene("single_accent").save(p_single, "PNG", optimize=True)
    render_theme_comparison().save(p_comp, "PNG", optimize=True)
    render_ecoflow_focus().save(p_eco, "PNG", optimize=True)
    tile = generate_example_tile_pack()

    print("Generated demo renders:")
    for p in (p_multi, p_single, p_comp, p_eco, tile):
        print(f"  {p.relative_to(REPO_ROOT)} ({p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
