"""Dynamic vertical card stack layout + DPI-adaptive Start11 / Windows 11 multi-panel geometry."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from typing import Any, Dict, List, Optional, Sequence, Tuple

Rect = Tuple[int, int, int, int]

CENTER_SIDES = ("center_weather", "center_clock")
CENTER_W = 308
CENTER_H = 156
CENTER_MIN_H = 96


@dataclass(frozen=True)
class CardSpec:
    """Height contract for a single widget card inside a wing."""

    key: str
    min_height: int
    preferred_height: int
    expandable: bool = False
    pinned_bottom: bool = False
    max_height: Optional[int] = None


@dataclass(frozen=True)
class CardSlot:
    """Resolved logical-pixel bounding box for a card inside a wing."""

    key: str
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


@dataclass(frozen=True)
class WingLayout:
    slots: List[CardSlot]
    pinned_slots: List[CardSlot]
    content_height: int
    viewport_height: int
    max_scroll: int
    margin: int = 12


def compute_wing_stack(
    specs: Sequence[CardSpec],
    width: int,
    wing_height: int,
    *,
    margin: int = 12,
    gap: int = 8,
) -> WingLayout:
    """Dynamically stack enabled cards vertically inside a wing with zero hardcoded coordinates.

    - Pinned-bottom cards (e.g. collapsed SMS bar or Quick Actions bar) stay anchored to the bottom.
    - Remaining vertical space is allocated to normal cards:
      * If total preferred height fits, extra space is distributed to expandable cards (capped by max_height).
      * If preferred height overflows, cards gently compress down toward min_height.
      * If even min_height overflows, the wing becomes smoothly scrollable (`max_scroll > 0`).
    """
    x1 = margin
    x2 = max(margin + 1, width - margin)

    pinned_specs = [s for s in specs if s.pinned_bottom]
    normal_specs = [s for s in specs if not s.pinned_bottom]

    # Place pinned-bottom cards from bottom upwards
    pinned_slots: List[CardSlot] = []
    bottom_cursor = wing_height - margin
    for spec in reversed(pinned_specs):
        h = spec.preferred_height
        y2 = bottom_cursor
        y1 = y2 - h
        pinned_slots.append(CardSlot(spec.key, x1, y1, x2, y2))
        bottom_cursor = y1 - gap
    pinned_slots.reverse()

    # Viewport area available for normal cards
    viewport_bottom = bottom_cursor if pinned_specs else (wing_height - margin)
    viewport_height = max(0, viewport_bottom - margin)

    if not normal_specs:
        return WingLayout(
            slots=[],
            pinned_slots=pinned_slots,
            content_height=max(wing_height, margin * 2),
            viewport_height=viewport_height,
            max_scroll=0,
            margin=margin,
        )

    total_gaps = gap * max(0, len(normal_specs) - 1)
    avail_for_cards = max(0, viewport_height - total_gaps)

    pref_sum = sum(s.preferred_height for s in normal_specs)
    min_sum = sum(s.min_height for s in normal_specs)

    heights: List[int] = [s.preferred_height for s in normal_specs]

    if avail_for_cards >= pref_sum:
        extra = avail_for_cards - pref_sum
        exp_indices = [i for i, s in enumerate(normal_specs) if s.expandable]
        if extra > 0 and exp_indices:
            remaining = extra
            active = list(exp_indices)
            while remaining > 0 and active:
                share = max(1, remaining // len(active))
                next_active = []
                for idx in active:
                    if remaining <= 0:
                        break
                    spec = normal_specs[idx]
                    cap = spec.max_height
                    room = (cap - heights[idx]) if cap is not None else remaining
                    add = min(share, room, remaining)
                    if add > 0:
                        heights[idx] += add
                        remaining -= add
                    if cap is None or heights[idx] < cap:
                        next_active.append(idx)
                if len(next_active) == len(active) and remaining > 0 and share == 1 and all(
                    normal_specs[i].max_height is not None and heights[i] >= normal_specs[i].max_height
                    for i in active
                ):
                    break
                active = next_active
    elif avail_for_cards >= min_sum:
        deficit = pref_sum - avail_for_cards
        slack_sum = max(1, pref_sum - min_sum)
        for i, spec in enumerate(normal_specs):
            slack = spec.preferred_height - spec.min_height
            cut = min(slack, round(deficit * (slack / slack_sum)))
            heights[i] = spec.preferred_height - cut
        diff = sum(heights) - avail_for_cards
        for i in range(len(heights) - 1, -1, -1):
            if diff == 0:
                break
            if diff > 0 and heights[i] > normal_specs[i].min_height:
                step = min(diff, heights[i] - normal_specs[i].min_height)
                heights[i] -= step
                diff -= step
            elif diff < 0 and heights[i] < normal_specs[i].preferred_height:
                step = min(-diff, normal_specs[i].preferred_height - heights[i])
                heights[i] += step
                diff += step
    else:
        heights = [s.min_height for s in normal_specs]

    slots: List[CardSlot] = []
    y = margin
    for spec, h in zip(normal_specs, heights):
        slots.append(CardSlot(spec.key, x1, y, x2, y + h))
        y += h + gap

    content_bottom = slots[-1].y2 if slots else margin
    content_height = max(viewport_bottom, content_bottom + margin)
    visible_limit = viewport_bottom
    max_scroll = (
        max(0, (content_bottom + margin) - visible_limit)
        if pinned_specs
        else max(0, (content_bottom + margin) - wing_height)
    )

    return WingLayout(
        slots=slots,
        pinned_slots=pinned_slots,
        content_height=content_height,
        viewport_height=visible_limit,
        max_scroll=max_scroll,
        margin=margin,
    )


def panel_layout(
    start_rect: Rect,
    work_area: Rect,
    *,
    left_width: int = 416,
    right_width: int = 430,
    outer_width: int = 344,
    gap: int = 10,
    has_left: bool = True,
    has_right: bool = True,
    adaptive_width: bool = True,
    min_wing_width: int = 300,
) -> Dict[str, Rect]:
    """Compute (x, y, width, height) rects for left/right wings without overlapping Start Menu.

    On tighter 1080p / high-DPI displays (`adaptive_width=True`), each wing gracefully shrinks down
    to `min_wing_width` to fit the real margin beside the Start menu instead of colliding with it.
    If one side has less than `min_wing_width` (e.g. left-aligned Start menu), that wing is skipped
    so the Start menu stays 100% clickable.
    """
    left, top, right, bottom = start_rect
    wl, wt, wr, wb = work_area
    y = max(wt, min(top, wb - 1))
    height = max(1, min(bottom, wb) - y)
    edge_pad = 6

    layout: Dict[str, Rect] = {}
    avail_left = max(0, left - wl - gap - edge_pad)
    avail_right = max(0, wr - right - gap - edge_pad)

    eff_lw = left_width
    eff_rw = right_width
    lx = max(wl, min(left - left_width - gap, wr - left_width))
    rx = max(wl, min(right + gap, wr - right_width))

    if has_left:
        if adaptive_width:
            if avail_left >= min_wing_width:
                eff_lw = min(left_width, avail_left)
                lx = left - gap - eff_lw
                layout["left"] = (lx, y, eff_lw, height)
        else:
            layout["left"] = (lx, y, left_width, height)

    if has_right:
        if adaptive_width:
            if avail_right >= min_wing_width:
                eff_rw = min(right_width, avail_right)
                rx = right + gap
                layout["right"] = (rx, y, eff_rw, height)
        else:
            layout["right"] = (rx, y, right_width, height)

    # Edge-case fallback: if neither wing fit (e.g. full-screen Start menu in hotkey/preview),
    # place compact wings near monitor edges so the user isn't left with nothing.
    if adaptive_width and not layout and (has_left or has_right):
        work_w = max(1, wr - wl)
        if has_left and work_w >= min_wing_width + 20:
            w = min(left_width, max(min_wing_width, work_w // 3))
            layout["left"] = (wl + edge_pad, y, w, height)
        if has_right and work_w >= (min_wing_width * 2 + 40 if has_left else min_wing_width + 20):
            w = min(right_width, max(min_wing_width, work_w // 3))
            layout["right"] = (wr - edge_pad - w, y, w, height)

    left_anchor = layout["left"][0] if "left" in layout else left
    right_anchor = (layout["right"][0] + layout["right"][2]) if "right" in layout else right
    left_space = left_anchor - wl - gap * 2
    right_space = wr - right_anchor - gap * 2

    if left_space >= 300:
        w = min(outer_width, left_space)
        layout["weather"] = (left_anchor - gap - w, y, w, height)
    if right_space >= 300:
        w = min(outer_width, right_space)
        layout["calendar"] = (right_anchor + gap, y, w, height)
    return layout


def standalone_panel_layout(
    work_area: Rect,
    *,
    left_width: int = 416,
    right_width: int = 430,
    wing_height: int = 774,
    gap: int = 14,
    has_left: bool = True,
    has_right: bool = True,
    min_wing_width: int = 300,
) -> Dict[str, Rect]:
    """Compute balanced edge/HUD panel positions for hotkey / standalone mode (no Start Menu needed)."""
    wl, wt, wr, wb = work_area
    work_w = max(1, wr - wl)
    work_h = max(1, wb - wt)
    h = min(wing_height, max(500, work_h - 48))
    y = wt + max(16, (work_h - h) // 2)
    margin_x = min(28, max(10, work_w // 40))

    max_each = max(min_wing_width, (work_w - margin_x * 2 - gap) // 2) if (has_left and has_right) else (work_w - margin_x * 2)
    layout: Dict[str, Rect] = {}
    if has_left:
        w = min(left_width, max_each)
        layout["left"] = (wl + margin_x, y, w, h)
    if has_right:
        w = min(right_width, max_each)
        layout["right"] = (wr - margin_x - w, y, w, h)
    return layout


def center_layouts(start_rect: Rect, work_area: Rect, grid: Optional[Dict[str, Any]] = None) -> Dict[str, Rect]:
    """Compute transparent center overlay rectangles beneath Start11 tile columns."""
    l, t, r, b = start_rect
    wl, wt, wr, wb = work_area
    if not grid or l < wl or t < wt or r > wr or b > wb:
        return {}
    nl, nt, nr, nb = grid["native_rect"]
    if not (l <= nl < nr <= r and t <= nt < nb <= b):
        return {}
    result: Dict[str, Rect] = {}
    scale = grid["unit"] / 52.0
    for side, group in zip(CENTER_SIDES, grid["groups"][:2]):
        x, width = nl + group["left"], group["width"]
        y = nt + group["bottom"] + round(14 * scale)
        height = min(round(CENTER_H * scale), min(nb, b - round(14 * scale)) - y)
        if height < round(CENTER_MIN_H * scale) or x + width > nr:
            continue
        if any(
            max(x, nl + a) < min(x + width, nl + c) and max(y, nt + bb) < min(y + height, nt + d)
            for a, bb, c, d in grid["tile_rects"]
        ):
            continue
        result[side] = (x, y, width, height)
    return result


def calibrated_tile_grid(registry: Dict[str, Any], native: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Calibrate Start11 TileMode=0 group geometry against native SysListView32 item bounds."""
    try:
        settings = registry["Start8"]
        if any(str(settings[k]) != v for k, v in dict(MenuMode="2", TileMode="0", RightIconMode="0").items()):
            return None
        if not native or not native["visible"] or tuple(native["scroll"]) != (0, 0):
            return None
        columns = int(settings["Win10WidthC"])
        if not 1 <= columns <= 16:
            return None

        groups, tiles, definitions = [], [], []
        used_columns, ids, occupied = set(), set(), set()

        for _, value in sorted(registry["Groups"].items(), key=lambda p: int(p[0])):
            p = value.split("|")
            if len(p) != 19 or p[2:6] != ["0"] * 4 or p[8:] != ["0", "0", "", "0", "", "9999", "0", "0", "", "-1", ""]:
                return None
            col = int(p[6])
            if col < 0 or col >= columns or col in used_columns or p[0] in ids:
                return None
            used_columns.add(col)
            ids.add(p[0])
            group = []
            for _, item_val in sorted(registry["GroupContents\\" + p[0]].items(), key=lambda pair: int(pair[0])):
                q = item_val.split("|")
                if len(q) < 6 or q[1] != "-1":
                    return None
                size, x, y = int(q[2]), int(q[3]), int(q[4])
                dimensions = {0: (1, 1), 1: (2, 2), 2: (4, 2), 3: (4, 4)}
                if size not in dimensions:
                    return None
                tw, th = dimensions[size]
                if x < 0 or y < 0 or x + tw > 6:
                    return None
                cells = {(col, x + dx, y + dy) for dx in range(tw) for dy in range(th)}
                if cells & occupied:
                    return None
                occupied.update(cells)
                tile = (col, x, y, tw, th)
                group.append(tile)
                tiles.append(tile)
            groups.append(group)
            definitions.append((p[0], p[1], col))

        reference = groups[0] if groups else []
        items = native["items"]
        if len(reference) != len(items):
            return None

        nr = native["rect"]
        client = native.get("client", (nr[2] - nr[0], nr[3] - nr[1]))
        panel_unit = client[0] * 52 / (columns * 324 - 16 + 23)
        if reference:
            first = items[0]
            candidates = {
                ((first[2] - first[0]) / (tw - 1 / 13) + (first[3] - first[1]) / (th - 1 / 13)) / 2
                for tw, th in {(tile[3], tile[4]) for tile in reference}
            }
        else:
            candidates = {panel_unit}

        for unit in sorted(candidates, key=lambda val: abs(val - panel_unit)):
            if not 20 <= unit <= 120:
                continue
            gap = unit / 13
            stride = 6 * unit + 3 * gap
            width = round(columns * stride - 4 * gap)
            if abs(client[0] - (width + 23 * unit / 52)) > 1 or client[1] != nr[3] - nr[1]:
                continue
            header = 47 * unit / 52
            expected = [
                (
                    round(x * unit),
                    round(header + y * unit),
                    round((x + tw) * unit - gap),
                    round(header + (y + th) * unit - gap),
                )
                for _, x, y, tw, th in reference
            ]
            remaining = Counter(tuple(r) for r in items)
            for box in expected:
                if remaining[box]:
                    remaining[box] -= 1
                    continue
                match = next(
                    (
                        near
                        for delta in product((-1, 0, 1), repeat=4)
                        if remaining[(near := tuple(a + d for a, d in zip(box, delta)))]
                    ),
                    None,
                )
                if match is None:
                    break
                remaining[match] -= 1
            else:
                break
        else:
            return None

        rects = [
            (
                round(col * stride + x * unit),
                round(header + y * unit),
                round(col * stride + (x + tw) * unit - gap),
                round(header + (y + th) * unit - gap),
            )
            for col, x, y, tw, th in tiles
        ]
        measured_groups = []
        for (gid, title, col), group in zip(definitions, groups):
            bottom = max((round(header + (y + th) * unit - gap) for _, x, y, tw, th in group), default=round(header))
            measured_groups.append(
                dict(id=gid, title=title, col=col, left=round(col * stride), width=round(6 * unit - gap), bottom=bottom)
            )
        measured_groups.sort(key=lambda g: g["col"])
        return dict(
            native_rect=tuple(nr),
            width=width,
            bottom=max((r[3] for r in rects), default=round(header)),
            tile_rects=rects,
            groups=measured_groups,
            counts=[len(g) for g in groups],
            unit=unit,
        )
    except (KeyError, ValueError, IndexError, TypeError, AttributeError, ZeroDivisionError):
        return None
