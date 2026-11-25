<#
.SYNOPSIS
    Installs StartHub into a local Python virtual environment (.venv).
.DESCRIPTION
    Detects a real Python 3.10+ interpreter (skipping the Windows 11 Microsoft Store alias stub),
    optionally installs Python via winget (-InstallPython), creates .venv, installs dependencies,
    bootstraps config.json, and optionally creates a Windows Startup shortcut (-AutoStart).
.EXAMPLE
    .\install.ps1
    .\install.ps1 -Optional -AutoStart
    .\install.ps1 -InstallPython -Optional -LaunchDemo
#>
[CmdletBinding()]
param(
    [switch]$Optional,
    [switch]$AutoStart,
    [switch]$LaunchDemo,
    [switch]$OpenSettings,
    [switch]$InstallPython
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== StartHub Installer ===" -ForegroundColor Cyan

function Find-RealPython {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() },
        @{ Exe = "python3"; Args = @() }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        # Skip the fake Microsoft Store execution alias stub if it doesn't actually execute Python
        try {
            $verOut = & $cmd.Source @($c.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}'); sys.exit(0 if sys.version_info >= (3, 10) else 2)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $verOut -match '^\d+\.\d+$') {
                return @{ Path = $cmd.Source; Args = $c.Args; Version = $verOut.Trim() }
            }
        } catch {
            continue
        }
    }
    return $null
}

# 1. Locate real Python 3.10+
$PyInfo = Find-RealPython
if (-not $PyInfo -and $InstallPython) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Installing Python 3.12 via winget..." -ForegroundColor Yellow
        & winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
        $PyInfo = Find-RealPython
    }
}

if (-not $PyInfo) {
    Write-Host ""
    Write-Host "Python 3.10+ was not found (Windows 11's Microsoft Store alias is not a real Python install)." -ForegroundColor Red
    Write-Host "Either run:  .\install.ps1 -InstallPython" -ForegroundColor Yellow
    Write-Host "Or install Python 3.12 from https://www.python.org/downloads/ (check 'Add Python to PATH')." -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Python $($PyInfo.Version) ($($PyInfo.Path))" -ForegroundColor Green

# 2. Create virtual environment
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPythonW = Join-Path $VenvDir "Scripts\pythonw.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment in .venv..." -ForegroundColor Yellow
    & $PyInfo.Path @($PyInfo.Args) -m venv $VenvDir
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
    Write-Host "Created config.json from config.example.json." -ForegroundColor Green
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
    $Shortcut.Description = "StartHub — Windows 11 & Start11 Acrylic Side Panels"
    $Shortcut.Save()
    Write-Host "Added Windows Startup shortcut: $ShortcutPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "Try Demo Mode immediately (no API keys required):" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\python.exe -m starthub --demo --preview" -ForegroundColor White
Write-Host "Launch live (Start11, native Windows 11 Start, or Alt+Space):" -ForegroundColor Cyan
Write-Host "  .\StartHub.cmd   (or .\.venv\Scripts\pythonw.exe -m starthub)" -ForegroundColor White
Write-Host "Open GUI Settings anytime from the system tray or via:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\pythonw.exe -m starthub --settings" -ForegroundColor White

if ($LaunchDemo) {
    Start-Process -FilePath $VenvPython -ArgumentList "-m", "starthub", "--demo", "--preview" -WorkingDirectory $RepoRoot
} elseif ($OpenSettings) {
    Start-Process -FilePath $VenvPythonW -ArgumentList "-m", "starthub", "--settings" -WorkingDirectory $RepoRoot
}
