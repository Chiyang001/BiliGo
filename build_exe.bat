@echo off
cd /d "%~dp0"
title BiliGo EXE Builder

echo ========================================
echo   BiliGo - Build Single EXE
echo ========================================
echo.

set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

echo [1/4] Installing build dependencies...
"%PY%" -m pip install -r requirements.txt pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [2/4] Installing Playwright Chromium browser...
"%PY%" -m playwright install chromium
if errorlevel 1 (
    echo [ERROR] Failed to install Playwright Chromium
    pause
    exit /b 1
)

echo [3/4] Building single EXE with bundled Chromium (this may take several minutes)...
"%PY%" -m PyInstaller --noconfirm --clean BiliGo.spec
if errorlevel 1 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo [4/4] Build complete!
"%PY%" -c "from app_version import EXE_BASENAME; print('Output: dist/' + EXE_BASENAME + '.exe')"
echo.
echo Usage:
echo   1. Copy the versioned EXE from dist to any folder
echo   2. Double-click to run (no Python required)
echo   3. User data is stored in your Windows AppData\Roaming\BiliGo folder
echo.
pause
