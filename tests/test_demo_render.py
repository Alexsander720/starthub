"""Headless visual PNG rendering tests across themes, languages, and Tier 1 vs Demo layouts."""
from __future__ import annotations

import datetime
from pathlib import Path

from PIL import ImageChops

from starthub.config import load_config
from starthub.i18n import I18n
from starthub.providers import build_demo_snapshot
from starthub.renderer import HubRenderer
from starthub.theme import Theme


def _image_diff_nonzero(img_a, img_b) -> bool:
    diff = ImageChops.difference(img_a.convert("RGB"), img_b.convert("RGB"))
    return diff.getbbox() is not None


def test_demo_renders_multi_and_single_accent_distinctly(tmp_path: Path):
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    results = {}
    for mode in ("multi_accent", "single_accent"):
        cfg = load_config(demo=True, overrides={"theme": {"mode": mode, "accent_color": "#58BCFF"}})
        i18n = I18n("en")
        theme = Theme.from_config(cfg)
        renderer = HubRenderer(cfg, theme, i18n)
        snap = build_demo_snapshot(i18n, now=fixed_now)

        im_l, spots_l, lay_l = renderer.render_wing("left", 416, 774, snap, now=fixed_now, tile_pack_label="Minimal")
        im_r, spots_r, lay_r = renderer.render_wing("right", 430, 774, snap, now=fixed_now, tile_pack_label="Minimal")
        im_c = renderer.render_center_strip_preview(snap, now=fixed_now)

        assert im_l.size == (416, 774)
        assert im_r.size == (430, 774)
        assert im_c.size == (308 * 2 + 16, 156)
        assert len(spots_l) >= 8
        assert len(spots_r) >= 6
        assert lay_l.slots and lay_r.slots

        out_l = tmp_path / f"{mode}_left.png"
        out_r = tmp_path / f"{mode}_right.png"
        im_l.save(out_l)
        im_r.save(out_r)
        assert out_l.stat().st_size > 5000
        assert out_r.stat().st_size > 5000
        results[mode] = (im_l, im_r)

    assert _image_diff_nonzero(results["multi_accent"][0], results["single_accent"][0])
    assert _image_diff_nonzero(results["multi_accent"][1], results["single_accent"][1])


def test_tier1_zero_key_default_layout_renders_cleanly():
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    cfg = load_config(demo=False)
    i18n = I18n("en")
    theme = Theme.from_config(cfg)
    renderer = HubRenderer(cfg, theme, i18n)
    snap = build_demo_snapshot(i18n, now=fixed_now)

    assert renderer.has_widgets("left", snap) is True
    assert renderer.has_widgets("right", snap) is True
    im_l, _, lay_l = renderer.render_wing("left", 416, 774, snap, now=fixed_now)
    im_r, _, lay_r = renderer.render_wing("right", 430, 774, snap, now=fixed_now)
    assert [s.key for s in lay_l.slots] == ["peripherals", "media_player", "system_monitor"]
    assert [s.key for s in lay_r.slots] == ["weather_card", "calendar_card"]
    assert im_l.size == (416, 774)
    assert im_r.size == (430, 774)


def test_all_languages_render_without_error():
    fixed_now = datetime.datetime(2026, 11, 25, 19, 24)
    for lang in ("en", "ru", "uk"):
        cfg = load_config(demo=True, overrides={"language": lang})
        i18n = I18n(lang)
        theme = Theme.from_config(cfg)
        renderer = HubRenderer(cfg, theme, i18n)
        snap = build_demo_snapshot(i18n, now=fixed_now)
        im_l, _, _ = renderer.render_wing("left", 416, 774, snap, now=fixed_now)
        im_r, _, _ = renderer.render_wing("right", 430, 774, snap, now=fixed_now)
        im_c = renderer.render_center_strip_preview(snap, now=fixed_now)
        assert im_l.getbbox() is not None
        assert im_r.getbbox() is not None
        assert im_c.getbbox() is not None
