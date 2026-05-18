@echo off
cd /d "%~dp0"
title BiliGoVer Launcher

echo ========================================
echo   BiliGoVer - One-Click Launcher
echo ========================================
echo.

:: Start frp (minimized to tray)
echo [1/2] Starting frp...
start "BiliGoVer-FRP" /min cmd /c "cd /d "%~dp0frp" && frpc.exe"
echo [OK] frp started (window minimized)

:: Start Flask app
echo [2/2] Starting Flask application...
echo Access at: http://localhost:4999
echo Press Ctrl+C to stop
echo ========================================
echo.

python app.py

echo.
echo Flask application stopped.
pause
