"""Universal peripherals battery & Windows Bluetooth drawer provider (Tier 1).

Supports:
- Windows Bluetooth / BLE PnP battery level (AirPods, Sony WH-1000, MX Master BT, Keychron BT, etc.)
- Xbox / XInput controllers (via native xinput1_4.dll, zero external dependencies)
- DualSense controllers (DSX UDP or HID)
- Logitech HID++ 2.0 mice & keyboards across Unifying, Logi Bolt, and Lightspeed receivers
- ASUS ROG wireless mice HID
- Optional handheld JSON battery file
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ..config import read_json_safe, write_json_atomic
from ..i18n import I18n
from ..surface import CREATE_NO_WINDOW, IS_WINDOWS, popen_on_default_desktop

logger = logging.getLogger("starthub.providers.peripherals")

# Logitech Unifying, Logi Bolt, and Lightspeed USB receiver PIDs
_LOGITECH_RECEIVER_PIDS = (0xC52B, 0xC548, 0xC539, 0xC547, 0xC54D)


class _XInputBatteryInfo(ctypes.Structure):
    _fields_ = [("BatteryType", ctypes.c_ubyte), ("BatteryLevel", ctypes.c_ubyte)]


def read_xinput_gamepad_battery() -> Optional[Dict[str, Any]]:
    """Query connected Xbox / XInput controller battery via native xinput1_4.dll (zero deps)."""
    if not IS_WINDOWS:
        return None
    xinp = None
    for dll in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            xinp = ctypes.WinDLL(dll)
            if hasattr(xinp, "XInputGetBatteryInformation"):
                break
            xinp = None
        except OSError:
            continue
    if xinp is None:
        return None
    # BATTERY_DEVTYPE_GAMEPAD = 0; BATTERY_TYPE_DISCONNECTED = 0, WIRED = 1
    level_map = {0: 10, 1: 30, 2: 65, 3: 100}
    for idx in range(4):
        info = _XInputBatteryInfo()
        try:
            res = xinp.XInputGetBatteryInformation(idx, 0, ctypes.byref(info))
        except Exception:
            break
        if res == 0 and info.BatteryType != 0:
            wired = info.BatteryType == 1
            batt = 100 if wired else level_map.get(int(info.BatteryLevel), 65)
            return {"name": "Xbox Controller", "battery": batt, "charging": wired, "online": True}
    return None


class PeripheralsProvider:
    """Reads wireless peripherals battery (HID, XInput, Windows BT/BLE PnP) and Bluetooth devices."""

    def __init__(
        self,
        config: Dict[str, Any],
        cache_dir: Path,
        i18n: I18n,
        on_change: Optional[Callable[[], None]] = None,
        on_toast: Optional[Callable[[str], None]] = None,
    ):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._dualsense_cache = self.cache_dir / "dualsense_battery.json"

        self._state: Dict[str, Any] = {
            "mouse": {"name": self.i18n.t("peripherals.mouse"), "battery": None, "charging": False, "online": False},
            "keyboard": {"name": self.i18n.t("peripherals.keyboard"), "battery": None, "online": False},
            "gamepad": {"name": self.i18n.t("peripherals.gamepad"), "battery": None, "charging": False, "online": False},
            "handheld": self._read_handheld_file(),
            "bt_on": True,
            "bt_devices": [],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mouse": dict(self._state["mouse"]),
                "keyboard": dict(self._state["keyboard"]),
                "gamepad": dict(self._state["gamepad"]),
                "handheld": dict(self._state["handheld"]),
                "bt_on": self._state["bt_on"],
                "bt_devices": [dict(d) for d in self._state["bt_devices"]],
            }

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=self._main_loop, name="starthub-peripherals", daemon=True).start()
        if self.config.get("show_keyboard", True) or self.config.get("show_mouse", True):
            threading.Thread(target=self._logitech_loop, name="starthub-logitech", daemon=True).start()
        if self.config.get("show_bluetooth", True) or self.config.get("show_bt_batteries", True):
            threading.Thread(target=self._bt_loop, name="starthub-bluetooth", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _notify(self) -> None:
        if self.on_change:
            self.on_change()

    def _main_loop(self) -> None:
        while not self._stopped.is_set():
            self.poll_mouse_and_gamepad()
            if self.config.get("show_handheld", False):
                self._update_handheld()
            self._notify()
            if self._stopped.wait(12.0):
                break

    def _logitech_loop(self) -> None:
        while not self._stopped.is_set():
            found = self.read_logitech_hidpp_devices(
                default_kb=self.i18n.t("peripherals.keyboard"),
                default_mouse=self.i18n.t("peripherals.mouse"),
            )
            changed = False
            with self._lock:
                if found.get("keyboard") is not None:
                    if self._state["keyboard"] != found["keyboard"]:
                        self._state["keyboard"] = found["keyboard"]
                        changed = True
                if found.get("mouse") is not None and found["mouse"].get("online"):
                    if self._state["mouse"] != found["mouse"]:
                        self._state["mouse"] = found["mouse"]
                        changed = True
            if changed:
                self._notify()
            if self._stopped.wait(45.0):
                break

    def _bt_loop(self) -> None:
        while not self._stopped.is_set():
            self.refresh_bluetooth()
            if self._stopped.wait(30.0):
                break

    def _read_handheld_file(self) -> Dict[str, Any]:
        name = str(self.config.get("handheld_name") or self.i18n.t("peripherals.handheld"))
        file_path = str(self.config.get("handheld_battery_file") or "").strip()
        cached = read_json_safe(file_path, {}) if file_path else {}
        if not isinstance(cached, dict):
            cached = {}
        battery = cached.get("battery")
        if type(battery) is not int or not 0 <= battery <= 100:
            battery = None
        try:
            ts = float(cached.get("ts", cached.get("updated_at", 0)))
        except (TypeError, ValueError):
            ts = 0.0
        status = str(cached.get("status", "Charging" if cached.get("charging") else "Unknown"))
        stale = battery is None or not (0 < ts <= time.time() + 300) or (time.time() - ts > 6 * 3600)
        return {
            "name": name,
            "battery": battery,
            "charging": status == "Charging",
            "status": status,
            "stale": stale,
            "updated_at": ts,
        }

    def _update_handheld(self) -> None:
        val = self._read_handheld_file()
        with self._lock:
            self._state["handheld"] = val

    def poll_mouse_and_gamepad(self) -> None:
        if self.config.get("show_mouse", True):
            self._poll_mouse_hid()
        if self.config.get("show_gamepad", True):
            self._poll_gamepad()

    def _poll_mouse_hid(self) -> None:
        try:
            import hid

            for dev in hid.enumerate(0x0B05):
                if dev.get("product_id") in (0x18E5, 0x18E3) and dev.get("usage_page") == 0xFF01:
                    h = hid.device()
                    h.open_path(dev["path"])
                    try:
                        h.set_nonblocking(False)
                        h.write([0x00, 0x12, 0x07] + [0x00] * 62)
                        resp = h.read(65, timeout_ms=250)
                    finally:
                        h.close()
                    if resp and len(resp) >= 10 and resp[0] == 0x12 and resp[1] == 0x07 and resp[4] <= 4:
                        with self._lock:
                            self._state["mouse"] = {
                                "name": dev.get("product_string") or self.i18n.t("peripherals.mouse"),
                                "battery": int(resp[4]) * 25,
                                "charging": resp[9] > 0,
                                "online": True,
                            }
                        break
        except Exception:
            pass

    def _poll_gamepad(self) -> None:
        updated = False
        if self.config.get("dsx_udp_enabled", False):
            updated = self._poll_dualsense_dsx()
        if not updated:
            updated = self._poll_dualsense_hid()
        if not updated:
            # Universal Xbox / XInput fallback (zero extra dependencies)
            xinfo = read_xinput_gamepad_battery()
            if xinfo is not None:
                with self._lock:
                    self._state["gamepad"] = xinfo
            else:
                with self._lock:
                    if not self._state["gamepad"].get("bt_fallback"):
                        self._state["gamepad"]["online"] = False

    def _poll_dualsense_dsx(self) -> bool:
        try:
            dsx_port = int(self.config.get("dsx_udp_port", 6969))
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            if local_app_data:
                port_file = Path(local_app_data) / "DSX" / "DSX_UDP_PortNumber.txt"
                if port_file.is_file():
                    raw_port = port_file.read_text(encoding="utf-8", errors="ignore").strip()
                    if raw_port.isdigit():
                        dsx_port = int(raw_port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.35)
            try:
                sock.sendto(b'{"instructions": [{"type": 0, "parameters": []}]}', ("127.0.0.1", dsx_port))
                raw_udp, _ = sock.recvfrom(4096)
                data = json.loads(raw_udp.decode("utf-8", errors="ignore"))
                is_conn = bool(data.get("isControllerConnected"))
                batt = int(data.get("BatteryLevel") or 0)
                devs = data.get("Devices") or []
                if isinstance(devs, list) and devs:
                    first = devs[0]
                    if isinstance(first, dict) and int(first.get("BatteryLevel") or 0) > 0:
                        batt = int(first["BatteryLevel"])
                        is_conn = True
                if is_conn and batt > 0:
                    write_json_atomic(self._dualsense_cache, {"battery": batt, "updated_at": time.time()})
                    with self._lock:
                        self._state["gamepad"] = {
                            "name": "DualSense",
                            "battery": batt,
                            "charging": False,
                            "online": True,
                        }
                    return True
            finally:
                sock.close()
        except Exception:
            pass
        return False

    def _poll_dualsense_hid(self) -> bool:
        try:
            import hid

            ds_list = [d for d in hid.enumerate(0x054C) if d.get("product_id") in (0x0CE6, 0x0DF2)]
            if not ds_list:
                return False
            h = hid.device()
            h.open_path(ds_list[0]["path"])
            try:
                h.set_nonblocking(False)
                rep = h.read(78, timeout_ms=180)
            finally:
                h.close()
            cached = read_json_safe(self._dualsense_cache, {"battery": None})
            batt = cached.get("battery")
            charging = False
            if rep:
                idx = 54 if rep[0] == 0x31 and len(rep) > 54 else (53 if len(rep) > 53 else -1)
                if idx > 0:
                    raw_b = rep[idx]
                    lvl = raw_b & 0x0F
                    state = (raw_b >> 4) & 0x0F
                    batt = min(100, lvl * 10 + 5)
                    charging = state in (1, 2)
                    write_json_atomic(self._dualsense_cache, {"battery": batt, "updated_at": time.time()})
            with self._lock:
                self._state["gamepad"] = {
                    "name": "DualSense",
                    "battery": batt,
                    "charging": charging,
                    "online": True,
                }
            return True
        except Exception:
            return False

    @staticmethod
    def read_logitech_hidpp_devices(
        default_kb: str = "Keyboard",
        default_mouse: str = "Mouse",
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Read-only HID++ 2.0 battery query across Logitech Unifying, Bolt, and Lightspeed receivers."""
        found_kb: Optional[Dict[str, Any]] = None
        found_mouse: Optional[Dict[str, Any]] = None
        handles: List[Any] = []
        try:
            import hid

            devices = [
                d
                for pid in _LOGITECH_RECEIVER_PIDS
                for d in hid.enumerate(0x046D, pid)
                if d.get("usage_page") == 0xFF00 and d.get("usage") in (1, 2)
            ]
            for long_dev in (d for d in devices if d["usage"] == 2):
                prefix = long_dev["path"].lower().split(b"&col")[0]
                group = [d for d in devices if d["path"].lower().split(b"&col")[0] == prefix]
                if {d["usage"] for d in group} != {1, 2}:
                    continue
                try:
                    writer = None
                    for d in group:
                        h = hid.device()
                        handles.append(h)
                        h.open_path(d["path"])
                        h.set_nonblocking(True)
                        if d["usage"] == 1:
                            writer = h
                    if writer is None:
                        continue
                    for reader in handles:
                        reader.read(64)

                    def request(slot: int, feature: int, function: int = 0, params=()):
                        cmd = function | 0x0D
                        payload = [0x10, slot, feature, cmd, *params]
                        payload += [0] * (7 - len(payload))
                        writer.write(payload)
                        deadline = time.monotonic() + 0.65
                        while time.monotonic() < deadline:
                            for reader in handles:
                                reply = reader.read(64)
                                if not reply or len(reply) < 7 or reply[1] != slot:
                                    continue
                                if reply[2:4] == [feature, cmd]:
                                    return reply[4:]
                                if reply[2] in (0x8F, 0xFF) and reply[3:5] == [feature, cmd]:
                                    return None
                            time.sleep(0.005)
                        return None

                    def feature_index(slot: int, feature: int) -> int:
                        r = request(slot, 0, params=(feature >> 8, feature & 255, 0))
                        return r[0] if r else 0

                    for slot in range(1, 7):
                        ping = request(slot, 0, 0x10, (0, 0, 0x5A))
                        if not ping or ping[0] < 2 or ping[2] != 0x5A:
                            continue
                        name_idx = feature_index(slot, 0x0005)
                        if not name_idx:
                            continue
                        kind = request(slot, name_idx, 0x20)
                        if not kind or kind[0] not in (0, 3):  # 0=Keyboard, 3=Mouse
                            continue
                        dev_kind = "keyboard" if kind[0] == 0 else "mouse"
                        name_bytes = b""
                        length = request(slot, name_idx)
                        if length:
                            while len(name_bytes) < min(80, length[0]):
                                part = request(slot, name_idx, 0x10, (len(name_bytes),))
                                if not part:
                                    break
                                name_bytes += bytes(part[: length[0] - len(name_bytes)])
                        dev_name = name_bytes.decode("utf-8", errors="replace") or (
                            default_kb if dev_kind == "keyboard" else default_mouse
                        )
                        batt_val: Optional[int] = None
                        for feat, func in ((0x1004, 0x10), (0x1000, 0)):
                            idx = feature_index(slot, feat)
                            if not idx:
                                continue
                            batt = request(slot, idx, func)
                            if batt and 0 < batt[0] <= 100:
                                batt_val = int(batt[0])
                                break
                        entry = {"name": dev_name, "battery": batt_val, "online": True}
                        if dev_kind == "keyboard" and found_kb is None:
                            found_kb = entry
                        elif dev_kind == "mouse" and found_mouse is None:
                            found_mouse = {**entry, "charging": False}
                finally:
                    for h in handles:
                        h.close()
                    handles.clear()
        except Exception:
            pass
        finally:
            for h in handles:
                try:
                    h.close()
                except Exception:
                    pass
        return {"keyboard": found_kb, "mouse": found_mouse}

    @staticmethod
    def read_logitech_keyboard_battery(default_name: str = "Keyboard") -> Dict[str, Any]:
        """Backwards-compatible helper returning keyboard battery dictionary."""
        res = PeripheralsProvider.read_logitech_hidpp_devices(default_kb=default_name)
        return res.get("keyboard") or {"name": default_name, "battery": None, "online": False}

    def refresh_gamepad_now(self) -> None:
        def _worker():
            self._poll_gamepad()
            gp = self.snapshot()["gamepad"]
            if self.on_toast:
                if gp.get("online") and gp.get("battery") is not None:
                    self.on_toast(self.i18n.t("peripherals.gamepad_connected", battery=gp["battery"]))
                else:
                    self.on_toast(self.i18n.t("peripherals.gamepad_offline"))
            self._notify()

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_bt_battery_fallbacks(self, devices: List[Dict[str, Any]]) -> None:
        """Populate mouse/keyboard/gamepad slots from Windows Bluetooth PnP battery when HID dongle is absent."""
        if not self.config.get("show_bt_batteries", True):
            return
        with self._lock:
            for dev in devices:
                if not dev.get("connected") or dev.get("battery") is None:
                    continue
                low = str(dev.get("name") or "").lower()
                batt = int(dev["battery"])
                if any(k in low for k in ("mouse", "mx master", "mx anywhere", "deathadder", "basilisk", "g pro", "viper")):
                    if not self._state["mouse"].get("online"):
                        self._state["mouse"] = {"name": dev["name"], "battery": batt, "charging": False, "online": True}
                elif any(k in low for k in ("keyboard", "keychron", "mx keys", "craft", "nuphy", "anne pro", "kbd")):
                    if not self._state["keyboard"].get("online"):
                        self._state["keyboard"] = {"name": dev["name"], "battery": batt, "online": True}
                elif any(k in low for k in ("xbox", "dualsense", "wireless controller", "gamepad", "8bitdo", "pro controller")):
                    if not self._state["gamepad"].get("online"):
                        self._state["gamepad"] = {
                            "name": dev["name"],
                            "battery": batt,
                            "charging": False,
                            "online": True,
                            "bt_fallback": True,
                        }

    def refresh_bluetooth(self) -> None:
        if not IS_WINDOWS:
            return
        try:
            ps = (
                "$bth = Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match '^BTHENUM\\\\DEV_|^BTHLE\\\\DEV_|^BTHLEDEVICE\\\\' }; "
                "$seen = @{}; "
                "foreach ($d in $bth) { "
                "  $n = $d.FriendlyName; "
                "  if (-not $n -or $n -match 'Generic|Enumerator|Service|Avrcp|Transport|RFCOMM|Protocol') { continue }; "
                "  $p = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName '{83da6326-97a6-4088-9453-a1923f573b29} 15' -ErrorAction SilentlyContinue; "
                "  $c = if ($p) { [bool]$p.Data } else { $false }; "
                "  $bp = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2' -ErrorAction SilentlyContinue; "
                "  $b = if ($bp -and $null -ne $bp.Data) { [int]$bp.Data } else { $null }; "
                "  if (-not $seen.ContainsKey($n)) { "
                "    $seen[$n] = @{ name=$n; connected=$c; battery=$b; id=$d.InstanceId } "
                "  } else { "
                "    if ($c) { $seen[$n].connected = $true }; "
                "    if ($null -ne $b) { $seen[$n].battery = $b } "
                "  } "
                "}; "
                "$seen.Values | ConvertTo-Json -Compress"
            )
            out = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command", ps],
                text=True,
                timeout=6.0,
                creationflags=CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="ignore",
            ).strip()
            if out:
                parsed = json.loads(out)
                if isinstance(parsed, dict):
                    parsed = [parsed]
                parsed.sort(key=lambda x: (not bool(x.get("connected")), x.get("battery") is None, str(x.get("name", "")).lower()))
                with self._lock:
                    self._state["bt_devices"] = parsed
                self._apply_bt_battery_fallbacks(parsed)
                self._notify()
        except Exception:
            pass

    def toggle_bt_radio(self) -> None:
        with self._lock:
            new_state = not self._state.get("bt_on", True)
            self._state["bt_on"] = new_state
        if self.on_toast:
            lbl = self.i18n.t("peripherals.bt_on" if new_state else "peripherals.bt_off")
            self.on_toast(f"Bluetooth: {lbl}")
        self._notify()
        if not IS_WINDOWS:
            return
        target = "On" if new_state else "Off"

        def _worker():
            ps = (
                "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
                "$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]; "
                "Function Await($WinRtTask, $ResultType) { $netTask = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask)); $netTask.Wait(-1) | Out-Null; $netTask.Result }; "
                "[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null; "
                "$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]); "
                f"foreach ($r in $radios) {{ if ($r.Kind -eq 'Bluetooth') {{ Await ($r.SetStateAsync([Windows.Devices.Radios.RadioState]::{target})) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null }} }}"
            )
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps],
                    timeout=5.0,
                    creationflags=CREATE_NO_WINDOW,
                )
            except Exception:
                pass
            self.refresh_bluetooth()

        threading.Thread(target=_worker, daemon=True).start()

    @staticmethod
    def open_bt_settings() -> None:
        if IS_WINDOWS:
            popen_on_default_desktop(["explorer.exe", "ms-settings:bluetooth"])
