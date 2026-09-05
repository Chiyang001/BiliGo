"""Verify XHS sticker detection via worker."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from xiaohongshu_playwright import XiaohongshuBrowserWorker

STORAGE = os.path.join(ROOT, 'xiaohongshu_storage.json')


def main():
    worker = XiaohongshuBrowserWorker(storage_path=STORAGE, headless=True)
    worker.start_worker()
    convs = worker.list_conversations(quick=False)
    print('conversations:', len(convs))
    for conv in convs[:3]:
        print(
            ' -', conv.nickname,
            '| preview:', repr(conv.last_message),
            '| unread:', conv.unread,
        )
    if convs:
        conv = convs[0]
        latest = worker.read_latest_incoming(str(conv.conv_id or ''), conv.nickname or '')
        print('latest incoming:', latest)
    worker.close_browser()
    worker.stop_worker()


if __name__ == '__main__':
    main()
