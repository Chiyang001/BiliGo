import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xiaohongshu_playwright import XiaohongshuBrowserWorker

w = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=True)
w.start_worker()
convs = w.list_conversations(quick=False)
for c in convs:
    print(c.nickname, c.last_message, c.max_store_id, c.last_msg_time, c.unread)
w.stop_worker()
