"""BiliGo single-file launcher: opens browser and runs the Flask app."""
import os
import threading
import time
import webbrowser

from app_paths import ensure_data_files, get_data_dir


def open_browser():
    time.sleep(1.5)
    webbrowser.open('http://localhost:4999')


def main():
    os.chdir(get_data_dir())
    ensure_data_files()

    print('========================================')
    print('  BiliGo - One-Click Launcher')
    print('========================================')
    print()
    print('[OK] Starting Flask application...')
    print('Access at: http://localhost:4999')
    print('Comment system: http://localhost:4999/comment')
    print('Press Ctrl+C to stop')
    print('========================================')
    print()

    threading.Thread(target=open_browser, daemon=True).start()

    from app import run_server
    run_server()


if __name__ == '__main__':
    main()
