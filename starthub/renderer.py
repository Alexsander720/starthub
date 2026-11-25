"""Headless 2x-supersampled PIL renderer for StartHub wings and center overlays.

Completely decoupled from Tkinter/Win32 so it runs identically in live Windows mode,
in tools/render_demo.py, and in headless Linux pytest CI.
"""
from __future__ import annotations

import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from .config import is_widget_enabled
from .i18n import I18n
from .layout import CENTER_H, CENTER_SIDES, CENTER_W, CardSpec, WingLayout, compute_wing_stack
from .surface import FontBank
from .theme import Theme
from .widgets import Hotspot, RenderContext, draw_toast, finish_panel_image
from .widgets.audio import draw_audio_card
from .widgets.custom_json import draw_custom_json_card
from .widgets.ecoflow import draw_ecoflow_card
from .widgets.focus_timer import draw_focus_card
from .widgets.hue import draw_hue_card
from .widgets.media import draw_media_card
from .widgets.peripherals import draw_bt_drawer, draw_peripherals_card
from .widgets.phone_adb import draw_phone_card, draw_photos_card, draw_sms_bar_or_drawer
from .widgets.quick_actions import draw_quick_actions_card, draw_tile_switcher_bar
from .widgets.storage_network import draw_storage_network_card
from .widgets.system_monitor import draw_system_monitor
from .widgets.todoist import draw_todoist_card
from .widgets.weather_clock import draw_calendar_card, draw_weather_card, render_center_part


def _noop(*_args, **_kwargs) -> None:
    return None


