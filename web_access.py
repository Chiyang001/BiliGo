"""Password authentication and revocable, per-browser panel sessions."""
from __future__ import annotations

import getpass
import hashlib
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from contextlib import contextmanager

from flask import g, jsonify, redirect, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

from app_paths import get_data_dir, get_static_root
from app_version import EXE_BASENAME
from web_files import is_path_within

AUTH_FILENAME = '.biligo_web_auth.sqlite3'
SESSION_COOKIE = 'biligo_session'
CSRF_HEADER = 'X-BiliGo-CSRF'
SESSION_SECONDS = 12 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60
INITIAL_SESSION_SECONDS = 15 * 60
PASSWORD_SETUP_URL = '/panel-security?setup=1'
LOGIN_WINDOW = 300
PASSWORD_METHOD = 'pbkdf2:sha256:600000'


def validate_password(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 256:
        raise ValueError('面板密码长度必须为 8～256 个字符')


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class WebAuthStore:
    def __init__(self, data_dir=None):
        self.path = os.path.join(data_dir or get_data_dir(), AUTH_FILENAME)
        self.lock = threading.RLock()
        self.initialized = False

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA secure_delete = ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, announce=True):
        with self.lock:
            if self.initialized:
                return
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            os.chmod(self.path, 0o600)
            initial_password = None
            legacy_password = False
            with self.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS credentials '
                           '(id INTEGER PRIMARY KEY CHECK (id = 1), password_hash TEXT NOT NULL, '
                           "password_state TEXT NOT NULL DEFAULT 'legacy', initial_password TEXT)")
                db.execute('CREATE TABLE IF NOT EXISTS sessions '
                           '(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires INTEGER NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS attempts '
                           '(key TEXT PRIMARY KEY, started INTEGER NOT NULL, failures INTEGER NOT NULL)')
                db.execute('BEGIN IMMEDIATE')
                columns = {row['name'] for row in db.execute('PRAGMA table_info(credentials)')}
                if 'password_state' not in columns:
                    db.execute("ALTER TABLE credentials ADD COLUMN password_state TEXT NOT NULL DEFAULT 'legacy'")
                if 'initial_password' not in columns:
                    db.execute('ALTER TABLE credentials ADD COLUMN initial_password TEXT')
                stored = db.execute('SELECT * FROM credentials WHERE id = 1').fetchone()
                configured = os.environ.get('BILIGO_PANEL_PASSWORD', '')
                if configured:
                    validate_password(configured)
                if stored is None:
                    if configured:
                        db.execute('INSERT INTO credentials (id, password_hash, password_state) VALUES (1, ?, ?)',
                                   (generate_password_hash(configured, method=PASSWORD_METHOD), 'custom'))
                    else:
                        initial_password = self._replace_initial_password(db)
                elif configured and (stored['password_state'] != 'custom'
                                     or not check_password_hash(stored['password_hash'], configured)):
                    self._replace_password(db, configured)
                elif stored['password_state'] == 'initial':
                    initial_password = stored['initial_password'] or self._replace_initial_password(db)
                elif stored['password_state'] == 'legacy':
                    legacy_password = True
            self.initialized = True
            if announce and initial_password:
                self._announce_initial_password(initial_password)
            elif announce and legacy_password:
                print('[BiliGo] 检测到旧版面板密码，原密码保持有效，登录后需设置新的自定义密码。\n'
                      '[BiliGo] 旧密码无法从哈希还原。如已忘记，在相同数据目录下执行：\n'
                      '  python web_access.py --reset-initial-password\n'
                      f'  EXE 用户可运行：{EXE_BASENAME}.exe --reset-panel-password\n', flush=True)

    @staticmethod
    def _announce_initial_password(password):
        # Printed only to the process terminal, never to application/web logs.
        print('\n[BiliGo] 尚未设置自定义面板密码。当前初始密码：\n'
              f'  {password}\n'
              '[BiliGo] 请用此密码登录；登录后必须先设置自己的密码。\n'
              '[BiliGo] 设置完成前，每次启动都会显示此初始密码；设置后不再显示。\n', flush=True)

    @staticmethod
    def _replace_initial_password(db):
        password = secrets.token_urlsafe(18)
        db.execute('INSERT INTO credentials (id, password_hash, password_state, initial_password) '
                   "VALUES (1, ?, 'initial', ?) ON CONFLICT(id) DO UPDATE SET "
                   "password_hash=excluded.password_hash, password_state='initial', initial_password=excluded.initial_password",
                   (generate_password_hash(password, method=PASSWORD_METHOD), password))
        db.execute('DELETE FROM sessions')
        db.execute('DELETE FROM attempts')
        return password

    @staticmethod
    def _replace_password(db, password):
        db.execute("UPDATE credentials SET password_hash = ?, password_state = 'custom', initial_password = NULL WHERE id = 1",
                   (generate_password_hash(password, method=PASSWORD_METHOD),))
        db.execute('DELETE FROM sessions')
        db.execute('DELETE FROM attempts')

    @staticmethod
    def _retry_after(db, keys, now):
        for key, limit in keys:
            row = db.execute('SELECT started, failures FROM attempts WHERE key = ?', (key,)).fetchone()
            if row and row['started'] > now - LOGIN_WINDOW and row['failures'] >= limit:
                return max(1, row['started'] + LOGIN_WINDOW - now)
        return 0

    @staticmethod
    def _failure(db, keys, now):
        db.execute('DELETE FROM attempts WHERE started <= ?', (now - LOGIN_WINDOW,))
        for key, _ in keys:
            db.execute('INSERT INTO attempts VALUES (?, ?, 1) '
                       'ON CONFLICT(key) DO UPDATE SET failures = failures + 1', (key, now))

    def login(self, password, address, remember):
        self.initialize()
        now = int(time.time())
        keys = [('ip:' + _digest(address), 8), ('global', 60)]
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            retry = self._retry_after(db, keys, now)
            if retry:
                return None, retry
            stored = db.execute('SELECT password_hash, password_state FROM credentials WHERE id = 1').fetchone()
            if not isinstance(password, str) or len(password) > 256 or not check_password_hash(stored[0], password):
                self._failure(db, keys, now)
                return None, 0
            db.execute('DELETE FROM attempts WHERE key = ?', (keys[0][0],))
            db.execute('DELETE FROM sessions WHERE expires <= ?', (now,))
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            lifetime = REMEMBER_SECONDS if remember else SESSION_SECONDS
            if stored['password_state'] != 'custom':
                lifetime = INITIAL_SESSION_SECONDS
            db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (_digest(token), csrf, now + lifetime))
            return token, 0

    def session(self, token):
        if not isinstance(token, str) or len(token) != 43:
            return None
        self.initialize()
        with self.connect() as db:
            return db.execute("SELECT s.csrf, s.expires, (c.password_state != 'custom') AS must_change "
                              'FROM sessions s JOIN credentials c ON c.id = 1 WHERE s.token_hash = ? AND s.expires > ?',
                              (_digest(token), int(time.time()))).fetchone()

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash = ?', (_digest(token),))

    def change_password(self, current, new, address):
        validate_password(new)
        now = int(time.time())
        keys = [('ip:' + _digest(address), 8), ('global', 60)]
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            retry = self._retry_after(db, keys, now)
            if retry:
                return False, retry
            stored = db.execute('SELECT password_hash FROM credentials WHERE id = 1').fetchone()
            if not isinstance(current, str) or len(current) > 256 or not check_password_hash(stored[0], current):
                self._failure(db, keys, now)
                return False, 0
            if new == current:
                raise ValueError('新密码不能与当前密码相同')
            self._replace_password(db, new)
            return True, 0

    def reset_password(self, password):
        validate_password(password)
        self.initialize(announce=False)
        with self.lock, self.connect() as db:
            self._replace_password(db, password)

    def reset_to_initial_password(self):
        if os.environ.get('BILIGO_PANEL_PASSWORD', ''):
            raise ValueError('请先移除 BILIGO_PANEL_PASSWORD 环境变量，或直接使用该变量指定的自定义密码')
        self.initialize(announce=False)
        with self.lock, self.connect() as db:
            password = self._replace_initial_password(db)
        self._announce_initial_password(password)


