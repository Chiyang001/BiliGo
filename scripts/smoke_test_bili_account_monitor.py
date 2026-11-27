"""Exercise the real monitor and HTTP client with two simulated Bilibili inboxes."""
import json
import logging
import time
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import smoke_test_bili_account_profiles as base

bili = base.bili


def wait_until(predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f'Timed out waiting for {predicate}')


class Response:
    status_code = 200

    def __init__(self, code=0, data=None):
        self.payload = {'code': code, 'data': data}

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


def check_monitor():
    uid_a, uid_b, sender = 1001, 1002, 77
    a, b = base.ACCOUNT_A, base.ACCOUNT_B
    accounts = [
        {'name': name, 'uid': uid, 'sessdata': token, 'bili_jct': token, 'enabled': True,
         'message_config': {'default_reply_message': reply}, 'im_dev_id': f'device-{uid}'}
        for name, uid, token, reply in [(a, uid_a, 'expired', 'reply-A'), (b, uid_b, 'live-B', 'reply-B')]
    ]
    accounts[0]['enabled'] = False
    bili.config.update(accounts=accounts, multi_account_mode=True, default_reply_enabled=True)
    bili.ensure_message_profiles()
    client = bili.app.test_client()
    base.login(client)
    tokens = {'renewed-A': uid_a, 'again-A': uid_a, 'live-B': uid_b}
    timestamp = int(time.time()) + 1
    incoming = {'sender_uid': sender, 'timestamp': timestamp, 'content': json.dumps({'content': 'hello'})}
    latest = {uid_a: incoming, uid_b: incoming}
    session_code = {}
    reject_send = set()
    delivered = []

    def get(session, url, **kwargs):
        token = session.cookies.get('SESSDATA')
        uid = tokens.get(token)
        if url.endswith('/nav'):
            return Response(0 if uid else -101, {'mid': uid})
        if url.endswith('/get_sessions'):
            return Response(session_code.get(uid, 0), {'session_list': [{'talker_id': sender, 'last_msg': latest[uid]}]})
        if url.endswith('/fetch_session_msgs'):
            return Response(data={'messages': [latest[uid]]})
        return Response()  # Session warmup

    def post(session, url, data, **kwargs):
        assert url.endswith('/send_msg')
        token = session.cookies.get('SESSDATA')
        uid = tokens[token]
        assert data['csrf'] == token
        assert data['msg[sender_uid]'] == uid and data['msg[receiver_id]'] == sender
        assert data['msg[dev_id]'] == f'device-{uid}'
        if token in reject_send:
            return Response(-101)
        text = json.loads(data['msg[content]'])['content']
        delivered.append((uid, text))
        latest[uid] = dict(latest[uid], sender_uid=uid, content=data['msg[content]'])
        return Response()

    def renew(token):
        return client.post('/api/accounts', json={
            'action': 'reauthenticate', 'name': a, 'sessdata': token, 'bili_jct': token,
        })

    def states():
        return client.get('/api/status').json['message_account_states']

    with patch.object(bili.requests.Session, 'get', get), patch.object(bili.requests.Session, 'post', post), \
            patch.object(bili, 'send_login_expired_notification') as notify:
        assert client.post('/api/start').json['success']
        try:
            wait_until(lambda: states() == {a: 'disabled', b: 'running'} and len(delivered) == 1)
            assert client.post('/api/accounts', json={'action': 'update', 'name': a, 'enabled': True}).json['success']
            wait_until(lambda: states() == {a: 'login_required', b: 'running'} and len(delivered) == 1)
            worker_b = bili.monitor_threads[b]
            assert renew('live-B').status_code == 400 and accounts[0]['sessdata'] == 'expired'
            assert not renew('invalid').json['success'] and accounts[0]['sessdata'] == 'expired'
            session_code[uid_a] = -509
            assert renew('renewed-A').json['success']
            wait_until(lambda: states()[a] == 'retrying')
            session_code[uid_a] = 0
            wait_until(lambda: len(delivered) == 2 and states()[a] == 'running')
            assert Counter(delivered) == {(uid_a, 'reply-A'): 1, (uid_b, 'reply-B'): 1}
            assert bili.monitor_threads[b] is worker_b
            metrics = bili.dashboard_metrics.snapshot('today', {})['platforms']
            assert next(row for row in metrics if row['id'] == 'bili_message')['inbound'] == 2
            saved = json.loads(Path(bili.CONFIG_FILE).read_text(encoding='utf-8'))['accounts']
            assert saved[0]['sessdata'] == 'renewed-A' and saved[1]['sessdata'] == 'live-B'
            assert saved[0]['message_config']['default_reply_message'] == 'reply-A'
            # An explicit send rejection can be retried after reauth, even at the same timestamp.
            reject_send.add('renewed-A')
            latest[uid_a] = dict(incoming, timestamp=timestamp + 1)
            wait_until(lambda: states()[a] == 'login_required')
            assert renew('again-A').json['success']
            wait_until(lambda: len(delivered) == 3)
            assert delivered[-1] == (uid_a, 'reply-A')
            session_code[uid_a] = -101
            wait_until(lambda: states()[a] == 'login_required')
            latest[uid_b] = dict(incoming, timestamp=timestamp + 2)
            wait_until(lambda: len(delivered) == 4)
            assert delivered[-1] == (uid_b, 'reply-B') and bili.monitor_threads[b] is worker_b
            assert [call.args for call in notify.call_args_list] == [(a,)] * 3
            # A fresh run with both accounts already logged in handles identical DMs independently.
            assert client.post('/api/stop').json['success']
            session_code.clear()
            latest[uid_a] = latest[uid_b] = dict(incoming, timestamp=timestamp + 3)
            assert client.post('/api/start').json['success']
            wait_until(lambda: len(delivered) == 6)
            assert Counter(delivered[-2:]) == {(uid_a, 'reply-A'): 1, (uid_b, 'reply-B'): 1}
        finally:
            assert client.post('/api/stop').json['success']
            assert not bili.monitor_thread.is_alive()
            assert all(not worker.is_alive() for worker in bili.monitor_threads.values())


if __name__ == '__main__':
    logging.getLogger().setLevel(logging.WARNING)
    try:
        check_monitor()
        print('Two-account monitoring, reauthentication, backoff and isolated replies passed')
    finally:
        base.DATA_DIR.cleanup()
