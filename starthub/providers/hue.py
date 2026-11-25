"""Philips Hue Bridge local LAN HTTPS provider + 1-click discovery & pairing (Tier 2, opt-in)."""
from __future__ import annotations

import ipaddress
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import warnings

import requests

from ..i18n import I18n

logger = logging.getLogger("starthub.providers.hue")


def is_valid_lan_ip(host: str) -> bool:
    """Allow only private/link-local IPv4 addresses for local Hue Bridge communication."""
    try:
        addr = ipaddress.IPv4Address(str(host or "").strip())
        return addr.is_private or addr.is_link_local
    except ValueError:
        return False


def discover_hue_bridges(timeout: float = 4.0) -> List[str]:
    """Discover local Philips Hue Bridge LAN IPs via Signify's official N-UPnP endpoint."""
    found: List[str] = []
    try:
        resp = requests.get("https://discovery.meethue.com/", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        ip = str(entry.get("internalipaddress") or "").strip()
                        if is_valid_lan_ip(ip) and ip not in found:
                            found.append(ip)
    except Exception as exc:
        logger.debug("Hue bridge discovery failed: %s", type(exc).__name__)
    return found


def pair_hue_bridge(bridge_ip: str, device_type: str = "starthub#windows") -> Tuple[bool, str]:
    """Press the physical Link button on the Hue Bridge, then call this to receive a local app_key."""
    host = str(bridge_ip or "").strip()
    if not is_valid_lan_ip(host):
        return False, "Invalid private LAN IP address"
    try:
        with requests.Session() as session:
            session.trust_env = False
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                resp = session.post(
                    f"https://{host}/api",
                    json={"devicetype": device_type},
                    timeout=(2.5, 4.0),
                    verify=False,
                )
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, list) and payload:
                first = payload[0]
                if isinstance(first, dict):
                    if "success" in first and isinstance(first["success"], dict):
                        key = str(first["success"].get("username") or "").strip()
                        if key:
                            return True, key
                    if "error" in first and isinstance(first["error"], dict):
                        return False, str(first["error"].get("description") or "Bridge rejected pairing")
            return False, "Unexpected response from Hue Bridge"
    except Exception as exc:
        return False, f"Connection error: {type(exc).__name__}"


def fetch_hue_catalog(bridge_ip: str, app_key: str) -> List[Dict[str, Any]]:
    """Fetch available rooms/zones (groups) and individual lights from a paired Hue Bridge."""
    host = str(bridge_ip or "").strip()
    key = str(app_key or "").strip()
    if not is_valid_lan_ip(host) or not key:
        return []
    targets: List[Dict[str, Any]] = []
    try:
        with requests.Session() as session:
            session.trust_env = False
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                for kind, icon in (("groups", "bulb"), ("lights", "monitor")):
                    r = session.get(f"https://{host}/api/{key}/{kind}", timeout=(2.0, 3.0), verify=False)
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    if not isinstance(data, dict):
                        continue
                    for ident, info in sorted(data.items(), key=lambda p: int(p[0]) if str(p[0]).isdigit() else 999):
                        if not isinstance(info, dict) or not str(ident).isdigit() or str(ident) == "0":
                            continue
                        targets.append(
                            {
                                "id": str(ident),
                                "kind": kind,
                                "label": str(info.get("name") or f"{kind.title()} {ident}"),
                                "icon": icon,
                                "dimmer": kind == "groups",
                            }
                        )
    except Exception as exc:
        logger.debug("Hue catalog fetch failed: %s", type(exc).__name__)
    return targets


