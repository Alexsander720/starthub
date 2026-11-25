@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" -m starthub %*
    exit /b 0
)
echo Virtual environment not found. Running Install.cmd first...
call "%~dp0Install.cmd"
