"""Verify account-specific AI, knowledge, conversation memory, handoffs and SMTP without external sends."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import smoke_test_bili_account_profiles as base

bili = base.bili
A, B = base.ACCOUNT_A, base.ACCOUNT_B
scoped = base.scoped


def check_services():
    client = bili.app.test_client()
    base.login(client)
    # Upgrade profiles created before AI/mail isolation without losing their existing settings.
    bili.config['ai_provider'] = {
        'enabled': False, 'format': 'openai', 'base_url': 'https://legacy.invalid/v1', 'model': 'legacy',
        'api_key': 'legacy-key', 'platforms': {'bili_message': True},
    }
    bili.config['email_notification'].update(enabled=True, sender_email='legacy@qq.com', receiver_email='legacy@example.com')
    knowledge_dir = Path(base.DATA_DIR.name) / 'ai_knowledge'
    knowledge_dir.mkdir(exist_ok=True)
    legacy_document = knowledge_dir / 'legacy.md'
    legacy_document.write_text('shared legacy knowledge', encoding='utf-8')
    bili.config['ai_knowledge_base'] = {
        'enabled': True, 'bases': [{'id': 'legacy', 'name': 'legacy', 'text': '',
                                  'documents': [{'id': 'legacy-doc', 'path': str(legacy_document)}]}],
        'platform_assignments': {'bili_message': ['legacy']},
    }
    for account in bili.config['accounts']:
        for key in bili.MESSAGE_SERVICE_DEFAULTS:
            account['message_config'].pop(key, None)
    bili.ensure_message_profiles()
    assert bili.get_message_config(A)['ai_provider'] is not bili.get_message_config(B)['ai_provider']
    assert bili.get_message_config(A)['email_notification'] is not bili.get_message_config(B)['email_notification']
    assert client.delete(scoped('/api/ai-knowledge/documents/legacy-doc', A)).json['success']
    assert legacy_document.is_file(), 'removing a migrated document must preserve other profiles'
    assert client.get(scoped('/api/ai-knowledge', B)).json['bases'][0]['text'] == 'shared legacy knowledge'

    for name, tag in [(A, 'a'), (B, 'b')]:
        base.post(client, '/api/ai-config', name, {
            'enabled': True, 'format': 'openai', 'base_url': f'https://{tag}.invalid/v1',
            'model': f'model-{tag}', 'api_key': f'key-{tag}', 'platforms': {'bili_message': True},
            'model_settings': {'context_enabled': True, 'context_window': 6000, 'prohibited_words': [tag]},
            'human_handoff': {'enabled': name == A},
        })
        config = client.get(scoped('/api/ai-config', name)).json
        assert config['api_key'] == '' and config['api_key_configured']
        base.post(client, '/api/ai-config', name, {'model_settings': {'auto_compress': False}})
        assert bili.get_message_config(name)['ai_provider']['api_key'] == f'key-{tag}'
        created = client.post(scoped('/api/ai-knowledge', name), json={'name': f'knowledge-{tag}', 'text': f'knowledge for {tag}'})
        knowledge_id = created.json['knowledge_base']['id']
        base.post(client, '/api/ai-knowledge/settings', name, {'enabled': True, 'platform_assignments': {'bili_message': [knowledge_id]}})
        base.post(client, '/api/save_email_config', name, {
            'enabled': True, 'smtp_server': f'smtp-{tag}.invalid', 'smtp_port': 587,
            'sender_email': f'{tag}@qq.com', 'sender_password': f'smtp-key-{tag}', 'receiver_email': f'{tag}@example.com',
        })
    assert bili.config['ai_provider']['model'] == 'legacy'
    assert bili.config['email_notification']['receiver_email'] == 'legacy@example.com'
    assert client.get(scoped('/api/get_email_config', A)).json['config']['receiver_email'] == 'a@example.com'
    assert client.get(scoped('/api/platform-email-config/bili_message', B)).json['config']['receiver_email'] == 'b@example.com'
    assert client.post('/api/save_email_config', json={'enabled': False}).status_code == 400
    assert client.get(scoped('/api/ai-config', 'missing')).status_code == 404

    # Provider tests and model-list requests reuse only the selected account's masked key.
    with patch.object(bili.requests, 'post', return_value=SimpleNamespace(ok=True)) as request:
        assert client.post(scoped('/api/ai-test', A), json={}).json['success']
        assert request.call_args.args[0] == 'https://a.invalid/v1/chat/completions'
        assert request.call_args.kwargs['headers']['Authorization'] == 'Bearer key-a'
    with patch.object(bili, '_request_ai_models', return_value=(SimpleNamespace(json=lambda: {'data': [{'id': 'test-model'}]}), 100)) as models:
        assert client.post(scoped('/api/ai-models', B), json={}).json['models'] == ['test-model']
        assert models.call_args.args[0]['api_key'] == 'key-b'

    class FakeAPI:
        def __init__(self, name):
            self.account_name = name

        def get_latest_message(self, _):
            return {'timestamp': int(time.time()) + 2, 'sender_uid': 555, 'content': json.dumps({'content': 'hello there'})}

    captured = []

    def decision(message, context, provider, knowledge, platform):
        selected_ids = set(knowledge['platform_assignments']['bili_message'])
        texts = [row['text'] for row in knowledge['bases'] if row['id'] in selected_ids]
        captured.append((provider['model'], texts))
        return {'needs_human': False, 'reply': provider['model']}

    def process(name):
        return bili.process_single_session_with_cache(FakeAPI(name), 1001, {'talker_id': 77}, {}, {}, account_uid=1001)

    with patch.object(bili, 'generate_shared_ai_decision', side_effect=decision):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(process, [A, B] * 10))
    assert [row[0]['rule']['reply'] for row in results] == ['model-a', 'model-b'] * 10
    assert all(texts == [f'knowledge for {model[-1]}'] for model, texts in captured)

    # One account can use AI while another keeps its traditional rules editable.
    base.post(client, '/api/ai-config', B, {'enabled': False})
    assert client.post(scoped('/api/rules', A), json={'rules': []}).status_code == 409
    base.post(client, '/api/rules', B, {'rules': []})
    result = {'talker_id': 77, 'timestamp': int(time.time()), 'message': 'same user', 'rule': {'title': 'AI reply'}}
    bili._record_bili_ai_context(result, 'private-answer-A', A)
    bili._record_bili_ai_context(result, 'private-answer-B', B)
    context_a = bili.build_conversation_context('bili_message', bili.message_conversation_key(77, A), bili.get_message_config(A)['ai_provider'])
    context_b = bili.build_conversation_context('bili_message', bili.message_conversation_key(77, B), bili.get_message_config(B)['ai_provider'])
    assert 'private-answer-A' in context_a and 'private-answer-B' not in context_a
    assert 'private-answer-B' in context_b and 'private-answer-A' not in context_b

    ids = [bili.queue_ai_handoff('bili_message', 'same-event', 'user', '77', 'help', 'uncertain', {'talker_id': 77, 'account_name': name}) for name in (A, B)]
    assert ids[0] != ids[1]
    for name, item_id in zip((A, B), ids):
        response = client.get(scoped('/api/ai-handoffs', name)).json
        assert response['pending_count'] == 1 and [row['id'] for row in response['items']] == [item_id]
    assert client.post(scoped(f'/api/ai-handoffs/{ids[0]}/dismiss', B)).status_code == 404
    assert client.post(scoped(f'/api/ai-handoffs/{ids[0]}/reply', B), json={'text': 'wrong account'}).status_code == 404
    assert client.get('/api/ai-handoffs').json['pending_count'] == 0

    # SMTP is intercepted; no test or alert reaches a real recipient.
    sent = []

    class FakeSMTP:
        def __init__(self, server, port, timeout):
            self.server = server

        def starttls(self):
            pass

        def login(self, sender, password):
            self.credentials = (sender, password)

        def send_message(self, message):
            sent.append((self.server, self.credentials, message['To']))

        def quit(self):
            pass

    with patch('smtplib.SMTP', FakeSMTP):
        bili.error_tracker.clear()
        bili.last_error_email_notify_times.clear()
        assert bili.track_and_notify_error('same-error', 'same-message', account_name=A)
        assert bili.track_and_notify_error('same-error', 'same-message', account_name=B)
        assert not bili.track_and_notify_error('another-error', 'same-message', account_name=A)
        assert bili.send_login_expired_notification(A)
        assert client.post(scoped('/api/test_email', B), json={}).json['success']
        base.post(client, '/api/save_email_config', B, {'enabled': False})
        assert not bili.send_login_expired_notification(B)
    assert [row[2] for row in sent] == ['a@example.com', 'b@example.com', 'a@example.com', 'b@example.com']
    assert sent[0][:2] == ('smtp-a.invalid', ('a@qq.com', 'smtp-key-a'))
    assert sent[1][:2] == ('smtp-b.invalid', ('b@qq.com', 'smtp-key-b'))
    bili.load_config()
    assert bili.get_message_config(A)['ai_provider']['model'] == 'model-a'
    assert bili.get_message_config(B)['ai_provider']['model'] == 'model-b'
    assert bili.get_message_email_config(B)['enabled'] is False


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
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            assert page.request.post(origin + '/api/auth/login', data={'password': os.environ['BILIGO_PANEL_PASSWORD']}, headers={'X-BiliGo-Login': '1'}).ok
            page.goto(origin + '/#tab=account')
            page.wait_for_function("document.querySelector('#message-config-account').options.length === 2")
            page.wait_for_function("document.querySelector('#receiver-email').value === 'a@example.com'")
            page.locator('.ai-reply-nav').click()
            page.wait_for_function("document.querySelector('#ai-model').value === 'model-a'")
            assert page.locator('#ai-enabled').is_checked()
            assert page.locator('#ai-config-account').input_value() == '0'
            assert page.locator('[data-tab="douyin"]').is_hidden()
            page.locator('#ai-config-account').select_option('1')
            page.wait_for_function("document.querySelector('#ai-model').value === 'model-b'")
            assert not page.locator('#ai-enabled').is_checked()
            page.locator('[data-tab="provider"]').click()
            page.locator('#ai-model').fill('ui-model-b')
            page.locator('#ai-save-button').click()
            page.wait_for_function("document.querySelector('#ai-save-result').textContent.includes('已保存')")
            assert bili.get_message_config(B)['ai_provider']['model'] == 'ui-model-b'
            assert bili.get_message_config(A)['ai_provider']['model'] == 'model-a'
            page.locator('#ai-back-button').click()
            page.locator('[data-platform-tab="account"]').click()
            page.wait_for_function("document.querySelector('#message-config-account').value === " + json.dumps(B))
            page.locator('#email-toggle-icon').click()
            page.locator('#email-notification-enabled').check()
            page.locator('#sender-email').fill('b@qq.com')
            page.locator('#sender-password').fill('ui-smtp-key-b')
            page.locator('#receiver-email').fill('ui-b@example.com')
            page.locator('button[onclick="saveEmailConfig()"]').click()
            page.wait_for_function("document.querySelector('#toast-container').textContent.includes('邮件配置保存成功')")
            assert bili.get_message_email_config(B)['receiver_email'] == 'ui-b@example.com'
            assert bili.get_message_email_config(A)['receiver_email'] == 'a@example.com'
            # A has AI locked; B remains editable after returning from the AI page.
            page.locator('[data-platform-tab="reply"]').click()
            assert page.locator('#default-reply-message').is_enabled()
            page.locator('#message-config-account').select_option(A)
            page.wait_for_function("document.body.classList.contains('ai-mode-active')")
            assert page.locator('#default-reply-message').is_disabled()
            page.goto(origin + '/ai-reply?from=douyin')
            page.wait_for_function("document.querySelector('#ai-model').value === 'legacy'")
            assert page.locator('#ai-config-account').input_value() == 'global'
            assert page.locator('[data-tab="douyin"]').is_visible()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    logging.getLogger('app').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    try:
        base.check_profiles()
        check_services()
        check_ui()
        print('Account AI, knowledge, context, handoff, email and UI checks passed (external calls mocked)')
    finally:
        base.DATA_DIR.cleanup()
