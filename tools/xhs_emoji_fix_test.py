import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from xiaohongshu_playwright import XiaohongshuBrowserWorker
from xiaohongshu_reply_system import XiaohongshuReplySystem
from douyin_playwright import DouyinConversation


def test_direct_preview():
    system = XiaohongshuReplySystem()
    conv = DouyinConversation(
        conv_id='6a959a490000000013002800',
        nickname='炽阳002',
        last_message='[表情]',
        unread=0,
        max_store_id=40,
    )
    assert system._should_use_direct_preview(conv, False) is True
    assert system._incoming_text(conv) == '[表情]'
    print('direct preview ok')


def test_live():
    w = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=True)
    w.start_worker()
    convs = w.list_conversations(quick=False)
    if not convs:
        print('no convs')
        w.stop_worker()
        return
    c = convs[0]
    print('conv', c.nickname, c.last_message, c.max_store_id)
    latest = w.read_latest_incoming(str(c.conv_id), c.nickname)
    print('latest', latest)
    w.stop_worker()


if __name__ == '__main__':
    test_direct_preview()
    test_live()
