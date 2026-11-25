# StartHub Setup Guide

This guide covers installing and customizing StartHub on Windows 11 — with **Stardock Start11**, the **native Windows 11 Start Menu**, or **Global Hotkey** mode.

## Prerequisites

- **Windows 11** (64-bit)
- **Portable EXE users:** No Python or Git needed — download `StartHub-v0.1.0-win64-portable.zip` from Releases and run `StartHub.exe`.
- **Source users:** Python 3.10+ (the installer can install Python 3.12 via `winget` automatically with `-InstallPython`).
- **Start Menu compatibility:**
  - `trigger_mode: "auto"` (default) tracks **Start11** (`DV2ControlHost`) first, and automatically falls back to the **native Windows 11 Start Menu** (`StartMenuExperienceHost` + `DWMWA_CLOAKED`).
  - Press **`Alt+Space`** (configurable) anytime to toggle the wings as a standalone HUD — even without opening Start.

## Step 1 — Install (Zero Friction)

Double-click **`Install.cmd`** (handles PowerShell ExecutionPolicy automatically), or run in PowerShell:

```powershell
# Recommended: core + optional hardware/EcoFlow extras + Windows Startup shortcut
.\install.ps1 -Optional -AutoStart

# If Python 3.10+ is not installed yet:
.\install.ps1 -InstallPython -Optional -AutoStart
```

`install.ps1` ignores Windows 11's fake Microsoft Store `python.exe` alias, creates an isolated `.venv`, installs dependencies, and copies `config.example.json` → `config.json`.

## Step 2 — Preview in Demo Mode (10 Seconds)

```powershell
.\.venv\Scripts\python.exe -m starthub --demo --preview
```

Test `single_accent` synced to your Windows 11 accent color:

```powershell
.\.venv\Scripts\python.exe -m starthub --demo --preview --theme single_accent --accent windows
```

## Step 3 — Customize Visually (GUI Settings)

Launch **`StartHub.cmd`** (or `.\.venv\Scripts\pythonw.exe -m starthub --settings`) and open **Tray → Settings...**:

- **Appearance & Triggers:** Pick a preset (*Balanced*, *Minimal*, *Productivity*), toggle `Multi-Accent` / `Single-Accent`, sync Windows accent, adjust opacity/blur/radius, choose Trigger Mode (`auto` / `start11` / `windows11` / `hotkey`), and customize your hotkey.
- **Widgets & Layout:** Enable/disable any Tier 1 or Tier 2 widget, reorder vertically (`↑ ↓`), or move cards between Left and Right wings (`← →`).
- **Weather & Peripherals:** Type your city name and click **Search City** (free Open-Meteo geocoding fills lat/lon automatically), choose `°C`/`°F`, toggle `auto_hide_offline` peripherals, and configure Focus Timer lengths.
- **Integrations:** Use 1-click **Find Bridge** + **Press Link & Pair** for Philips Hue, or configure Todoist, EcoFlow, and Android ADB. Saving preserves any `${ENV_VAR}` placeholders in `config.json`.

## CLI Reference

```text
python -m starthub [options]

  --demo                    Run with synthetic showcase data (all modules enabled)
  --preview                 Keep wings visible on screen without waiting for Start
  --settings                Open the GUI Settings window immediately on startup
  --doctor                  Print a sanitized environment diagnostics report and exit
  --trigger MODE            Override trigger mode (auto | start11 | windows11 | hotkey)
  --theme MODE              Override theme mode (multi_accent | single_accent)
  --accent COLOR            Override accent (#RRGGBB or "windows")
  --lang LANG               Override language (en | ru | uk)
  --config PATH             Use a custom config.json path
  --render-test DIR         Headlessly render PNG previews into DIR and exit
```

## Troubleshooting

1. **Run diagnostics first:** `.\.venv\Scripts\python.exe -m starthub --doctor` (or **Tray → Copy Diagnostics Report**). It prints OS, monitors, GPU backend, audio endpoints, Start11/Win11 detection, and dependency status with zero secrets.
2. **Panels don't appear with Start Menu:**
   - Ensure StartHub isn't paused in the tray.
   - Try pressing `Alt+Space` or launching with `--preview` to verify rendering independently.
3. **1080p / 125–150% DPI screens:**
   - Keep `"adaptive_width": true` (default) so wings gracefully narrow to fit beside Start without overlapping it.
4. **GPU shows `—`:**
   - NVIDIA uses `nvidia-ml-py` (`-Optional`) or `nvidia-smi`. AMD and Intel GPUs automatically use Windows PDH GPU Engine counters via `pywin32`.
