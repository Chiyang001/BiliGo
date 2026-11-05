"""Account profile isolation, migration, runtime dispatch and UI refresh regression checks."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

DATA_DIR = tempfile.TemporaryDirectory()
os.environ['BILIGO_DATA_DIR'] = DATA_DIR.name
os.environ['BILIGO_PANEL_PASSWORD'] = 'BiliGo-profile-test-password'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as bili  # noqa: E402

ACCOUNT_A = "主号 <A>"
ACCOUNT_B = "备用 & '号"


def scoped(path, name):
    return path + '?' + urlencode({'account': name})


def login(client):
    assert client.post('/api/auth/login', json={'password': os.environ['BILIGO_PANEL_PASSWORD']},
                       headers={'X-BiliGo-Login': '1'}).status_code == 200
    client.environ_base['HTTP_X_BILIGO_CSRF'] = client.get('/api/auth/status').json['csrf_token']


def post(client, path, name, data):
    response = client.post(scoped(path, name), json=data)
    assert response.status_code == 200 and response.json['success'], response.get_data(as_text=True)


def check_profiles():
    bili.config.update(multi_account_mode=True, default_reply_enabled=True, default_reply_message='legacy',
                       accounts=[{'name': name, 'uid': uid, 'sessdata': 'test-session', 'bili_jct': 'test-token', 'enabled': True}
                                 for name, uid in [(ACCOUNT_A, 1001), (ACCOUNT_B, 1002)]])
    bili.rules = [{'id': 1, 'name': 'legacy', 'keyword': 'legacy', 'reply': 'old', 'enabled': True}]
    bili.precompile_rules()
    bili.save_config()
    bili.save_rules()
    client = bili.app.test_client()
    login(client)

    # Migrate once, preserving legacy behavior without sharing mutable lists.
    assert client.get(scoped('/api/config', ACCOUNT_A)).json['default_reply_message'] == 'legacy'
    assert bili.get_message_account(ACCOUNT_A)['message_rules'] is not bili.get_message_account(ACCOUNT_B)['message_rules']
    for name, message in [(ACCOUNT_A, 'reply-A'), (ACCOUNT_B, 'reply-B')]:
        post(client, '/api/config', name, {'default_reply_message': message})
        post(client, '/api/rules', name, {'rules': [{'id': 2, 'name': name, 'keyword': 'hello', 'reply': message, 'enabled': True}]})
        post(client, '/api/follow-reply-config', name, {'follow_reply_message': message})
        post(client, '/api/unfollow-reply-config', name, {'unfollow_reply_message': message})
    post(client, '/api/timing-config', ACCOUNT_A, {'message_check_interval': 0.1, 'send_delay_interval': 2})
    post(client, '/api/new-message-config', ACCOUNT_A, {'unlimited_replies_per_user': False, 'max_replies_per_user': 2})
    assert bili.get_user_reply_limit(ACCOUNT_A) == 2
    assert bili.get_user_reply_limit(ACCOUNT_B) is None
    assert client.get(scoped('/api/timing-config', ACCOUNT_B)).json['send_delay_interval'] == 1
    assert bili.config['default_reply_message'] == 'legacy'
    assert bili.rules[0]['keyword'] == 'legacy'
    assert client.post('/api/rules', json={'rules': []}).status_code == 400
    assert client.post(scoped('/api/config', ACCOUNT_A), json={'accounts': []}).status_code == 400
    assert client.post(scoped('/api/config', 'missing'), json={'default_reply_message': 'wrong'}).status_code == 404

    # Reducing one account's limit must preserve the other's counters.
    bili.save_user_reply_stats({'1001_77': {'count': 2}, '1002_77': {'count': 3}, '77': {'count': 1}})
    post(client, '/api/new-message-config', ACCOUNT_A, {'max_replies_per_user': 1})
    stats = bili.load_user_reply_stats()
    assert '1001_77' not in stats and stats['1002_77']['count'] == 3 and '77' in stats
    bili.save_user_reply_stats({})

    class FakeAPI:
        def __init__(self, name, message):
            self.account_name = name
            self.message = message

        def get_latest_message(self, talker_id):
            return {'timestamp': int(time.time()) + 1, 'sender_uid': 777, 'content': json.dumps({'content': self.message})}

    def process(case):
        name, message = case
        uid = 1001 if name == ACCOUNT_A else 1002
        result = bili.process_single_session_with_cache(FakeAPI(name, message), uid, {'talker_id': 77}, {}, {}, account_uid=uid)
        return result[0]['rule']['reply']

    cases = [(ACCOUNT_A, 'hello'), (ACCOUNT_B, 'hello'), (ACCOUNT_A, 'other'), (ACCOUNT_B, 'other')] * 20
    with ThreadPoolExecutor(max_workers=8) as executor:
        replies = list(executor.map(process, cases))
    assert replies == ['reply-A', 'reply-B', 'reply-A', 'reply-B'] * 20

    # Empty account rules are intentional and survive loading; exports contain only this profile.
    post(client, '/api/rules', ACCOUNT_B, {'rules': []})
    bili.load_config()
    bili.load_rules()
    assert bili.check_keywords_fast('hello', ACCOUNT_B) is None
    assert bili.check_keywords_fast('hello', ACCOUNT_A)['reply'] == 'reply-A'
    exported = json.loads(client.get(scoped('/api/export-config', ACCOUNT_A)).data)
    assert exported['config']['default_reply_message'] == 'reply-A'
    assert 'accounts' not in exported['config'] and 'sessdata' not in exported['config']
    response = client.post(scoped('/api/import-config', ACCOUNT_B), data={
        'file': (io.BytesIO(json.dumps(exported).encode()), 'profile.json'), 'import_mode': 'replace',
    })
    assert response.status_code == 200 and response.json['success'], response.get_data(as_text=True)
    post(client, '/api/config', ACCOUNT_B, {'default_reply_message': 'reply-B'})
    assert bili.get_message_config(ACCOUNT_A)['default_reply_message'] == 'reply-A'
    assert bili.check_keywords_fast('hello', ACCOUNT_B)['reply'] == 'reply-A'

    # Cross-platform imports also respect the chosen target/source account.
    bili.comment_config.update(default_comment_reply_enabled=True, default_comment_reply_message='comment')
    bili.comment_rules[:] = [{'id': 3, 'name': 'comment', 'keyword': 'comment', 'reply': 'from-comment'}]
    bili.save_comment_config()
    bili.save_comment_rules()
    post(client, '/api/platform-import', ACCOUNT_B, {'source': 'bili_comment', 'target': 'bili_message', 'mode': 'replace'})
    assert bili.get_message_config(ACCOUNT_A)['default_reply_message'] == 'reply-A'
    assert bili.get_message_config(ACCOUNT_B)['default_reply_message'] == 'comment'
    post(client, '/api/platform-import', ACCOUNT_A, {'source': 'bili_message', 'target': 'bili_comment', 'mode': 'replace'})
    assert bili.comment_config['default_comment_reply_message'] == 'reply-A'
    post(client, '/api/config', ACCOUNT_B, {'default_reply_message': 'reply-B'})

    # Single-account behavior and its independent settings remain available.
    client.post('/api/accounts', json={'action': 'toggle_mode', 'enabled': False})
    assert client.post('/api/config', json={'default_reply_message': 'single'}).json['success']
    assert bili.get_message_config(ACCOUNT_A)['default_reply_message'] == 'reply-A'
    client.post('/api/accounts', json={'action': 'toggle_mode', 'enabled': True})


def check_ui():
    from playwright.sync_api import sync_playwright
    from werkzeug.serving import make_server

    server = make_server('127.0.0.1', 0, bili.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page_errors = []
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            assert page.request.post(origin + '/api/auth/login', data={'password': os.environ['BILIGO_PANEL_PASSWORD']},
                                     headers={'X-BiliGo-Login': '1'}).ok
            page.goto(origin + '/#tab=reply')
            page.wait_for_function("document.querySelector('#default-reply-message').value === 'reply-A'")
            assert page.locator('#message-config-account').input_value() == ACCOUNT_A
            page.locator('#message-config-account').select_option(ACCOUNT_B)
            page.wait_for_function("document.querySelector('#default-reply-message').value === 'reply-B'")
            assert page.locator('#message-config-account').input_value() == ACCOUNT_B
            page.wait_for_function("rules.length === 1 && rules[0].keyword === 'comment'")
            cached_a = page.evaluate("name => JSON.parse(localStorage.getItem('bilibili_reply_rules:account:' + encodeURIComponent(name)))", ACCOUNT_A)
            cached_b = page.evaluate("name => JSON.parse(localStorage.getItem('bilibili_reply_rules:account:' + encodeURIComponent(name)))", ACCOUNT_B)
            assert cached_a[0]['keyword'] == 'hello' and cached_b[0]['keyword'] == 'comment'
            # Save through the actual form and verify it does not affect A.
            page.locator('#default-reply-message').fill('UI-B')
            with page.expect_response(lambda response: '/api/config?' in response.url and response.request.method == 'POST'):
                page.locator('button[onclick="saveDefaultReply()"]').click()
            assert bili.get_message_config(ACCOUNT_B)['default_reply_message'] == 'UI-B'
            assert bili.get_message_config(ACCOUNT_A)['default_reply_message'] == 'reply-A'
            screenshot_dir = os.environ.get('BILIGO_TEST_SCREENSHOT_DIR')
            if screenshot_dir:
                Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(screenshot_dir) / 'bili-profiles-desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.locator('#message-config-account').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            if screenshot_dir:
                page.screenshot(path=str(Path(screenshot_dir) / 'bili-profiles-mobile.png'))
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.locator('[data-platform-tab="account"]').click()
            assert page.locator('.account-name').first.text_content().startswith(ACCOUNT_A)
            page.locator('[data-platform-tab="control"]').click()
            page.wait_for_function("!document.querySelector('#start-btn').disabled")
            # Model a cached logged-out homepage, then return from account configuration.
            page.locator('[data-platform-tab="account"]').click()
            page.evaluate('isMessageLoggedIn=false; updateButtonStates()')
            assert page.locator('#start-btn').is_disabled()
            with page.expect_response(lambda response: '/api/status' in response.url):
                page.locator('[data-platform-tab="control"]').click()
            page.wait_for_function("!document.querySelector('#start-btn').disabled")
            assert page.locator('#login-required-hint').is_hidden()
            page.evaluate('isMessageLoggedIn=false; updateButtonStates(); window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted:true}))')
            page.wait_for_function("!document.querySelector('#start-btn').disabled")
            # A real single-account login save must refresh the previously disabled homepage.
            page.evaluate("fetch('/api/accounts', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action:'toggle_mode', enabled:false})}).then(r => r.json())")
            page.reload()
            page.locator('[data-platform-tab="account"]').click()
            page.locator('#sessdata').fill('ui-session')
            page.locator('#bili_jct').fill('ui-token')
            page.evaluate('saveConfig()')
            page.locator('[data-platform-tab="control"]').click()
            page.wait_for_function("!document.querySelector('#start-btn').disabled")
            assert not page_errors, page_errors
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    try:
        check_profiles()
        check_ui()
        print('Bilibili account profile and homepage refresh checks passed')
    finally:
        DATA_DIR.cleanup()
