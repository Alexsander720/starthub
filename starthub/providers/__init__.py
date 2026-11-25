"""Unified ProviderHub coordinating Tier 1 + Tier 2 providers and rich --demo snapshots."""
from __future__ import annotations

import datetime
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ..config import DEFAULT_CACHE_DIR
from ..i18n import I18n
from .audio import AudioControlProvider
from .custom_json import CustomJsonProvider
from .ecoflow import EcoFlowProvider
from .focus_timer import FocusTimerProvider
from .hue import HueProvider
from .local_tasks import LocalTasksProvider
from .media import MediaProvider
from .peripherals import PeripheralsProvider
from .phone_adb import PhoneAdbProvider
from .storage_network import StorageNetworkProvider
from .system_monitor import SystemMonitorProvider
from .todoist import TodoistProvider
from .weather import WeatherProvider


def build_demo_snapshot(i18n: I18n, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """Generate rich, realistic, 100% synthetic showcase data for --demo mode."""
    ref = now or datetime.datetime.now()
    today = ref.date()
    days = [(today + datetime.timedelta(days=d)).isoformat() for d in range(5)]

    is_ru = i18n.lang == "ru"
    is_uk = i18n.lang == "uk"

    if is_ru:
        city = "Киев"
        hue_labels = ("Свет в кабинете", "Подсветка монитора")
        todo_proj = "Сегодня"
        audio_dev = "Наушники · Studio Pro"
        audio_devs = [
            {"id": "d1", "name": "Наушники (Studio Pro)", "short_name": "Наушники · Studio Pro", "active": True},
            {"id": "d2", "name": "Динамики (Desk Audio)", "short_name": "Динамики · Desk Audio", "active": False},
            {"id": "d3", "name": "Монитор (HDMI Audio)", "short_name": "Монитор · HDMI", "active": False},
        ]
        todo_items = [
            {"id": "d1", "content": "Опубликовать StartHub v0.1.0 на GitHub", "priority": 4, "due": {"date": today.isoformat()}},
            {"id": "d2", "content": "Проверить тему single_accent и blur", "priority": 3, "due": {"date": today.isoformat()}},
            {"id": "d3", "content": "Настроить виджеты через GUI Settings", "priority": 2, "due": {"date": (today + datetime.timedelta(days=1)).isoformat()}},
            {"id": "d4", "content": "Проверить сборку portable ZIP с SHA-256", "priority": 1, "due": {"date": (today + datetime.timedelta(days=1)).isoformat()}},
        ]
        custom_cards = [
            {
                "id": "ai_quotas",
                "title": "API & AI Quotas",
                "badge": "3 сервиса",
                "subtitle": "Демо JSON",
                "url": "",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "LLM 5ч", "value": "34%", "percent": 34, "sublabel": "сброс 22:00", "tag": "OK", "status": "info"},
                    {"label": "Неделя", "value": "68%", "percent": 68, "sublabel": "ост. 32%", "tag": "Pro", "status": "info"},
                    {"label": "GPU Cloud", "value": "19%", "percent": 19, "sublabel": "$4.20 / мес", "tag": "API", "status": "ok"},
                ],
                "items": [],
            },
            {
                "id": "homelab",
                "title": "Home Lab",
                "badge": "Локально",
                "subtitle": "JSON-виджет",
                "url": "",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "NAS Диск", "value": "64%", "percent": 64, "sublabel": "7.6 / 12 ТБ", "tag": "OK", "status": "ok"},
                    {"label": "Pi-hole", "value": "24%", "percent": 24, "sublabel": "14.2k блок", "tag": "DNS", "status": "info"},
                    {"label": "Роутер", "value": "12ms", "percent": 18, "sublabel": "940 Мбит/с", "tag": "WAN", "status": "ok"},
                ],
                "items": [],
            },
        ]
        sms_items = [
            {"sender": "GitHub", "body": "Ваш код подтверждения входа: 482910", "time_str": "2 мин назад", "otp": "482910"},
            {"sender": "Cloud", "body": "Резервная копия успешно завершена", "time_str": "18:15", "otp": None},
        ]
    elif is_uk:
        city = "Київ"
        hue_labels = ("Світло кабінету", "Підсвітка монітора")
        todo_proj = "Сьогодні"
        audio_dev = "Навушники · Studio Pro"
        audio_devs = [
            {"id": "d1", "name": "Навушники (Studio Pro)", "short_name": "Навушники · Studio Pro", "active": True},
            {"id": "d2", "name": "Динаміки (Desk Audio)", "short_name": "Динаміки · Desk Audio", "active": False},
            {"id": "d3", "name": "Монітор (HDMI Audio)", "short_name": "Монітор · HDMI", "active": False},
        ]
        todo_items = [
            {"id": "d1", "content": "Опублікувати StartHub v0.1.0 на GitHub", "priority": 4, "due": {"date": today.isoformat()}},
            {"id": "d2", "content": "Перевірити тему single_accent та blur", "priority": 3, "due": {"date": today.isoformat()}},
            {"id": "d3", "content": "Налаштувати віджети через GUI Settings", "priority": 2, "due": {"date": (today + datetime.timedelta(days=1)).isoformat()}},
            {"id": "d4", "content": "Перевірити збірку portable ZIP із SHA-256", "priority": 1, "due": {"date": (today + datetime.timedelta(days=1)).isoformat()}},
        ]
        custom_cards = [
            {
                "id": "ai_quotas",
                "title": "API & AI Quotas",
                "badge": "3 сервіси",
                "subtitle": "Демо JSON",
                "url": "",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "LLM 5г", "value": "34%", "percent": 34, "sublabel": "скид 22:00", "tag": "OK", "status": "info"},
                    {"label": "Тиждень", "value": "68%", "percent": 68, "sublabel": "зал. 32%", "tag": "Pro", "status": "info"},
                    {"label": "GPU Cloud", "value": "19%", "percent": 19, "sublabel": "$4.20 / міс", "tag": "API", "status": "ok"},
                ],
                "items": [],
            },
            {
                "id": "homelab",
                "title": "Home Lab",
                "badge": "Локально",
                "subtitle": "JSON-віджет",
                "url": "",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "NAS Диск", "value": "64%", "percent": 64, "sublabel": "7.6 / 12 ТБ", "tag": "OK", "status": "ok"},
                    {"label": "Pi-hole", "value": "24%", "percent": 24, "sublabel": "14.2k блок", "tag": "DNS", "status": "info"},
                    {"label": "Роутер", "value": "12ms", "percent": 18, "sublabel": "940 Мбіт/с", "tag": "WAN", "status": "ok"},
                ],
                "items": [],
            },
        ]
        sms_items = [
            {"sender": "GitHub", "body": "Ваш код підтвердження входу: 482910", "time_str": "2 хв тому", "otp": "482910"},
            {"sender": "Cloud", "body": "Резервну копію успішно створено", "time_str": "18:15", "otp": None},
        ]
    else:
        city = "Kyiv"
        hue_labels = ("Office Light", "Monitor Bar")
        todo_proj = "Today"
        audio_dev = "Headphones · Studio Pro"
        audio_devs = [
            {"id": "d1", "name": "Headphones (Studio Pro)", "short_name": "Headphones · Studio Pro", "active": True},
            {"id": "d2", "name": "Speakers (Desk Audio)", "short_name": "Speakers · Desk Audio", "active": False},
            {"id": "d3", "name": "Monitor (HDMI Audio)", "short_name": "Monitor · HDMI", "active": False},
        ]
        todo_items = [
            {"id": "d1", "content": "Ship StartHub v0.1.0 open-source release", "priority": 4, "due": {"date": today.isoformat()}},
            {"id": "d2", "content": "Test Windows 11 native Start & Hotkey modes", "priority": 3, "due": {"date": today.isoformat()}},
            {"id": "d3", "content": "Customize widgets with built-in Settings UI", "priority": 2, "due": {"date": (today + datetime.timedelta(days=1)).isoformat()}},
            {"id": "d4", "content": "Verify portable ZIP release & SHA-256", "priority": 1, "due": {"date": (today + datetime.timedelta(days=1)).isoformat()}},
        ]
        custom_cards = [
            {
                "id": "ai_quotas",
                "title": "API & AI Quotas",
                "badge": "3 pools",
                "subtitle": "Custom JSON",
                "url": "",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "5h Window", "value": "34%", "percent": 34, "sublabel": "resets 22:00", "tag": "OK", "status": "info"},
                    {"label": "Weekly", "value": "68%", "percent": 68, "sublabel": "32% left", "tag": "Pro", "status": "info"},
                    {"label": "GPU Cloud", "value": "19%", "percent": 19, "sublabel": "$4.20 / mo", "tag": "API", "status": "ok"},
                ],
                "items": [],
            },
            {
                "id": "homelab",
                "title": "Home Lab",
                "badge": "Local JSON",
                "subtitle": "3 nodes",
                "url": "",
                "layout": "columns",
                "ok": True,
                "metrics": [
                    {"label": "NAS Pool", "value": "64%", "percent": 64, "sublabel": "7.6 / 12 TB", "tag": "OK", "status": "ok"},
                    {"label": "Pi-hole", "value": "24%", "percent": 24, "sublabel": "14.2k blocked", "tag": "DNS", "status": "info"},
                    {"label": "Fiber WAN", "value": "12ms", "percent": 18, "sublabel": "940 Mbps", "tag": "UP", "status": "ok"},
                ],
                "items": [],
            },
        ]
        sms_items = [
            {"sender": "GitHub", "body": "Your authentication code is 482910", "time_str": "2m ago", "otp": "482910"},
            {"sender": "Cloud", "body": "Nightly backup completed cleanly", "time_str": "18:15", "otp": None},
        ]

    return {
        "monitor": {"cpu": 28, "gpu": 42, "ram": 56, "temperature": 54},
        "storage_network": {
            "drives": [
                {"label": "C:", "percent": 64, "free_text": "362 GB", "total_text": "1.0 TB"},
                {"label": "D:", "percent": 48, "free_text": "1.0 TB", "total_text": "2.0 TB"},
                {"label": "E:", "percent": 82, "free_text": "184 GB", "total_text": "1.0 TB"},
            ],
            "down_bps": 4_404_019.0,
            "up_bps": 838_860.0,
            "down_text": "4.2 MB/s",
            "up_text": "819 KB/s",
        },
        "audio": {
            "available": True,
            "volume": 60,
            "muted": False,
            "device_id": "d1",
            "device_name": audio_dev,
            "devices": audio_devs,
        },
        "focus_timer": {
            "phase": "work",
            "running": True,
            "remaining_sec": 1125,
            "total_sec": 1500,
            "percent": 25.0,
            "display": "18:45",
            "sessions_done": 2,
        },
        "media": {
            "playing": True,
            "available": True,
            "title": "Midnight City (Synthwave Mix)",
            "artist": "M83 · Hurry Up, We're Dreaming",
            "app_id": "Spotify.exe",
            "source_name": "Spotify",
            "is_spotify": True,
            "position": 148.0,
            "duration": 244.0,
            "cover": None,
            "cover_track": ("Midnight City", "M83", "Demo"),
            "media_track": ("Midnight City", "M83", "Demo"),
            "like_enabled": True,
            "like_saved": True,
            "like_ready": True,
            "like_busy": False,
            "like_message": "",
        },
        "peripherals": {
            "mouse": {"name": "Wireless Mouse", "battery": 75, "charging": False, "online": True},
            "keyboard": {"name": "Mechanical KB", "battery": 90, "online": True},
            "gamepad": {"name": "DualSense", "battery": 80, "charging": False, "online": True},
            "handheld": {"name": "Handheld", "battery": 84, "charging": False, "status": "Discharging", "stale": False},
            "bt_on": True,
            "bt_devices": [
                {"name": "Sony WH-1000XM5", "connected": True, "battery": 85},
                {"name": "DualSense Wireless", "connected": True, "battery": 80},
                {"name": "Keychron Q1 Pro", "connected": False, "battery": None},
            ],
        },
        "hue": {
            "ready": True,
            "message": "",
            "targets": [
                {"key": "groups:1:0", "kind": "groups", "id": "1", "label": hue_labels[0], "icon": "bulb", "dimmer": True, "on": True, "bri": 191, "reachable": True},
                {"key": "lights:2:1", "kind": "lights", "id": "2", "label": hue_labels[1], "icon": "monitor", "dimmer": False, "on": True, "bri": 215, "reachable": True},
            ],
        },
        "phone": {
            "online": True,
            "name": "Pixel 9 Pro",
            "battery": 84,
            "charging": True,
            "auto_clip_sync": True,
            "sms_expanded": False,
            "photos_expanded": False,
            "enable_sms_otp": True,
            "enable_photos": True,
            "frame_image_path": "",
            "photos": [],
            "sms": sms_items,
        },
        "ecoflow": {
            "stale": False,
            "last_update": time.time(),
            "soc": 96,
            "in_watts": 195.0,
            "out_watts": 182.0,
            "est_dsg_min": 575,
            "remain_wh": 1966,
            "full_wh": 2048,
            "is_grid": True,
            "chg_pow_max": 400,
            "chg_pow_max_reported": True,
            "usb_open": True,
            "dc_out_open": False,
            "beep_on": True,
            "device_name": "DELTA 3 Max",
            "image_path": "",
        },
        "custom_json": custom_cards,
        "todoist": {
            "configured": True,
            "is_local": False,
            "projects": [{"id": "demo", "name": todo_proj}],
            "proj_idx": 0,
            "tasks": todo_items,
            "all_tasks": todo_items,
        },
        "weather": {
            "city": city,
            "units": "metric",
            "current": {
                "temperature_2m": 18.4,
                "apparent_temperature": 17.1,
                "weather_code": 2,
                "wind_speed_10m": 3.4,
                "relative_humidity_2m": 58,
                "is_day": 1,
            },
            "daily": {
                "time": days,
                "temperature_2m_max": [20.0, 21.0, 17.0, 19.0, 22.0],
                "temperature_2m_min": [11.0, 12.0, 9.0, 10.0, 13.0],
                "weather_code": [2, 0, 61, 1, 0],
                "sunrise": [f"{d}T06:42" for d in days],
                "sunset": [f"{d}T19:18" for d in days],
            },
            "updated_at": time.time(),
            "offline": False,
        },
    }


