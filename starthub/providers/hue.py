"""Universal Smart Lights provider supporting Philips Hue, Home Assistant, and WLED (Tier 2, opt-in).

Backends (configured via `widgets.philips_hue.backend`):
- `hue` (default): Local LAN HTTPS Philips Hue Bridge + 1-click discovery & Link-button pairing.
- `home_assistant`: Local Home Assistant REST API (`light.*` and `switch.*` — covers Xiaomi/Yeelight,
  Tuya/Smart Life, Aqara, IKEA Tradfri, TP-Link Tapo/Kasa, Govee, Nanoleaf, LIFX, Zigbee2MQTT, Matter).
- `wled`: Local Wi-Fi WLED LED strips (`http://<LAN_IP>/json/state`, zero API keys required).
"""
from __future__ import annotations

import ipaddress
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit
import warnings

import requests

from ..i18n import I18n

logger = logging.getLogger("starthub.providers.hue")


def is_valid_lan_ip(host: str) -> bool:
    """Allow only private/link-local IPv4 addresses for local Hue Bridge / WLED communication."""
    try:
        addr = ipaddress.IPv4Address(str(host or "").strip())
        return addr.is_private or addr.is_link_local
    except ValueError:
        return False


def is_valid_ha_url(url: str) -> bool:
    """Validate a Home Assistant base URL (http/https with non-empty hostname)."""
    raw = str(url or "").strip()
    if not raw:
        return False
    parsed = urlsplit(raw)
    return parsed.scheme in ("http", "https") and bool(parsed.hostname)


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


