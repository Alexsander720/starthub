<#
.SYNOPSIS
    Safely updates StartHub without losing your config.json, tile packs, or local tasks.
.DESCRIPTION
    Backs up config.json to cache/backups/, pulls the latest release from GitHub, refreshes .venv
    dependencies, and runs privacy/health verification.
#>
[CmdletBinding()]
param(
    [switch]$Optional
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== StartHub Safe Updater ===" -ForegroundColor Cyan

# 1. Backup user config.json before touching anything
$ConfigPath = Join-Path $RepoRoot "config.json"
if (Test-Path $ConfigPath) {
    $BackupDir = Join-Path $RepoRoot "cache\backups"
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $BackupFile = Join-Path $BackupDir "config_$Stamp.json"
    Copy-Item $ConfigPath $BackupFile -Force
    Write-Host "Backed up config.json -> $BackupFile" -ForegroundColor Green
}

# 2. Pull latest changes via git (preserves git-ignored config.json, cache/, packs/)
$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git -or -not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Host "This folder is not a git clone (portable release). Download the latest ZIP from:" -ForegroundColor Yellow
    Write-Host "  https://github.com/Alexsander720/starthub/releases/latest" -ForegroundColor White
    Write-Host "Copy your existing config.json and cache\local_tasks.json into the new folder — schema migrations run automatically!" -ForegroundColor Cyan
    exit 0
}

Write-Host "Pulling latest updates..." -ForegroundColor Yellow
& git pull --ff-only

# 3. Refresh virtual environment packages
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    Write-Host "Updating Python dependencies..." -ForegroundColor Yellow
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt") --quiet
    if ($Optional) {
        & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements-optional.txt") --quiet
    }
    Write-Host "Running environment doctor..." -ForegroundColor Yellow
    & $VenvPython -m starthub --doctor
}

Write-Host ""
Write-Host "Update complete! Your config.json, tasks, and tile packs were preserved." -ForegroundColor Green
Write-Host "Restart StartHub via StartHub.cmd (config schema migrates automatically)." -ForegroundColor Cyan
