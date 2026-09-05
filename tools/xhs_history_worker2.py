"""Fetch XHS message history with correct last_id."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xiaohongshu_playwright import XiaohongshuBrowserWorker

CHAT_USER_ID = '6a959a490000000013002800'


def main():
    worker = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=True)
    worker.start_worker()
    convs = worker.list_conversations(quick=False)
    conv = convs[0] if convs else None
    print('conv', conv.nickname if conv else None, conv.max_store_id if conv else None)
    worker._call('navigate_messages', timeout=60)
    for last_id in (0, conv.max_store_id if conv else 0, (conv.max_store_id + 1) if conv else 0):
        url = (
            'https://edith.xiaohongshu.com/api/im/web/messages/history'
            f'?chat_user_id={CHAT_USER_ID}&last_id={last_id}&start_id=0&limit=10'
        )
        body = worker._call('fetch_xhs_json', timeout=30, url=url) if False else None
    worker.stop_worker()


if __name__ == '__main__':
    main()