def fetch_ha_catalog(
    ha_url: str,
    ha_token: str,
    *,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """Fetch available `light.*` and `switch.*` entities from Home Assistant REST API."""
    base = str(ha_url or "").strip().rstrip("/")
    token = str(ha_token or "").strip()
    if not is_valid_ha_url(base) or not token:
        return []
    targets: List[Dict[str, Any]] = []
    try:
        http = session or requests.Session()
        if session is None:
            http.trust_env = False
        try:
            resp = http.get(
                f"{base}/api/states",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=(2.5, 4.0),
            )
            resp.raise_for_status()
            rows = resp.json()
        finally:
            if session is None:
                http.close()
        if not isinstance(rows, list):
            return []
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            eid = str(entry.get("entity_id") or "").strip()
            if not (eid.startswith("light.") or eid.startswith("switch.")):
                continue
            domain = eid.split(".", 1)[0]
            attrs = entry.get("attributes") if isinstance(entry.get("attributes"), dict) else {}
            label = str(attrs.get("friendly_name") or eid.split(".", 1)[1].replace("_", " ").title())
            targets.append(
                {
                    "id": eid,
                    "kind": f"ha_{domain}",
                    "label": label,
                    "icon": "bulb" if domain == "light" else "monitor",
                    "dimmer": domain == "light",
                }
            )
        targets.sort(key=lambda t: (0 if t["kind"] == "ha_light" else 1, t["label"].lower()))
    except Exception as exc:
        logger.debug("Home Assistant catalog fetch failed: %s", type(exc).__name__)
    return targets


class HueProvider:
    """Visibility-gated Smart Lights controller (Philips Hue / Home Assistant / WLED)."""

    def __init__(
        self,
        config: Dict[str, Any],
        i18n: I18n,
        on_change: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
        session: Optional[requests.Session] = None,
    ):
        self.config = config
        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self._injected_session = session
        self.interval = max(2.0, float(config.get("poll_interval_sec", 8.0)))
        self.backend = str(config.get("backend") or "hue").strip().lower()
        if self.backend not in ("hue", "home_assistant", "wled"):
            self.backend = "hue"

        self._lock = threading.Lock()
        self._visible = threading.Event()
        self._stopped = threading.Event()
        self._commands: queue.Queue[tuple] = queue.Queue(maxsize=8)
        self._due = 0.0
        self._selected_dimmer_key: Optional[str] = None
        self._state: Dict[str, Any] = {
            "ready": False,
            "backend": self.backend,
            "message": self.i18n.t("hue.need_key"),
            "dimmer_key": None,
            "targets": [],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "ready": self._state["ready"],
                "backend": self._state.get("backend", self.backend),
                "message": self._state["message"],
                "dimmer_key": self._state.get("dimmer_key"),
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
        threading.Thread(target=self._loop, name="starthub-smart-lights", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _publish(self, value: Dict[str, Any]) -> None:
        value.setdefault("backend", self.backend)
        value.setdefault("dimmer_key", self._selected_dimmer_key)
        with self._lock:
            changed = self._state != value
            self._state = value
        if changed and self.on_change:
            self.on_change()

    # ------------------------------------------------------------------
    # Backend 1: Philips Hue Bridge (Local LAN HTTPS)
    # ------------------------------------------------------------------

    def _configured_bridge(self) -> Optional[tuple[str, str]]:
        host = str(self.config.get("bridge_ip") or "").strip()
        key = str(self.config.get("app_key") or "").strip()
        if not is_valid_lan_ip(host) or not key:
            return None
        return host, key

    def _hue_request(self, host: str, key: str, method: str, path: str, payload=None):
        http = self._injected_session or requests.Session()
        if self._injected_session is None:
            http.trust_env = False
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                response = http.request(
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
        finally:
            if self._injected_session is None:
                http.close()

    def _poll_hue(self) -> Dict[str, Any]:
        bridge = self._configured_bridge()
        if not bridge:
            self._publish({"ready": False, "message": self.i18n.t("hue.need_key"), "targets": []})
            return self.snapshot()

        host, key = bridge
        raw_targets = self.config.get("targets") or []
        results: List[Dict[str, Any]] = []
        try:
            for idx, item_cfg in enumerate(raw_targets[:4]):
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
                    item = self._hue_request(host, key, "GET", f"/{kind}/{ident}")
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

    # ------------------------------------------------------------------
    # Backend 2: Home Assistant REST API (any smart-home brand!)
    # ------------------------------------------------------------------

    def _configured_ha(self) -> Optional[tuple[str, str]]:
        url = str(self.config.get("ha_url") or "").strip().rstrip("/")
        token = str(self.config.get("ha_token") or self.config.get("app_key") or "").strip()
        if not is_valid_ha_url(url) or not token:
            return None
        return url, token

    def _ha_request(self, base: str, token: str, method: str, path: str, payload=None):
        http = self._injected_session or requests.Session()
        if self._injected_session is None:
            http.trust_env = False
        try:
            resp = http.request(
                method,
                f"{base}{path}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
                timeout=(2.0, 3.0),
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        finally:
            if self._injected_session is None:
                http.close()

    def _poll_home_assistant(self) -> Dict[str, Any]:
        ha = self._configured_ha()
        if not ha:
            self._publish({"ready": False, "message": "Set Home Assistant URL + Token in Settings", "targets": []})
            return self.snapshot()
        base, token = ha
        raw_targets = self.config.get("targets") or []
        results: List[Dict[str, Any]] = []
        for idx, item_cfg in enumerate(raw_targets[:4]):
            if not isinstance(item_cfg, dict):
                continue
            eid = str(item_cfg.get("id") or "").strip()
            if "." not in eid:
                continue
            domain = eid.split(".", 1)[0]
            if domain not in ("light", "switch", "input_boolean", "fan"):
                continue
            target_key = f"ha:{eid}:{idx}"
            label = str(item_cfg.get("label") or eid.split(".", 1)[1].replace("_", " ").title())
            icon = str(item_cfg.get("icon") or ("bulb" if domain == "light" else "monitor"))
            dimmer = bool(item_cfg.get("dimmer", domain == "light" and idx == 0))
            try:
                data = self._ha_request(base, token, "GET", f"/api/states/{eid}")
                st = str(data.get("state") or "").lower()
                attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
                reachable = st not in ("unavailable", "unknown", "")
                is_on = st == "on"
                raw_bri = attrs.get("brightness")
                if isinstance(raw_bri, (int, float)):
                    bri = max(0, min(254, round(float(raw_bri) * 254.0 / 255.0)))
                else:
                    bri = 254 if is_on else 0
                results.append(
                    {
                        "key": target_key,
                        "kind": f"ha_{domain}",
                        "id": eid,
                        "label": label,
                        "icon": icon,
                        "dimmer": dimmer,
                        "on": is_on,
                        "bri": bri,
                        "reachable": reachable,
                    }
                )
            except Exception:
                results.append(
                    {
                        "key": target_key,
                        "kind": f"ha_{domain}",
                        "id": eid,
                        "label": label,
                        "icon": icon,
                        "dimmer": dimmer,
                        "on": False,
                        "bri": 0,
                        "reachable": False,
                    }
                )
        msg = "" if results else self.i18n.t("hue.no_targets")
        self._publish({"ready": bool(results), "message": msg, "targets": results})
        return self.snapshot()

    # ------------------------------------------------------------------
    # Backend 3: WLED Local Wi-Fi LED Strips (Zero Tokens!)
    # ------------------------------------------------------------------

    def _wled_request(self, host: str, method: str, payload=None):
        http = self._injected_session or requests.Session()
        if self._injected_session is None:
            http.trust_env = False
        try:
            resp = http.request(method, f"http://{host}/json/state", json=payload, timeout=(1.5, 2.5))
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        finally:
            if self._injected_session is None:
                http.close()

    def _poll_wled(self) -> Dict[str, Any]:
        default_ip = str(self.config.get("bridge_ip") or "").strip()
        raw_targets = list(self.config.get("targets") or [])
        if not raw_targets and is_valid_lan_ip(default_ip):
            raw_targets = [{"id": default_ip, "kind": "wled", "label": "WLED Strip", "icon": "monitor", "dimmer": True}]
        results: List[Dict[str, Any]] = []
        for idx, item_cfg in enumerate(raw_targets[:4]):
            if not isinstance(item_cfg, dict):
                continue
            host = str(item_cfg.get("id") or "").strip()
            if not is_valid_lan_ip(host):
                host = default_ip
            if not is_valid_lan_ip(host):
                continue
            target_key = f"wled:{host}:{idx}"
            label = str(item_cfg.get("label") or f"WLED {idx + 1}")
            icon = str(item_cfg.get("icon") or "monitor")
            dimmer = bool(item_cfg.get("dimmer", idx == 0))
            try:
                data = self._wled_request(host, "GET")
                is_on = bool(data.get("on", False))
                raw_bri = int(data.get("bri", 128) or 0)
                bri = max(0, min(254, round(raw_bri * 254.0 / 255.0)))
                results.append(
                    {
                        "key": target_key,
                        "kind": "wled",
                        "id": host,
                        "label": label,
                        "icon": icon,
                        "dimmer": dimmer,
                        "on": is_on,
                        "bri": bri,
                        "reachable": True,
                    }
                )
            except Exception:
                results.append(
                    {
                        "key": target_key,
                        "kind": "wled",
                        "id": host,
                        "label": label,
                        "icon": icon,
                        "dimmer": dimmer,
                        "on": False,
                        "bri": 0,
                        "reachable": False,
                    }
                )
        msg = "" if results else "Set WLED LAN IP in Settings"
        self._publish({"ready": bool(results), "message": msg, "targets": results})
        return self.snapshot()

    # ------------------------------------------------------------------
    # Unified Poll & Command Dispatch
    # ------------------------------------------------------------------

    def poll_once(self) -> Dict[str, Any]:
        if self.backend == "home_assistant":
            return self._poll_home_assistant()
        if self.backend == "wled":
            return self._poll_wled()
        return self._poll_hue()

    def command(self, target_key: str, action: Any) -> None:
        if action == "select_dimmer":
            self._selected_dimmer_key = target_key
            with self._lock:
                self._state["dimmer_key"] = target_key
            if self.on_change:
                self.on_change()
            return
        is_pct = type(action) is int and 1 <= action <= 100
        if not self._visible.is_set() or not (is_pct or action in ("toggle", "up", "down")):
            return
        try:
            self._commands.put_nowait((target_key, action))
        except queue.Full:
            pass

    def _send_command(self, target_key: str, action: Any) -> None:
        self.poll_once()
        target = next((t for t in self.snapshot()["targets"] if t["key"] == target_key), None)
        if not target or not target.get("reachable", True):
            return

        if self.backend == "home_assistant":
            ha = self._configured_ha()
            if not ha:
                return
            base, token = ha
            eid = str(target["id"])
            domain = eid.split(".", 1)[0]
            if type(action) is int and 1 <= action <= 100 and domain == "light":
                bri_255 = max(1, min(255, round(action * 255 / 100)))
                self._ha_request(base, token, "POST", "/api/services/light/turn_on", {"entity_id": eid, "brightness": bri_255})
            elif action == "toggle":
                self._ha_request(base, token, "POST", f"/api/services/{domain}/toggle", {"entity_id": eid})
            elif action in ("up", "down") and domain == "light":
                delta = 51 if action == "up" else -51
                bri_255 = max(1, min(255, round(target["bri"] * 255 / 254) + delta))
                self._ha_request(base, token, "POST", "/api/services/light/turn_on", {"entity_id": eid, "brightness": bri_255})
            self.poll_once()
            return

        if self.backend == "wled":
            host = str(target["id"])
            if not is_valid_lan_ip(host):
                return
            if type(action) is int and 1 <= action <= 100:
                payload = {"on": True, "bri": max(1, min(255, round(action * 255 / 100)))}
            elif action == "toggle":
                payload = {"on": not target["on"]}
            elif action in ("up", "down"):
                delta = 51 if action == "up" else -51
                payload = {"on": True, "bri": max(1, min(255, round(target["bri"] * 255 / 254) + delta))}
            else:
                return
            self._wled_request(host, "POST", payload)
            self.poll_once()
            return

        # Default: Philips Hue Bridge
        bridge = self._configured_bridge()
        if not bridge:
            return
        host, key = bridge
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
        self._hue_request(host, key, "PUT", f"/{target['kind']}/{target['id']}/{endpoint}", payload)
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
                logger.debug("Smart Lights loop error")
