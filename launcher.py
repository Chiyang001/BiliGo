"""BiliGo single-file launcher: opens browser and runs the Flask app."""
import os
import argparse

from app_paths import ensure_data_files, get_data_dir
from app_version import APP_VERSION, APP_VERSION_DATE
from playwright_runtime import configure_playwright_env

configure_playwright_env()


def main():
    parser = argparse.ArgumentParser(description=f'BiliGo {APP_VERSION}')
    parser.add_argument('--version', action='version', version=f'BiliGo {APP_VERSION} ({APP_VERSION_DATE})')
    parser.add_argument('--reset-panel-password', action='store_true', help='重置为初始面板密码并退出')
    args = parser.parse_args()
    open_browser = os.environ.get('BILIGO_OPEN_BROWSER', '1').strip().lower() not in ('0', 'false', 'no', 'off')
    data_dir = get_data_dir()
    if args.reset_panel_password:
        from web_access import WebAuthStore
        try:
            WebAuthStore(data_dir).reset_to_initial_password()
        except ValueError as exc:
            parser.error(str(exc))
        return
    os.makedirs(data_dir, exist_ok=True)
    os.chdir(data_dir)
    ensure_data_files()
    print('========================================')
    print(f'  BiliGo {APP_VERSION} - One-Click Launcher')
    print('========================================')
    print(f'[INFO] 用户数据目录: {data_dir}')
    print()
    print('[OK] Starting Flask application...')
    if open_browser:
        print('The browser will open automatically after the server is ready.')
    print('Press Ctrl+C to stop')
    print('========================================')
    print()

    from app import run_server
    run_server(open_browser=open_browser)


if __name__ == '__main__':
    main()
