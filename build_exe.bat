@echo off
cd /d "%~dp0"
title BiliGo EXE Builder

echo ========================================
echo   BiliGo - Build Single EXE
echo ========================================
echo.

echo [1/3] Installing build dependencies...
python -m pip install flask==2.3.3 requests==2.31.0 pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo [2/3] Building single EXE (this may take a few minutes)...
python -m PyInstaller --noconfirm --clean BiliGo.spec
if errorlevel 1 (
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo Output: dist\BiliGo.exe
echo.
echo Usage:
echo   1. Copy dist\BiliGo.exe to any folder
echo   2. Double-click to run (no Python required)
echo   3. Config files will be created next to the EXE
echo.
pause
