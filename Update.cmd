@echo off
setlocal
cd /d "%~dp0"
echo Running StartHub Safe Updater (config.json will be backed up automatically)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" -Optional %*
echo.
pause
