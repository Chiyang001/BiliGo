import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from xiaohongshu_playwright import XiaohongshuBrowserWorker
from xiaohongshu_reply_system import XiaohongshuReplySystem
from douyin_playwright import DouyinConversation


def main():
    system = XiaohongshuReplySystem()
    system.load_config()

    w = XiaohongshuBrowserWorker(os.path.join(ROOT, 'xiaohongshu_storage.json'), headless=True)
    account = system.config.get('account') or {}
    w.set_account_identity(uid=str(account.get('uid') or ''), nickname=str(account.get('nickname') or ''))
    w.start_worker()
    convs = w.list_conversations(quick=False)
    if not convs:
        print('no conversations')
        w.stop_worker()
        return

    c = convs[0]
    print('conv:', c.nickname, c.last_message, 'store_id=', c.max_store_id)

    debug = w._call(
        'fetch_history_debug', timeout=30,
        chat_user_id=str(c.conv_id), last_id=int(c.max_store_id or 0),
    )
    out = os.path.join(ROOT, 'tools', 'xhs_history_debug.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(debug, f, ensure_ascii=False, indent=2)
    print('saved', out)
    print('rows', len((debug or {}).get('rows') or []))

    peek = w.peek_latest_incoming(str(c.conv_id), int(c.max_store_id or 0))
    print('peek', peek)

    conv = DouyinConversation(
        conv_id=c.conv_id,
        nickname=c.nickname,
        last_message=c.last_message,
        unread=c.unread,
        max_store_id=c.max_store_id,
        last_msg_time=c.last_msg_time,
        update_time=c.update_time,
    )
    baseline = system._raw_preview(conv)
    print('baseline fp:', baseline)
    print('direct preview?', system._should_use_direct_preview(conv, False))
    print('incoming:', system._incoming_text(conv))
    print('postprocess:', system._postprocess_incoming_text(conv, '[表情]', w))

    w.stop_worker()


if __name__ == '__main__':
    main()