def _safe_next(value):
    if not isinstance(value, str) or not value.startswith('/'):
        return '/'
    decoded = urllib.parse.unquote(value)
    if decoded.startswith('//') or '\\' in decoded or any(ord(c) < 32 for c in decoded):
        return '/'
    parsed = urllib.parse.urlsplit(decoded)
    if parsed.scheme or parsed.netloc or parsed.path == '/login':
        return '/'
    if parsed.path.startswith(('/api/', '/auth-assets/')):
        return '/'
    return value


def _same_origin():
    origin = request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site') == 'cross-site':
        return False
    if not origin:
        return True
    try:
        expected = urllib.parse.urlsplit(request.host_url)
        received = urllib.parse.urlsplit(origin)
    except ValueError:
        return False
    expected_scheme = 'https' if _secure_cookie() else expected.scheme
    return (received.scheme, received.netloc) == (expected_scheme, expected.netloc)


def _secure_cookie():
    return request.is_secure or os.environ.get('BILIGO_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')


def register_web_auth(app):
    if 'biligo_web_auth' in app.extensions:
        return
    store = WebAuthStore()
    app.extensions['biligo_web_auth'] = store

    def auth_asset(filename):
        root = get_static_root()
        if not is_path_within(root, os.path.join(root, filename)):
            return error('文件不存在', 404)
        return send_from_directory(root, filename)

    def error(message, status, retry=0, code=None):
        response = jsonify(success=False, error=message)
        if code:
            response = jsonify(success=False, error=message, code=code, next=PASSWORD_SETUP_URL)
        response.status_code = status
        if retry:
            response.headers['Retry-After'] = str(retry)
        return response

    @app.route('/health')
    def biligo_healthcheck():
        return 'ok', 200

    @app.route('/login')
    def biligo_login_page():
        if g.panel_session:
            if g.panel_session['must_change']:
                return redirect(PASSWORD_SETUP_URL)
            return redirect(_safe_next(request.args.get('next', '/')))
        store.initialize()
        return auth_asset('panel_login.html')

    @app.route('/panel-security')
    def biligo_security_page():
        return auth_asset('panel_security.html')

    @app.route('/auth-assets/<filename>')
    def biligo_auth_assets(filename):
        if filename not in {'panel_auth.css', 'panel_login.js', 'panel_theme.js', 'developer-avatar.png',
                            'bilibili.png', 'tik-tok.png', 'xiaohongshu-seeklogo.png'}:
            return error('文件不存在', 404)
        return auth_asset(filename)

    @app.route('/api/auth/status')
    def biligo_auth_status():
        return jsonify(authenticated=bool(g.panel_session),
                       csrf_token=g.panel_session['csrf'] if g.panel_session else None,
                       must_change_password=bool(g.panel_session and g.panel_session['must_change']))

    @app.route('/api/auth/login', methods=['POST'])
    def biligo_login():
        if not _same_origin() or request.headers.get('X-BiliGo-Login') != '1':
            return error('登录请求来源校验失败，请刷新页面重试', 403)
        if request.content_length and request.content_length > 4096:
            return error('请求内容过大', 413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error('请使用 JSON 提交登录信息', 400)
        remember = data.get('remember') is True
        token, retry = store.login(data.get('password'), request.remote_addr or '', remember)
        if retry:
            return error('尝试次数过多，请稍后重试', 429, retry)
        if not token:
            return error('面板密码错误', 401)
        previous = request.cookies.get(SESSION_COOKIE)
        if previous:
            store.logout(previous)
        must_change = bool(store.session(token)['must_change'])
        response = jsonify(success=True, must_change_password=must_change,
                           next=PASSWORD_SETUP_URL if must_change else _safe_next(data.get('next', '/')))
        if must_change:
            remember = False
        response.set_cookie(SESSION_COOKIE, token, max_age=REMEMBER_SECONDS if remember else None,
                            secure=_secure_cookie(), httponly=True, samesite='Strict', path='/')
        response.delete_cookie('biligo_token', path='/')
        return response

    @app.route('/api/auth/logout', methods=['POST'])
    def biligo_logout():
        store.logout(request.cookies.get(SESSION_COOKIE, ''))
        response = jsonify(success=True)
        response.delete_cookie(SESSION_COOKIE, path='/')
        response.delete_cookie('biligo_token', path='/')
        return response

    @app.route('/api/auth/password', methods=['POST'])
    def biligo_change_password():
        if request.content_length and request.content_length > 4096:
            return error('请求内容过大', 413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return error('密码格式错误', 400)
        try:
            changed, retry = store.change_password(data.get('current_password'), data.get('new_password'),
                                                   request.remote_addr or '')
        except ValueError as exc:
            return error(str(exc), 400)
        if retry:
            return error('尝试次数过多，请稍后重试', 429, retry)
        if not changed:
            return error('当前面板密码错误', 401)
        response = jsonify(success=True)
        response.delete_cookie(SESSION_COOKIE, path='/')
        return response

    public_endpoints = {'biligo_healthcheck', 'biligo_login_page', 'biligo_auth_assets',
                        'biligo_auth_status', 'biligo_login'}
    setup_endpoints = {'biligo_security_page', 'biligo_change_password', 'biligo_logout'}
    setup_assets = frozenset({'/web_auth.js', '/panel_security.js'})

    @app.before_request
    def require_panel_session():
        g.panel_session = store.session(request.cookies.get(SESSION_COOKIE))
        if request.endpoint in public_endpoints:
            return None
        if not g.panel_session:
            if request.path.startswith('/api/'):
                return error('请先登录面板', 401)
            if request.method not in ('GET', 'HEAD'):
                return error('请先登录面板', 401)
            destination = _safe_next(request.full_path.rstrip('?'))
            return redirect('/login?' + urllib.parse.urlencode({'next': destination}))
        if (g.panel_session['must_change'] and request.endpoint not in setup_endpoints
                and not (request.endpoint == 'static_files' and request.path in setup_assets)):
            if request.path.startswith('/api/') or request.method not in ('GET', 'HEAD'):
                return error('请先设置自定义面板密码', 428, code='PASSWORD_CHANGE_REQUIRED')
            return redirect(PASSWORD_SETUP_URL)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            supplied = request.headers.get(CSRF_HEADER, '')
            if not _same_origin() or not secrets.compare_digest(supplied.encode(), g.panel_session['csrf'].encode()):
                return error('请求安全校验失败，请刷新页面重试', 403)

    @app.after_request
    def secure_panel_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        if request.endpoint in {'biligo_login_page', 'biligo_security_page'}:
            response.headers['Content-Security-Policy'] += "; default-src 'self'; script-src 'self'; style-src 'self'; form-action 'self'"
        return response


def build_access_url(port, path='/', host='localhost'):
    normalized = path if path.startswith('/') else '/' + path
    return f'http://{host}:{port}{normalized}'


def wait_until_server_ready(port, timeout=60.0):
    probe_url = build_access_url(port, '/health', host='127.0.0.1')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(probe_url, timeout=1.5) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.HTTPError):
            pass
        time.sleep(0.35)
    return False


def open_browser_when_ready(port, path='/'):
    if wait_until_server_ready(port):
        webbrowser.open(build_access_url(port, path))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='BiliGo 面板密码管理')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--reset-password', action='store_true')
    action.add_argument('--reset-initial-password', action='store_true')
    args = parser.parse_args()
    if args.reset_initial_password:
        try:
            WebAuthStore().reset_to_initial_password()
        except ValueError as exc:
            parser.error(str(exc))
        raise SystemExit(0)
    password = getpass.getpass('新面板密码（至少8个字符）：')
    confirmation = getpass.getpass('再次输入新密码：')
    if password != confirmation:
        parser.error('两次输入的密码不一致')
    try:
        WebAuthStore().reset_password(password)
    except ValueError as exc:
        parser.error(str(exc))
    print('面板密码已重置，所有设备需要重新登录。')
