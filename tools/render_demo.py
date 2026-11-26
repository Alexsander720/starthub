"""Generate clean, copyright-free showcase renders with realistic frosted-glass acrylic blur.

Outputs into docs/assets/:
- demo_multi_accent.png     : Full 3-panel StartHub showcase (multi_accent)
- demo_single_accent.png    : Full 3-panel StartHub showcase (single_accent)
- demo_tier1_default.png    : Zero-API-key Out-of-the-Box Tier 1 showcase
- theme_comparison.png      : Side-by-side multi_accent vs single_accent comparison
- ecoflow_focus.png         : EcoFlow DELTA 3 Grid Bypass vs Blackout comparison
- custom_json_layouts.png   : Custom JSON 'columns' vs 'hero' vs 'list' layouts
Also ensures packs/example_minimal/sample_terminal.png exists.
"""
from __future__ import annotations

import datetime
import math
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
from starthub.widgets.custom_json import draw_custom_json_card
from starthub.widgets.ecoflow import draw_ecoflow_card


def _rich_wallpaper_backdrop(width: int, height: int, accent_rgb: Tuple[int, int, int]) -> Image.Image:
    """Procedural atmospheric desktop wallpaper so frosted acrylic panel translucency visibly shines."""
    base = Image.new("RGBA", (width, height), (14, 20, 32, 255))
    draw = ImageDraw.Draw(base)
    top_rgb = (15, 22, 38)
    mid_rgb = (26, 36, 56)
    bot_rgb = (18, 28, 36)
    for y in range(height):
        t = y / max(1, height - 1)
        if t < 0.55:
            k = t / 0.55
            r = int(top_rgb[0] * (1 - k) + mid_rgb[0] * k)
            g = int(top_rgb[1] * (1 - k) + mid_rgb[1] * k)
            b = int(top_rgb[2] * (1 - k) + mid_rgb[2] * k)
        else:
            k = (t - 0.55) / 0.45
            r = int(mid_rgb[0] * (1 - k) + bot_rgb[0] * k)
            g = int(mid_rgb[1] * (1 - k) + bot_rgb[1] * k)
            b = int(mid_rgb[2] * (1 - k) + bot_rgb[2] * k)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Vivid soft bokeh & aurora ribbons behind panels to demonstrate real glass translucency
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-int(width * 0.08), int(height * 0.06), int(width * 0.40), int(height * 0.74)), fill=(232, 134, 68, 92))
    gd.ellipse((int(width * 0.25), -int(height * 0.10), int(width * 0.78), int(height * 0.58)), fill=(*accent_rgb, 88))
    gd.ellipse((int(width * 0.62), int(height * 0.24), int(width * 1.06), int(height * 0.96)), fill=(56, 198, 152, 84))
    gd.ellipse((int(width * 0.06), int(height * 0.56), int(width * 0.52), int(height * 1.08)), fill=(138, 98, 236, 72))
    glow = glow.filter(ImageFilter.GaussianBlur(84))
    scene = Image.alpha_composite(base, glow)

    # Layered silhouetted landscape hills for depth behind the acrylic wings
    hills = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hills)
    for layer_idx, (base_y, amp, freq, phase, col) in enumerate(
        (
            (0.68, 0.07, 2.2, 0.4, (22, 34, 52, 165)),
            (0.77, 0.055, 3.1, 1.8, (16, 28, 42, 195)),
            (0.86, 0.04, 4.0, 3.2, (12, 20, 30, 225)),
        )
    ):
        pts = [(0, height)]
        for x in range(0, width + 16, 16):
            nx = x / float(max(1, width))
            y = height * base_y - height * amp * (0.6 * math.sin(nx * math.tau * freq + phase) + 0.4 * math.cos(nx * math.tau * (freq * 0.6) - phase))
            pts.append((x, int(y)))
        pts.append((width, height))
        hd.polygon(pts, fill=col)
    hills = hills.filter(ImageFilter.GaussianBlur(3))
    return Image.alpha_composite(scene, hills)


def _composite_acrylic_panel(scene: Image.Image, panel: Image.Image, pos: Tuple[int, int], corner: int = 10) -> None:
    """Composite a semi-transparent panel with authentic frosted-glass blur and soft drop shadow."""
    x, y = pos
    w, h = panel.size

    # Soft elevated shadow
    shadow_pad = 16
    sh = Image.new("RGBA", (w + shadow_pad * 2, h + shadow_pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        (shadow_pad, shadow_pad + 3, shadow_pad + w, shadow_pad + h + 3),
        radius=corner,
        fill=(0, 0, 0, 125),
    )
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    scene.alpha_composite(sh, (max(0, x - shadow_pad), max(0, y - shadow_pad)))

    # Frosted acrylic blur of the underlying wallpaper clipped to panel rounded corners
    crop = scene.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(22))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=corner, fill=255)
    scene.paste(crop, (x, y), mask)
    scene.alpha_composite(panel, (x, y))