class ProviderHub:
    """Facade combining all active Tier 1 + Tier 2 providers (or synthetic --demo state) + toast notifications."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: I18n,
        *,
        demo: bool = False,
        cache_dir: Optional[Path] = None,
        on_change: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.i18n = i18n
        self.demo = demo
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.on_change = on_change

        self._toast_lock = threading.Lock()
        self.toast_message = ""
        self.toast_until = 0.0

        self._demo_state = build_demo_snapshot(i18n) if demo else {}

        widgets = config.get("widgets", {})
        self.system_monitor = SystemMonitorProvider(widgets.get("system_monitor", {}), on_change=self._notify)
        self.storage_network = StorageNetworkProvider(widgets.get("storage_network", {}), on_change=self._notify)
        self.audio = AudioControlProvider(
            widgets.get("audio_control", {}), i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.focus_timer = FocusTimerProvider(
            widgets.get("focus_timer", {}), i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.local_tasks = LocalTasksProvider(
            widgets.get("tasks", {}), self.cache_dir, i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.media = MediaProvider(
            widgets.get("media_player", {}), self.cache_dir, i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.peripherals = PeripheralsProvider(
            widgets.get("peripherals", {}), self.cache_dir, i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.weather = WeatherProvider(widgets.get("weather", {}), self.cache_dir, on_change=self._notify)
        self.hue = HueProvider(widgets.get("philips_hue", {}), i18n, on_change=self._notify, on_toast=self.show_toast)
        self.phone = PhoneAdbProvider(
            widgets.get("phone_adb", {}), self.cache_dir, i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.todoist = TodoistProvider(
            widgets.get("todoist", {}), self.cache_dir, i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.ecoflow = EcoFlowProvider(
            widgets.get("ecoflow", {}), self.cache_dir, i18n, on_change=self._notify, on_toast=self.show_toast
        )
        self.custom_json = CustomJsonProvider(widgets.get("custom_json", {}), on_change=self._notify)

    def use_todoist_backend(self) -> bool:
        widgets = self.config.get("widgets", {})
        t_mode = str(widgets.get("tasks", {}).get("mode", "auto")).lower()
        td_cfg = widgets.get("todoist", {})
        td_ready = bool(td_cfg.get("enabled", False) and str(td_cfg.get("api_token") or "").strip())
        if t_mode == "local":
            return False
        if t_mode == "todoist":
            return True
        return td_ready

    def _notify(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def show_toast(self, message: str, duration: float = 2.6) -> None:
        with self._toast_lock:
            self.toast_message = message
            self.toast_until = time.time() + duration
        self._notify()

    def current_toast(self) -> str:
        with self._toast_lock:
            if self.toast_message and time.time() < self.toast_until:
                return self.toast_message
            self.toast_message = ""
            return ""

    def start(self) -> None:
        if self.demo:
            return
        self.system_monitor.start()
        self.storage_network.start()
        self.audio.start()
        self.focus_timer.start()
        self.media.start()
        self.peripherals.start()
        self.weather.start()
        self.hue.start()
        self.phone.start()
        self.todoist.start()
        self.ecoflow.start()
        self.custom_json.start()

    def stop(self) -> None:
        self.system_monitor.stop()
        self.storage_network.stop()
        self.audio.stop()
        self.focus_timer.stop()
        self.media.stop()
        self.peripherals.stop()
        self.weather.stop()
        self.hue.stop()
        self.phone.stop()
        self.todoist.stop()
        self.ecoflow.stop()
        self.custom_json.stop()

    def set_visible(self, visible: bool) -> None:
        if self.demo:
            return
        photos_open = bool(self.phone.snapshot().get("photos_expanded", False))
        active = visible and not photos_open
        self.system_monitor.set_visible(active)
        self.storage_network.set_visible(active)
        self.audio.set_visible(active)
        self.media.set_visible(active)
        self.hue.set_visible(active)

    def snapshot(self) -> Dict[str, Any]:
        if self.demo:
            return self._demo_state
        tasks_snap = self.todoist.snapshot() if self.use_todoist_backend() else self.local_tasks.snapshot()
        return {
            "monitor": self.system_monitor.snapshot(),
            "storage_network": self.storage_network.snapshot(),
            "audio": self.audio.snapshot(),
            "focus_timer": self.focus_timer.snapshot(),
            "media": self.media.snapshot(),
            "peripherals": self.peripherals.snapshot(),
            "weather": self.weather.snapshot(),
            "hue": self.hue.snapshot(),
            "phone": self.phone.snapshot(),
            "todoist": tasks_snap,
            "ecoflow": self.ecoflow.snapshot(),
            "custom_json": self.custom_json.snapshot(),
        }

    # Interactive dispatchers (work live AND smoothly in --demo mode)
    def toggle_demo_audio_mute(self) -> None:
        if not self.demo:
            self.audio.toggle_mute()
            return
        a = self._demo_state["audio"]
        a["muted"] = not bool(a.get("muted"))
        self._notify()

    def set_demo_audio_volume(self, pct: int) -> None:
        if not self.demo:
            self.audio.set_volume(pct)
            return
        a = self._demo_state["audio"]
        a["volume"] = max(0, min(100, int(pct)))
        a["muted"] = False
        self._notify()

    def cycle_demo_audio_output(self) -> None:
        if not self.demo:
            self.audio.cycle_output()
            return
        a = self._demo_state["audio"]
        devs = a.get("devices") or []
        if len(devs) >= 2:
            cur = next((i for i, d in enumerate(devs) if d.get("id") == a.get("device_id")), 0)
            nxt = devs[(cur + 1) % len(devs)]
            for d in devs:
                d["active"] = d["id"] == nxt["id"]
            a["device_id"] = nxt["id"]
            a["device_name"] = nxt["short_name"]
            self.show_toast(self.i18n.t("audio.toast_switched", name=nxt["short_name"]))
            self._notify()

    def toggle_demo_focus(self, action: str) -> None:
        if not self.demo:
            getattr(self.focus_timer, action)()
            return
        ft = self._demo_state["focus_timer"]
        if action == "toggle":
            ft["running"] = not bool(ft.get("running"))
        elif action == "reset":
            ft["running"] = False
            ft["percent"] = 0.0
            ft["display"] = "25:00" if ft["phase"] == "work" else "05:00"
        elif action == "switch_phase":
            ft["phase"] = "break" if ft["phase"] == "work" else "work"
            ft["running"] = False
            ft["percent"] = 0.0
            ft["display"] = "25:00" if ft["phase"] == "work" else "05:00"
        self._notify()

    def toggle_demo_hue(self, key: str, action: Any) -> None:
        if not self.demo:
            self.hue.command(key, action)
            return
        for target in self._demo_state["hue"]["targets"]:
            if target["key"] == key:
                if action == "toggle":
                    target["on"] = not target["on"]
                elif isinstance(action, int):
                    target["bri"] = max(1, round(action * 254 / 100))
                    target["on"] = True
                break
        self._notify()

    def toggle_demo_media(self, action: str) -> None:
        if not self.demo:
            self.media.command(action)
            return
        if action == "toggle":
            self._demo_state["media"]["playing"] = not self._demo_state["media"]["playing"]
        self._notify()

    def toggle_demo_media_like(self) -> None:
        if not self.demo:
            self.media.toggle_like()
            return
        cur = not bool(self._demo_state["media"].get("like_saved"))
        self._demo_state["media"]["like_saved"] = cur
        self.show_toast(self.i18n.t("media.like_added" if cur else "media.like_removed"))

    def toggle_demo_ecoflow(self, action: str) -> None:
        if not self.demo:
            getattr(self.ecoflow, action)()
            return
        ef = self._demo_state["ecoflow"]
        if action == "cycle_charge_watts":
            steps = [200, 400, 600, 800, 1000, 1500]
            cur = ef["chg_pow_max"]
            ef["chg_pow_max"] = steps[(steps.index(cur) + 1) % len(steps)] if cur in steps else 400
            self.show_toast(self.i18n.t("ecoflow.toast_limit", w=ef["chg_pow_max"]))
        elif action == "toggle_usb":
            ef["usb_open"] = not ef["usb_open"]
        elif action == "toggle_dc12v":
            ef["dc_out_open"] = not ef["dc_out_open"]
        elif action == "toggle_beep":
            ef["beep_on"] = not ef["beep_on"]
        self._notify()

    def toggle_demo_todoist_complete(self, idx: int) -> None:
        if not self.demo:
            if self.use_todoist_backend():
                self.todoist.complete_task(idx)
            else:
                self.local_tasks.complete_task(idx)
            return
        tasks = self._demo_state["todoist"]["tasks"]
        if 0 <= idx < len(tasks):
            t = tasks.pop(idx)
            self.show_toast(self.i18n.t("todoist.toast_done", title=t["content"][:30]))

    def cycle_tasks_project(self) -> None:
        if self.demo:
            return
        if self.use_todoist_backend():
            self.todoist.cycle_project()
        else:
            self.local_tasks.cycle_project()

    def toggle_demo_phone_flag(self, field: str) -> None:
        if not self.demo:
            if field == "auto_clip_sync":
                self.phone.toggle_auto_clip_sync()
            elif field == "photos_expanded":
                self.phone.toggle_photos_expanded()
            elif field == "sms_expanded":
                self.phone.toggle_sms_expanded()
            return
        self._demo_state["phone"][field] = not bool(self._demo_state["phone"].get(field))
        self._notify()

    def upcoming_tasks(self, today: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
        if self.demo:
            return list(self._demo_state["todoist"]["tasks"])
        if self.use_todoist_backend():
            return self.todoist.upcoming_tasks(today)
        return list(self.local_tasks.snapshot().get("tasks", []))
