"""Optional Spotify Liked Songs PKCE OAuth client (explicit user auth only)."""
from __future__ import annotations

import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlsplit
import webbrowser

import requests

from ..config import DEFAULT_CACHE_DIR

REDIRECT_URI = "http://127.0.0.1:43827/callback"
SCOPES = "user-library-read user-library-modify user-read-currently-playing"
SETUP_MESSAGE = "Spotify Like requires one-time PKCE setup (see docs/WIDGETS.md)"


class SpotifyError(Exception):
    """Static sanitized error without leaking HTTP headers, bodies, or tokens."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def secure_write_token(path: Path | str, token: Dict[str, Any]) -> None:
    """Atomically save token JSON with owner-only filesystem permissions."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{secrets.token_hex(8)}.tmp")
    if os.name == "nt":
        try:
            import ntsecuritycon
            import pywintypes
            import win32api
            import win32con
            import win32file
            import win32security

            process_token = win32security.OpenProcessToken(
                win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
            )
            try:
                sid = win32security.GetTokenInformation(process_token, win32security.TokenUser)[0]
            finally:
                process_token.Close()
            acl = win32security.ACL()
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, sid)
            descriptor = win32security.SECURITY_DESCRIPTOR()
            descriptor.SetSecurityDescriptorDacl(True, acl, False)
            descriptor.SetSecurityDescriptorControl(
                win32security.SE_DACL_PROTECTED, win32security.SE_DACL_PROTECTED
            )
            attrs = pywintypes.SECURITY_ATTRIBUTES()
            attrs.SECURITY_DESCRIPTOR = descriptor
            attrs.bInheritHandle = False
            handle = win32file.CreateFile(
                str(tmp),
                win32con.GENERIC_WRITE,
                0,
                attrs,
                win32con.CREATE_NEW,
                win32con.FILE_ATTRIBUTE_NORMAL,
                None,
            )
            try:
                win32file.WriteFile(handle, json.dumps(token).encode("utf-8"))
                win32file.FlushFileBuffers(handle)
            finally:
                handle.Close()
            os.replace(tmp, target)
            return
        except ImportError:
            pass

    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(token, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, target)


