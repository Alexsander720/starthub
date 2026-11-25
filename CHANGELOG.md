# Changelog

All notable changes to StartHub are documented in this file.

## [0.1.0] - 2026-11-25

### Added
- **Multi-trigger Windows 11 support (`window.trigger_mode`):**
  - `auto` (tracks Stardock Start11 `DV2ControlHost` first, automatically falls back to native Windows 11 Start Menu `StartMenuExperienceHost` via `DWMWA_CLOAKED`)
  - `start11`, `windows11`, and standalone `hotkey` mode (`Alt+Space` global toggle via Win32 `RegisterHotKey`)
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
- **Built-in Dark GUI Settings Window (`--settings` / Tray → Settings...):**
  - Quick layout presets (*Balanced*, *Minimal*, *Productivity*), visual Left/Right wing widget reorderer (`↑ ↓ ← →`), live theme/accent/opacity controls, city search, and **1-click Philips Hue Bridge discovery & pairing**
  - Non-destructive config patching (`save_config_patch`) preserving `${ENV_VAR}` placeholders
- **Tier 2 opt-in modules:** EcoFlow DELTA 3/2 Cloud MQTT (TLS 8883 + Protobuf/JSON, bounded 2 MB rotating logs, atomic writes), Philips Hue LAN HTTPS, Android Phone Hub (ADB + scrcpy + clipboard screenshots + gallery + opt-in SMS/2FA), Custom JSON cards (`columns`, `hero`, `list` layouts + 4 ready scripts in `examples/custom_json/`), and independent Start11 Tile Pack Switcher
- **Diagnostics & Distribution:** `python -m starthub --doctor` sanitized environment report, `Install.cmd` / `StartHub.cmd` zero-friction launchers, fixed `install.ps1` (skips Windows 11 Microsoft Store Python alias, supports `-InstallPython`), PyInstaller `starthub.spec`, and automated GitHub Actions portable EXE release workflow
- **Multi-language UI & Docs:** English, Ukrainian (`README.uk.md`), and Russian (`README.ru.md`)
