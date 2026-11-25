# StartHub Widget Configuration Guide

All **Tier 1** widgets work out of the box with zero API keys. All **Tier 2** widgets are opt-in (`"enabled": false` by default) and support `${ENV_VAR}` placeholders so secrets never sit in plaintext.

You can configure every widget visually via **Tray → Settings...** or by editing `config.json`.

---

## Tier 1 Highlights (Zero Keys)

- **Audio Volume & Output Switcher (`audio_control`):** Click the speaker to Mute/Unmute, click any of the 10 volume steps, or click the device pill (`⇄`) to cycle between Headphones, Speakers, and Monitor audio outputs via Windows Core Audio.
- **System Monitor (`system_monitor`):** Visibility-gated CPU, GPU (NVIDIA NVML / `nvidia-smi` + universal AMD/Intel Windows PDH fallback), GPU temp, and RAM.
- **Storage & Network (`storage_network`):** Auto-detects fixed drives (`drives: ["auto"]` or explicit `["C:", "D:"]`, up to `max_drives: 3`) + live Download/Upload rates.
- **Peripherals & Bluetooth (`peripherals`):** Reads Windows Bluetooth/BLE PnP batteries (AirPods, Sony WH-1000, MX Master BT, Keychron), Xbox/XInput controllers, DualSense (HID or DSX UDP), and Logitech HID++ (Unifying, Logi Bolt, Lightspeed). Set `"auto_hide_offline": true` to hide disconnected device slots.
- **Tasks (`tasks`):** Works locally out of the box (`mode: "auto"` uses offline `cache/local_tasks.json`; click `+` to add tasks and click circles to complete them). Automatically switches to Todoist when `todoist.enabled` and `api_token` are configured.
- **Focus / Pomodoro Timer (`focus_timer`):** Click the `Focus`/`Break` pill to switch phases, play/pause, or reset. Configurable `work_minutes`, `break_minutes`, and `sound_on_done`.
- **Weather (`weather`):** Free Open-Meteo API with built-in city geocoding (`"auto_geocode": true`). Set `"show_card": "auto"` to avoid duplicating the Start11 center weather overlay.
- **Quick Actions (`quick_actions`):** Built-in actions: `snip`, `terminal`, `lock`, `sleep`, `explorer`, `starthub_settings`, any `https://...` URL, or a custom `"command"`.

---

## Tier 2 — Opt-In Modules

### 1. EcoFlow Power Station (DELTA 3 / DELTA 2)

Requires optional extras (`.\install.ps1 -Optional`). Supports **Cloud MQTT** (TLS `8883`, Protobuf + JSON fallback, 2 MB rotating logs) or an **external `state_file`**.

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

Leave `"device_sn": ""` to auto-discover the first bound station on your account.

### 2. Philips Hue (Local LAN HTTPS — 1-Click Pairing)

Open **Tray → Settings → Integrations → Philips Hue**:
1. Click **Find Bridge** (or enter your bridge's LAN IP).
2. Press the physical Link button on your Hue Bridge.
3. Click **Press Link & Pair**, then **Load Rooms** → **Apply & Save**.

Manual config equivalent:

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

### 3. Custom JSON Cards (`columns` / `hero` / `list`)

Reads any local JSON file or `localhost` HTTP endpoint (`http://127.0.0.1:...`). Ready-to-run Python example scripts live in [`examples/custom_json/`](../examples/custom_json/).

- **`"layout": "columns"`**: 1–3 columns with big values, optional `percent` progress bars, `tag`, `sublabel`, and `status` (`info`/`ok`/`warn`/`danger`).
- **`"layout": "hero"`**: headline `hero_value` + `hero_sub` + up to 2 lower stat tiles (`metrics`).
- **`"layout": "list"`**: up to 4 compact key–value rows (`items: [{"label": "...", "value": "...", "status": "ok"}]`).

### 4. Todoist

Set `TODOIST_API_TOKEN` (from Todoist **Settings → Integrations → Developer**) or paste it in GUI Settings under **Integrations → Tasks & Todoist**. Leave `"projects": []` to auto-discover all projects.

### 5. Android Phone Hub (ADB + scrcpy)

Requires `adb` and [`scrcpy`](https://github.com/Genymobile/scrcpy) in `PATH` or configured by path. Supports 1-click screen mirror, instant phone screenshot straight to Windows clipboard (`Ctrl+V`), collapsible recent photos + gallery modal, and opt-in SMS/2FA OTP bar.

### 6. Optional Spotify Liked Songs Heart (PKCE OAuth)

Run the one-time PKCE auth CLI (no client secret needed):

```powershell
.\.venv\Scripts\python.exe -m starthub.providers.spotify_like --auth --client-id YOUR_32_CHAR_CLIENT_ID
```

Then enable `widgets.media_player.spotify_like.enabled: true` and set `SPOTIFY_CLIENT_ID`.

### 7. Start11 Tile Pack Switcher

Place user-created tile packs in subfolders inside `packs/` (see `packs/example_minimal/`). Enable `"tile_switcher": { "enabled": true }` — the quick-switch pill appears in the Tasks header when Tasks is enabled, or as a dedicated **Start11 Tile Pack** bar when Tasks is disabled.
