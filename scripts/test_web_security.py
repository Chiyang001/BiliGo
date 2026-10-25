"""Security regressions using isolated data; never read the user's platform credentials."""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DATA = tempfile.TemporaryDirectory()
os.environ['BILIGO_DATA_DIR'] = DATA.name
os.environ['BILIGO_PANEL_PASSWORD'] = 'BiliGo-security-test-password'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402
from web_access import AUTH_FILENAME, SESSION_COOKIE, WebAuthStore, _digest  # noqa: E402
from web_files import PUBLIC_ASSETS, get_image_root  # noqa: E402

PASSWORD = os.environ['BILIGO_PANEL_PASSWORD']
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aG1sAAAAASUVORK5CYII=')


class PanelSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        cls.store = app.extensions['biligo_web_auth']
        cls.store.initialize()

    def setUp(self):
        with self.store.connect() as db:
            db.execute('DELETE FROM attempts')
            db.execute('DELETE FROM sessions')
        self.client = app.test_client()

    def login(self, client=None, remember=False, next_path='/'):
        client = client or self.client
        response = client.post('/api/auth/login', json={
            'password': PASSWORD, 'remember': remember, 'next': next_path,
        }, headers={'X-BiliGo-Login': '1'})
        self.assertEqual(response.status_code, 200)
        csrf = client.get('/api/auth/status').json['csrf_token']
        return response, {'X-BiliGo-CSRF': csrf}

    def test_every_registered_page_and_api_is_protected(self):
        public = {'biligo_healthcheck', 'biligo_login_page', 'biligo_auth_assets',
                  'biligo_auth_status', 'biligo_login'}
        import re
        for rule in app.url_map.iter_rules():
            if rule.endpoint in public:
                continue
            url = re.sub(r'<[^>]+>', 'security-probe', str(rule))
            method = 'GET' if 'GET' in rule.methods else next(m for m in rule.methods if m not in {'OPTIONS', 'HEAD'})
            with self.subTest(url=url, method=method):
                response = self.client.open(url, method=method, json={})
                self.assertIn(response.status_code, (302, 401))
                self.assertNotIn(b'password_hash', response.data)

    def test_legacy_tokens_and_disable_switch_do_not_bypass_password(self):
        with patch.dict(os.environ, {'BILIGO_WEB_AUTH': '0', 'BILIGO_WEB_TOKEN': 'old-token'}):
            self.client.set_cookie('biligo_token', 'old-token')
            self.assertEqual(self.client.get('/api/config?token=old-token',
                             headers={'X-BiliGo-Token': 'old-token'}).status_code, 401)

    def test_login_and_other_device(self):
        response, _ = self.login()
        self.assertNotIn('Max-Age=', response.headers['Set-Cookie'])
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', response.headers['Set-Cookie'])
        self.assertEqual(self.client.get('/api/config').status_code, 200)
        self.assertEqual(app.test_client().get('/api/config').status_code, 401)
        self.assertTrue(self.client.get('/login').location.endswith('/'))

    def test_remembered_session_survives_store_restart_and_expires(self):
        response, _ = self.login(remember=True)
        self.assertIn('Max-Age=2592000', response.headers['Set-Cookie'])
        token = self.client.get_cookie(SESSION_COOKIE).value
        restarted = WebAuthStore(DATA.name)
        self.assertIsNotNone(restarted.session(token))
        with restarted.connect() as db:
            self.assertEqual(db.execute('SELECT token_hash FROM sessions').fetchone()[0], _digest(token))
            self.assertNotEqual(db.execute('SELECT password_hash FROM credentials').fetchone()[0], PASSWORD)
            db.execute('UPDATE sessions SET expires = 1')
        self.assertEqual(self.client.get('/api/config').status_code, 401)

    def test_logout_revokes_replayed_cookie_and_preserves_other_device(self):
        _, headers = self.login()
        other = app.test_client()
        self.login(other)
        token = self.client.get_cookie(SESSION_COOKIE).value
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 200)
        self.client.set_cookie(SESSION_COOKIE, token)
        self.assertEqual(self.client.get('/api/config').status_code, 401)
        self.assertEqual(other.get('/api/config').status_code, 200)

    def test_csrf_and_cross_origin_rejected_before_handler(self):
        _, headers = self.login()
        self.assertEqual(self.client.post('/api/config', json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/config', json={}, headers={'X-BiliGo-CSRF': 'wrong'}).status_code, 403)
        for url in ('/api/config', '/api/auth/logout', '/api/auth/password'):
            self.assertEqual(self.client.post(url, json={}, headers={
                **headers, 'Origin': 'https://attacker.invalid',
            }).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout', headers=headers).status_code, 200)

    def test_login_requires_json_and_custom_header(self):
        self.assertEqual(self.client.post('/api/auth/login', json={'password': PASSWORD}).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/login', json={'password': PASSWORD}, headers={
            'X-BiliGo-Login': '1', 'Origin': 'https://attacker.invalid',
        }).status_code, 403)
        self.assertEqual(self.client.post('/api/auth/login', data={'password': PASSWORD},
                         headers={'X-BiliGo-Login': '1'}).status_code, 400)
        self.assertEqual(self.client.post('/api/auth/login', json={'password': PASSWORD}, headers={
            'X-BiliGo-Login': '1', 'Origin': 'https://[invalid',
        }).status_code, 403)

    def test_tls_proxy_cookie_and_origin_configuration(self):
        with patch.dict(os.environ, {'BILIGO_COOKIE_SECURE': '1'}):
            response = self.client.post('/api/auth/login', json={'password': PASSWORD}, headers={
                'X-BiliGo-Login': '1', 'Origin': 'https://localhost',
            })
            self.assertEqual(response.status_code, 200)
            self.assertIn('Secure', response.headers['Set-Cookie'])

    def test_login_throttle_is_persistent(self):
        for _ in range(8):
            response = self.client.post('/api/auth/login', json={'password': 'wrong'}, headers={'X-BiliGo-Login': '1'})
            self.assertEqual(response.status_code, 401)
        response = self.client.post('/api/auth/login', json={'password': PASSWORD}, headers={'X-BiliGo-Login': '1'})
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers['Retry-After']), 0)
        restarted = WebAuthStore(DATA.name)
        token, retry = restarted.login(PASSWORD, '127.0.0.1', False)
        self.assertIsNone(token)
        self.assertGreater(retry, 0)
        with self.store.connect() as db:
            db.execute('UPDATE attempts SET started = 1')
        self.login()

    def test_password_change_revokes_all_devices(self):
        _, headers = self.login()
        other = app.test_client()
        self.login(other, remember=True)
        new_password = 'New-security-test-password'
        try:
            response = self.client.post('/api/auth/password', json={
                'current_password': 'wrong', 'new_password': new_password,
            }, headers=headers)
            self.assertEqual(response.status_code, 401)
            response = self.client.post('/api/auth/password', json={
                'current_password': PASSWORD, 'new_password': new_password,
            }, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(other.get('/api/config').status_code, 401)
            self.assertEqual(self.client.get('/api/config').status_code, 401)
            self.assertIsNotNone(self.store.login(new_password, '127.0.0.1', False)[0])
            self.assertIsNone(self.store.login(PASSWORD, '127.0.0.1', False)[0])
        finally:
            self.store.reset_password(PASSWORD)

    def test_initial_password_and_cli_reset_policy(self):
        from web_access import validate_password
        for value in ('short', 'a' * 7, None, 'a' * 257):
            with self.assertRaises(ValueError):
                validate_password(value)
        for value in ('a' * 8, 'a' * 256):
            validate_password(value)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'BILIGO_PANEL_PASSWORD': ''}), patch('builtins.print') as output:
            store = WebAuthStore(directory)
            store.initialize()
            self.assertEqual(output.call_count, 1)
            with store.connect() as db:
                initial = db.execute('SELECT initial_password FROM credentials').fetchone()[0]
            self.assertIn(initial, str(output.call_args))
            WebAuthStore(directory).initialize()
            self.assertEqual(output.call_count, 2)
            self.assertIn(initial, str(output.call_args))
            store.initialize()
            self.assertEqual(output.call_count, 2, 'Only announce once per server instance')
            store.reset_password(PASSWORD)
            self.assertIsNotNone(store.login(PASSWORD, 'local', False)[0])
            with store.connect() as db:
                row = db.execute('SELECT password_state, initial_password FROM credentials').fetchone()
            self.assertEqual(row['password_state'], 'custom')
            self.assertIsNone(row['initial_password'])
            self.assertNotIn(initial.encode(), Path(store.path).read_bytes())
            output.reset_mock()
            WebAuthStore(directory).initialize()
            output.assert_not_called()

    def test_initial_login_cannot_bypass_password_setup(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'BILIGO_PANEL_PASSWORD': ''}), \
                patch.object(self.store, 'path', str(Path(directory) / AUTH_FILENAME)), \
                patch.object(self.store, 'initialized', False), patch('builtins.print'):
            self.store.initialize()
            with self.store.connect() as db:
                initial = db.execute('SELECT initial_password FROM credentials').fetchone()[0]
            client = app.test_client()
            response = client.post('/api/auth/login', json={'password': initial, 'remember': True},
                                   headers={'X-BiliGo-Login': '1'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['next'], '/panel-security?setup=1')
            self.assertTrue(response.json['must_change_password'])
            self.assertNotIn('Max-Age=', response.headers['Set-Cookie'])
            status = client.get('/api/auth/status').json
            self.assertTrue(status['must_change_password'])
            headers = {'X-BiliGo-CSRF': status['csrf_token']}
            token = client.get_cookie(SESSION_COOKIE).value
            pending = self.store.session(token)
            import time
            self.assertLessEqual(pending['expires'] - int(time.time()), 900)
            for path in ('/', '/dashboard', '/comment', '/index.html', '/config.json', '/logs.html'):
                response = client.get(path)
                self.assertEqual(response.status_code, 302, path)
                self.assertEqual(response.location, '/panel-security?setup=1')
            for path in ('/api/config', '/api/accounts', '/api/logs', '/api/export-config', '/api/douyin-config'):
                response = client.get(path)
                self.assertEqual(response.status_code, 428, path)
                self.assertEqual(response.json['code'], 'PASSWORD_CHANGE_REQUIRED')
            self.assertEqual(client.post('/api/config', json={}, headers=headers).status_code, 428)
            for path in ('/panel-security', '/web_auth.js', '/panel_security.js', '/auth-assets/panel_theme.js'):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, path)
                response.close()
            # Direct POST cannot bypass the current-password or different-password checks.
            self.assertEqual(client.post('/api/auth/password', json={
                'current_password': initial, 'new_password': PASSWORD,
            }).status_code, 403)
            self.assertEqual(client.post('/api/auth/password', json={
                'current_password': initial, 'new_password': initial,
            }, headers=headers).status_code, 400)
            response = client.post('/api/auth/password', json={
                'current_password': initial, 'new_password': PASSWORD,
            }, headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(self.store.session(token))
            self.assertEqual(client.get('/api/config').status_code, 401)
            response = client.post('/api/auth/login', json={'password': initial}, headers={'X-BiliGo-Login': '1'})
            self.assertEqual(response.status_code, 401)
            response = client.post('/api/auth/login', json={'password': PASSWORD}, headers={'X-BiliGo-Login': '1'})
            self.assertFalse(response.json['must_change_password'])
            self.assertEqual(client.get('/api/config').status_code, 200)

    def test_legacy_password_is_preserved_and_requires_setup(self):
        import sqlite3
        from werkzeug.security import generate_password_hash
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'BILIGO_PANEL_PASSWORD': ''}), patch('builtins.print') as output:
            database = Path(directory) / AUTH_FILENAME
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE credentials (id INTEGER PRIMARY KEY, password_hash TEXT NOT NULL)')
                old_hash = generate_password_hash(PASSWORD, method='pbkdf2:sha256:600000')
                db.execute('INSERT INTO credentials VALUES (1, ?)', (old_hash,))
            db.close()
            store = WebAuthStore(directory)
            store.initialize()
            with store.connect() as db:
                row = db.execute('SELECT * FROM credentials').fetchone()
            self.assertEqual(row['password_hash'], old_hash)
            self.assertEqual(row['password_state'], 'legacy')
            self.assertNotIn(PASSWORD, str(output.call_args))
            token, _ = store.login(PASSWORD, 'local', True)
            self.assertTrue(store.session(token)['must_change'])
            store.reset_to_initial_password()
            self.assertIsNone(store.session(token))
            self.assertIsNone(store.login(PASSWORD, 'local', False)[0])

    def test_local_initial_reset_cli(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            environment = {**os.environ, 'BILIGO_DATA_DIR': directory, 'BILIGO_PANEL_PASSWORD': '', 'PYTHONIOENCODING': 'utf-8'}
            result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'web_access.py'),
                                     '--reset-initial-password'], env=environment, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0)
            store = WebAuthStore(directory)
            with store.connect() as db:
                row = db.execute('SELECT password_state, initial_password FROM credentials').fetchone()
            self.assertEqual(row['password_state'], 'initial')
            self.assertIn(row['initial_password'], result.stdout.decode('utf-8'))

    def test_secure_cookie_and_cache_headers(self):
        with patch.dict(os.environ, {'BILIGO_COOKIE_SECURE': '1'}):
            response, _ = self.login()
        self.assertIn('Secure', response.headers['Set-Cookie'])
        for url in ('/login', '/api/config', '/config.json', '/health'):
            response = self.client.get(url)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            self.assertEqual(response.headers['X-Frame-Options'], 'DENY')

    def test_redirect_destination_is_local(self):
        for destination in ('//evil.invalid', '/%2f/evil.invalid', '/\\evil.invalid', '/api/config', '/%0d%0aLocation:bad'):
            response, _ = self.login(next_path=destination)
            self.assertEqual(response.json['next'], '/')
        response, _ = self.login(next_path='/dashboard?from=bili_message')
        self.assertEqual(response.json['next'], '/dashboard?from=bili_message')

    def test_sensitive_and_traversal_paths_blocked_even_after_login(self):
        self.login()
        urls = ('/config.json', '/douyin_storage.json', '/app.py', '/README.md',
                '/.git/config', '/.env', '/.biligo_web_token', '/' + AUTH_FILENAME,
                '/ai_conversations.sqlite3', '/docker/defaults/config.json', '/tools/xhs_history_debug.json',
                '/config.json::$DATA', '/C:/Windows/win.ini', '/%2e%2e/config.json',
                '/..%5cconfig.json', '/%252e%252e%252fconfig.json', '/static/config.json',
                '/auth-assets/config.json', '/auth-assets/../config.json', '/ai_knowledge/test.md')
        for url in urls:
            with self.subTest(url=url):
                self.assertIn(self.client.get(url).status_code, (403, 404))
        for name in PUBLIC_ASSETS:
            with self.subTest(asset=name):
                response = self.client.get('/' + name)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_image_browser_and_preview_boundaries(self):
        _, headers = self.login()
        root = Path(get_image_root())
        (root / 'safe.png').write_bytes(PNG)
        (root / 'pretend.png').write_text('secret plaintext', encoding='utf-8')
        (root / 'nested').mkdir(exist_ok=True)
        outside = Path(DATA.name) / 'outside.png'
        outside.write_bytes(PNG)
        home = self.client.get('/api/get-home-directory').json
        self.assertEqual(home['home_directory'], str(root))
        response = self.client.post('/api/browse-images', json={}, headers=headers)
        self.assertTrue(response.json['success'])
        self.assertNotIn('..', [item['name'] for item in response.json['items']])
        for path in (str(outside), '../outside.png', str(root) + '-sibling', 'C:\\Windows', '//server/share', 'safe.png:stream'):
            for api, key in (('/api/browse-images', 'folder_path'), ('/api/preview-image', 'image_path')):
                with self.subTest(path=path, api=api):
                    response = self.client.post(api, json={key: path}, headers=headers)
                    self.assertEqual(response.status_code, 403)
        preview = self.client.post('/api/preview-image', json={'image_path': str(root / 'safe.png')}, headers=headers)
        self.assertEqual(base64.b64decode(preview.json['image_data']), PNG)
        self.assertEqual(self.client.post('/api/preview-image', json={'image_path': str(root / 'pretend.png')}, headers=headers).status_code, 403)

    def test_symlinks_cannot_escape_asset_or_image_root(self):
        _, headers = self.login()
        with tempfile.TemporaryDirectory() as assets, tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / 'secret.png'
            secret.write_bytes(PNG)
            asset_link = Path(assets) / 'style.css'
            image_link = Path(get_image_root()) / 'escape.png'
            try:
                asset_link.symlink_to(secret)
                image_link.symlink_to(secret)
            except OSError as exc:
                self.skipTest('Host cannot create symlinks: ' + str(exc))
            try:
                with patch('web_files.get_static_root', return_value=assets):
                    self.assertEqual(self.client.get('/style.css').status_code, 404)
                response = self.client.post('/api/preview-image', json={'image_path': str(image_link)}, headers=headers)
                self.assertEqual(response.status_code, 403)
                listing = self.client.post('/api/browse-images', json={}, headers=headers).json
                self.assertNotIn('escape.png', [item['name'] for item in listing['items']])
            finally:
                image_link.unlink(missing_ok=True)

    def test_knowledge_symlinks_cannot_read_or_delete_other_files(self):
        import app as app_module
        from ai_reply_service import build_knowledge_context
        _, headers = self.login()
        root = Path(DATA.name) / 'ai_knowledge'
        root.mkdir(exist_ok=True)
        secret = Path(DATA.name) / 'private.txt'
        secret.write_text('private-content-must-stay-private', encoding='utf-8')
        link = root / 'escape.md'
        try:
            link.symlink_to(secret)
        except OSError as exc:
            self.skipTest('Host cannot create symlinks: ' + str(exc))
        knowledge = {
            'enabled': True,
            'bases': [{'id': 'test-base', 'name': 'test', 'text': '', 'documents': [
                {'id': 'escape', 'name': 'escape.md', 'path': str(link)},
            ]}],
        }
        try:
            with patch.dict(app_module.config, {'ai_knowledge_base': knowledge}):
                result = self.client.get('/api/ai-knowledge')
                self.assertNotIn('private-content', result.get_data(as_text=True))
                self.assertNotIn('private-content', build_knowledge_context(knowledge))
                response = self.client.delete('/api/ai-knowledge/documents/escape', headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(secret.exists())
        finally:
            link.unlink(missing_ok=True)

    def test_image_send_cannot_upload_files_outside_image_root(self):
        from app import BilibiliAPI
        outside = Path(DATA.name) / 'private-image.png'
        outside.write_bytes(PNG)
        api = BilibiliAPI.__new__(BilibiliAPI)
        with patch.object(api, '_get_upload_info') as network:
            self.assertIsNone(api.upload_image(str(outside)))
            network.assert_not_called()


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        DATA.cleanup()
