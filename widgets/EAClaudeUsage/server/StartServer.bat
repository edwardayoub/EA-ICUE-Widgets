@echo off
setlocal

echo.
echo   Claude Usage Server - Launch
echo   ============================
echo.

:: Check for Python
where pythonw >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python was not found.
    echo   Please install Python 3.10 or later from https://www.python.org
    echo   Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Found %PYVER%
echo.

:: Optional tray icon (Quit menu). The server runs fine without it.
python -c "import pystray, PIL" >nul 2>&1
if %errorlevel% neq 0 (
    echo   Installing optional tray-icon support ^(pystray, Pillow^)...
    python -m pip install --quiet pystray Pillow >nul 2>&1
)

echo   Starting server on http://localhost:16330/usage
echo   It reads Claude Code transcripts from %%USERPROFILE%%\.claude\projects
echo   Nothing is sent off this PC. Right-click the tray icon to quit.
echo.

start "" pythonw "%~dp0ClaudeUsageServer.pyw"
exit /b 0
