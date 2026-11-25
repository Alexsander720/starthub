# StartHub Widget Configuration Guide

All **Tier 2** widgets are **opt-in** (`"enabled": false` by default). Sensitive keys support `${ENV_VAR}` placeholders so you can store secrets in Windows user environment variables instead of plaintext in `config.json`.

---

## 1. EcoFlow Power Station (DELTA 3 / DELTA 2)

Requires optional dependencies:

```powershell
.\.venv\Scripts\pip.exe install -r requirements-optional.txt
```

### Mode A — Built-in Cloud MQTT (Recommended)

Connects directly to EcoFlow's MQTT broker over TLS `8883` using Protobuf (DELTA 3) with JSON fallback (DELTA 2), bounded 2 MB rotating logs (`cache/logs/ecoflow.log`), and clean atomic state persistence.

```json
"ecoflow": {
  "enabled": true,
  "mode": "mqtt",
  "email": "${ECOFLOW_EMAIL}",
  "password": "${ECOFLOW_PASSWORD}",
  "device_sn": "${ECOFLOW_DEVICE_SN}",
  "device_name": "DELTA 3 Max",
  "region": "europe",
  "image_path": "",
  "charge_watt_steps": [200, 400, 600, 800, 1000, 1500]
}
```

- Leave `"device_sn": ""` to auto-discover the first bound station on your account.
- Set `"region"` to `"europe"` or `"us"` (StartHub automatically falls back between regional endpoints).
- Optional `"image_path"`: path to your own transparent PNG if you prefer a photo over the built-in vector silhouette.

### Mode B — External State File

If you already run your own EcoFlow daemon that writes a JSON snapshot:

```json
"ecoflow": {
  "enabled": true,
  "mode": "state_file",
  "state_file": "path/to/state.json",
  "command_file": "path/to/command.json",
  "device_name": "DELTA 3"
}
```

---

## 2. Philips Hue (Local LAN HTTPS)

StartHub talks **only** to private RFC1918 LAN IPv4 addresses (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`).

1. Find your Hue Bridge IP in the Philips Hue app or your router.
2. Generate a local `app_key` via the Hue Bridge CLIP API (press the physical Link button, then `POST https://<bridge_ip>/api` with `{"devicetype": "starthub#windows"}`).
3. List your room/group IDs (`GET https://<bridge_ip>/api/<app_key>/groups`) and light IDs (`/lights`).
4. Add them to `config.json`:

```json
"philips_hue": {
  "enabled": true,
  "bridge_ip": "192.168.1.50",
  "app_key": "${HUE_APP_KEY}",
  "targets": [
    { "id": "1", "kind": "groups", "label": "Office Light", "icon": "bulb", "dimmer": true },
    { "id": "2", "kind": "lights", "label": "Monitor Bar", "icon": "monitor", "dimmer": false }
  ]
}
```

---

## 3. Custom JSON Cards (Home Assistant, Pi-hole, AI Quotas, Scripts)

Display any metric from a local JSON file or a `localhost` HTTP endpoint (`http://127.0.0.1:...`).

```json
"custom_json": {
  "enabled": true,
  "allow_remote_urls": false,
  "cards": [
    {
      "id": "homelab",
      "title": "Home Lab",
      "source": "cache/homelab.json",
      "refresh_sec": 15,
      "click_url": "http://127.0.0.1:3000"
    }
  ]
}
```

Have your script write JSON matching this clean schema (1 to 3 items in `metrics`):

```json
{
  "title": "Home Lab",
  "badge": "3 nodes",
  "subtitle": "Updated 19:10",
  "url": "http://127.0.0.1:3000",
  "metrics": [
    { "label": "NAS Pool", "value": "64%", "percent": 64, "sublabel": "7.6 / 12 TB", "tag": "OK", "status": "ok" },
    { "label": "Pi-hole",  "value": "24%", "percent": 24, "sublabel": "14.2k blocked", "tag": "DNS", "status": "info" },
    { "label": "UPS Load", "value": "92%", "percent": 92, "sublabel": "Peak alert", "tag": "HIGH", "status": "danger" }
  ]
}
```

Supported `"status"` values: `"info"`, `"ok"`, `"warn"`, `"danger"`. Even in `single_accent` theme mode, `"warn"` and `"danger"` preserve alert colors.

---

## 4. Todoist

1. Copy your API token from Todoist **Settings → Integrations → Developer**.
2. Set `TODOIST_API_TOKEN` as an environment variable (recommended) or place it in `config.json`:

```json
"todoist": {
  "enabled": true,
  "api_token": "${TODOIST_API_TOKEN}",
  "poll_interval_sec": 30,
  "projects": []
}
```

Leave `"projects": []` to auto-discover all your Todoist projects, or specify explicit `[{"id": "...", "name": "..."}]` entries to pin a custom order. Click the project title to cycle projects; click any task circle to complete it in 1 click.

---

## 5. Android Phone Hub (ADB + scrcpy)

Requires Android `adb` (Platform Tools) and [`scrcpy`](https://github.com/Genymobile/scrcpy) in `PATH` or configured by path.

```json
"phone_adb": {
  "enabled": true,
  "device_name": "Pixel 9 Pro",
  "adb_path": "adb",
  "scrcpy_path": "scrcpy",
  "device_serial": "",
  "wifi_address": "",
  "unlock_pin": "${PHONE_UNLOCK_PIN}",
  "enable_photos": true,
  "enable_sms_otp": false,
  "auto_clip_sync": true,
  "frame_image_path": "",
  "image_editor_path": ""
}
```

- `unlock_pin` is completely optional; leave empty to skip automated lockscreen PIN entry.
- `enable_sms_otp` queries Android's SMS inbox via ADB (requires device permissions/root on modern Android; disabled by default).
- `frame_image_path`: optional custom phone frame PNG; defaults to the built-in vector phone chassis.

---

## 6. Optional Spotify Liked Songs Heart (PKCE OAuth)

Media transport & cover art already work for Spotify and every other player via Windows SMTC with **zero setup**. If you also want the **Like / Heart** button synced with your Spotify library:

1. Create a free app at [developer.spotify.com](https://developer.spotify.com/dashboard) with Redirect URI `http://127.0.0.1:43827/callback`.
2. Copy the 32-character Client ID (no client secret is needed — StartHub uses PKCE).
3. Run the one-time authorization CLI:

```powershell
.\.venv\Scripts\python.exe -m starthub.providers.spotify_like --auth --client-id YOUR_32_CHAR_CLIENT_ID
```

4. Enable `widgets.media_player.spotify_like.enabled: true` in `config.json` and set `SPOTIFY_CLIENT_ID`. Tokens are stored with owner-only Windows DACL permissions inside `cache/spotify_token.json`.

---

## 7. Start11 Tile Pack Switcher

Create one subfolder per pack inside `packs/` (see `packs/example_minimal/` for a template):

```text
packs/
├── minimal_dark/
│   ├── pack.json
│   └── terminal.png
└── minimal_light/
    ├── pack.json
    └── terminal.png
```

Enable `"tile_switcher": { "enabled": true, "packs_dir": "packs" }` in `config.json` to show the quick-switch pill in the right wing, or test from the CLI:

```powershell
python tools/tile_switcher.py --list
python tools/tile_switcher.py --pack example_minimal          # dry-run (no registry writes)
python tools/tile_switcher.py --pack example_minimal --apply  # backs up HKCU Start11 key, applies, refreshes
```
