"""Fetch XHS message history via worker thread."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xiaohongshu_playwright import XiaohongshuBrowserWorker, XHS_CHAT_MESSAGES_JS

CHAT_USER_ID = '6a959a490000000013002800'


def main():
    worker = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=True)
    worker.start_worker()
    worker._call('navigate_messages', timeout=60)
    worker._call('open_conversation', timeout=45, nickname='炽阳002', category='friend', from_panel=True)
    worker._scroll_xhs_chat_to_bottom()
    history_url = (
        'https://edith.xiaohongshu.com/api/im/web/messages/history'
        f'?chat_user_id={CHAT_USER_ID}&last_id=0&start_id=0&limit=10'
    )
    body = worker._fetch_xhs_json(history_url)
    out = os.path.join(ROOT, 'tools', 'xhs_message_history_worker.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(body or {}, f, ensure_ascii=False, indent=2)
    print('saved', out)
    if body:
        print(json.dumps(body, ensure_ascii=False, indent=2)[:8000])
    msgs = worker._page.evaluate(XHS_CHAT_MESSAGES_JS) or []
    print('dom messages tail:', json.dumps(msgs[-5:], ensure_ascii=False))
    worker.close_browser()
    worker.stop_worker()


if __name__ == '__main__':
    main()
