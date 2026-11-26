# Changelog

All notable changes to StartHub are documented in this file.

## [0.1.0] - 2026-11-26

### Added
- **Multi-trigger Windows 11 support (`window.trigger_mode`):**
  - `auto` (tracks Stardock Start11 `DV2ControlHost` first, automatically falls back to native Windows 11 Start Menu `StartMenuExperienceHost` via `DWMWA_CLOAKED`)
  - `start11`, `windows11`, and standalone `hotkey` mode (`Alt+Space` global toggle via Win32 `RegisterHotKey`)
- **Ironclad Start11 Zero-Overlap & Click-Through Guard:**
  - Center Weather & Clock overlays use `WS_EX_TRANSPARENT` (100% click-through — tiles and context menus behind or near them are never blocked)
  - Double collision verification against both Start11 registry `tile_rects` and live native `LVM_GETITEMRECT` bounds with configurable `window.center_overlay_safety_margin` (default `14 px`)
  - Instant auto-hide on active Start11 search text, `#32768` context menus, or child popup occluders
  - Resilient Start11 `Groups` registry parsing across future Stardock updates; Weather automatically relocates into the side wing (`show_card: "auto"`) whenever tiles expand downward
- **Full Theme & Visual Customization Engine:**
  - **6 built-in presets** (`--preset` CLI flag & GUI selector): `fluent_dark`, `fluent_light` (frosted white + dark ink), `amoled_black`, `catppuccin_mocha`, `nord`, and `tokyo_night`
  - **Custom surface colors** (`theme.custom_colors`: `panel_bg`, `tile_bg`, `border`, `text_primary`, `text_secondary`) with automatic dark/light contrast adaptation
  - **Per-widget accent overrides** (`theme.role_overrides`) + `multi_accent` / `single_accent` / Windows DWM accent sync
  - **Shareable zero-secret profiles** (`Export Profile...` / `Import Profile...`) — exports only theme, layout, and window geometry with zero API keys, IPs, or personal paths
- **Smooth 120ms cubic ease-out fade-in** via `UpdateLayeredWindow` `SourceConstantAlpha`, single-instance mutex guard, 40ms low-power idle polling, and DPI/1080p adaptive wing widths (`adaptive_width`)
- **Rich Tier 1 zero-API-key widgets out of the box:**
  - **Audio Volume & 1-Click Output Switcher** (pure Windows Core Audio COM — master volume, mute, Headphones ⇄ Speakers ⇄ Monitor switching)
  - **System Monitor** with NVIDIA NVML/`nvidia-smi` + universal AMD/Intel Windows PDH GPU fallback
  - **Storage & Network** (auto-detected fixed drives + live Download/Upload throughput)
  - **Universal Peripherals & Bluetooth** (Windows BT/BLE PnP battery levels, Xbox/XInput, DualSense HID/DSX, Logitech Unifying/Bolt/Lightspeed, `auto_hide_offline` option)
  - **Local Quick Tasks** offline checklist with instant `+` creation dialog and seamless Todoist REST API v1 upgrade
  - **Focus / Pomodoro Timer** (25/5 Work & Break countdown with completion chime)
  - **Weather & Calendar** with free Open-Meteo city geocoding by name and smart `"show_card": "auto"` deduplication
  - **Customizable Quick Actions Bar** (Snip, Terminal, Lock, Settings, custom commands/URLs)
- **6-Tab GUI Settings & Visual Builders (`--settings` / Tray → Settings...):**
  - *Themes & Triggers* (6 presets, custom surface color pickers, per-widget color overrides, tile safety margin, triggers/hotkey)
  - *Widgets & Layout* (Balanced/Minimal/Productivity presets, enable/reorder `↑ ↓ ← →`, single-wing *Disable All*)
  - *Custom Cards & Actions* (GUI builders for Quick Actions buttons and Custom JSON cards)
  - *Weather & Peripherals*, *Integrations (Tier 2)* (including 1-click Philips Hue Bridge discovery, pairing & interactive room/light checkbox picker), and *Diagnostics & Updates*
  - Non-destructive config patching (`save_config_patch`) preserving `${ENV_VAR}` placeholders
- **Update Resilience & Config Migrations:**
  - Schema versioning (`config_version: 2`) with automatic non-destructive `migrate_config()`
  - Non-intrusive 24h cached GitHub Releases update checker (`starthub/updater.py`) — never auto-downloads or executes code
  - 1-click `Update.cmd` / `update.ps1` safe updater with automatic `config.json` backup to `cache/backups/`
- **Tier 2 opt-in modules:** EcoFlow DELTA 3/2 Cloud MQTT (TLS 8883 + Protobuf/JSON, bounded 2 MB rotating logs, atomic writes), Universal Smart Lights (**Philips Hue** LAN HTTPS + **Home Assistant** for Xiaomi/Yeelight/Tuya/Aqara/IKEA/Tapo/Govee/Zigbee + **WLED** LED strips, 1–4 tile grid + Right-Click dimmer selection), Android Phone Hub (ADB + scrcpy + clipboard screenshots + gallery + opt-in SMS/2FA), Custom JSON cards (`columns`, `hero`, `list` layouts + 6 ready scripts in `examples/custom_json/` including AI Quotas & Monthly Tracker), and Start11 Tile Pack Switcher with `--export` snapshot
- **Diagnostics, Docs & Distribution:** `python -m starthub --doctor`, `docs/CUSTOMIZATION.md` complete customization manual, `Install.cmd` / `StartHub.cmd` / `Update.cmd` launchers, fixed `install.ps1` (skips Windows 11 Microsoft Store Python alias, supports `-InstallPython`), PyInstaller `starthub.spec`, and automated GitHub Actions portable EXE release workflow
- **Multi-language UI & Docs:** English, Ukrainian (`README.uk.md`), and Russian (`README.ru.md`)