class HubRenderer:
    """Stateless-friendly wing and overlay renderer backed by dynamic layout calculation."""

    SCALE = 2

    def __init__(self, config: Dict[str, Any], theme: Theme, i18n: I18n, fonts: Optional[FontBank] = None):
        self.config = config
        self.theme = theme
        self.i18n = i18n
        self.fonts = fonts or FontBank()
        self.img_cache: Dict[Any, Any] = {}

    def build_wing_specs(
        self,
        side: str,
        snapshot: Dict[str, Any],
        *,
        center_overlay_active: bool = False,
    ) -> List[CardSpec]:
        layout_cfg = self.config.get("layout", {})
        widget_ids = list(layout_cfg.get(f"{side}_widgets") or [])
        specs: List[CardSpec] = []

        phone_state = snapshot.get("phone") or {}
        photos_expanded = bool(phone_state.get("photos_expanded", False))
        media_state = snapshot.get("media") or {}
        media_playing = bool(media_state.get("playing", False))
        has_tasks_in_wing = any(
            w in ("tasks", "todoist") and is_widget_enabled(self.config, w, center_overlay_active=center_overlay_active)
            for w in widget_ids
        )

        for wid in widget_ids:
            if not is_widget_enabled(self.config, wid, center_overlay_active=center_overlay_active):
                continue
            if wid == "phone_adb":
                specs.append(CardSpec("phone_adb", min_height=170, preferred_height=176, expandable=False))
                if phone_state.get("enable_photos", True):
                    if photos_expanded:
                        specs.append(CardSpec("phone_photos", min_height=280, preferred_height=340, expandable=True))
                    else:
                        specs.append(CardSpec("phone_photos", min_height=46, preferred_height=46, expandable=False))
                if phone_state.get("enable_sms_otp", False):
                    specs.append(CardSpec("phone_sms", min_height=54, preferred_height=54, pinned_bottom=True))
            elif wid == "peripherals":
                specs.append(CardSpec("peripherals", min_height=98, preferred_height=104, expandable=False))
            elif wid == "audio_control":
                if photos_expanded and side == "left":
                    continue
                specs.append(CardSpec("audio_control", min_height=76, preferred_height=82, expandable=False))
            elif wid == "media_player":
                if photos_expanded and side == "left":
                    continue
                h = 114 if media_playing else 48
                specs.append(CardSpec("media_player", min_height=h, preferred_height=h, expandable=False))
            elif wid == "system_monitor":
                if photos_expanded and side == "left":
                    continue
                specs.append(CardSpec("system_monitor", min_height=78, preferred_height=84, expandable=False))
            elif wid == "storage_network":
                if photos_expanded and side == "left":
                    continue
                specs.append(CardSpec("storage_network", min_height=82, preferred_height=88, expandable=False))
            elif wid == "philips_hue":
                if photos_expanded and side == "left":
                    continue
                specs.append(CardSpec("philips_hue", min_height=124, preferred_height=134, expandable=True, max_height=156))
            elif wid == "ecoflow":
                specs.append(CardSpec("ecoflow", min_height=208, preferred_height=214, expandable=False))
            elif wid == "custom_json":
                cards = list(snapshot.get("custom_json") or [])
                for idx, card in enumerate(cards):
                    cid = str(card.get("id") or idx)
                    specs.append(CardSpec(f"custom_json:{cid}", min_height=138, preferred_height=144, expandable=False))
            elif wid in ("tasks", "todoist"):
                specs.append(CardSpec("tasks", min_height=158, preferred_height=196, expandable=True))
            elif wid == "focus_timer":
                specs.append(CardSpec("focus_timer", min_height=64, preferred_height=68, expandable=False))
            elif wid == "weather_card":
                specs.append(CardSpec("weather_card", min_height=140, preferred_height=255, expandable=True, max_height=290))
            elif wid == "calendar_card":
                specs.append(CardSpec("calendar_card", min_height=236, preferred_height=288, expandable=True, max_height=340))
            elif wid == "quick_actions":
                specs.append(CardSpec("quick_actions", min_height=64, preferred_height=68, expandable=False))
            elif wid == "tile_switcher":
                # Only render standalone bar when Tasks/Todoist isn't already hosting the Tile Switcher pill
                if not has_tasks_in_wing:
                    specs.append(CardSpec("tile_switcher", min_height=48, preferred_height=50, expandable=False))
        return specs

    def has_widgets(self, side: str, snapshot: Dict[str, Any], *, center_overlay_active: bool = False) -> bool:
        return len(self.build_wing_specs(side, snapshot, center_overlay_active=center_overlay_active)) > 0

    def render_wing(
        self,
        side: str,
        width: int,
        height: int,
        snapshot: Dict[str, Any],
        *,
        scroll_offset: int = 0,
        hover: Optional[str] = None,
        bt_drawer_open: bool = False,
        calendar_month: Optional[Tuple[int, int]] = None,
        now: Optional[datetime.datetime] = None,
        toast_message: str = "",
        tile_pack_label: Optional[str] = None,
        tile_busy: bool = False,
        center_overlay_active: bool = False,
        actions: Optional[Dict[str, Callable[..., None]]] = None,
    ) -> Tuple[Image.Image, List[Hotspot], WingLayout]:
        S = self.SCALE
        ref_now = now or datetime.datetime.now()
        cal_month = calendar_month or (ref_now.year, ref_now.month)
        acts = actions or {}

        specs = self.build_wing_specs(side, snapshot, center_overlay_active=center_overlay_active)
        wing_layout = compute_wing_stack(specs, width, height, margin=12, gap=8)

        # Render normal scrollable area
        canvas_h = max(height, wing_layout.content_height)
        img = Image.new("RGBA", (width * S, canvas_h * S), self.theme.panel_bg)
        draw = ImageDraw.Draw(img)
        hotspots: List[Hotspot] = []
        ctx = RenderContext(
            img=img,
            draw=draw,
            scale=S,
            theme=self.theme,
            fonts=self.fonts,
            i18n=self.i18n,
            hover=hover,
            hotspots=hotspots,
            img_cache=self.img_cache,
            side=side,
        )

        custom_map = {str(c.get("id") or idx): c for idx, c in enumerate(snapshot.get("custom_json") or [])}
        tile_enabled = bool(self.config.get("widgets", {}).get("tile_switcher", {}).get("enabled", False))

        for slot in wing_layout.slots:
            box = (slot.x1, slot.y1, slot.x2, slot.y2)
            k = slot.key
            if k == "phone_adb":
                draw_phone_card(
                    ctx,
                    box,
                    snapshot.get("phone") or {},
                    on_scrcpy=acts.get("phone_scrcpy", _noop),
                    on_screenshot=acts.get("phone_screenshot", _noop),
                    on_toggle_auto_clip=acts.get("phone_auto_clip", _noop),
                )
            elif k == "phone_photos":
                draw_photos_card(
                    ctx,
                    box,
                    snapshot.get("phone") or {},
                    on_toggle_expand=acts.get("phone_photos_toggle", _noop),
                    on_open_gallery=acts.get("phone_open_gallery", _noop),
                    on_copy_photo=acts.get("phone_copy_photo", _noop),
                    on_open_photo=acts.get("phone_open_photo", _noop),
                )
            elif k == "peripherals":
                draw_peripherals_card(
                    ctx,
                    box,
                    snapshot.get("peripherals") or {},
                    self.config.get("widgets", {}).get("peripherals", {}),
                    bt_drawer_open=bt_drawer_open,
                    on_refresh_gamepad=acts.get("refresh_gamepad", _noop),
                    on_toggle_bt_drawer=acts.get("toggle_bt_drawer", _noop),
                )
            elif k == "audio_control":
                draw_audio_card(
                    ctx,
                    box,
                    snapshot.get("audio") or {},
                    on_toggle_mute=acts.get("audio_mute", _noop),
                    on_set_volume=acts.get("audio_volume", _noop),
                    on_cycle_output=acts.get("audio_output", _noop),
                )
            elif k == "media_player":
                draw_media_card(
                    ctx,
                    box,
                    snapshot.get("media") or {},
                    on_command=acts.get("media_command", _noop),
                    on_like=acts.get("media_like", _noop),
                )
            elif k == "system_monitor":
                draw_system_monitor(ctx, box, snapshot.get("monitor") or {})
            elif k == "storage_network":
                draw_storage_network_card(ctx, box, snapshot.get("storage_network") or {})
            elif k == "philips_hue":
                draw_hue_card(ctx, box, snapshot.get("hue") or {}, on_command=acts.get("hue_command", _noop))
            elif k == "ecoflow":
                draw_ecoflow_card(
                    ctx,
                    box,
                    snapshot.get("ecoflow") or {},
                    on_cycle_charge=acts.get("ecoflow_charge", _noop),
                    on_toggle_usb=acts.get("ecoflow_usb", _noop),
                    on_toggle_dc12v=acts.get("ecoflow_dc", _noop),
                    on_toggle_beep=acts.get("ecoflow_beep", _noop),
                )
            elif k.startswith("custom_json:"):
                cid = k.split(":", 1)[1]
                draw_custom_json_card(
                    ctx,
                    box,
                    custom_map.get(cid, {"id": cid, "title": cid, "ok": False, "metrics": []}),
                    on_open_url=acts.get("custom_open_url", _noop),
                )
            elif k in ("tasks", "todoist"):
                draw_todoist_card(
                    ctx,
                    box,
                    snapshot.get("todoist") or {},
                    on_cycle_project=acts.get("todoist_cycle", _noop),
                    on_complete_task=acts.get("todoist_complete", _noop),
                    on_open_app=acts.get("todoist_open", _noop),
                    tile_pack_label=tile_pack_label if tile_enabled else None,
                    tile_busy=tile_busy,
                    on_cycle_tiles=acts.get("tile_cycle", _noop) if tile_enabled else None,
                )
            elif k == "focus_timer":
                draw_focus_card(
                    ctx,
                    box,
                    snapshot.get("focus_timer") or {},
                    on_toggle=acts.get("focus_toggle", _noop),
                    on_reset=acts.get("focus_reset", _noop),
                    on_switch_phase=acts.get("focus_phase", _noop),
                )
            elif k == "weather_card":
                draw_weather_card(ctx, box, snapshot.get("weather") or {}, ref_now)
            elif k == "calendar_card":
                draw_calendar_card(
                    ctx,
                    box,
                    month_tuple=cal_month,
                    today=ref_now.date(),
                    on_change_month=acts.get("calendar_change_month", _noop),
                    on_today=acts.get("calendar_today", _noop),
                )
            elif k == "quick_actions":
                qa_items = self.config.get("widgets", {}).get("quick_actions", {}).get("items") or []
                draw_quick_actions_card(ctx, box, qa_items, on_trigger=acts.get("quick_action", _noop))
            elif k == "tile_switcher":
                draw_tile_switcher_bar(
                    ctx,
                    box,
                    pack_label=tile_pack_label,
                    busy=tile_busy,
                    on_cycle=acts.get("tile_cycle", _noop),
                )

        # Apply scroll viewport if content exceeds visible height
        offset = max(0, min(wing_layout.max_scroll, int(scroll_offset)))
        if wing_layout.max_scroll > 0 or canvas_h != height:
            viewport_h = wing_layout.viewport_height if wing_layout.pinned_slots else height
            out = Image.new("RGBA", (width * S, height * S), self.theme.panel_bg)
            crop_top = offset * S
            crop_bot = min(img.height, (offset + viewport_h) * S)
            if crop_bot > crop_top:
                out.paste(img.crop((0, crop_top, width * S, crop_bot)), (0, 0))
            img = out
            draw = ImageDraw.Draw(img)
            ctx.img = img
            ctx.draw = draw
            hotspots[:] = [
                (x1, y1 - offset, x2, y2 - offset, lcb, rcb, hid)
                for x1, y1, x2, y2, lcb, rcb, hid in hotspots
                if y2 > offset and y1 < offset + viewport_h
            ]

        # Render bottom-pinned cards (e.g. collapsed SMS/2FA bar or expanded drawer)
        for pslot in wing_layout.pinned_slots:
            if pslot.key == "phone_sms":
                draw_sms_bar_or_drawer(
                    ctx,
                    (pslot.x1, pslot.y1, pslot.x2, pslot.y2),
                    snapshot.get("phone") or {},
                    on_toggle_expand=acts.get("phone_sms_toggle", _noop),
                    on_copy_sms=acts.get("phone_copy_sms", _noop),
                )

        # Optional interactive Bluetooth drawer overlay
        if side == "left" and bt_drawer_open:
            draw_bt_drawer(
                ctx,
                (12, min(296, max(12, height - 380)), width - 12, min(598, height - 74)),
                snapshot.get("peripherals") or {},
                on_toggle_radio=acts.get("bt_toggle_radio", _noop),
                on_close=acts.get("toggle_bt_drawer", _noop),
                on_open_settings=acts.get("bt_open_settings", _noop),
            )

        if toast_message:
            draw_toast(ctx, width, height, toast_message)

        return finish_panel_image(img, width, height, S, self.theme), hotspots, wing_layout

    def render_center_overlay(
        self,
        side: str,
        size: Tuple[int, int],
        snapshot: Dict[str, Any],
        now: Optional[datetime.datetime] = None,
    ) -> Image.Image:
        return render_center_part(
            side,
            size,
            weather=snapshot.get("weather") or {},
            now=now or datetime.datetime.now(),
            theme=self.theme,
            fonts=self.fonts,
            i18n=self.i18n,
            scale=self.SCALE,
        )

    def render_center_strip_preview(
        self, snapshot: Dict[str, Any], now: Optional[datetime.datetime] = None
    ) -> Image.Image:
        """Render both transparent center overlays side by side for offline previews."""
        w, h = CENTER_W, CENTER_H
        strip = Image.new("RGBA", (w * 2 + 16, h), (0, 0, 0, 0))
        for x, side in zip((0, w + 16), CENTER_SIDES):
            strip.alpha_composite(self.render_center_overlay(side, (w, h), snapshot, now=now), (x, 0))
        return strip
