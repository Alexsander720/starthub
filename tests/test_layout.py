"""Tests for dynamic vertical card stacking and multi-panel Start11 geometry."""
from __future__ import annotations

from starthub.layout import CardSpec, calibrated_tile_grid, center_layouts, compute_wing_stack, panel_layout


def test_dynamic_stack_distributes_extra_height_to_expandable():
    specs = [
        CardSpec("top", min_height=100, preferred_height=100, expandable=False),
        CardSpec("flex", min_height=120, preferred_height=150, expandable=True),
    ]
    layout = compute_wing_stack(specs, width=416, wing_height=500, margin=12, gap=8)
    assert layout.max_scroll == 0
    assert len(layout.slots) == 2
    assert layout.slots[0].y1 == 12
    assert layout.slots[0].height == 100
    assert layout.slots[1].y1 == 120
    assert layout.slots[1].y2 == 488  # fills right down to bottom margin


def test_dynamic_stack_compresses_before_scrolling():
    specs = [
        CardSpec("a", min_height=100, preferred_height=160),
        CardSpec("b", min_height=100, preferred_height=160),
    ]
    # Available = 280 - 24 - 8 = 248 (between min 200 and pref 320)
    layout = compute_wing_stack(specs, width=416, wing_height=280, margin=12, gap=8)
    assert layout.max_scroll == 0
    assert layout.slots[0].height >= 100
    assert layout.slots[1].height >= 100
    assert layout.slots[1].y2 <= 268


def test_dynamic_stack_enables_scroll_when_min_height_overflows():
    specs = [
        CardSpec("a", min_height=200, preferred_height=220),
        CardSpec("b", min_height=200, preferred_height=220),
        CardSpec("c", min_height=200, preferred_height=220),
    ]
    layout = compute_wing_stack(specs, width=416, wing_height=500, margin=12, gap=8)
    assert layout.max_scroll > 0
    assert layout.slots[-1].y2 > 500


def test_pinned_bottom_card_stays_anchored():
    specs = [
        CardSpec("phone", min_height=170, preferred_height=176),
        CardSpec("peripherals", min_height=98, preferred_height=104),
        CardSpec("sms", min_height=54, preferred_height=54, pinned_bottom=True),
    ]
    layout = compute_wing_stack(specs, width=416, wing_height=774, margin=12, gap=8)
    assert len(layout.pinned_slots) == 1
    sms = layout.pinned_slots[0]
    assert sms.key == "phone_sms" or sms.key == "sms"
    assert sms.y2 == 774 - 12
    assert sms.y1 == 774 - 12 - 54
    assert all(s.y2 < sms.y1 for s in layout.slots)


def test_panel_layout_hides_disabled_wings_and_clamps_to_work_area():
    # Start menu centered on 2560x1440 monitor
    lay = panel_layout((900, 400, 1660, 1174), (0, 0, 2560, 1400), has_left=True, has_right=True)
    assert "left" in lay and "right" in lay
    assert lay["left"][0] + lay["left"][2] == 900 - 10
    assert lay["right"][0] == 1660 + 10
    assert lay["left"][3] == lay["right"][3] == 774

    # Only left wing enabled
    lay_left = panel_layout((900, 400, 1660, 1174), (0, 0, 2560, 1400), has_left=True, has_right=False)
    assert "left" in lay_left and "right" not in lay_left


def test_calibrated_tile_grid_and_center_layouts():
    unit = 52.0
    gap = unit / 13.0
    stride = 6 * unit + 3 * gap
    width = round(2 * stride - 4 * gap)
    header = 47 * unit / 52.0
    client_w = round(width + 23 * unit / 52.0)
    client_h = 680

    registry = {
        "Start8": {"MenuMode": "2", "TileMode": "0", "RightIconMode": "0", "Win10WidthC": "2"},
        "Groups": {
            "0": "G0|Pinned|0|0|0|0|0|1|0|0||0||9999|0|0||-1|",
            "1": "G1|Tools|0|0|0|0|1|2|0|0||0||9999|0|0||-1|",
        },
        "GroupContents\\G0": {
            "0": "app1|-1|1|0|0|-1||1|1|0|-1",
            "1": "app2|-1|1|2|0|-1||2|1|0|-1",
        },
        "GroupContents\\G1": {
            "0": "app3|-1|1|0|0|-1||1|1|0|-1",
        },
    }
    native = {
        "visible": True,
        "scroll": (0, 0),
        "rect": (920, 460, 920 + client_w, 460 + client_h),
        "client": (client_w, client_h),
        "items": [
            (round(0 * unit), round(header), round(2 * unit - gap), round(header + 2 * unit - gap)),
            (round(2 * unit), round(header), round(4 * unit - gap), round(header + 2 * unit - gap)),
        ],
    }
    grid = calibrated_tile_grid(registry, native)
    assert grid is not None
    assert len(grid["groups"]) == 2

    overlays = center_layouts((900, 400, 920 + client_w + 20, 460 + client_h + 20), (0, 0, 2560, 1400), grid)
    assert "center_weather" in overlays
    assert "center_clock" in overlays
