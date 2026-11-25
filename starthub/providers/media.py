"""Universal Windows SMTC media provider (Spotify, YouTube Music, Tidal, browsers, etc.)."""
from __future__ import annotations

import asyncio
import datetime
import io
import logging
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from PIL import Image

from ..i18n import I18n
from .spotify_like import LikeState, SpotifyClient

logger = logging.getLogger("starthub.providers.media")


class MediaProvider:
    """Visibility-gated Windows SMTC reader + playback transport + optional Spotify Like."""

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
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.i18n = i18n
        self.on_change = on_change
        self.on_toast = on_toast
        self.interval = max(0.5, float(config.get("poll_interval_sec", 2.0)))
        self.preferred_apps: List[str] = [str(a).lower() for a in config.get("preferred_apps", [])]

        like_cfg = config.get("spotify_like", {}) or {}
        self.spotify_like_enabled = bool(like_cfg.get("enabled", False))
        self._like_state = LikeState(
            client=SpotifyClient(cache=self.cache_dir, client_id=str(like_cfg.get("client_id", ""))),
            added_msg=self.i18n.t("media.like_added"),
            removed_msg=self.i18n.t("media.like_removed"),
        )

        self._lock = threading.Lock()
        self._visible = threading.Event()
        self._stopped = threading.Event()
        self._commands: queue.Queue[str] = queue.Queue(maxsize=8)
        self._like_commands: queue.Queue[tuple] = queue.Queue(maxsize=8)
        self._media_manager = None
        self._cover_track = None
        self._like_track = None
        self._like_value = self._like_state.snapshot()
        self._like_busy = False

        self._state: Dict[str, Any] = {
            "playing": False,
            "available": False,
            "title": "",
            "artist": "",
            "app_id": "",
            "is_spotify": False,
            "position": 0.0,
            "duration": 0.0,
            "cover": None,
            "cover_track": None,
            "media_track": None,
            "like_enabled": self.spotify_like_enabled,
            "like_saved": None,
            "like_ready": False,
            "like_busy": False,
            "like_message": self.i18n.t("media.like_setup"),
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def set_visible(self, visible: bool) -> None:
        if visible:
            self._visible.set()
        else:
            self._visible.clear()

    def start(self) -> None:
        if not self.config.get("enabled", True):
            return
        threading.Thread(target=lambda: asyncio.run(self._loop()), name="starthub-media", daemon=True).start()
        if self.spotify_like_enabled:
            threading.Thread(target=self._like_loop, name="starthub-spotify-like", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _publish(self, value: Dict[str, Any]) -> None:
        with self._lock:
            changed = self._state != value
            self._state = value
        if changed and self.on_change:
            self.on_change()

    def command(self, action: str) -> None:
        if action not in ("previous", "toggle", "next") or not self._visible.is_set():
            return
        try:
            self._commands.put_nowait(action)
        except queue.Full:
            pass

    def toggle_like(self) -> None:
        if not self.spotify_like_enabled:
            return
        with self._lock:
            if not self._state.get("is_spotify"):
                return
            track = self._state.get("media_track")
            ready = bool(self._state.get("like_ready", False))
            message = self._state.get("like_message") or self.i18n.t("media.like_setup")
            if self._like_busy or not self._visible.is_set():
                return
            retry = not ready and bool(track) and self._like_state.client.configured
            if ready or retry:
                self._like_busy = True
                self._state["like_busy"] = True
        if not ready and not retry:
            if self.on_toast:
                self.on_toast(message)
            return
        try:
            self._like_commands.put_nowait(("retry" if retry else "toggle", track))
        except queue.Full:
            with self._lock:
                self._like_busy = False
                self._state["like_busy"] = False
        if self.on_change:
            self.on_change()

    async def _pick_session(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

        if self._media_manager is None:
            self._media_manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        sessions = list(self._media_manager.get_sessions() or [])
        if not sessions:
            return None

        def is_playing(sess) -> bool:
            try:
                return int(sess.get_playback_info().playback_status) == 4
            except Exception:
                return False

        def app_rank(sess) -> int:
            app_id = (sess.source_app_user_model_id or "").lower()
            for idx, pref in enumerate(self.preferred_apps):
                if pref and pref in app_id:
                    return idx
            return len(self.preferred_apps) + 1

        playing_sessions = [s for s in sessions if is_playing(s)]
        if playing_sessions:
            playing_sessions.sort(key=app_rank)
            return playing_sessions[0]

        current = self._media_manager.get_current_session()
        if current is not None:
            return current
        sessions.sort(key=app_rank)
        return sessions[0]

    async def _poll_once(self) -> None:
        session = await self._pick_session()
        result: Dict[str, Any] = {
            "playing": False,
            "available": False,
            "title": "",
            "artist": "",
            "app_id": "",
            "is_spotify": False,
            "position": 0.0,
            "duration": 0.0,
            "cover": None,
            "cover_track": self._cover_track,
            "media_track": None,
            "like_enabled": self.spotify_like_enabled,
        }
        if session is not None:
            info = session.get_playback_info()
            props = await session.try_get_media_properties_async()
            timeline = session.get_timeline_properties()
            start = timeline.start_time.total_seconds()
            playing = int(info.playback_status) == 4
            duration = max(0.0, timeline.end_time.total_seconds() - start)
            position = max(0.0, timeline.position.total_seconds() - start)
            if playing:
                elapsed = max(
                    0.0,
                    (datetime.datetime.now(datetime.timezone.utc) - timeline.last_updated_time).total_seconds(),
                )
                rate = info.playback_rate if info.playback_rate is not None else 1.0
                position += elapsed * rate
            app_id = session.source_app_user_model_id or ""
            is_spotify = "spotify" in app_id.lower()
            track = (props.title or "", props.artist or "", props.album_title or "")
            result.update(
                available=True,
                playing=playing,
                title=props.title or "",
                artist=props.artist or "",
                app_id=app_id,
                is_spotify=is_spotify,
                position=min(duration, position) if duration else 0.0,
                duration=duration,
                media_track=track,
            )

            if self._cover_track != track or not self._state.get("cover"):
                self._cover_track = None
                if props.thumbnail:
                    stream = None
                    try:
                        from winrt.windows.storage.streams import Buffer, InputStreamOptions

                        stream = await props.thumbnail.open_read_async()
                        if stream.size <= 4 * 1024 * 1024:
                            buf = await stream.read_async(
                                Buffer(stream.size), stream.size, InputStreamOptions.NONE
                            )
                            with Image.open(io.BytesIO(bytes(memoryview(buf)))) as source:
                                source.thumbnail((128, 128))
                                dest = self.cache_dir / "media_cover.png"
                                tmp = self.cache_dir / "media_cover.png.tmp"
                                source.convert("RGB").save(tmp, format="PNG")
                                os.replace(tmp, dest)
                                result["cover"] = str(dest)
                                self._cover_track = track
                    except Exception:
                        logger.debug("Media artwork unavailable")
                    finally:
                        if stream is not None:
                            try:
                                stream.close()
                            except Exception:
                                pass
            else:
                result["cover"] = self._state.get("cover")

        result["cover_track"] = self._cover_track
        track = result["media_track"] if result["is_spotify"] else None
        changed_like = False
        if self.spotify_like_enabled:
            with self._lock:
                changed_like = track != self._like_track
                if changed_like:
                    self._like_track = track
                    self._like_value = {
                        "like_saved": None,
                        "like_ready": False,
                        "like_message": self.i18n.t("media.like_setup"),
                    }
                result.update(self._like_value, like_busy=self._like_busy)
        else:
            result.update(like_saved=None, like_ready=False, like_busy=False, like_message="")

        self._publish(result)
        if self.spotify_like_enabled and changed_like:
            try:
                self._like_commands.put_nowait(("observe", track))
            except queue.Full:
                with self._lock:
                    self._like_track = object()

    async def _send_command(self, action: str) -> None:
        session = await self._pick_session()
        if not session:
            return
        method = {
            "previous": "try_skip_previous_async",
            "toggle": "try_toggle_play_pause_async",
            "next": "try_skip_next_async",
        }[action]
        await getattr(session, method)()

    async def _loop(self) -> None:
        deadline = 0.0
        while not self._stopped.is_set():
            if self._visible.is_set():
                try:
                    while self._visible.is_set() and not self._commands.empty():
                        await asyncio.wait_for(self._send_command(self._commands.get_nowait()), 3.0)
                    if self._visible.is_set() and time.monotonic() >= deadline:
                        deadline = time.monotonic() + self.interval
                        await asyncio.wait_for(self._poll_once(), 3.0)
                except Exception as exc:
                    self._media_manager = None
                    self._publish(
                        {
                            **self._state,
                            "playing": False,
                            "available": False,
                            "title": "",
                            "artist": "",
                        }
                    )
                    logger.debug("SMTC unavailable: %s", type(exc).__name__)
            else:
                while not self._commands.empty():
                    self._commands.get_nowait()
            await asyncio.sleep(0.25)

    def _like_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                cmd, track = self._like_commands.get(timeout=0.25)
            except queue.Empty:
                continue
            message = None
            try:
                with self._lock:
                    current = self._state.get("media_track") if self._state.get("is_spotify") else None
                if track != current:
                    continue
                if cmd == "observe":
                    self._like_state.observe(track)
                elif cmd == "retry" and self._visible.is_set():
                    val = self._like_state.observe(track, force=True)
                    message = val.get("like_message")
                elif self._visible.is_set():
                    message = self._like_state.toggle(track)
                val = self._like_state.snapshot()
                with self._lock:
                    if self._state.get("media_track") == track:
                        self._like_value = val
                        self._state.update(val)
                if message and self.on_toast:
                    self.on_toast(message)
            except Exception:
                logger.debug("Spotify like worker error")
            finally:
                with self._lock:
                    if cmd in ("toggle", "retry"):
                        self._like_busy = False
                        self._state["like_busy"] = False
                if self.on_change:
                    self.on_change()