class HueProvider:
    """Visibility-gated Philips Hue v1 local HTTPS control for configured rooms and lights."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: I18n,
        on_change: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self.interval = max(2.0, float(config.get("poll_interval_sec", 8.0)))

        self._lock = threading.Lock()
        self._visible = threading.Event()
        self._stopped = threading.Event()
        self._commands: queue.Queue[tuple] = queue.Queue(maxsize=8)
        self._due = 0.0
        self._state: Dict[str, Any] = {
            "ready": False,
            "message": self.i18n.t("hue.need_key"),
            "targets": [],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ready": self._state["ready"],
                "message": self._state["message"],
                "targets": [dict(t) for t in self._state["targets"]],
            }

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._visible.set()
            self._due = 0.0
        else:
            self._visible.clear()

    def start(self) -> None:
        if not self.config.get("enabled", False):
            return
        threading.Thread(target=self._loop, name="starthub-hue", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _publish(self, value: Dict[str, Any]) -> None:
        with self._lock:
            changed = self._state != value
            self._state = value
        if changed and self.on_change:
            self.on_change()

    def _configured_bridge(self) -> Optional[tuple[str, str]]:
        host = str(self.config.get("bridge_ip") or "").strip()
        key = str(self.config.get("app_key") or "").strip()
        if not is_valid_lan_ip(host) or not key:
            return None
        return host, key

    def _request(self, host: str, key: str, method: str, path: str, payload=None):
        with requests.Session() as session:
            session.trust_env = False
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                response = session.request(
                    method,
                    f"https://{host}/api/{key}{path}",
                    json=payload,
                    timeout=(1.5, 2.0),
                    verify=False,
                )
            response.raise_for_status()
            value = response.json()
            if isinstance(value, list) and any("error" in item for item in value if isinstance(item, dict)):
                raise ValueError("Hue bridge rejected request")
            return value

    def poll_once(self) -> Dict[str, Any]:
        bridge = self._configured_bridge()
        if not bridge:
            self._publish({"ready": False, "message": self.i18n.t("hue.need_key"), "targets": []})
            return self.snapshot()

        host, key = bridge
        raw_targets = self.config.get("targets") or []
        results: List[Dict[str, Any]] = []
        try:
            for idx, item_cfg in enumerate(raw_targets):
                if not isinstance(item_cfg, dict):
                    continue
                kind = str(item_cfg.get("kind", "")).strip()
                ident = str(item_cfg.get("id", "")).strip()
                if kind not in ("groups", "lights") or not ident.isdigit() or ident == "0":
                    continue
                target_key = f"{kind}:{ident}:{idx}"
                label = str(item_cfg.get("label") or f"{kind.title()} {ident}")
                icon = str(item_cfg.get("icon") or ("bulb" if kind == "groups" else "monitor"))
                dimmer = bool(item_cfg.get("dimmer", idx == 0))
                try:
                    item = self._request(host, key, "GET", f"/{kind}/{ident}")
                except Exception:
                    results.append(
                        {
                            "key": target_key,
                            "kind": kind,
                            "id": ident,
                            "label": label,
                            "icon": icon,
                            "dimmer": dimmer,
                            "on": False,
                            "bri": 0,
                            "reachable": False,
                        }
                    )
                    continue
                state = item.get("action", {}) if kind == "groups" else item.get("state", {})
                is_on = (
                    item.get("state", {}).get("any_on", state.get("on", False))
                    if kind == "groups"
                    else state.get("on", False)
                )
                results.append(
                    {
                        "key": target_key,
                        "kind": kind,
                        "id": ident,
                        "label": label,
                        "icon": icon,
                        "dimmer": dimmer,
                        "on": bool(is_on),
                        "bri": int(state.get("bri", 0)),
                        "reachable": bool(state.get("reachable", True)),
                    }
                )
            msg = "" if results else self.i18n.t("hue.no_targets")
            self._publish({"ready": bool(results), "message": msg, "targets": results})
        except Exception:
            self._publish({"ready": False, "message": self.i18n.t("hue.unreachable_bridge"), "targets": []})
        return self.snapshot()

    def command(self, target_key: str, action: Any) -> None:
        is_pct = type(action) is int and 1 <= action <= 100
        if not self._visible.is_set() or not (is_pct or action in ("toggle", "up", "down")):
            return
        try:
            self._commands.put_nowait((target_key, action))
        except queue.Full:
            pass

    def _send_command(self, target_key: str, action: Any) -> None:
        bridge = self._configured_bridge()
        if not bridge:
            return
        host, key = bridge
        self.poll_once()
        target = next((t for t in self.snapshot()["targets"] if t["key"] == target_key), None)
        if not target or not target.get("reachable", True):
            return
        if type(action) is int and 1 <= action <= 100:
            payload = {"bri": max(1, round(action * 254 / 100)), "on": True}
        elif action == "toggle":
            payload = {"on": not target["on"]}
        elif action in ("up", "down"):
            delta = 51 if action == "up" else -51
            payload = {"bri": max(1, min(254, target["bri"] + delta))}
        else:
            return
        endpoint = "action" if target["kind"] == "groups" else "state"
        self._request(host, key, "PUT", f"/{target['kind']}/{target['id']}/{endpoint}", payload)
        self.poll_once()

    def _loop(self) -> None:
        while not self._stopped.wait(0.25):
            if not self._visible.is_set():
                while not self._commands.empty():
                    self._commands.get_nowait()
                continue
            try:
                while not self._commands.empty():
                    self._send_command(*self._commands.get_nowait())
                now = time.monotonic()
                if now >= self._due:
                    self._due = now + self.interval
                    self.poll_once()
            except Exception:
                logger.debug("Hue loop error")
