"""Simulate XHS emoji fingerprint + reply decision logic."""
import os
import sys
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from douyin_playwright import DouyinConversation
from xiaohongshu_reply_system import XiaohongshuReplySystem


def test_fingerprint_changes_on_same_preview():
    system = XiaohongshuReplySystem()
    conv1 = DouyinConversation(
        conv_id='abc', nickname='test', last_message='[表情]', max_store_id=10,
    )
    conv2 = DouyinConversation(
        conv_id='abc', nickname='test', last_message='[表情]', max_store_id=11,
    )
    fp1 = system._raw_preview(conv1)
    fp2 = system._raw_preview(conv2)
    assert fp1 != fp2, (fp1, fp2)
    assert system._incoming_text(conv1) == '[表情]'
    assert system._fallback_incoming_text(conv1) == '[表情]'
    assert system._should_verify_incoming_in_chat(conv1, has_unread=False) is True
    print('fingerprint ok:', fp1, '->', fp2)


if __name__ == '__main__':
    test_fingerprint_changes_on_same_preview()
