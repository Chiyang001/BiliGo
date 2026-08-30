@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title BiliGo Docker Deploy

echo ========================================
echo   BiliGo - Docker One-Click Deploy
echo ========================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not found. Please install Docker Desktop first.
    echo         https://docs.docker.com/get-docker/
    pause
    exit /b 1
)

set "BASE_IMAGE=python:3.11-slim-bookworm"

echo [1/2] Pulling base image from Docker Hub...
echo       Image: %BASE_IMAGE%
echo.
docker pull %BASE_IMAGE%
if errorlevel 1 goto :network_error

echo.
echo [2/2] Building and starting container...
docker compose up -d --build
if errorlevel 1 goto :build_error

echo.
echo Deploy complete!
echo.
echo Access:
echo   Main UI:    http://localhost:4999
echo   Comments:   http://localhost:4999/comment
echo   Logs:       http://localhost:4999/logs.html
echo.
echo Useful commands:
echo   View logs:  docker compose logs -f
echo   Stop:       docker compose down
echo   Restart:    docker compose restart
echo.
echo Data is persisted in Docker volume: biligo-data
echo.
pause
exit /b 0

:network_error
echo.
echo ========================================
echo   网络错误：无法从 Docker Hub 拉取镜像
echo ========================================
echo.
echo 这通常是因为当前网络无法访问 docker.io / auth.docker.io，
echo 并非 BiliGo 项目本身的问题。
echo.
echo 你可以尝试：
echo   1. 检查网络连接，或开启 VPN / 代理后重试
echo   2. 暂时不用 Docker，直接运行：
echo        pip install -r requirements.txt
echo        python app.py
echo.
echo 手动测试：
echo   docker pull hello-world
echo.
pause
exit /b 1

:build_error
echo.
echo [ERROR] 容器构建或启动失败。
echo.
echo 若上方出现 auth.docker.io / docker.io 相关超时，
echo 同样属于网络问题，请参考上面的「网络错误」提示。
echo.
echo 查看详细日志：
echo   docker compose logs
echo.
pause
exit /b 1
