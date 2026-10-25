@echo off
cd /d "%~dp0"
title BiliGoVer Launcher

echo ========================================
echo   BiliGoVer - One-Click Launcher
echo ========================================
echo.

set "VENV_DIR=%~dp0.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%PY%" (
    echo [Setup] Creating portable Python environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
)

echo [Setup] Installing dependencies...
"%PY%" -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [Setup] Ensuring Playwright Chromium...
"%PY%" -c "from playwright_runtime import ensure_playwright_ready; import sys; sys.exit(0 if ensure_playwright_ready() else 1)"
if errorlevel 1 (
    echo [ERROR] Failed to prepare Playwright Chromium
    pause
    exit /b 1
)

:: Start frp (minimized to tray)
echo [1/2] Starting frp...
start "BiliGoVer-FRP" /min cmd /c "cd /d "%~dp0frp" && frpc.exe"
echo [OK] frp started (window minimized)

:: Start Flask app
echo [2/2] Starting Flask application...
echo Browser will open automatically after startup.
echo Press Ctrl+C to stop
echo ========================================
echo.

"%PY%" app.py

echo.
echo Flask application stopped.
pause
