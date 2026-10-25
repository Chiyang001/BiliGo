"""Audit a release EXE and test it using disposable data and a hidden process."""
from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from PyInstaller.archive.readers import CArchiveReader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_version import APP_VERSION, APP_VERSION_DATE, EXE_BASENAME  # noqa: E402


def audit_archive(executable):
    archive = CArchiveReader(str(executable))
    names = {name.replace('\\', '/'): name for name in archive.toc}
    forbidden = [name for name in names if name.endswith(('_storage.json', '.sqlite3'))
                 or '_browser_profile/' in name or name.endswith('.biligo_web_token')
                 or name.endswith(('.env', '.env.local'))]
    assert not forbidden, 'Private runtime files were bundled: ' + repr(forbidden)
    defaults = list((ROOT / 'docker' / 'defaults').glob('*.json'))
    for source in defaults:
        assert source.name in names, 'Missing default template: ' + source.name
        assert archive.extract(names[source.name]) == source.read_bytes(), 'Wrong template: ' + source.name
    for name in ('panel_login.html', 'panel_security.html', 'panel_auth.css', 'panel_login.js',
                 'panel_security.js', 'web_auth.js'):
        assert name in names, 'Missing authentication asset: ' + name
    assert any('.local-browsers/chromium-' in name and name.endswith('/chrome.exe') for name in names)
    assert any('.local-browsers/chromium_headless_shell-' in name and name.endswith('.exe') for name in names)
    pyz = next(name for name in archive.toc if name.endswith('.pyz'))
    modules = archive.open_embedded_archive(pyz).toc
    for name in ('app', 'app_version', 'web_access', 'web_files', 'sqlite3', 'hashlib'):
        assert name in modules, 'Missing Python module: ' + name
    print(f'Archive verified: {len(defaults)} clean default templates, authentication assets and Chromium included', flush=True)


def run_smoke(executable):
    with tempfile.TemporaryDirectory(prefix='biligo-exe-smoke-') as directory:
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        password = secrets.token_urlsafe(24)
        environment = {**os.environ, 'BILIGO_DATA_DIR': directory, 'PORT': str(port),
                       'BILIGO_OPEN_BROWSER': '0', 'BILIGO_PANEL_PASSWORD': password,
                       'BILIGO_COOKIE_SECURE': '0', 'PLAYWRIGHT_BROWSERS_PATH': '0',
                       'PYTHONIOENCODING': 'utf-8'}
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        version = subprocess.run([str(executable), '--version'], cwd=directory, env=environment,
                                 capture_output=True, timeout=90, creationflags=flags)
        assert version.returncode == 0, 'EXE --version failed'
        version_text = version.stdout.decode('utf-8', errors='replace').strip()
        assert APP_VERSION in version_text and APP_VERSION_DATE in version_text, version_text
        print('EXE reports: ' + version_text, flush=True)
        origin = f'http://127.0.0.1:{port}'
        logfile = Path(directory) / 'smoke.log'
        process = None
        try:
            with logfile.open('wb') as output:
                process = subprocess.Popen([str(executable)], cwd=directory, env=environment,
                                           stdout=output, stderr=subprocess.STDOUT, creationflags=flags)
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError('EXE exited before server startup')
                    try:
                        if requests.get(origin + '/health', timeout=1).text == 'ok':
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(0.3)
                else:
                    raise AssertionError('EXE server startup timed out')
                print('Packaged server started with isolated data and bundled browser runtime', flush=True)
                assert requests.get(origin + '/api/config', timeout=5).status_code == 401
                response = requests.get(origin + '/', allow_redirects=False, timeout=5)
                assert response.status_code == 302 and response.headers['Location'].startswith('/login?')
                session = requests.Session()
                response = session.post(origin + '/api/auth/login', json={'password': password, 'remember': True},
                                        headers={'X-BiliGo-Login': '1'}, timeout=10)
                assert response.status_code == 200
                config = session.get(origin + '/api/config', timeout=5).json()
                assert not config.get('sessdata') and not config.get('bili_jct') and not config.get('accounts')
                assert not (config.get('ai_provider') or {}).get('api_key')
                for path in ('/config.json', '/app.py', '/.biligo_web_auth.sqlite3', '/douyin_storage.json',
                             '/.git/config', '/..%5cconfig.json', '/docker/defaults/config.json'):
                    assert session.get(origin + path, timeout=5).status_code == 404, path
                csrf = session.get(origin + '/api/auth/status', timeout=5).json()['csrf_token']
                assert session.post(origin + '/api/browse-images', json={'folder_path': str(ROOT)},
                                    headers={'X-BiliGo-CSRF': csrf}, timeout=5).status_code == 403
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.goto(origin + '/', wait_until='domcontentloaded')
                    assert page.title() == '登录面板 · BiliGo'
                    page.locator('#panel-password').fill(password)
                    page.get_by_role('checkbox').check()
                    page.locator('#login-submit').click()
                    page.wait_for_url(lambda url: url.split('#')[0] == origin + '/')
                    page.get_by_role('link', name='面板安全', exact=True).wait_for()
                    assert page.locator('.version-badge').text_content() == APP_VERSION
                    page.goto(origin + '/panel-security', wait_until='domcontentloaded')
                    assert page.locator('#panel-password-form').is_visible()
                    page.locator('#panel-logout').click()
                    page.wait_for_url(origin + '/login')
                    browser.close()
                print('Packaged EXE login, version badge, password settings and file access protections passed', flush=True)
        except Exception:
            if logfile.exists():
                log = logfile.read_text(encoding='utf-8', errors='replace').replace(password, '[test password]')
                print('\n'.join(log.splitlines()[-25:]), file=sys.stderr)
            raise
        finally:
            if process and process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                                   creationflags=flags, timeout=15)
                else:
                    process.terminate()
                process.wait(timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', nargs='?', default=str(ROOT / 'dist' / (EXE_BASENAME + '.exe')))
    arguments = parser.parse_args()
    target = Path(arguments.executable).resolve()
    audit_archive(target)
    run_smoke(target)
