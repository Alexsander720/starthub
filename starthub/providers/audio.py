"""Windows Core Audio volume, mute, and 1-click output device switcher (Tier 1, zero API keys)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..i18n import I18n
from ..surface import IS_WINDOWS

logger = logging.getLogger("starthub.providers.audio")


# ------------------------------------------------------------------
# Pure ctypes / comtypes Windows Core Audio helpers (no hard pycaw dep)
# ------------------------------------------------------------------

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid_from_str(s: str) -> _GUID:
    import uuid

    u = uuid.UUID(s)
    d4 = (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:])
    return _GUID(u.fields[0], u.fields[1], u.fields[2], d4)


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", wintypes.DWORD)]


class _PROPVARIANT_UNION(ctypes.Union):
    _fields_ = [("pwszVal", wintypes.LPWSTR), ("ulVal", wintypes.ULONG), ("raw", ctypes.c_ubyte * 16)]


class _PROPVARIANT(ctypes.Structure):
    _fields_ = [
        ("vt", wintypes.WORD),
        ("r1", wintypes.WORD),
        ("r2", wintypes.WORD),
        ("r3", wintypes.WORD),
        ("val", _PROPVARIANT_UNION),
    ]


if IS_WINDOWS:
    _CLSID_MMDeviceEnumerator = _guid_from_str("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    _IID_IMMDeviceEnumerator = _guid_from_str("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    _IID_IAudioEndpointVolume = _guid_from_str("{5CDF2C82-841E-4546-9722-0CF74078229A}")
    _CLSID_PolicyConfigClient = _guid_from_str("{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}")
    _IID_IPolicyConfig = _guid_from_str("{F8679F50-850A-41CF-9C72-430F290290C8}")
    _IID_IPolicyConfigVista = _guid_from_str("{568B9108-44BF-40B4-9006-86AFE5B5A620}")
    _PKEY_Device_FriendlyName = _PROPERTYKEY(
        _guid_from_str("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14
    )


def _vtable_fn(obj_ptr: int, index: int, restype, *argtypes):
    vtbl = ctypes.cast(obj_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    func_type = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return func_type(vtbl[index])


def _com_release(ptr: Optional[int]) -> None:
    if ptr:
        try:
            _vtable_fn(ptr, 2, wintypes.ULONG)(ptr)
        except Exception:
            pass


def _read_device_name(dev_ptr: int) -> str:
    store_ptr = ctypes.c_void_p()
    # IMMDevice::OpenPropertyStore (vtable index 4), STGM_READ = 0
    hr = _vtable_fn(dev_ptr, 4, ctypes.c_long, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(
        dev_ptr, 0, ctypes.byref(store_ptr)
    )
    if hr != 0 or not store_ptr.value:
        return ""
    try:
        pv = _PROPVARIANT()
        # IPropertyStore::GetValue (vtable index 5)
        hr2 = _vtable_fn(
            store_ptr.value, 5, ctypes.c_long, ctypes.POINTER(_PROPERTYKEY), ctypes.POINTER(_PROPVARIANT)
        )(store_ptr.value, ctypes.byref(_PKEY_Device_FriendlyName), ctypes.byref(pv))
        if hr2 == 0 and pv.vt == 31 and pv.val.pwszVal:  # VT_LPWSTR = 31
            name = str(pv.val.pwszVal)
            try:
                ctypes.windll.ole32.PropVariantClear(ctypes.byref(pv))
            except Exception:
                pass
            return name
    finally:
        _com_release(store_ptr.value)
    return ""


def _read_device_id(dev_ptr: int) -> str:
    # IMMDevice::GetId (vtable index 5)
    raw_id = wintypes.LPWSTR()
    hr = _vtable_fn(dev_ptr, 5, ctypes.c_long, ctypes.POINTER(wintypes.LPWSTR))(dev_ptr, ctypes.byref(raw_id))
    if hr == 0 and raw_id.value:
        val = str(raw_id.value)
        try:
            ctypes.windll.ole32.CoTaskMemFree(raw_id)
        except Exception:
            pass
        return val
    return ""


def _create_mm_enumerator() -> Optional[int]:
    if not IS_WINDOWS:
        return None
    ole32 = ctypes.windll.ole32
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    ptr = ctypes.c_void_p()
    # CLSCTX_ALL = 23
    hr = ole32.CoCreateInstance(
        ctypes.byref(_CLSID_MMDeviceEnumerator),
        None,
        23,
        ctypes.byref(_IID_IMMDeviceEnumerator),
        ctypes.byref(ptr),
    )
    return int(ptr.value) if (hr == 0 and ptr.value) else None


def _get_default_render_device(enum_ptr: int) -> Optional[int]:
    dev_ptr = ctypes.c_void_p()
    # IMMDeviceEnumerator::GetDefaultAudioEndpoint (vtable index 4): eRender=0, eConsole=0
    hr = _vtable_fn(enum_ptr, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
        enum_ptr, 0, 0, ctypes.byref(dev_ptr)
    )
    return int(dev_ptr.value) if (hr == 0 and dev_ptr.value) else None


def _open_endpoint_volume(dev_ptr: int) -> Optional[int]:
    vol_ptr = ctypes.c_void_p()
    # IMMDevice::Activate (vtable index 3)
    hr = _vtable_fn(
        dev_ptr,
        3,
        ctypes.c_long,
        ctypes.POINTER(_GUID),
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    )(dev_ptr, ctypes.byref(_IID_IAudioEndpointVolume), 23, None, ctypes.byref(vol_ptr))
    return int(vol_ptr.value) if (hr == 0 and vol_ptr.value) else None


def query_windows_audio_state() -> Dict[str, Any]:
    """Read current master volume (0-100), mute state, and active render devices via Core Audio COM."""
    empty: Dict[str, Any] = {
        "available": False,
        "volume": 0,
        "muted": False,
        "device_id": "",
        "device_name": "",
        "devices": [],
    }
    if not IS_WINDOWS:
        return empty
    enum_ptr = _create_mm_enumerator()
    if not enum_ptr:
        return empty
    try:
        default_dev = _get_default_render_device(enum_ptr)
        active_id = ""
        active_name = ""
        vol_pct = 0
        muted = False
        if default_dev:
            try:
                active_id = _read_device_id(default_dev)
                active_name = _read_device_name(default_dev)
                vol_ptr = _open_endpoint_volume(default_dev)
                if vol_ptr:
                    try:
                        # IAudioEndpointVolume::GetMasterVolumeLevelScalar (index 9)
                        scalar = ctypes.c_float(0.0)
                        _vtable_fn(vol_ptr, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_float))(
                            vol_ptr, ctypes.byref(scalar)
                        )
                        vol_pct = max(0, min(100, int(round(scalar.value * 100.0))))
                        # IAudioEndpointVolume::GetMute (index 15)
                        mval = wintypes.BOOL(0)
                        _vtable_fn(vol_ptr, 15, ctypes.c_long, ctypes.POINTER(wintypes.BOOL))(
                            vol_ptr, ctypes.byref(mval)
                        )
                        muted = bool(mval.value)
                    finally:
                        _com_release(vol_ptr)
            finally:
                _com_release(default_dev)

        # Enumerate active render endpoints: EnumAudioEndpoints (vtable index 3), eRender=0, DEVICE_STATE_ACTIVE=1
        devices: List[Dict[str, Any]] = []
        coll_ptr = ctypes.c_void_p()
        hr = _vtable_fn(
            enum_ptr, 3, ctypes.c_long, ctypes.c_int, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)
        )(enum_ptr, 0, 1, ctypes.byref(coll_ptr))
        if hr == 0 and coll_ptr.value:
            try:
                count = wintypes.UINT(0)
                # IMMDeviceCollection::GetCount (index 3)
                _vtable_fn(coll_ptr.value, 3, ctypes.c_long, ctypes.POINTER(wintypes.UINT))(
                    coll_ptr.value, ctypes.byref(count)
                )
                for idx in range(min(32, int(count.value))):
                    item_ptr = ctypes.c_void_p()
                    # IMMDeviceCollection::Item (index 4)
                    hr_i = _vtable_fn(
                        coll_ptr.value, 4, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)
                    )(coll_ptr.value, idx, ctypes.byref(item_ptr))
                    if hr_i == 0 and item_ptr.value:
                        try:
                            did = _read_device_id(item_ptr.value)
                            dname = _read_device_name(item_ptr.value)
                            if did and dname:
                                devices.append(
                                    {
                                        "id": did,
                                        "name": dname,
                                        "short_name": shorten_audio_name(dname),
                                        "active": did == active_id,
                                    }
                                )
                        finally:
                            _com_release(item_ptr.value)
            finally:
                _com_release(coll_ptr.value)

        return {
            "available": bool(active_id or devices),
            "volume": vol_pct,
            "muted": muted,
            "device_id": active_id,
            "device_name": shorten_audio_name(active_name) if active_name else "",
            "device_full_name": active_name,
            "devices": devices,
        }
    except Exception as exc:
        logger.debug("Audio query failed: %s", exc)
        return empty
    finally:
        _com_release(enum_ptr)


def set_windows_master_volume(percent: Optional[int] = None, mute: Optional[bool] = None) -> bool:
    if not IS_WINDOWS:
        return False
    enum_ptr = _create_mm_enumerator()
    if not enum_ptr:
        return False
    try:
        default_dev = _get_default_render_device(enum_ptr)
        if not default_dev:
            return False
        try:
            vol_ptr = _open_endpoint_volume(default_dev)
            if not vol_ptr:
                return False
            try:
                if percent is not None:
                    scalar = max(0.0, min(1.0, float(percent) / 100.0))
                    # IAudioEndpointVolume::SetMasterVolumeLevelScalar (index 7)
                    _vtable_fn(vol_ptr, 7, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)(
                        vol_ptr, ctypes.c_float(scalar), None
                    )
                if mute is not None:
                    # IAudioEndpointVolume::SetMute (index 14)
                    _vtable_fn(vol_ptr, 14, ctypes.c_long, wintypes.BOOL, ctypes.c_void_p)(
                        vol_ptr, wintypes.BOOL(1 if mute else 0), None
                    )
                return True
            finally:
                _com_release(vol_ptr)
        finally:
            _com_release(default_dev)
    except Exception as exc:
        logger.debug("Audio set failed: %s", exc)
        return False
    finally:
        _com_release(enum_ptr)


def set_windows_default_audio_endpoint(device_id: str) -> bool:
    """Switch the Windows default audio playback endpoint across Console/Multimedia/Communications roles."""
    if not IS_WINDOWS or not device_id:
        return False
    ole32 = ctypes.windll.ole32
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long

    for iid, vtable_idx in ((_IID_IPolicyConfig, 13), (_IID_IPolicyConfigVista, 13)):
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(_CLSID_PolicyConfigClient),
            None,
            23,
            ctypes.byref(iid),
            ctypes.byref(ptr),
        )
        if hr == 0 and ptr.value:
            try:
                set_fn = _vtable_fn(ptr.value, vtable_idx, ctypes.c_long, wintypes.LPCWSTR, ctypes.c_int)
                ok = True
                for role in (0, 1, 2):  # eConsole, eMultimedia, eCommunications
                    if set_fn(ptr.value, device_id, role) != 0:
                        ok = False
                if ok:
                    return True
            except Exception as exc:
                logger.debug("IPolicyConfig switch failed: %s", exc)
            finally:
                _com_release(ptr.value)
    return False


def shorten_audio_name(full_name: str) -> str:
    """Turn 'Headphones (Sony WH-1000XM5 Stereo)' into a crisp, distinguishable label."""
    text = str(full_name or "").strip()
    if not text:
        return "Audio"
    if "(" in text and text.endswith(")"):
        head, tail = text.split("(", 1)
        head = head.strip()
        inner = tail[:-1].strip()
        for noise in ("High Definition Audio Device", "USB Audio Device", "NVIDIA High Definition Audio"):
            inner = inner.replace(noise, "").strip(" -")
        if inner:
            if len(inner) > 22:
                inner = inner[:21].rstrip() + "…"
            return f"{head} · {inner}" if len(head) <= 10 else inner
        return head or text
    return text


class AudioControlProvider:
    """Visibility-gated Windows Core Audio controller (volume, mute, 1-click output switching)."""

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
        self.interval = max(0.5, float(config.get("poll_interval_sec", 1.5)))

        self._lock = threading.Lock()
        self._visible = threading.Event()
        self._stopped = threading.Event()
        self._commands: queue.Queue[Tuple[str, Any]] = queue.Queue(maxsize=12)
        self._due = 0.0
        self._state: Dict[str, Any] = {
            "available": False,
            "volume": 0,
            "muted": False,
            "device_id": "",
            "device_name": "",
            "devices": [],
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                **self._state,
                "devices": [dict(d) for d in self._state.get("devices", [])],
            }

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._visible.set()
            self._due = 0.0
        else:
            self._visible.clear()

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=self._loop, name="starthub-audio", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _publish(self, value: Dict[str, Any]) -> None:
        with self._lock:
            changed = self._state != value
            self._state = value
        if changed and self.on_change:
            self.on_change()

    def set_volume(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        with self._lock:
            self._state["volume"] = pct
            if pct > 0:
                self._state["muted"] = False
        if self.on_change:
            self.on_change()
        try:
            self._commands.put_nowait(("volume", pct))
        except queue.Full:
            pass

    def toggle_mute(self) -> None:
        with self._lock:
            nxt = not bool(self._state.get("muted", False))
            self._state["muted"] = nxt
        if self.on_change:
            self.on_change()
        try:
            self._commands.put_nowait(("mute", nxt))
        except queue.Full:
            pass

    def cycle_output(self) -> None:
        snap = self.snapshot()
        devs = snap.get("devices") or []
        if len(devs) < 2:
            if self.on_toast:
                self.on_toast(self.i18n.t("audio.single_device"))
            return
        cur_id = snap.get("device_id", "")
        cur_idx = next((i for i, d in enumerate(devs) if d.get("id") == cur_id), -1)
        nxt = devs[(cur_idx + 1) % len(devs)]
        try:
            self._commands.put_nowait(("switch", nxt))
        except queue.Full:
            pass

    def poll_once(self) -> Dict[str, Any]:
        state = query_windows_audio_state()
        self._publish(state)
        return state

    def _loop(self) -> None:
        com_ok = False
        if IS_WINDOWS:
            try:
                ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
                com_ok = True
            except Exception:
                pass
        try:
            # Initial one-shot read so the very first frame already has real audio info
            self.poll_once()
            while not self._stopped.wait(0.2):
                while not self._commands.empty():
                    cmd, arg = self._commands.get_nowait()
                    if cmd == "volume":
                        set_windows_master_volume(percent=int(arg), mute=False if int(arg) > 0 else None)
                        self.poll_once()
                    elif cmd == "mute":
                        set_windows_master_volume(mute=bool(arg))
                        self.poll_once()
                    elif cmd == "switch" and isinstance(arg, dict):
                        ok = set_windows_default_audio_endpoint(str(arg.get("id") or ""))
                        if ok and self.on_toast:
                            self.on_toast(self.i18n.t("audio.toast_switched", name=arg.get("short_name", "Audio")))
                        self.poll_once()
                if not self._visible.is_set():
                    continue
                now = time.monotonic()
                if now >= self._due:
                    self._due = now + self.interval
                    self.poll_once()
        finally:
            if com_ok and IS_WINDOWS:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
