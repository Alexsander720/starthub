"""Android ADB + scrcpy + screenshot-to-clipboard + optional SMS/OTP provider (Tier 2, opt-in)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ctypes
import datetime
import ipaddress
import logging
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ..config import read_json_safe, write_json_atomic
from ..i18n import I18n
from ..surface import (
    CREATE_NO_WINDOW,
    IS_WINDOWS,
    copy_image_and_file_to_clipboard,
    copy_text_to_clipboard,
    popen_on_default_desktop,
)

logger = logging.getLogger("starthub.providers.phone_adb")


class PhoneConnectionError(RuntimeError):
    pass


class PhoneAdbTarget:
    """Resolve a user-configured Android device by serial, mDNS, or Wi-Fi endpoint."""

    def __init__(
        self,
        adb_exe: str,
        device_serial: str = "",
        wifi_address: str = "",
        cache_file: Optional[Path] = None,
    ):
        self.adb_exe = adb_exe or "adb"
        self.device_serial = device_serial.strip()
        self.cache_file = Path(cache_file) if cache_file else None
        self.last_serial = self._load_cached_serial(wifi_address.strip())
        self._serial: Optional[str] = None
        self._checked_at = 0.0
        self._lock = threading.Lock()

    def _load_cached_serial(self, fallback: str) -> str:
        if self.cache_file and self.cache_file.is_file():
            try:
                cached = self.cache_file.read_text(encoding="utf-8").strip()
                if cached:
                    return cached
            except OSError:
                pass
        return fallback

    def _save_cached_serial(self, serial: str) -> None:
        if not self.cache_file:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(serial, encoding="utf-8")
        except OSError:
            pass

    def _adb(self, *args: str, timeout: float = 3.0) -> str:
        return subprocess.check_output(
            [self.adb_exe, *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
        ).strip()

    def _connected_phone(self) -> Optional[str]:
        lines = self._adb("devices", "-l").splitlines()
        candidates = []
        for line in lines:
            fields = line.split()
            if len(fields) < 2 or fields[1] != "device":
                continue
            candidates.append(fields[0])
        if not candidates:
            return None
        if not self.device_serial:
            if self.last_serial and self.last_serial in candidates:
                return self.last_serial
            return candidates[0]
        for serial in candidates:
            if serial == self.device_serial:
                return serial
            if self.last_serial and serial != self.last_serial:
                continue
            try:
                ident = self._adb("-s", serial, "shell", "getprop", "ro.serialno")
                if ident == self.device_serial:
                    return serial
            except (OSError, subprocess.SubprocessError):
                continue
        return None

    def _known_serials(self) -> set[str]:
        serials: set[str] = set()
        try:
            for line in self._adb("devices", "-l").splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[1] in ("device", "offline", "unauthorized"):
                    serials.add(fields[0])
        except (OSError, subprocess.SubprocessError):
            pass
        return serials

    def _scan_subnet_candidates(self, excluded: set[str]) -> List[str]:
        if ":" not in self.last_serial:
            return []
        host, port_str = self.last_serial.rsplit(":", 1)
        try:
            ip = ipaddress.IPv4Address(host)
            port = int(port_str)
        except ValueError:
            return []
        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
        targets = [str(addr) for addr in network.hosts() if f"{addr}:{port}" not in excluded]

        def _probe(addr: str) -> Optional[str]:
            try:
                with socket.create_connection((addr, port), timeout=0.25):
                    return f"{addr}:{port}"
            except OSError:
                return None

        with ThreadPoolExecutor(max_workers=48) as pool:
            return [ep for ep in pool.map(_probe, targets) if ep]

    def resolve(self, force: bool = False) -> str:
        with self._lock:
            if self._serial and not force and time.monotonic() - self._checked_at < 10.0:
                return self._serial
            self._serial = None
            try:
                serial = self._connected_phone()
                if not serial and (self.device_serial or self.last_serial):
                    candidates: List[str] = []
                    if self.device_serial:
                        try:
                            for line in self._adb("mdns", "services").splitlines():
                                fields = line.split()
                                if len(fields) >= 3 and fields[1] in ("_adb._tcp", "_adb-tls-connect._tcp"):
                                    if fields[0] == self.device_serial or fields[0].startswith(f"adb-{self.device_serial}-"):
                                        candidates.append(fields[2])
                        except (OSError, subprocess.SubprocessError):
                            pass
                    if self.last_serial and self.last_serial not in candidates:
                        candidates.append(self.last_serial)
                    tried: set[str] = set()
                    for endpoint in candidates:
                        tried.add(endpoint)
                        try:
                            self._adb("connect", endpoint, timeout=5.0)
                        except (OSError, subprocess.SubprocessError):
                            pass
                        serial = self._connected_phone()
                        if serial:
                            break
                    if not serial and self.device_serial and ":" in self.last_serial:
                        excluded = tried | self._known_serials()
                        for endpoint in self._scan_subnet_candidates(excluded):
                            try:
                                self._adb("connect", endpoint, timeout=3.0)
                            except (OSError, subprocess.SubprocessError):
                                pass
                            serial = self._connected_phone()
                            if serial:
                                break
                if serial:
                    if serial != self.last_serial:
                        self._save_cached_serial(serial)
                    self.last_serial = self._serial = serial
                    self._checked_at = time.monotonic()
                    return serial
            except (OSError, subprocess.SubprocessError):
                pass
            raise PhoneConnectionError("ADB device unreachable")


class PhoneAdbProvider:
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
        self.photos_dir = self.cache_dir / "photos"
        self.gallery_dir = self.cache_dir / "gallery"
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.gallery_dir.mkdir(parents=True, exist_ok=True)
        self._prefs_file = self.cache_dir / "phone_prefs.json"

        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self.adb_exe = str(config.get("adb_path") or "adb")
        self.scrcpy_exe = str(config.get("scrcpy_path") or "scrcpy")
        self.device_name = str(config.get("device_name") or "Android Phone")
        self.unlock_pin = str(config.get("unlock_pin") or "")
        self.enable_sms_otp = bool(config.get("enable_sms_otp", False))
        self.enable_photos = bool(config.get("enable_photos", True))
        self.frame_image_path = str(config.get("frame_image_path") or "").strip()
        self.image_editor_path = str(config.get("image_editor_path") or "").strip()

        self.target = PhoneAdbTarget(
            adb_exe=self.adb_exe,
            device_serial=str(config.get("device_serial") or ""),
            wifi_address=str(config.get("wifi_address") or ""),
            cache_file=self.cache_dir / "phone_serial.txt",
        )

        prefs = read_json_safe(self._prefs_file, {})
        if not isinstance(prefs, dict):
            prefs = {}
        self._lock = threading.Lock()
        self._photo_lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._last_synced_shot_ts: Optional[float] = None

        self._state: Dict[str, Any] = {
            "online": False,
            "name": self.device_name,
            "battery": None,
            "charging": False,
            "auto_clip_sync": bool(prefs.get("auto_clip_sync", config.get("auto_clip_sync", True))),
            "sms_expanded": bool(prefs.get("sms_expanded", False)),
            "photos_expanded": bool(prefs.get("photos_expanded", False)),
            "enable_sms_otp": self.enable_sms_otp,
            "enable_photos": self.enable_photos,
            "frame_image_path": self.frame_image_path,
            "photos": [],
            "sms": [],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._state,
                "photos": [dict(p) for p in self._state["photos"]],
                "sms": [dict(s) for s in self._state["sms"]],
            }

    def start(self) -> None:
        if not self.config.get("enabled", False):
            return
        threading.Thread(target=self._loop, name="starthub-phone", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()
        self._wake.set()

    def _save_prefs(self) -> None:
        with self._lock:
            data = {
                "auto_clip_sync": self._state["auto_clip_sync"],
                "sms_expanded": self._state["sms_expanded"],
                "photos_expanded": self._state["photos_expanded"],
            }
        write_json_atomic(self._prefs_file, data)

    def _notify(self) -> None:
        if self.on_change:
            self.on_change()

    def _toast(self, msg: str) -> None:
        if self.on_toast:
            self.on_toast(msg)

    def _loop(self) -> None:
        while not self._stopped.is_set():
            self._wake.clear()
            self.poll_once()
            self._notify()
            self._wake.wait(10.0)

    def poll_once(self) -> None:
        try:
            serial = self.target.resolve()
            out = subprocess.check_output(
                [self.adb_exe, "-s", serial, "shell", "dumpsys battery"],
                text=True,
                timeout=3.5,
                creationflags=CREATE_NO_WINDOW,
                errors="ignore",
            )
            lvl = None
            status = 3
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("level:"):
                    lvl = int(line.split(":", 1)[1].strip())
                elif line.startswith("status:"):
                    status = int(line.split(":", 1)[1].strip())
            if lvl is not None:
                with self._lock:
                    self._state["online"] = True
                    self._state["battery"] = lvl
                    self._state["charging"] = status in (2, 5)
        except Exception:
            with self._lock:
                self._state["online"] = False
            return

        if self.enable_photos and self._state.get("photos_expanded", False):
            self._poll_photos()
        if self.enable_sms_otp:
            self._poll_sms()

    def _poll_photos(self) -> None:
        if not self._photo_lock.acquire(blocking=False):
            return
        try:
            cmd = (
                "for f in $(ls -1t /sdcard/Pictures/Screenshots/* /sdcard/DCIM/Screenshots/* "
                "/sdcard/DCIM/Camera/*.jpg /sdcard/DCIM/Camera/*.png 2>/dev/null | head -n 4); "
                'do stat -c "%Y|%n" "$f" 2>/dev/null; done'
            )
            serial = self.target.resolve()
            out = subprocess.check_output(
                [self.adb_exe, "-s", serial, "shell", cmd],
                text=True,
                timeout=4.5,
                creationflags=CREATE_NO_WINDOW,
                errors="ignore",
            )
            photos = []
            for line in out.splitlines():
                if not self._state.get("photos_expanded", False):
                    return
                if "|" not in line:
                    continue
                ts_s, rpath = line.strip().split("|", 1)
                if not ts_s.isdigit():
                    continue
                ts = float(ts_s)
                bname = os.path.basename(rpath)
                lpath = str(self.photos_dir / bname)
                if not os.path.exists(lpath) or os.path.getsize(lpath) == 0:
                    subprocess.run(
                        [self.adb_exe, "-s", serial, "pull", rpath, lpath],
                        timeout=6.0,
                        creationflags=CREATE_NO_WINDOW,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                if os.path.exists(lpath) and os.path.getsize(lpath) > 0:
                    is_scr = "Screenshot" in rpath or "Screenshots" in rpath
                    photos.append(
                        {
                            "name": self.i18n.t("phone.screen_label" if is_scr else "phone.photo_label"),
                            "filename": bname,
                            "remote_path": rpath,
                            "local_path": lpath,
                            "time_str": self.i18n.format_relative_time(ts),
                            "ts": ts,
                        }
                    )
            if photos:
                newest_ts = max(p["ts"] for p in photos)
                if self._last_synced_shot_ts is None:
                    self._last_synced_shot_ts = newest_ts
                elif newest_ts > self._last_synced_shot_ts:
                    self._last_synced_shot_ts = newest_ts
                    if self._state.get("auto_clip_sync", True):
                        newest = max(photos, key=lambda p: p["ts"])
                        if copy_image_and_file_to_clipboard(newest["local_path"]):
                            self._toast(self.i18n.t("phone.toast_copied", name=newest["name"]))
                with self._lock:
                    self._state["photos"] = photos[:4]
        except Exception as exc:
            logger.debug("Phone photo sync error: %s", exc)
        finally:
            self._photo_lock.release()

    def _poll_sms(self) -> None:
        try:
            serial = self.target.resolve()
            sms_cmd = (
                'content query --uri content://sms/inbox --projection address:date:body --sort "date DESC" 2>/dev/null | head -n 15'
            )
            out = subprocess.check_output(
                [self.adb_exe, "-s", serial, "shell", sms_cmd],
                text=True,
                timeout=4.5,
                creationflags=CREATE_NO_WINDOW,
                errors="ignore",
                encoding="utf-8",
            )
            rows = re.split(r"(?:^|\n)Row:\s+\d+\s+", out)
            sms_list = []
            for raw in rows:
                raw = raw.strip()
                if not raw:
                    continue
                m = re.match(r"address=(.*?),\s*date=(\d+),\s*body=(.*)", raw, re.DOTALL)
                if not m:
                    continue
                addr, date_ms, body = m.group(1).strip(), int(m.group(2)), " ".join(m.group(3).strip().splitlines())
                otp = None
                for cand in re.findall(r"(?<!\d)(\d{4,8})(?!\d)", body):
                    if cand not in ("2024", "2025", "2026", "2027", "2028"):
                        otp = cand
                        break
                sms_list.append(
                    {
                        "sender": addr,
                        "body": body,
                        "time_str": self.i18n.format_relative_time(date_ms / 1000.0),
                        "otp": otp,
                    }
                )
                if len(sms_list) >= 6:
                    break
            if sms_list:
                with self._lock:
                    self._state["sms"] = sms_list
        except Exception as exc:
            logger.debug("Phone SMS sync error: %s", exc)

    def launch_scrcpy(self) -> None:
        self._toast(self.i18n.t("phone.toast_opening_screen", name=self.device_name))

        def _worker():
            try:
                if IS_WINDOWS:
                    try:
                        u32 = ctypes.windll.user32
                        hdesk = u32.OpenDesktopW("Default", 0, False, 0x01FF)
                        if hdesk:
                            u32.SetThreadDesktop(hdesk)
                    except Exception:
                        pass

                serial = self.target.resolve(force=True)
                env = os.environ.copy()
                if os.path.isabs(self.adb_exe):
                    env["ADB"] = self.adb_exe
                cwd = os.path.dirname(self.scrcpy_exe) if os.path.isabs(self.scrcpy_exe) else None
                popen_on_default_desktop(
                    [
                        self.scrcpy_exe,
                        "--serial",
                        serial,
                        f"--window-title={self.device_name}",
                        "--stay-awake",
                        "--always-on-top",
                    ],
                    cwd=cwd,
                    env=env,
                    no_window=True,
                )
                subprocess.run(
                    [self.adb_exe, "-s", serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                    timeout=3.0,
                    creationflags=CREATE_NO_WINDOW,
                )
                if self.unlock_pin:
                    win_dump = subprocess.check_output(
                        [self.adb_exe, "-s", serial, "shell", "dumpsys window policy"],
                        text=True,
                        timeout=3.0,
                        creationflags=CREATE_NO_WINDOW,
                        errors="ignore",
                    )
                    if "mShowingLockscreen=true" in win_dump or "isStatusBarKeyguard=true" in win_dump:
                        time.sleep(0.5)
                        subprocess.run(
                            [self.adb_exe, "-s", serial, "shell", "input", "swipe", "540", "2000", "540", "800", "200"],
                            timeout=3.0,
                            creationflags=CREATE_NO_WINDOW,
                        )
                        time.sleep(0.5)
                        subprocess.run(
                            [self.adb_exe, "-s", serial, "shell", "input", "text", self.unlock_pin],
                            timeout=3.0,
                            creationflags=CREATE_NO_WINDOW,
                        )
                        time.sleep(0.25)
                        subprocess.run(
                            [self.adb_exe, "-s", serial, "shell", "input", "keyevent", "66"],
                            timeout=3.0,
                            creationflags=CREATE_NO_WINDOW,
                        )
                self._toast(self.i18n.t("phone.toast_screen_ready", name=self.device_name))
            except PhoneConnectionError:
                self._toast(self.i18n.t("phone.toast_offline"))
            except Exception as exc:
                self._toast(f"scrcpy: {exc}")

        threading.Thread(target=_worker, daemon=True).start()

    def screenshot_to_clipboard(self) -> None:
        def _worker():
            try:
                serial = self.target.resolve()
                raw = subprocess.check_output(
                    [self.adb_exe, "-s", serial, "exec-out", "screencap", "-p"],
                    timeout=6.0,
                    creationflags=CREATE_NO_WINDOW,
                )
                if len(raw) > 1000:
                    fname = f"Screenshot_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
                    lpath = str(self.photos_dir / fname)
                    with open(lpath, "wb") as fh:
                        fh.write(raw)
                    copy_image_and_file_to_clipboard(lpath)
                    now_ts = time.time()
                    self._last_synced_shot_ts = now_ts
                    with self._lock:
                        self._state["photos"].insert(
                            0,
                            {
                                "name": self.i18n.t("phone.screen_label"),
                                "filename": fname,
                                "remote_path": "",
                                "local_path": lpath,
                                "time_str": self.i18n.t("time.just_now"),
                                "ts": now_ts,
                            },
                        )
                        self._state["photos"] = self._state["photos"][:4]
                    self._toast(self.i18n.t("phone.toast_screenshot_taken"))
                    self._notify()
                    return
            except Exception:
                pass
            self._toast(self.i18n.t("phone.toast_screenshot_fail"))

        threading.Thread(target=_worker, daemon=True).start()

    def toggle_auto_clip_sync(self) -> None:
        with self._lock:
            cur = not self._state["auto_clip_sync"]
            self._state["auto_clip_sync"] = cur
        self._save_prefs()
        lbl = self.i18n.t("peripherals.bt_on" if cur else "peripherals.bt_off")
        self._toast(self.i18n.t("phone.toast_auto_clip", state=lbl))
        self._notify()

    def toggle_photos_expanded(self) -> None:
        with self._lock:
            cur = not self._state["photos_expanded"]
            self._state["photos_expanded"] = cur
        self._save_prefs()
        if cur:
            self._wake.set()
        self._notify()

    def toggle_sms_expanded(self) -> None:
        with self._lock:
            self._state["sms_expanded"] = not self._state["sms_expanded"]
        self._save_prefs()
        self._notify()

    def copy_photo(self, idx: int) -> None:
        photos = self.snapshot()["photos"]
        if 0 <= idx < len(photos) and copy_image_and_file_to_clipboard(photos[idx]["local_path"]):
            self._toast(self.i18n.t("phone.toast_copied", name=photos[idx]["name"]))

    def open_photo_file(self, lpath: str) -> None:
        if not lpath or not os.path.exists(lpath):
            return
        if self.image_editor_path and os.path.exists(self.image_editor_path):
            popen_on_default_desktop([self.image_editor_path, lpath])
        elif IS_WINDOWS:
            os.startfile(lpath)

    def open_photo(self, idx: int) -> None:
        photos = self.snapshot()["photos"]
        if 0 <= idx < len(photos):
            self.open_photo_file(photos[idx]["local_path"])

    def copy_sms(self, idx: int) -> None:
        sms_list = self.snapshot()["sms"]
        if not (0 <= idx < len(sms_list)):
            return
        item = sms_list[idx]
        target = item["otp"] if item.get("otp") else item["body"]
        if copy_text_to_clipboard(target):
            if item.get("otp"):
                self._toast(self.i18n.t("phone.toast_otp_copied", otp=item["otp"]))
            else:
                self._toast(self.i18n.t("phone.toast_sms_copied"))

    def fetch_gallery_items(self, category: str = "all", limit: int = 28) -> List[Dict[str, Any]]:
        if category == "screenshots":
            paths_expr = "/sdcard/Pictures/Screenshots/* /sdcard/DCIM/Screenshots/*"
        elif category == "camera":
            paths_expr = "/sdcard/DCIM/Camera/*.jpg /sdcard/DCIM/Camera/*.png"
        elif category == "downloads":
            paths_expr = "/sdcard/Download/*.jpg /sdcard/Download/*.png /sdcard/Download/*.webp"
        else:
            paths_expr = (
                "/sdcard/Pictures/Screenshots/* /sdcard/DCIM/Screenshots/* "
                "/sdcard/DCIM/Camera/*.jpg /sdcard/DCIM/Camera/*.png "
                "/sdcard/Download/*.jpg /sdcard/Download/*.png"
            )
        cmd = f'for f in $(ls -1t {paths_expr} 2>/dev/null | head -n {limit}); do stat -c "%Y|%n" "$f" 2>/dev/null; done'
        items: List[Dict[str, Any]] = []
        try:
            serial = self.target.resolve()
            out = subprocess.check_output(
                [self.adb_exe, "-s", serial, "shell", cmd],
                text=True,
                timeout=6.0,
                creationflags=CREATE_NO_WINDOW,
                errors="ignore",
            )
            for line in out.splitlines():
                if "|" not in line:
                    continue
                ts_s, rpath = line.strip().split("|", 1)
                if not ts_s.isdigit():
                    continue
                ts = float(ts_s)
                bname = os.path.basename(rpath)
                is_scr = "Screenshot" in rpath
                items.append(
                    {
                        "name": self.i18n.t("phone.screen_label" if is_scr else "phone.photo_label"),
                        "filename": bname,
                        "remote_path": rpath,
                        "local_path": str(self.gallery_dir / bname),
                        "time_str": self.i18n.format_relative_time(ts),
                        "ts": ts,
                    }
                )
        except Exception as exc:
            logger.debug("Gallery list error: %s", exc)
        return items

    def ensure_gallery_file(self, item: Dict[str, Any]) -> bool:
        lpath = item["local_path"]
        if os.path.exists(lpath) and os.path.getsize(lpath) > 0:
            return True
        alt = str(self.photos_dir / item["filename"])
        if os.path.exists(alt) and os.path.getsize(alt) > 0:
            item["local_path"] = alt
            return True
        try:
            serial = self.target.resolve()
            subprocess.run(
                [self.adb_exe, "-s", serial, "pull", item["remote_path"], lpath],
                timeout=8.0,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return os.path.exists(lpath) and os.path.getsize(lpath) > 0
        except Exception:
            return False
