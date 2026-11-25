@echo off
setlocal
cd /d "%~dp0"
echo Starting StartHub installer (bypassing PowerShell ExecutionPolicy)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Optional -AutoStart %*
if errorlevel 1 (
    echo.
    echo Installer exited with an error. Press any key to close...
    pause >nul
    exit /b 1
)
echo.
echo Press any key to launch StartHub with GUI Settings, or close this window...
pause >nul
start "" "%~dp0.venv\Scripts\pythonw.exe" -m starthub --settings
