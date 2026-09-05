import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from douyin_playwright import DouyinConversation
from xiaohongshu_reply_system import XiaohongshuReplySystem


def simulate(system, conv, *, prev_raw, only_new=True, has_unread=False):
    user_key = system._conv_user_key(conv)
    raw_fp = system._raw_preview(conv)
    steps = []

    if not raw_fp:
        return 'skip: empty raw_fp', steps
    if prev_raw is not None and raw_fp == prev_raw:
        return 'skip: same fingerprint', steps
    if prev_raw is None and only_new:
        return 'skip: only_new first sight', steps

    verify = system._should_verify_incoming_in_chat(conv, has_unread)
    steps.append(f'verify_in_chat={verify}')
    if has_unread and not verify:
        msg = system._incoming_text(conv)
        steps.append(f'direct preview -> {msg!r}')
    else:
        msg = system._fallback_incoming_text(conv) or '[would open chat]'
        steps.append(f'chat/fallback -> {msg!r}')
    return msg, steps


def main():
    system = XiaohongshuReplySystem()
    system.load_config()
    system.precompile_rules()
    conv = DouyinConversation(
        conv_id='6a959a490000000013002800',
        nickname='炽阳002',
        last_message='[表情]',
        unread=0,
        max_store_id=31,
        last_msg_time=1788191792000,
    )
    baseline = system._raw_preview(conv)
    print('baseline fp:', baseline)
    print('emoji direct preview?', system._should_use_direct_preview(conv, False))

    conv2 = DouyinConversation(**{**conv.__dict__, 'max_store_id': 32})
    if system._should_use_direct_preview(conv2, False):
        msg = system._incoming_text(conv2)
        print('new emoji via direct preview:', msg)
    print('match_rule:', system.match_rule('[表情]'))
    print('default enabled:', system.config.get('default_reply_enabled'))


if __name__ == '__main__':
    main()
