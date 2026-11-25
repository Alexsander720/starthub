<#
.SYNOPSIS
    Installs StartHub into a local Python virtual environment (.venv).
.DESCRIPTION
    Creates .venv, installs core requirements (and optional hardware/EcoFlow extras with -Optional),
    bootstraps config.json from config.example.json if missing, and optionally registers a Windows
    Startup shortcut with -AutoStart.
.EXAMPLE
    .\install.ps1
    .\install.ps1 -Optional -AutoStart
#>
[CmdletBinding()]
param(
    [switch]$Optional,
    [switch]$AutoStart,
    [switch]$LaunchDemo
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== StartHub Installer ===" -ForegroundColor Cyan

# 1. Locate Python 3.10+
$PythonCmd = $null
foreach ($cand in @("python", "py")) {
    $found = Get-Command $cand -ErrorAction SilentlyContinue
    if ($found) {
        $PythonCmd = $cand
        break
    }
}
if (-not $PythonCmd) {
    Write-Error "Python 3.10+ was not found in PATH. Install it from https://www.python.org/downloads/ and re-run."
}

$VerText = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "Using $PythonCmd ($VerText)" -ForegroundColor Green

# 2. Create virtual environment
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPythonW = Join-Path $VenvDir "Scripts\pythonw.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment in .venv..." -ForegroundColor Yellow
    & $PythonCmd -m venv $VenvDir
}

# 3. Install dependencies
Write-Host "Installing core requirements..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")

if ($Optional) {
    Write-Host "Installing optional requirements (NVML, HID++, EcoFlow MQTT/Protobuf)..." -ForegroundColor Yellow
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements-optional.txt")
}

# 4. Copy config.example.json -> config.json on first install
$ConfigPath = Join-Path $RepoRoot "config.json"
$ExamplePath = Join-Path $RepoRoot "config.example.json"
if (-not (Test-Path $ConfigPath) -and (Test-Path $ExamplePath)) {
    Copy-Item $ExamplePath $ConfigPath
    Write-Host "Created config.json from config.example.json (edit it to customize city, theme, or opt-in modules)." -ForegroundColor Green
}

# 5. Optional Windows Startup shortcut (windowless via pythonw.exe)
if ($AutoStart) {
    $StartupDir = [Environment]::GetFolderPath("Startup")
    $ShortcutPath = Join-Path $StartupDir "StartHub.lnk"
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = if (Test-Path $VenvPythonW) { $VenvPythonW } else { $VenvPython }
    $Shortcut.Arguments = "-m starthub"
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "StartHub — Start11 Acrylic Side Panels"
    $Shortcut.Save()
    Write-Host "Added Windows Startup shortcut: $ShortcutPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "Try demo mode immediately (no API keys required):" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m starthub --demo --preview" -ForegroundColor White
Write-Host "Run with Start11 tracking:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\pythonw.exe -m starthub" -ForegroundColor White

if ($LaunchDemo) {
    Start-Process -FilePath $VenvPython -ArgumentList "-m", "starthub", "--demo", "--preview" -WorkingDirectory $RepoRoot
}