def _render_center_start11_mockup(width: int, height: int, center_overlay: Image.Image, theme: Theme, fonts: FontBank) -> Image.Image:
    """Clean, original Start11-inspired glass center panel with geometric app tiles + live overlay."""
    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=10, fill=(28, 30, 36, 188), outline=(74, 80, 94, 175), width=1)

    d.rounded_rectangle((20, 18, width - 20, 52), radius=16, fill=(20, 22, 28, 210), outline=(66, 72, 84, 195), width=1)
    d.ellipse((34, 28, 46, 40), outline=(160, 168, 184, 255), width=2)
    d.line([(45, 39), (50, 44)], fill=(160, 168, 184, 255), width=2)
    d.text((60, 26), "Search apps, settings, and files", font=fonts.get(13, "regular"), fill=(156, 164, 180, 255))

    d.text((24, 68), "Pinned", font=fonts.get(13, "semibold"), fill=(226, 232, 242, 255))
    d.text((width // 2 + 12, 68), "Workspace", font=fonts.get(13, "semibold"), fill=(226, 232, 242, 255))

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
            fill = theme.tint_dark(acc, 0.25, alpha=230)
            d.rounded_rectangle((tx, ty, tx + tile_sz, ty + tile_sz), radius=9, fill=fill, outline=(*acc, 130), width=1)
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

    ox = (width - center_overlay.width) // 2
    oy = height - center_overlay.height - 20
    panel.alpha_composite(center_overlay, (ox, oy))
    return panel


def _draw_taskbar(scene: Image.Image, theme: Theme) -> None:
    d = ImageDraw.Draw(scene)
    total_w, total_h = scene.size
    tb_y = total_h - 34
    d.rectangle((0, tb_y, total_w, total_h), fill=(18, 20, 26, 218))
    d.line([(0, tb_y), (total_w, tb_y)], fill=(66, 72, 86, 185), width=1)
    mid = total_w // 2
    for i in range(-3, 4):
        bx = mid + i * 28
        col = (*theme.accent, 255) if i == -3 else (152, 162, 178, 215)
        d.rounded_rectangle((bx - 7, tb_y + 10, bx + 7, tb_y + 24), radius=3, fill=col)


def render_three_panel_scene(mode: str, accent: str = "#58BCFF", lang: str = "en", *, tier1_only: bool = False) -> Image.Image:
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    if tier1_only:
        cfg = load_config(demo=False, overrides={"language": lang, "theme": {"mode": mode, "accent_color": accent}})
    else:
        cfg = load_config(demo=True, overrides={"language": lang, "theme": {"mode": mode, "accent_color": accent}})
    i18n = I18n(lang)
    theme = Theme.from_config(cfg)
    fonts = FontBank()
    renderer = HubRenderer(cfg, theme, i18n, fonts)
    snap = build_demo_snapshot(i18n, now=fixed_now)
    if tier1_only:
        # In Tier-1 default showcase, show realistic zero-key Quick Tasks + active center overlay (no weather duplicate)
        snap["todoist"]["is_local"] = True
        snap["todoist"]["projects"] = [{"id": "local", "name": i18n.t("tasks.local_list")}]
        snap["media"]["like_enabled"] = False

    wing_h = 774
    lw, rw = 416, 430
    cw = 626
    gap = 12
    pad_x, pad_y = 36, 36

    left_img, _, _ = renderer.render_wing("left", lw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal", center_overlay_active=True)
    right_img, _, _ = renderer.render_wing("right", rw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal", center_overlay_active=True)
    center_strip = renderer.render_center_strip_preview(snap, now=fixed_now)
    center_img = _render_center_start11_mockup(cw, wing_h, center_strip, theme, fonts)

    total_w = pad_x * 2 + lw + gap + cw + gap + rw
    total_h = pad_y * 2 + wing_h + 28

    scene = _rich_wallpaper_backdrop(total_w, total_h, theme.accent)
    _composite_acrylic_panel(scene, left_img, (pad_x, pad_y))
    _composite_acrylic_panel(scene, center_img, (pad_x + lw + gap, pad_y))
    _composite_acrylic_panel(scene, right_img, (pad_x + lw + gap + cw + gap, pad_y))
    _draw_taskbar(scene, theme)
    return scene.convert("RGB")


def render_theme_comparison(lang: str = "en") -> Image.Image:
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
    canvas = _rich_wallpaper_backdrop(total_w, total_h, (88, 188, 255))
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
        left_img, _, _ = renderer.render_wing("left", lw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal", center_overlay_active=True)
        right_img, _, _ = renderer.render_wing("right", rw, wing_h, snap, now=fixed_now, tile_pack_label="Minimal", center_overlay_active=True)

        ox = pad + idx * (col_w + sep)
        d.text((ox + 4, pad), title, font=fonts.get(20, "bold"), fill=(246, 248, 252, 255))
        d.text((ox + 4, pad + 26), subtitle, font=fonts.get(13, "regular"), fill=(186, 196, 214, 255))
        _composite_acrylic_panel(canvas, left_img, (ox, pad + hdr_h))
        _composite_acrylic_panel(canvas, right_img, (ox + lw + gap, pad + hdr_h))

    return canvas.convert("RGB")


def render_ecoflow_focus(lang: str = "en") -> Image.Image:
    fonts = FontBank()
    i18n = I18n(lang)
    cfg = load_config(demo=True, overrides={"language": lang, "theme": {"mode": "multi_accent"}})
    theme = Theme.from_config(cfg)
    base_ef = build_demo_snapshot(i18n)["ecoflow"]
    blackout_ef = dict(base_ef, is_grid=False, in_watts=0.0, out_watts=265.0, soc=78, remain_wh=1597, est_dsg_min=310)
    cw, ch = 406, 214
    pad, gap, S = 24, 20, 2

    out = _rich_wallpaper_backdrop(pad * 2 + cw * 2 + gap, pad * 2 + ch + 34, (74, 222, 128))
    d = ImageDraw.Draw(out)
    for idx, (label, state) in enumerate((("Grid AC Bypass", base_ef), ("Battery Blackout Alert", blackout_ef))):
        card = Image.new("RGBA", (cw * S, ch * S), (0, 0, 0, 0))
        ctx = RenderContext(card, ImageDraw.Draw(card), S, theme, fonts, i18n, None, [], {}, "right")
        draw_ecoflow_card(ctx, (0, 0, cw, ch), state, on_cycle_charge=lambda: None, on_toggle_usb=lambda: None, on_toggle_dc12v=lambda: None, on_toggle_beep=lambda: None)
        small = card.resize((cw, ch), Image.Resampling.LANCZOS)
        ox = pad + idx * (cw + gap)
        d.text((ox + 4, pad), label, font=fonts.get(15, "bold"), fill=(242, 246, 252, 255))
        _composite_acrylic_panel(out, small, (ox, pad + 28), corner=14)
    return out.convert("RGB")


def render_custom_json_layouts(lang: str = "en") -> Image.Image:
    """Showcase all 3 Custom JSON card layouts: columns, hero, list."""
    fonts = FontBank()
    i18n = I18n(lang)
    cfg = load_config(demo=True, overrides={"language": lang, "theme": {"mode": "multi_accent"}})
    theme = Theme.from_config(cfg)
    cw, ch = 392, 152
    pad, gap, S = 24, 18, 2

    samples = [
        (
            'layout: "columns"',
            {
                "id": "c1",
                "title": "Home Lab",
                "subtitle": "3 nodes",
                "badge": "Local JSON",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "NAS Pool", "value": "64%", "percent": 64, "sublabel": "7.6 / 12 TB", "tag": "OK", "status": "ok"},
                    {"label": "Pi-hole", "value": "24%", "percent": 24, "sublabel": "14.2k ads", "tag": "DNS", "status": "info"},
                    {"label": "UPS Load", "value": "88%", "percent": 88, "sublabel": "Peak load", "tag": "HI", "status": "warn"},
                ],
                "items": [],
            },
        ),
        (
            'layout: "hero"',
            {
                "id": "c2",
                "title": "Market Pulse",
                "subtitle": "19:24",
                "badge": "Live",
                "layout": "hero",
                "ok": True,
                "hero_value": "$94,280",
                "hero_sub": "BTC +3.4%",
                "hero_status": "ok",
                "metrics": [
                    {"label": "Ethereum (24h)", "value": "$3,410 (+2.1%)", "status": "ok"},
                    {"label": "USD / EUR", "value": "0.942", "status": "info"},
                ],
                "items": [],
            },
        ),
        (
            'layout: "list"',
            {
                "id": "c3",
                "title": "Ollama Local AI",
                "subtitle": "1 loaded",
                "badge": "3 models",
                "layout": "list",
                "ok": True,
                "metrics": [],
                "items": [
                    {"label": "qwen2.5-coder:14b", "value": "ACTIVE · 9.0 GB", "status": "ok"},
                    {"label": "llama3.2:latest", "value": "2.0 GB", "status": "info"},
                    {"label": "nomic-embed-text", "value": "0.3 GB", "status": "info"},
                ],
            },
        ),
    ]

    total_w = pad * 2 + cw * 3 + gap * 2
    total_h = pad * 2 + ch + 34
    out = _rich_wallpaper_backdrop(total_w, total_h, (88, 188, 255))
    d = ImageDraw.Draw(out)
    for idx, (caption, payload) in enumerate(samples):
        card = Image.new("RGBA", (cw * S, ch * S), (0, 0, 0, 0))
        ctx = RenderContext(card, ImageDraw.Draw(card), S, theme, fonts, i18n, None, [], {}, "right")
        draw_custom_json_card(ctx, (0, 0, cw, ch), payload, on_open_url=lambda _u: None)
        small = card.resize((cw, ch), Image.Resampling.LANCZOS)
        ox = pad + idx * (cw + gap)
        d.text((ox + 4, pad), caption, font=fonts.get(15, "bold"), fill=(242, 246, 252, 255))
        _composite_acrylic_panel(out, small, (ox, pad + 28), corner=14)
    return out.convert("RGB")


def render_theme_presets_showcase(lang: str = "en") -> Image.Image:
    """Showcase 4 distinct built-in theme presets side by side: Fluent Dark, Fluent Light, Catppuccin Mocha, Tokyo Night."""
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    fonts = FontBank()
    i18n = I18n(lang)
    w, h = 416, 774
    pad, gap, hdr_h = 28, 22, 50
    presets = [
        ("fluent_dark", "Fluent Dark", "Default Windows 11 acrylic"),
        ("fluent_light", "Fluent Light", "Frosted light surface & dark ink"),
        ("catppuccin_mocha", "Catppuccin Mocha", "Pastel dark community favorite"),
        ("tokyo_night", "Tokyo Night", "Deep indigo & neon accents"),
    ]
    total_w = pad * 2 + w * len(presets) + gap * (len(presets) - 1)
    total_h = pad * 2 + hdr_h + h
    canvas = _rich_wallpaper_backdrop(total_w, total_h, (88, 188, 255))
    d = ImageDraw.Draw(canvas)
    for idx, (key, title, sub) in enumerate(presets):
        cfg = load_config(demo=False, overrides={"language": lang, "theme": {"preset": key, "mode": "multi_accent"}})
        theme = Theme.from_config(cfg)
        renderer = HubRenderer(cfg, theme, i18n, fonts)
        snap = build_demo_snapshot(i18n, now=fixed_now)
        snap["media"]["like_enabled"] = False
        wing_img, _, _ = renderer.render_wing("left", w, h, snap, now=fixed_now, center_overlay_active=True)
        ox = pad + idx * (w + gap)
        d.text((ox + 4, pad), title, font=fonts.get(18, "bold"), fill=(246, 248, 252, 255))
        d.text((ox + 4, pad + 24), sub, font=fonts.get(12, "regular"), fill=(186, 196, 214, 255))
        _composite_acrylic_panel(canvas, wing_img, (ox, pad + hdr_h))
    return canvas.convert("RGB")


def generate_example_tile_pack() -> Path:
    pack_dir = REPO_ROOT / "packs" / "example_minimal"
    pack_dir.mkdir(parents=True, exist_ok=True)
    tile_path = pack_dir / "sample_terminal.png"
    size = 512
    im = Image.new("RGBA", (size, size), (22, 28, 40, 255))
    d = ImageDraw.Draw(im)
    for y in range(size):
        t = y / (size - 1)
        d.line([(0, y), (size, y)], fill=(int(20 + 28 * t), int(34 + 48 * t), int(56 + 78 * t), 255))
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

    outputs = [
        (assets_dir / "demo_multi_accent.png", render_three_panel_scene("multi_accent")),
        (assets_dir / "demo_single_accent.png", render_three_panel_scene("single_accent")),
        (assets_dir / "demo_tier1_default.png", render_three_panel_scene("multi_accent", tier1_only=True)),
        (assets_dir / "theme_comparison.png", render_theme_comparison()),
        (assets_dir / "theme_presets.png", render_theme_presets_showcase()),
        (assets_dir / "ecoflow_focus.png", render_ecoflow_focus()),
        (assets_dir / "custom_json_layouts.png", render_custom_json_layouts()),
    ]
    for path, image in outputs:
        image.save(path, "PNG", optimize=True)
    tile = generate_example_tile_pack()

    print("Generated showcase renders:")
    for p in [o[0] for o in outputs] + [tile]:
        print(f"  {p.relative_to(REPO_ROOT)} ({p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
