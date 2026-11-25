# StartHub Setup Guide

This guide walks through installing StartHub on Windows 11 alongside Stardock Start11.

## Prerequisites

1. **Windows 11** (64-bit)
2. **Python 3.10+** — install from [python.org](https://www.python.org/downloads/) (check **"Add Python to PATH"**)
3. **Stardock Start11** (v1 or v2) — StartHub tracks Start11's native window class (`DV2ControlHost`)
   - For the transparent **Center Weather & Clock overlay**, use Start11's **Windows 10 style** (`MenuMode=2`) with space left below your pinned tile groups.
   - StartHub wings also work with any Start11 style that exposes `DV2ControlHost`, and you can preview without Start11 via `--preview`.

## Step 1 — Install Dependencies

Open PowerShell in the cloned repository folder:

```powershell
# Core install (Tier 1 + HTTP widgets)
.\install.ps1

# Or install with optional hardware/MQTT extras + Windows auto-start:
.\install.ps1 -Optional -AutoStart
```

`install.ps1` creates an isolated `.venv`, installs dependencies, and copies `config.example.json` → `config.json` (which is git-ignored so your settings never leak).

## Step 2 — Test in Demo Mode

Verify visuals and theme modes before editing anything:

```powershell
.\.venv\Scripts\python.exe -m starthub --demo --preview
```

Try `single_accent` with your Windows 11 system accent color:

```powershell
.\.venv\Scripts\python.exe -m starthub --demo --preview --theme single_accent --accent windows
```

Press `Esc` on either panel or choose **Quit** from the StartHub tray icon to exit.

## Step 3 — Customize `config.json`

Edit `config.json` (or click **Open config.json** in the StartHub tray menu):

- **`language`**: `"en"` (default), `"ru"`, or `"uk"`.
- **`theme`**:
  - `"mode"`: `"multi_accent"` or `"single_accent"`
  - `"accent_color"`: hex color like `"#58BCFF"` or `"windows"` (reads DWM `AccentColor` from Windows registry)
  - `"panel_alpha"`: background translucency `80..255` (default `180` matches Start11 acrylic)
  - `"blur"`: `true` enables native Windows blur-behind
- **`widgets.weather`**: set your `city`, `latitude`, `longitude`, and `units` (`"metric"` or `"imperial"`). Uses free Open-Meteo with zero API keys.
- **`layout.left_widgets` & `layout.right_widgets`**: reorder or remove widgets freely — card heights and scrolling recalculate automatically.

## Step 4 — Run in Background

Launch windowless via `pythonw.exe`:

```powershell
.\.venv\Scripts\pythonw.exe -m starthub
```

If you used `-AutoStart` during installation, StartHub starts automatically when you sign in to Windows via a shortcut in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\StartHub.lnk`.

## CLI Reference

```text
python -m starthub [options]

  --demo                  Run with synthetic showcase data (all modules enabled)
  --preview               Keep panels visible on screen without waiting for Start11
  --config PATH           Use a custom config.json path
  --theme MODE            Override theme mode (multi_accent | single_accent)
  --accent COLOR          Override accent (#RRGGBB or "windows")
  --lang LANG             Override language (en | ru | uk)
  --render-test DIR       Headlessly render PNG previews into DIR and exit
```

## Troubleshooting

- **Panels don't appear when pressing the Windows key:**
  - Verify Start11 is running (not paused in tray).
  - Run with `--preview` to confirm rendering works independently of Start11.
- **No GPU stats in System Monitor:**
  - Install `nvidia-ml-py` (`.\install.ps1 -Optional`) or ensure `nvidia-smi` is available for NVIDIA GPUs. CPU & RAM always work via `psutil`.
- **Center Weather/Clock overlay doesn't show:**
  - StartHub only displays the center overlay when Start11 is in Windows 10 tile mode (`TileMode=0`), unscrolled, and has enough empty height below your pinned tile groups so it never overlaps icons.
- **Reloading settings:**
  - Right-click the StartHub tray icon → **Reload Config** (no need to kill Python manually).
