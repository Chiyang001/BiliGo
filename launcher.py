"""BiliGo single-file launcher: opens browser and runs the Flask app."""
import os

from app_paths import ensure_data_files, get_data_dir
from playwright_runtime import configure_playwright_env, ensure_playwright_ready

configure_playwright_env()


def main():
    data_dir = get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    os.chdir(data_dir)
    ensure_data_files()
    if not ensure_playwright_ready():
        print('[WARN] Playwright Chromium 未就绪，抖音/小红书等浏览器功能可能不可用')

    print('========================================')
    print('  BiliGo - One-Click Launcher')
    print('========================================')
    print(f'[INFO] 用户数据目录: {data_dir}')
    print()
    print('[OK] Starting Flask application...')
    print('The browser will open automatically after the server is ready.')
    print('Press Ctrl+C to stop')
    print('========================================')
    print()

    from app import run_server
    run_server(open_browser=True)


if __name__ == '__main__':
    main()
