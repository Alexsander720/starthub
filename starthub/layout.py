"""Dynamic vertical card stack layout + Start11 multi-panel & center-overlay geometry."""
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

    - Pinned-bottom cards (e.g. collapsed SMS bar) always stay anchored to the bottom of the wing.
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
            # Distribute extra height across expandable cards respecting max_height
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
        # Proportionally compress between preferred_height and min_height
        deficit = pref_sum - avail_for_cards
        slack_sum = max(1, pref_sum - min_sum)
        for i, spec in enumerate(normal_specs):
            slack = spec.preferred_height - spec.min_height
            cut = min(slack, round(deficit * (slack / slack_sum)))
            heights[i] = spec.preferred_height - cut
        # Clean up any 1px rounding remainder
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
    # Logical scrollable height excludes bottom pinned bar region
    content_height = max(viewport_bottom, content_bottom + margin)
    visible_limit = viewport_bottom
    max_scroll = max(0, (content_bottom + margin) - visible_limit) if pinned_specs else max(0, (content_bottom + margin) - wing_height)

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
) -> Dict[str, Rect]:
    """Compute (x, y, width, height) rects for left/right wings and optional outer columns."""
    left, top, right, bottom = start_rect
    wl, wt, wr, wb = work_area
    y = max(wt, min(top, wb - 1))
    height = max(1, min(bottom, wb) - y)

    layout: Dict[str, Rect] = {}
    lx = max(wl, min(left - left_width - gap, wr - left_width))
    rx = max(wl, min(right + gap, wr - right_width))

    if has_left:
        layout["left"] = (lx, y, left_width, height)
    if has_right:
        layout["right"] = (rx, y, right_width, height)

    left_anchor = lx if has_left else left
    right_anchor = (rx + right_width) if has_right else right
    left_space = left_anchor - wl - gap * 2
    right_space = wr - right_anchor - gap * 2

    if left_space >= 300:
        w = min(outer_width, left_space)
        layout["weather"] = (left_anchor - gap - w, y, w, height)
    if right_space >= 300:
        w = min(outer_width, right_space)
        layout["calendar"] = (right_anchor + gap, y, w, height)
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
