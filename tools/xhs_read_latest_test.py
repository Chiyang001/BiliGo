import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xiaohongshu_playwright import XiaohongshuBrowserWorker

w = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=True)
w.start_worker()
convs = w.list_conversations(quick=False)
print('convs', len(convs))
if convs:
    c = convs[0]
    print('fp fields:', c.last_message, c.max_store_id, c.last_msg_time, c.unread)
    latest = w.read_latest_incoming(str(c.conv_id), c.nickname)
    print('latest', latest)
w.stop_worker()
