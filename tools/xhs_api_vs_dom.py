import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xiaohongshu_playwright import XiaohongshuBrowserWorker

for headless in (True, False):
    w = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=headless)
    w.start_worker()
    convs = w.list_conversations(quick=False)
    print('headless=', headless, 'count=', len(convs))
    for c in convs:
        print(' ', c.nickname, repr(c.last_message), 'store_id=', c.max_store_id, 'unread=', c.unread)
    w.stop_worker()