class SpotifyClient:
    def __init__(
        self,
        cache: Path = DEFAULT_CACHE_DIR,
        client_id: str = "",
        api_base: str = "https://api.spotify.com/v1",
        accounts_base: str = "https://accounts.spotify.com",
        session: Optional[requests.Session] = None,
        library_mode: str = "auto",
    ):
        self.cache = Path(cache)
        self.api_base = api_base.rstrip("/")
        self.accounts_base = accounts_base.rstrip("/")
        self.http = session or requests.Session()
        self.library_mode = library_mode
        self.retry_after = 0.0
        self.token: Dict[str, Any] = {}
        self.client_id = str(client_id or "").strip()
        if not self.client_id:
            try:
                self.client_id = (self.cache / "spotify_client_id.txt").read_text(encoding="utf-8-sig").strip()
            except OSError:
                pass
        if not re.fullmatch(r"[0-9a-fA-F]{32}", self.client_id):
            self.client_id = ""
        try:
            token = json.loads((self.cache / "spotify_token.json").read_text(encoding="utf-8"))
            if isinstance(token, dict) and token.get("client_id") == self.client_id:
                self.token = token
        except (OSError, ValueError):
            pass

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.token.get("refresh_token"))

    def _request(self, method: str, url: str, **kwargs):
        if time.monotonic() < self.retry_after:
            raise SpotifyError("Spotify: rate limited, please wait", 429)
        try:
            response = self.http.request(method, url, timeout=(2, 4), allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise SpotifyError("Spotify: network unavailable") from None
        if response.status_code == 429:
            try:
                delay = max(1.0, min(86400.0, float(response.headers.get("Retry-After", "30"))))
            except ValueError:
                delay = 30.0
            self.retry_after = time.monotonic() + delay
        if not 200 <= response.status_code < 300:
            messages = {
                401: SETUP_MESSAGE,
                403: "Spotify: access denied; check scopes and account permissions",
                429: "Spotify: too many requests, try again later",
            }
            raise SpotifyError(messages.get(response.status_code, "Spotify: request failed"), response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise SpotifyError("Spotify: invalid JSON response") from None

    def _store(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
            raise SpotifyError("Spotify: invalid auth payload")
        token = dict(self.token)
        token.update(data)
        token.update(client_id=self.client_id, expires_at=time.time() + float(data.get("expires_in", 3600)) - 30)
        if not token.get("refresh_token"):
            raise SpotifyError(SETUP_MESSAGE)
        try:
            secure_write_token(self.cache / "spotify_token.json", token)
        except OSError:
            raise SpotifyError("Spotify: failed to store token safely") from None
        self.token = token

    def _refresh(self) -> None:
        if not self.configured:
            raise SpotifyError(SETUP_MESSAGE)
        data = self._request(
            "POST",
            f"{self.accounts_base}/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.token["refresh_token"],
                "client_id": self.client_id,
            },
        )
        self._store(data)

    def api(self, method: str, path: str, **kwargs):
        if not self.configured:
            raise SpotifyError(SETUP_MESSAGE)
        if not self.token.get("access_token") or self.token.get("expires_at", 0) <= time.time():
            self._refresh()
        for attempt in range(2):
            try:
                return self._request(
                    method,
                    self.api_base + path,
                    headers={"Authorization": f"Bearer {self.token['access_token']}"},
                    **kwargs,
                )
            except SpotifyError as exc:
                if exc.status != 401 or attempt:
                    raise
                self._refresh()

    @staticmethod
    def _matches(item: Dict[str, Any], track) -> bool:
        def norm(s):
            return " ".join(str(s).casefold().split())

        title, artist = track[:2]
        artists = [norm(a.get("name", "")) for a in item.get("artists", []) if isinstance(a, dict)]
        labels = set(artists)
        labels.update(sep.join(artists) for sep in (", ", "; ", " & ", " / ", " and "))
        album = item.get("album") or {}
        album_matches = (
            len(track) <= 2
            or not track[2]
            or not album.get("name")
            or norm(album["name"]) == norm(track[2])
        )
        return norm(item.get("name")) == norm(title) and norm(artist) in labels and album_matches

    def resolve_track(self, track) -> str:
        current = self.api("GET", "/me/player/currently-playing")
        item = current.get("item") if isinstance(current, dict) else None
        if (
            not isinstance(item, dict)
            or item.get("type") != "track"
            or item.get("is_local")
            or not self._matches(item, track)
        ):
            raise SpotifyError("Spotify: active track mismatch")
        ident = item.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9]{22}", ident):
            raise SpotifyError("Spotify: track ID unavailable")
        return ident

    def _library(self, method: str, ident: str):
        modes = ("modern", "legacy") if self.library_mode == "auto" else (self.library_mode,)
        for mode in modes:
            path = "/me/library" if mode == "modern" else "/me/tracks"
            if method == "GET":
                path += "/contains"
            params = {"uris": f"spotify:track:{ident}"} if mode == "modern" else {"ids": ident}
            try:
                result = self.api(method, path, params=params)
                if self.library_mode == "auto":
                    self.library_mode = mode
                return result
            except SpotifyError as exc:
                if len(modes) < 2 or mode == "legacy" or exc.status not in (404, 405):
                    raise

    def contains(self, ident: str) -> bool:
        result = self._library("GET", ident)
        if not isinstance(result, list) or len(result) != 1 or type(result[0]) is not bool:
            raise SpotifyError("Spotify: like status unavailable")
        return result[0]

    def set_saved(self, ident: str, saved: bool) -> None:
        self._library("PUT" if saved else "DELETE", ident)

    def authorize(self, open_browser=webbrowser.open, timeout: int = 180) -> None:
        if not self.client_id:
            raise SpotifyError(SETUP_MESSAGE)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        state = secrets.token_urlsafe(32)
        received: Dict[str, Any] = {}
        callback_done = threading.Event()
        callback_lock = threading.Lock()

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                valid = url.path == "/callback" and secrets.compare_digest(query.get("state", [""])[0], state)
                if valid and ("code" in query or "error" in query):
                    with callback_lock:
                        if not callback_done.is_set():
                            received.update(code=query.get("code", [""])[0], error=bool(query.get("error")))
                            callback_done.set()
                try:
                    self.send_response(200 if valid else 400)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(("Spotify authorized. You can close this window." if valid else "Invalid callback.").encode("utf-8"))
                except OSError:
                    pass

        class CallbackServer(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

            def get_request(self):
                sock, address = super().get_request()
                sock.settimeout(0.5)
                return sock, address

        parsed = urlsplit(REDIRECT_URI)
        try:
            server = CallbackServer(("127.0.0.1", parsed.port or 43827), Callback)
        except OSError:
            raise SpotifyError("Spotify: callback port already in use") from None
        with server:
            server.timeout = 0.1
            auth_url = f"{self.accounts_base}/authorize?" + urlencode(
                {
                    "response_type": "code",
                    "client_id": self.client_id,
                    "scope": SCOPES,
                    "redirect_uri": REDIRECT_URI,
                    "state": state,
                    "code_challenge_method": "S256",
                    "code_challenge": challenge,
                }
            )
            if not open_browser(auth_url):
                raise SpotifyError("Spotify: could not open browser")
            deadline = time.monotonic() + timeout
            while not callback_done.is_set() and time.monotonic() < deadline:
                server.handle_request()
        if not received or received.get("error") or not received.get("code"):
            raise SpotifyError("Spotify: authorization cancelled or timed out")
        data = self._request(
            "POST",
            f"{self.accounts_base}/api/token",
            data={
                "grant_type": "authorization_code",
                "code": received["code"],
                "redirect_uri": REDIRECT_URI,
                "client_id": self.client_id,
                "code_verifier": verifier,
            },
        )
        self._store(data)


class LikeState:
    def __init__(self, client: Optional[SpotifyClient] = None, added_msg: str = "Added to Liked Songs", removed_msg: str = "Removed from Liked Songs"):
        self.client = client or SpotifyClient()
        self.added_msg = added_msg
        self.removed_msg = removed_msg
        self.track = None
        self.ident: Optional[str] = None
        self.saved: Optional[bool] = None
        self.message = SETUP_MESSAGE

    def snapshot(self) -> Dict[str, Any]:
        return {
            "like_saved": self.saved,
            "like_ready": self.ident is not None and self.saved is not None,
            "like_message": self.message,
        }

    def observe(self, track, *, force: bool = False) -> Dict[str, Any]:
        if track == self.track and not force:
            return self.snapshot()
        self.track = track
        self.ident = None
        self.saved = None
        self.message = SETUP_MESSAGE
        if not track or not self.client.configured:
            return self.snapshot()
        try:
            ident = self.client.resolve_track(track)
            saved = self.client.contains(ident)
            self.ident, self.saved, self.message = ident, saved, ""
        except SpotifyError as exc:
            self.message = str(exc)
        return self.snapshot()

    def toggle(self, track) -> str:
        if track != self.track or self.ident is None or self.saved is None:
            return self.message or "Spotify: waiting for current track"
        try:
            if self.client.resolve_track(track) != self.ident:
                return "Spotify: track changed, try again"
            target = not self.saved
            self.client.set_saved(self.ident, target)
            self.saved = target
            return self.added_msg if target else self.removed_msg
        except SpotifyError as exc:
            self.message = str(exc)
            if exc.status in (401, 403):
                self.ident = None
                self.saved = None
            return self.message


def main() -> int:
    parser = argparse.ArgumentParser(description="One-time Spotify PKCE OAuth setup for StartHub")
    parser.add_argument("--auth", action="store_true", help="Launch browser PKCE login flow")
    parser.add_argument("--client-id", default="", help="Spotify Developer App Client ID (32 hex chars)")
    args = parser.parse_args()
    if not args.auth:
        parser.print_help()
        return 0
    try:
        SpotifyClient(client_id=args.client_id).authorize()
    except SpotifyError as exc:
        print(str(exc))
        return 1
    print("Spotify authorized! Token saved with owner-only permissions. Restart StartHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
