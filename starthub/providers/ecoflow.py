"""EcoFlow DELTA 3 / DELTA 2 Cloud MQTT (TLS 8883 + Protobuf) and state-file provider (Tier 2, opt-in).

Fixes vs legacy personal scripts:
- Bounded log rotation via RotatingFileHandler (2 MB max, 2 backups).
- Atomic state/command writes with Windows retry + guaranteed temp cleanup (zero stray tmp*.json files).
- Zero hardcoded credentials, device serial numbers, or personal station names.
"""
from __future__ import annotations

import base64
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import random
import ssl
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

import requests

from ..config import read_json_safe, write_json_atomic
from ..i18n import I18n

logger = logging.getLogger("starthub.providers.ecoflow")

BMS_HEARTBEAT_COMMANDS = {
    (3, 1), (3, 2), (3, 30), (3, 50),
    (32, 1), (32, 3), (32, 50), (32, 51), (32, 52),
    (254, 24), (254, 25), (254, 26), (254, 27), (254, 28),
}


def attach_ecoflow_rotating_log(log_dir: Path, max_bytes: int = 2 * 1024 * 1024, backup_count: int = 2) -> None:
    """Attach a bounded 2 MB RotatingFileHandler once to the EcoFlow logger."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "ecoflow.log"
    for h in logger.handlers:
        if isinstance(h, RotatingFileHandler) and Path(getattr(h, "baseFilename", "")) == log_path:
            return
    handler = RotatingFileHandler(str(log_path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)


class Delta3Decoder:
    """Decoder for EcoFlow DELTA 3 series Protobuf telemetry (with JSON fallback for DELTA 2 / others)."""

    @staticmethod
    def decode_payload(raw_data: bytes) -> Dict[str, Any]:
        try:
            text = raw_data.decode("utf-8")
            stripped = text.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                data = json.loads(stripped)
                if isinstance(data, dict):
                    params = data.get("params") or (data.get("data") or {}).get("params")
                    return params if isinstance(params, dict) and params else data
        except Exception:
            pass
        try:
            return Delta3Decoder._decode_protobuf(raw_data)
        except Exception as exc:
            logger.debug("Protobuf decode failed: %s", exc)
            return {}

    @staticmethod
    def _decode_protobuf(raw_data: bytes) -> Dict[str, Any]:
        from google.protobuf.json_format import MessageToDict
        from . import ef_delta3_pb2 as pb

        try:
            raw_data = base64.b64decode(raw_data, validate=True)
        except Exception:
            pass

        header_msg = pb.Delta3HeaderMessage()
        header_msg.ParseFromString(raw_data)
        if not header_msg.header:
            return {}

        merged: Dict[str, Any] = {}
        for header in header_msg.header:
            pdata = getattr(header, "pdata", b"")
            if not pdata:
                continue
            enc_type = getattr(header, "enc_type", 0)
            src = getattr(header, "src", 0)
            seq = getattr(header, "seq", 0)
            cmd_func = getattr(header, "cmd_func", 0)
            cmd_id = getattr(header, "cmd_id", 0)
            if enc_type == 1 and src != 32 and seq != 0:
                pdata = bytes((b ^ seq) & 0xFF for b in pdata)
            decoded = Delta3Decoder._decode_by_cmd(pb, MessageToDict, cmd_func, cmd_id, pdata)
            if decoded:
                if cmd_func == 254:
                    decoded["_hdr_src"] = src
                    decoded["_hdr_ver"] = getattr(header, "version", 3) or 3
                merged.update(decoded)
        return merged

    @staticmethod
    def _decode_by_cmd(pb, to_dict, cmd_func: int, cmd_id: int, pdata: bytes) -> Dict[str, Any]:
        try:
            mapping = {
                (254, 21): pb.Delta3DisplayPropertyUpload,
                (254, 22): pb.Delta3RuntimePropertyUpload,
                (254, 17): pb.Delta3SetCommand,
                (254, 18): pb.Delta3SetReply,
                (32, 2): pb.Delta3CMSHeartBeatReport,
            }
            cls = mapping.get((cmd_func, cmd_id))
            if cls is None and (cmd_func, cmd_id) in BMS_HEARTBEAT_COMMANDS:
                cls = pb.Delta3BMSHeartBeatReport
            if cls is not None:
                msg = cls()
                msg.ParseFromString(pdata)
                return to_dict(msg, preserving_proto_field_name=True)
            for fallback_cls, keys in (
                (pb.Delta3DisplayPropertyUpload, ("pow_in_sum_w", "pow_out_sum_w", "bms_batt_soc")),
                (pb.Delta3BMSHeartBeatReport, ("soc", "cycles", "act_soc")),
            ):
                try:
                    msg = fallback_cls()
                    msg.ParseFromString(pdata)
                    res = to_dict(msg, preserving_proto_field_name=True)
                    if any(k in res for k in keys):
                        return res
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("EcoFlow cmd (%s, %s) decode error: %s", cmd_func, cmd_id, exc)
        return {}


class EcoFlowMqttClient:
    """Self-healing EcoFlow Cloud MQTT TLS-8883 client with stale-session watchdog."""

    STALE_TELEMETRY_SEC = 75.0

    def __init__(
        self,
        *,
        email: str,
        password: str,
        device_sn: str = "",
        device_name: str = "EcoFlow Station",
        region: str = "europe",
        on_state_update: Callable[[Dict[str, Any]], None],
    ):
        self.email = email.strip()
        self.password = password.strip()
        self.device_sn = device_sn.strip()
        self.region = region.strip().lower()
        self.api_domain = "api.ecoflow.com" if self.region in ("us", "global") else "api-e.ecoflow.com"
        self.on_state_update = on_state_update

        self.token = ""
        self.user_id = ""
        self.mqtt_url = ""
        self.mqtt_port = 8883
        self.mqtt_username = ""
        self.mqtt_password = ""
        self.client_id = ""

        self.mqtt_client = None
        self.is_connected = False
        self.is_running = False
        self._connected_mono = 0.0
        self._last_rx_mono = 0.0
        self._stale_reconnects = 0
        self._connect_failures = 0
        self._prev_grid: Optional[bool] = None

        self.current_state: Dict[str, Any] = {
            "soc": 0,
            "act_soc": 0.0,
            "in_watts": 0.0,
            "ac_in_watts": 0.0,
            "out_watts": 0.0,
            "usb_watts": 0.0,
            "dsg_time": 0,
            "chg_time": 0,
            "est_dsg_min": 0,
            "is_grid": True,
            "ac_in_vol": 0.0,
            "chg_pow_max": 200,
            "chg_pow_max_reported": False,
            "usb_open": False,
            "dc_out_open": False,
            "beep_on": True,
            "remain_cap": 0,
            "full_cap": 0,
            "remain_wh": 0,
            "full_wh": 2048,
            "device_name": device_name,
            "device_sn": self.device_sn,
            "last_update": 0.0,
            "stale": True,
        }

    def login(self) -> bool:
        if not self.email or not self.password:
            return False
        headers = {"lang": "en_US", "Content-Type": "application/json"}
        payload = {
            "email": self.email,
            "password": base64.b64encode(self.password.encode("utf-8")).decode("utf-8"),
            "scene": "IOT_APP",
            "userType": "ECOFLOW",
        }
        fallback = "api.ecoflow.com" if self.api_domain != "api.ecoflow.com" else "api-e.ecoflow.com"
        token_ok = False
        for dom in (self.api_domain, fallback):
            try:
                res = requests.post(f"https://{dom}/auth/login", headers=headers, json=payload, timeout=12)
                if res.status_code == 200:
                    j = res.json()
                    if j.get("code") == "0" or "token" in (j.get("data") or {}):
                        self.token = j["data"]["token"]
                        self.user_id = str((j["data"].get("user") or {}).get("userId", ""))
                        self.api_domain = dom
                        token_ok = True
                        break
            except Exception as exc:
                logger.warning("EcoFlow auth error on %s: %s", dom, type(exc).__name__)
        if not token_ok:
            return False

        try:
            cert_res = requests.get(
                f"https://{self.api_domain}/iot-auth/app/certification",
                headers={"lang": "en_US", "Authorization": f"Bearer {self.token}"},
                timeout=12,
            )
            if cert_res.status_code != 200:
                return False
            cdata = cert_res.json().get("data") or {}
            self.mqtt_url = str(cdata.get("url") or "")
            self.mqtt_port = int(cdata.get("port", 8883))
            self.mqtt_username = str(cdata.get("certificateAccount") or "")
            self.mqtt_password = str(cdata.get("certificatePassword") or "")
            self.client_id = f"ANDROID_{uuid.uuid4().hex.upper()}_{self.user_id}"
            if not self.mqtt_url:
                return False
        except Exception as exc:
            logger.warning("EcoFlow MQTT certification failed: %s", type(exc).__name__)
            return False

        if not self.device_sn:
            self._discover_device_sn()
        return bool(self.device_sn)

    def _discover_device_sn(self) -> None:
        auth_headers = {"lang": "en_US", "Authorization": f"Bearer {self.token}"}
        for ep in ("/app/user/device/list", "/iot-service/open/api/device/list"):
            try:
                r = requests.get(f"https://{self.api_domain}{ep}", headers=auth_headers, timeout=10)
                if r.status_code == 200:
                    items = r.json().get("data", [])
                    if isinstance(items, list) and items:
                        first = items[0]
                        self.device_sn = str(first.get("sn") or first.get("deviceSn") or "")
                        dev_name = str(first.get("deviceName") or first.get("productName") or "EcoFlow Station")
                        self.current_state["device_name"] = dev_name
                        self.current_state["device_sn"] = self.device_sn
                        return
            except Exception:
                continue

    def start(self) -> None:
        self.is_running = True
        threading.Thread(target=self._run_loop, name="starthub-ecoflow-mqtt", daemon=True).start()

    def stop(self) -> None:
        self.is_running = False
        self._teardown_mqtt()

    def _is_telemetry_stale(self) -> bool:
        if not self.is_connected:
            return False
        baseline = max(self._connected_mono, self._last_rx_mono)
        return baseline > 0 and (time.monotonic() - baseline) >= self.STALE_TELEMETRY_SEC

    def _teardown_mqtt(self) -> None:
        old = self.mqtt_client
        self.mqtt_client = None
        if old is None:
            return
        for attr in ("on_connect", "on_disconnect", "on_message"):
            try:
                setattr(old, attr, None)
            except Exception:
                pass
        try:
            old.disconnect()
        except Exception:
            pass
        try:
            old.loop_stop()
        except Exception:
            pass

    def _connect_mqtt(self) -> None:
        import paho.mqtt.client as mqtt

        self._teardown_mqtt()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id, clean_session=True)
        client.username_pw_set(self.mqtt_username, self.mqtt_password)
        client.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_REQUIRED)
        client.tls_insecure_set(False)
        client.reconnect_delay_set(min_delay=30, max_delay=120)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.connect(self.mqtt_url, self.mqtt_port, keepalive=30)
        client.loop_start()
        self.mqtt_client = client

    def _run_loop(self) -> None:
        while self.is_running:
            if not self.is_connected:
                if not self.token or not self.mqtt_url:
                    if not self.login():
                        time.sleep(15)
                        continue
                try:
                    self._connect_mqtt()
                except Exception as exc:
                    logger.warning("EcoFlow MQTT connect error: %s", type(exc).__name__)
                    self.is_connected = False
                    self._connect_failures += 1
                    if self._connect_failures >= 3:
                        self.token = ""
                        self.mqtt_url = ""
                        self._connect_failures = 0
                    time.sleep(10)
                    continue
                for _ in range(40):
                    if self.is_connected or not self.is_running:
                        break
                    time.sleep(0.5)
                if not self.is_connected:
                    self._teardown_mqtt()
                    self._connect_failures += 1
                    if self._connect_failures >= 3:
                        self.token = ""
                        self.mqtt_url = ""
                        self._connect_failures = 0
                    time.sleep(15)
                    continue

            for _ in range(60):
                if not self.is_running or not self.is_connected:
                    break
                if self._is_telemetry_stale():
                    logger.warning("EcoFlow MQTT telemetry stale; reconnecting")
                    self.is_connected = False
                    self._teardown_mqtt()
                    self._stale_reconnects += 1
                    if self._stale_reconnects >= 2:
                        self.token = ""
                        self.mqtt_url = ""
                        self._stale_reconnects = 0
                    break
                time.sleep(0.5)
            if self.is_connected:
                self._send_snapshot_request()

    def _on_connect(self, client, userdata, flags, rc, properties=None) -> None:
        if rc == 0:
            self.is_connected = True
            self._connected_mono = time.monotonic()
            self._connect_failures = 0
            topics = (
                f"/app/device/property/{self.device_sn}",
                f"/app/{self.user_id}/{self.device_sn}/thing/property/report",
                f"/app/{self.user_id}/{self.device_sn}/thing/property/get_reply",
                f"/app/{self.user_id}/{self.device_sn}/thing/property/set_reply",
                f"/app/device/status/{self.device_sn}",
            )
            for topic in topics:
                client.subscribe(topic, qos=1)
            self._send_snapshot_request()
        else:
            self.is_connected = False

    def _on_disconnect(self, client, userdata, disconnect_flags, rc, properties=None) -> None:
        self.is_connected = False

    def _send_snapshot_request(self) -> None:
        if not self.mqtt_client or not self.is_connected or not self.device_sn:
            return
        try:
            from . import ef_delta3_pb2 as pb

            packet = pb.Delta3SendHeaderMsg()
            header = packet.msg.add()
            header.src = 32
            header.dest = 32
            header.seq = random.randint(100000000, 999999999)
            setattr(header, "from", "StartHub")
            topic = f"/app/{self.user_id}/{self.device_sn}/thing/property/get"
            self.mqtt_client.publish(topic, packet.SerializeToString(), qos=1)
        except Exception:
            pass

    def send_set_command(self, params: Dict[str, Any]) -> bool:
        if not self.mqtt_client or not self.is_connected or not self.device_sn:
            return False
        try:
            import paho.mqtt.client as mqtt
            from . import ef_delta3_pb2 as pb

            cmd = pb.Delta3SetCommand()
            changed = False
            if "chg_pow_max" in params:
                cmd.plug_in_info_ac_in_chg_pow_max = int(params["chg_pow_max"])
                cmd.plug_in_info_ac_in_chg_mode = 0
                changed = True
            if "ac_out_open" in params:
                cmd.cfg_ac_out_open = 1 if params["ac_out_open"] else 0
                changed = True
            if "dc_out_open" in params:
                cmd.cfg_dc12v_out_open = 1 if params["dc_out_open"] else 0
                changed = True
            if "usb_open" in params:
                cmd.cfg_usb_open = 1 if params["usb_open"] else 0
                changed = True
            if "en_beep" in params:
                cmd.en_beep = 1 if params["en_beep"] else 0
                changed = True
            if not changed:
                return False

            pdata = cmd.SerializeToString()
            dest_id = int(self.current_state.get("_hdr_src", 2) or 2)
            for dst in list(dict.fromkeys([dest_id, 2])):
                packet = pb.Delta3SendHeaderMsg()
                header = packet.msg.add()
                header.pdata = pdata
                header.src = 32
                header.dest = dst
                header.d_src = 1
                header.d_dest = 1
                header.enc_type = 0
                header.check_type = 3
                header.cmd_func = 254
                header.cmd_id = 17
                header.data_len = len(pdata)
                header.need_ack = 1
                header.seq = random.randint(100000000, 999999999)
                header.version = 3
                header.payload_ver = 1
                setattr(header, "from", "Android")
                header.device_sn = self.device_sn
                topic = f"/app/{self.user_id}/{self.device_sn}/thing/property/set"
                res = self.mqtt_client.publish(topic, packet.SerializeToString(), qos=1)
                if res.rc != mqtt.MQTT_ERR_SUCCESS:
                    return False
            return True
        except Exception as exc:
            logger.warning("EcoFlow set command error: %s", type(exc).__name__)
            return False

    def apply_decoded(self, decoded: Dict[str, Any]) -> bool:
        """Apply a decoded telemetry dictionary to current_state; returns True if metrics updated."""
        if not decoded:
            return False
        updated = False
        st = self.current_state
        for k in ("bms_batt_soc", "cms_batt_soc", "soc", "act_soc", "f32_show_soc"):
            if decoded.get(k) is not None:
                st["soc"] = round(float(decoded[k]))
                updated = True
                break
        for k in ("act_soc", "f32_show_soc", "bms_batt_soc", "cms_batt_soc"):
            if decoded.get(k) is not None:
                st["act_soc"] = round(float(decoded[k]), 1)
                updated = True
                break
        for k in ("pow_in_sum_w", "wattsInSum"):
            if decoded.get(k) is not None:
                st["in_watts"] = abs(float(decoded[k]))
                updated = True
                break
        if decoded.get("pow_get_ac_in") is not None:
            st["ac_in_watts"] = abs(float(decoded["pow_get_ac_in"]))
            updated = True
        for k in ("pow_out_sum_w", "pow_get_ac_out", "wattsOutSum"):
            if decoded.get(k) is not None:
                st["out_watts"] = abs(float(decoded[k]))
                updated = True
                break
        if decoded.get("plug_in_info_ac_in_vol") is not None:
            st["ac_in_vol"] = round(float(decoded["plug_in_info_ac_in_vol"]), 1)
        if decoded.get("plug_in_info_ac_in_chg_pow_max") is not None:
            st["chg_pow_max"] = int(decoded["plug_in_info_ac_in_chg_pow_max"])
            st["chg_pow_max_reported"] = True
            updated = True
        if decoded.get("dc_out_open") is not None:
            st["dc_out_open"] = bool(int(decoded["dc_out_open"]))
            updated = True
        elif decoded.get("cfg_dc12v_out_open") is not None:
            st["dc_out_open"] = bool(int(decoded["cfg_dc12v_out_open"]))
            updated = True
        elif decoded.get("flow_info_12v") is not None:
            st["dc_out_open"] = bool(int(decoded["flow_info_12v"]) & 2)
            updated = True
        if decoded.get("cfg_usb_open") is not None:
            st["usb_open"] = bool(int(decoded["cfg_usb_open"]))
            updated = True
        elif decoded.get("flow_info_qcusb1") is not None:
            st["usb_open"] = bool(int(decoded["flow_info_qcusb1"]) & 2)
            updated = True
        if decoded.get("en_beep") is not None:
            st["beep_on"] = bool(int(decoded["en_beep"]))
            updated = True
        if decoded.get("_hdr_src"):
            st["_hdr_src"] = int(decoded["_hdr_src"])
        for k in ("bms_remain_cap", "remain_cap"):
            if decoded.get(k) is not None:
                st["remain_cap"] = int(decoded[k])
                break
        for k in ("bms_full_cap", "full_cap", "design_cap"):
            if decoded.get(k) is not None:
                st["full_cap"] = int(decoded[k])
                break
        for k in ("bms_dsg_rem_time", "cms_dsg_rem_time", "remain_time", "remainTime"):
            if decoded.get(k) is not None:
                st["dsg_time"] = int(decoded[k])
                updated = True
                break
        if updated:
            ac_in = st.get("ac_in_watts", 0.0)
            tot_in = st.get("in_watts", 0.0)
            ac_vol = st.get("ac_in_vol", 0.0)
            is_grid_now = (ac_in > 15) or (tot_in > 25) or (ac_vol > 150)
            self._prev_grid = is_grid_now
            st["is_grid"] = is_grid_now

            rem_wh = round((st["remain_cap"] / 1000.0) * 51.2) if st["remain_cap"] > 0 else 0
            full_wh = round((st["full_cap"] / 1000.0) * 51.2) if st["full_cap"] > 0 else 0
            if full_wh <= 0:
                full_wh = 2048
                rem_wh = round(full_wh * (st["act_soc"] / 100.0))
            st["remain_wh"] = rem_wh
            st["full_wh"] = full_wh

            out_w = st.get("out_watts", 0.0)
            bms_dsg = st.get("dsg_time", 0)
            if not is_grid_now and 0 < bms_dsg < 3000:
                st["est_dsg_min"] = bms_dsg
            else:
                effective_load = max(out_w + 25.0, 35.0)
                st["est_dsg_min"] = int((rem_wh * 0.90 / effective_load) * 60)

            st["last_update"] = time.time()
            st["stale"] = False
            self._last_rx_mono = time.monotonic()
            self._stale_reconnects = 0
        return updated

    def _on_message(self, client, userdata, msg) -> None:
        try:
            decoded = Delta3Decoder.decode_payload(msg.payload)
            if self.apply_decoded(decoded):
                self.on_state_update(dict(self.current_state))
        except Exception as exc:
            logger.debug("EcoFlow message processing error: %s", type(exc).__name__)


class EcoFlowProvider:
    """High-level StartHub provider supporting built-in MQTT or external state_file mode."""

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
        self.mode = str(config.get("mode") or "mqtt").lower()
        self.state_cache_file = self.cache_dir / "ecoflow_state.json"
        self.charge_steps = list(config.get("charge_watt_steps") or [200, 400, 600, 800, 1000, 1500])

        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._mqtt: Optional[EcoFlowMqttClient] = None
        self._state: Dict[str, Any] = {
            "stale": True,
            "last_update": 0.0,
            "soc": 0,
            "in_watts": 0.0,
            "out_watts": 0.0,
            "est_dsg_min": 0,
            "remain_wh": 0,
            "full_wh": 2048,
            "is_grid": True,
            "chg_pow_max": 200,
            "chg_pow_max_reported": False,
            "usb_open": False,
            "dc_out_open": False,
            "beep_on": True,
            "device_name": str(config.get("device_name") or "EcoFlow Station"),
            "image_path": str(config.get("image_path") or "").strip(),
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snap = dict(self._state)
            stamp = float(snap.get("last_update", 0) or 0)
            age = time.time() - stamp
            snap["stale"] = not (stamp > 0 and 0 <= age <= 90)
            return snap

    def start(self) -> None:
        if not self.config.get("enabled", False):
            return
        attach_ecoflow_rotating_log(self.cache_dir / "logs")
        if self.mode == "mqtt" and self.config.get("email") and self.config.get("password"):
            self._mqtt = EcoFlowMqttClient(
                email=str(self.config.get("email") or ""),
                password=str(self.config.get("password") or ""),
                device_sn=str(self.config.get("device_sn") or ""),
                device_name=str(self.config.get("device_name") or "EcoFlow Station"),
                region=str(self.config.get("region") or "europe"),
                on_state_update=self._on_mqtt_state,
            )
            self._mqtt.start()
        threading.Thread(target=self._poll_loop, name="starthub-ecoflow-poll", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()
        if self._mqtt:
            self._mqtt.stop()

    def _on_mqtt_state(self, state: Dict[str, Any]) -> None:
        write_json_atomic(self.state_cache_file, state)
        with self._lock:
            self._state.update(state)
            self._state["image_path"] = str(self.config.get("image_path") or "").strip()
        if self.on_change:
            self.on_change()

    def _poll_loop(self) -> None:
        while not self._stopped.is_set():
            if self.mode == "state_file":
                state_path = str(self.config.get("state_file") or "").strip()
                if state_path:
                    data = read_json_safe(state_path, None)
                    if isinstance(data, dict):
                        with self._lock:
                            self._state.update(data)
            if self.on_change:
                self.on_change()
            if self._stopped.wait(2.5):
                break

    def _send_command(self, payload: Dict[str, Any]) -> bool:
        if self._mqtt is not None:
            return self._mqtt.send_set_command(payload)
        cmd_file = str(self.config.get("command_file") or "").strip()
        if cmd_file:
            return write_json_atomic(cmd_file, payload)
        return False

    def cycle_charge_watts(self) -> None:
        snap = self.snapshot()
        cur = int(snap.get("chg_pow_max", 200) or 200)
        steps = self.charge_steps
        nxt = steps[(steps.index(cur) + 1) % len(steps)] if cur in steps else steps[0]
        threading.Thread(target=lambda: self._send_command({"chg_pow_max": nxt}), daemon=True).start()
        if self.on_toast:
            self.on_toast(self.i18n.t("ecoflow.toast_limit", w=nxt))

    def toggle_usb(self) -> None:
        nxt = not bool(self.snapshot().get("usb_open", False))
        threading.Thread(target=lambda: self._send_command({"usb_open": 1 if nxt else 0}), daemon=True).start()
        if self.on_toast:
            lbl = self.i18n.t("peripherals.bt_on" if nxt else "peripherals.bt_off")
            self.on_toast(self.i18n.t("ecoflow.toast_usb", state=lbl))

    def toggle_dc12v(self) -> None:
        nxt = not bool(self.snapshot().get("dc_out_open", False))
        threading.Thread(target=lambda: self._send_command({"dc_out_open": 1 if nxt else 0}), daemon=True).start()
        if self.on_toast:
            lbl = self.i18n.t("peripherals.bt_on" if nxt else "peripherals.bt_off")
            self.on_toast(self.i18n.t("ecoflow.toast_dc", state=lbl))

    def toggle_beep(self) -> None:
        nxt = not bool(self.snapshot().get("beep_on", True))
        threading.Thread(target=lambda: self._send_command({"en_beep": 1 if nxt else 0}), daemon=True).start()
        if self.on_toast:
            lbl = self.i18n.t("peripherals.bt_on" if nxt else "peripherals.bt_off")
            self.on_toast(self.i18n.t("ecoflow.toast_beep", state=lbl))
