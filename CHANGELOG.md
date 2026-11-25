# Changelog

All notable changes to StartHub are documented in this file.

## [0.1.0] - 2026-11-25

Initial public open-source release of StartHub (`Alexsander720/starthub`).

### Added
- **Core Acrylic Engine:** Native Win32 `UpdateLayeredWindow` premultiplied DIB rendering, DWM blur-behind, Windows 11 rounded corners, and `DV2ControlHost` Start11 tracker.
- **Dynamic Layout Engine:** Automatic vertical stacking, expandable card height distribution, pinned bottom bar support, smooth scroll viewport on compact heights, and Start11 TileMode=0 center-overlay calibration.
- **Themes:** `multi_accent` (default) and `single_accent` (with `#RRGGBB` or live Windows DWM `"windows"` accent color sync, always preserving critical alert colors).
- **Localization:** Built-in English (`en`, default), Russian (`ru`), and Ukrainian (`uk`).
- **Demo Mode (`--demo`):** Instant full-showcase preview with synthetic data and zero keys required.
- **System Tray:** Reload config, open `config.json`, toggle Demo mode, live toggle Multi/Single Accent theme, pause tracking, and quit.
- **Tier 1 Widgets (Zero API Keys):**
  - Visibility-gated System Monitor (CPU / GPU + temp / RAM).
  - Universal Windows SMTC Media Player (Spotify, YouTube Music, Tidal, browsers, etc.) + optional Spotify PKCE Like OAuth.
  - Peripherals battery tiles (Mouse, Logitech HID++ Keyboard, DualSense HID/DSX UDP, optional Handheld file) + interactive Windows Bluetooth drawer.
  - Free Open-Meteo Weather + Clock center transparent overlays and wing Weather & Calendar cards.
- **Tier 2 Opt-In Widgets:**
  - EcoFlow DELTA 3 / DELTA 2 Cloud MQTT (TLS 8883 + Protobuf/JSON) with 2 MB `RotatingFileHandler` and leak-free atomic JSON writes.
  - Philips Hue local LAN HTTPS room/light controls + brightness dimmer.
  - Android ADB Phone Hub (`scrcpy`, clipboard screenshots, gallery, opt-in SMS/2FA OTP) with clean vector chassis.
  - Todoist REST API v1 tasks with auto-discovered projects and 1-click completion.
  - Universal Custom JSON metrics cards (local file or `localhost` URL).
  - Start11 Custom Tile Pack Switcher (`tools/tile_switcher.py`) with automatic `.reg` backup and rollback.
- **Safety & CI:** Offline `tools/scan_private.py` privacy gate, full `pytest` suite including headless PNG render tests, `install.ps1`, and GitHub Actions CI.
