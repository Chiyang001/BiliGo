"""小红书网页版私信 Playwright 自动化。"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from douyin_playwright import (
    DouyinAccountInfo,
    DouyinBrowserWorker,
    EXTRACT_CHAT_MESSAGES_JS,
    FOCUS_CHAT_EDITOR_JS,
)

logger = logging.getLogger(__name__)

XHS_HOME = 'https://www.xiaohongshu.com/explore'
XHS_CHAT = 'https://www.xiaohongshu.com/chat'
XHS_SESSION_COOKIES = {'web_session'}
XHS_CHATS_API = 'https://edith.xiaohongshu.com/api/im/web/v3/chats?limit=100&complete=true&page={page}&source=pc'
XHS_UNREAD_API = 'https://edith.xiaohongshu.com/api/im/web/chat/get_unread'
XHS_HISTORY_API = (
    'https://edith.xiaohongshu.com/api/im/web/messages/history'
    '?chat_user_id={chat_user_id}&last_id={last_id}&start_id=0&limit={limit}'
)

EXTRACT_XHS_CONVERSATIONS_JS = r"""
() => {
  const result = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('.xhs-im-conv-item[data-conv-id], .xhs-im-conv-item')) {
    const nickname = (el.querySelector('.xhs-im-conv-item__name')?.innerText || '').trim();
    if (!nickname || seen.has(nickname)) continue;
    let preview = (el.querySelector('.xhs-im-conv-item__summary')?.innerText || '').trim();
    if (!preview) {
      const sticker = el.querySelector('.xhs-im-conv-item__bottom img, .xhs-im-conv-item__summary img');
      if (sticker) preview = (sticker.getAttribute('alt') || '').trim() || '[表情]';
    }
    const convId = el.getAttribute('data-conv-id') || nickname;
    let unread = 0;
    for (const badge of el.querySelectorAll('[class*="unread" i], [class*="badge" i]')) {
      const n = parseInt((badge.innerText || '').trim(), 10);
      if (Number.isFinite(n) && n > 0) { unread = n; break; }
      if (badge.getBoundingClientRect().width > 0) { unread = 1; break; }
    }
    seen.add(nickname);
    result.push({
      conv_id: convId,
      nickname,
      last_message: preview,
      unread,
      category: 'friend',
      sender_nickname: '',
    });
  }
  return result;
}
"""

XHS_CHAT_MESSAGES_JS = """
() => {
  const xhsMessageText = (bubble) => {
    if (!bubble) return '';
    const text = (bubble.innerText || bubble.textContent || '').replace(/\\s+/g, ' ').trim();
    if (text) return text;
    const emoji = bubble.querySelector('.xhs-im-bubble__emoji, img[class*="bubble__emoji" i]');
    if (emoji) {
      const alt = (emoji.getAttribute('alt') || '').trim();
      if (alt === '表情' || alt === '[表情]') return '[表情]';
      return alt || '[表情]';
    }
    for (const img of bubble.querySelectorAll('img')) {
      const src = String(img.getAttribute('src') || '');
      if (!src || /avatar|sns-avatar/i.test(src)) continue;
      const alt = (img.getAttribute('alt') || img.getAttribute('title') || '').trim();
      if (alt) return alt;
      if (/fe-platform|picasso-static|emoji|sticker|redmoji/i.test(src)) return '[表情]';
    }
    if (/bubble--emoji|bubble--sticker|bubble--image/i.test(String(bubble.className || ''))) {
      return '[表情]';
    }
    return '';
  };
  const isSelfRow = (row) => {
    const bubble = row.querySelector('.chat-item__bubble');
    if (!bubble) return false;
    if (bubble.classList.contains('chat-item__bubble--me')) return true;
    return /bubble--me|--me\\b/.test(String(bubble.className || '')) ||
      row.classList.contains('chat-item__bubble-row--right');
  };
  const raw = [];
  const seen = new Set();
  for (const row of document.querySelectorAll('.chat-item__bubble-row')) {
    const bubble = row.querySelector('.chat-item__bubble');
    if (!bubble) continue;
    const text = xhsMessageText(bubble);
    if (!text || text.length > 800 || /^(发送|消息|搜索)$/.test(text)) continue;
    const self = isSelfRow(row);
    const r = row.getBoundingClientRect();
    const key = `${text}|${self ? 1 : 0}|${Math.round(r.top)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    raw.push({ text, is_self: self, y: r.top });
  }
  raw.sort((a, b) => a.y - b.y);
  const result = [];
  for (const item of raw) {
    const previous = result[result.length - 1];
    if (previous && previous.text === item.text && previous.is_self === item.is_self &&
        Math.abs((previous.y || 0) - item.y) < 8) continue;
    result.push(item);
  }
  return result.slice(-30).map(({text, is_self}) => ({text, is_self}));
}
"""

XHS_OUTGOING_COUNT_JS = """
() => {
  const exact = document.querySelectorAll('.chat-item__bubble--me');
  if (exact.length) return exact.length;
  const roots = new Set();
  for (const node of document.querySelectorAll('[class*="message" i], [class*="bubble" i], [data-testid*="message" i]')) {
    const r = node.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.left + r.width / 2 < innerWidth * 0.70) continue;
    let self = false;
    let el = node;
    for (let i = 0; i < 6 && el; i++, el = el.parentElement) {
      const cls = String(el.className || '').toLowerCase();
      const style = getComputedStyle(el);
      if (/is-self|self|mine|outgoing|right/.test(cls) || style.justifyContent === 'flex-end' || style.textAlign === 'right') {
        self = true; break;
      }
    }
    if (self) roots.add(node.closest('[class*="message" i]') || node);
  }
  return roots.size;
}
"""

XHS_OUTGOING_TEXT_COUNT_JS = """
(text) => {
  const target = String(text || '').replace(/\\s+/g, ' ').trim();
  if (!target) return 0;
  const norm = value => String(value || '').replace(/\\s+/g, ' ').trim();
  return [...document.querySelectorAll('.chat-item__bubble--me')]
    .filter(node => norm(node.innerText || node.textContent || '') === target).length;
}
"""

XHS_CHAT_PANEL_STATE_JS = r"""
() => {
  const body = (document.body?.innerText || '').replace(/\s+/g, ' ');
  const emptyHints = /暂无消息|还没有私信|点击消息开启会话|暂无会话/;
  const listShell = document.querySelector(
    '.xhs-im-conv-list, .xhs-im-conv-item, [class*="im-conv" i], [class*="conv-list" i], [class*="chat-list" i]'
  );
  return {
    empty: emptyHints.test(body),
    list_ready: !!listShell,
  };
}
"""


class XiaohongshuBrowserWorker(DouyinBrowserWorker):
    """与抖音工作线程保持相同接口，使用小红书网页 DOM。"""

    PROFILE_DIR_NAME = 'xiaohongshu_browser_profile'

    def __init__(self, storage_path: str, headless: bool = True):
        super().__init__(storage_path, headless=headless)
        self._xhs_unread_counts: Dict[str, int] = {}
        self._xhs_account_uid: str = ''

    @staticmethod
    def _normalize_xhs_message_text(value: Any) -> str:
        text = str(value or '').strip()
        if not text:
            return ''
        if text in {'表情', '[表情]'}:
            return '[表情]'
        return text

    @classmethod
    def _is_emoji_preview(cls, preview: str) -> bool:
        return cls._normalize_xhs_message_text(preview) == '[表情]'

    def _remember_xhs_account_uid(self) -> None:
        account_uid = str(getattr(self._account, 'uid', '') or '').strip()
        if account_uid:
            self._xhs_account_uid = account_uid

    def _message_is_self(self, message: Dict[str, Any]) -> bool:
        if not isinstance(message, dict):
            return False
        sender_id = str(message.get('sender_id') or '').strip()
        if sender_id and self._xhs_account_uid:
            return sender_id == self._xhs_account_uid
        for key in ('is_self', 'isSelf', 'self', 'from_self', 'is_sender', 'sender_is_self'):
            if key in message:
                return bool(message.get(key))
        return False

    def _message_is_from_partner(self, message: Dict[str, Any], chat_user_id: str) -> bool:
        if not isinstance(message, dict):
            return False
        partner_id = str(chat_user_id or '').strip()
        sender_id = str(message.get('sender_id') or '').strip()
        if partner_id and sender_id:
            return sender_id == partner_id
        return not self._message_is_self(message)

    def _extract_history_messages(self, body: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(body, dict):
            return []
        payload = body.get('data')
        if isinstance(payload, dict):
            for key in ('out_message_list', 'messages', 'message_list', 'msg_list', 'items'):
                rows = payload.get(key)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    def _parse_xhs_content_blob(self, raw: Any) -> str:
        if raw is None:
            return ''
        if isinstance(raw, dict):
            payload = raw
        else:
            text = str(raw or '').strip()
            if not text:
                return ''
            try:
                payload = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                return self._normalize_xhs_message_text(text)

        if not isinstance(payload, dict):
            return self._normalize_xhs_message_text(str(payload))

        nested = payload.get('content')
        if isinstance(nested, str):
            try:
                nested = json.loads(nested)
            except (TypeError, ValueError, json.JSONDecodeError):
                nested = None

        candidates: List[Any] = []
        if isinstance(nested, dict):
            candidates.extend([
                nested.get('emojiKey'),
                nested.get('emoji_key'),
                nested.get('content'),
                nested.get('text'),
                nested.get('front_chain'),
            ])
        candidates.extend([
            payload.get('front_chain'),
            payload.get('content') if isinstance(payload.get('content'), str) else None,
            payload.get('text'),
        ])

        for value in candidates:
            text = self._normalize_xhs_message_text(value)
            if text:
                return text

        try:
            if int(payload.get('content_type') or 0) == 13:
                return '[表情]'
        except (TypeError, ValueError):
            pass
        return ''

    def _history_row_text(self, row: Dict[str, Any]) -> str:
        return self._parse_xhs_content_blob(row.get('content'))

    def _fetch_xhs_message_history(
        self, chat_user_id: str, max_store_id: int = 0, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        chat_user_id = str(chat_user_id or '').strip()
        if not chat_user_id:
            return []
        cap = int(max_store_id or 0)
        url = XHS_HISTORY_API.format(
            chat_user_id=chat_user_id,
            last_id=0,
            limit=max(1, limit),
        )
        rows = self._extract_history_messages(self._fetch_xhs_json(url))
        if cap and rows:
            filtered = [
                row for row in rows
                if int(row.get('store_id') or 0) <= cap
            ]
            if filtered:
                return filtered
            url = XHS_HISTORY_API.format(
                chat_user_id=chat_user_id,
                last_id=cap,
                limit=max(1, limit),
            )
            anchored = self._extract_history_messages(self._fetch_xhs_json(url))
            if anchored:
                return anchored
        return rows or []

    def _read_latest_incoming_from_history(
        self, chat_user_id: str, max_store_id: int,
    ) -> Optional[Dict[str, Any]]:
        self._remember_xhs_account_uid()
        rows = self._fetch_xhs_message_history(chat_user_id, max_store_id, limit=20)
        if not rows:
            return None

        def _sort_key(row: Dict[str, Any]) -> tuple[int, int]:
            try:
                return (0, int(row.get('store_id') or 0))
            except (TypeError, ValueError):
                pass
            try:
                return (1, int(row.get('created_at') or row.get('timestamp') or row.get('time') or 0))
            except (TypeError, ValueError):
                return (1, 0)

        rows = sorted(rows, key=_sort_key)
        if max_store_id:
            rows = [row for row in rows if int(row.get('store_id') or 0) <= int(max_store_id)]
        for row in reversed(rows):
            text = self._history_row_text(row)
            if not text:
                continue
            if not self._message_is_from_partner(row, chat_user_id):
                continue
            return {'text': text, 'is_self': False}
        return None

    def _fetch_xhs_json(self, url: str) -> Optional[Dict[str, Any]]:
        if not self._page or self._abort:
            return None
        try:
            body = self._page.evaluate(
                """async (url) => {
                  const res = await fetch(url, {
                    credentials: 'include',
                    headers: { accept: 'application/json, text/plain, */*' }
                  });
                  if (!res.ok) return null;
                  return res.json();
                }""",
                url,
            )
            return body if isinstance(body, dict) else None
        except Exception as exc:
            logger.debug('XHS API 请求失败: %s', exc)
            return None

    def _refresh_xhs_unread_counts(self) -> None:
        body = self._fetch_xhs_json(XHS_UNREAD_API)
        if not isinstance(body, dict):
            return
        payload = body.get('data') or {}
        counts = payload.get('user_chat_unread_counts') or {}
        if isinstance(counts, dict):
            self._xhs_unread_counts = {
                str(uid): int(count or 0) for uid, count in counts.items()
            }

    def _ingest_xhs_chat_rows(self, chats: List[Dict[str, Any]]) -> None:
        for item in chats:
            if not isinstance(item, dict):
                continue
            info = item.get('info') or {}
            nickname = str(info.get('nickname') or info.get('user_name') or '').strip()
            chat_user_id = str(item.get('chat_user_id') or '').strip()
            if not nickname:
                continue
            last_msg = str(item.get('last_msg_content') or '').strip()
            cid = chat_user_id or f'friend:{nickname}'
            self._api_conversations[cid] = {
                'conv_id': cid,
                'nickname': nickname,
                'last_message': last_msg,
                'unread': int(self._xhs_unread_counts.get(chat_user_id, 0)),
                'category': 'friend',
                'sender_nickname': '',
                'last_msg_time': int(item.get('last_msg_time') or 0),
                'max_store_id': int(item.get('max_store_id') or 0),
                'update_time': int(item.get('update_time') or 0),
            }

    def _fetch_conversations_from_api(self) -> List[Dict[str, Any]]:
        self._remember_xhs_account_uid()
        self._refresh_xhs_unread_counts()
        for page_num in range(5):
            body = self._fetch_xhs_json(XHS_CHATS_API.format(page=page_num))
            if not isinstance(body, dict) or body.get('success') is False:
                break
            payload = body.get('data') or {}
            chats = payload.get('chats') or []
            if not isinstance(chats, list) or not chats:
                break
            self._ingest_xhs_chat_rows(chats)
            if payload.get('next_ts', -1) == -1 or len(chats) < 100:
                break
        merged: Dict[str, Dict[str, Any]] = {}
        for item in self._api_conversations.values():
            nick = str(item.get('nickname') or '').strip()
            if nick:
                merged[nick] = dict(item)
        return list(merged.values())

    def _scroll_xhs_chat_to_bottom(self) -> None:
        if not self._page:
            return
        try:
            self._page.evaluate(
                r"""() => {
                  const selectors = [
                    '.chat-scroll', '[class*="chat-scroll" i]', '[class*="message-list" i]',
                    '[class*="chat-main" i]', '[class*="chat-window" i] [class*="scroll" i]'
                  ];
                  let scroller = null;
                  for (const sel of selectors) {
                    const node = document.querySelector(sel);
                    if (node && node.scrollHeight > node.clientHeight + 20) {
                      scroller = node; break;
                    }
                  }
                  const target = scroller || document.scrollingElement || document.documentElement;
                  target.scrollTop = target.scrollHeight;
                }"""
            )
            self._sleep(0.35)
        except Exception:
            pass

    def _has_session_cookie(self) -> bool:
        if not self._context:
            return False
        names = {str(c.get('name') or '') for c in self._context.cookies()}
        return bool(XHS_SESSION_COOKIES & names)

    def _read_authenticated_account(self) -> Dict[str, str]:
        """从登录用户接口读取本人信息；不从信息流作者链接猜测账号。"""
        if not self._page:
            return {}
        try:
            info = self._page.evaluate(
                r"""async () => {
                  try {
                    const response = await fetch('/api/sns/web/v1/user/selfinfo', {
                      credentials: 'include',
                      headers: {'accept': 'application/json, text/plain, */*'}
                    });
                    if (!response.ok) return null;
                    const body = await response.json();
                    if (body?.success === false || (body?.code != null && Number(body.code) !== 0)) {
                      return null;
                    }
                    const data = body?.data || {};
                    const uid = String(data.user_id || data.userId || data.userid || '').trim();
                    const nickname = String(data.nickname || data.nick_name || '').trim();
                    let avatar = data.imageb || data.images || data.avatar || data.avatar_url || '';
                    if (Array.isArray(avatar)) avatar = avatar[0] || '';
                    if (avatar && typeof avatar === 'object') {
                      avatar = avatar.url || avatar.url_default || avatar.url_pre || '';
                    }
                    if (!uid || !nickname) return null;
                    return {uid, nickname, avatar: String(avatar || ''), sec_uid: ''};
                  } catch (_) {
                    return null;
                  }
                }"""
            ) or {}

            # selfinfo 在部分小红书版本中会返回服务端 500。此时只认左侧导航
            # 中结构固定、文字为“我”的本人入口；信息流作者使用 author 类，
            # 不会命中这个选择器，因此不会重现把推荐作者当成本人的问题。
            if not info:
                own_link = self._page.evaluate(
                    r"""() => {
                      const links = [...document.querySelectorAll(
                        '.user.side-bar-component a.link-wrapper[href*="/user/profile/"]'
                      )];
                      for (const link of links) {
                        const text = (link.innerText || '').trim();
                        const href = link.href || link.getAttribute('href') || '';
                        const uid = (href.match(/\/user\/profile\/([^/?#]+)/) || [])[1] || '';
                        const rect = link.getBoundingClientRect();
                        if (text !== '我' || !uid || rect.width <= 0 || rect.height <= 0) continue;
                        return {
                          uid,
                          href,
                          avatar: link.querySelector('img')?.src || ''
                        };
                      }
                      return null;
                    }"""
                ) or {}
                own_uid = str(own_link.get('uid') or '').strip()
                own_href = str(own_link.get('href') or '').strip()
                if self._is_valid_uid(own_uid) and own_href.startswith('https://www.xiaohongshu.com/'):
                    if f'/user/profile/{own_uid}' not in (self._page.url or ''):
                        self._page.goto(own_href, wait_until='domcontentloaded')
                        self._sleep(1.5)
                    profile = self._page.evaluate(
                        r"""() => ({
                          nickname: (document.querySelector('.user-name, .user-nickname')?.innerText || '').trim(),
                          avatar: document.querySelector('img.user-image')?.src || ''
                        })"""
                    ) or {}
                    info = {
                        'uid': own_uid,
                        'nickname': str(profile.get('nickname') or '').strip(),
                        'avatar': str(profile.get('avatar') or own_link.get('avatar') or ''),
                        'sec_uid': '',
                    }
            uid = str(info.get('uid') or '').strip()
            nickname = str(info.get('nickname') or '').strip()
            if not self._is_valid_uid(uid) or not self._is_valid_nickname(nickname):
                return {}
            return {
                'uid': uid,
                'nickname': nickname,
                'avatar': str(info.get('avatar') or ''),
                'sec_uid': '',
            }
        except Exception as exc:
            logger.debug('验证小红书登录用户失败: %s', exc)
            return {}

    @staticmethod
    def _is_valid_uid(uid: str) -> bool:
        return len((uid or '').strip()) >= 4

    @staticmethod
    def _is_valid_nickname(nickname: str) -> bool:
        nickname = (nickname or '').strip()
        return bool(nickname and len(nickname) <= 40 and nickname not in {'登录', '我', '消息', '小红书'})

    def _op_check_session(self) -> bool:
        self.headless = True
        self._ensure_browser()
        try:
            self._page.goto(XHS_HOME, wait_until='domcontentloaded')
            self._sleep(1.5)
            info = self._read_authenticated_account()
            if not info:
                return False
            self._account = DouyinAccountInfo(**info)
            self._remember_xhs_account_uid()
            return True
        except Exception:
            return False

    def _op_open_login(self) -> Dict[str, Any]:
        self.headless = False
        if self._context and self._current_headless is True:
            self._cleanup_browser()
            self._current_headless = None
        self._ensure_browser()
        self._page.goto(XHS_HOME, wait_until='domcontentloaded')
        time.sleep(1.5)
        return {'ok': True, 'message': '请在 Chromium 窗口中完成小红书登录'}

    def _op_wait_login(self, login_timeout: int) -> Dict[str, str]:
        self._ensure_browser()
        deadline = time.time() + login_timeout
        while time.time() < deadline:
            info = self._read_authenticated_account()
            if info:
                self._account = DouyinAccountInfo(**info)
                self._op_save_session()
                return self._account.to_dict()
            time.sleep(2)
        raise TimeoutError('登录超时，请重试')

    def _extract_account_from_page(self) -> None:
        if not self._page:
            return
        try:
            self._page.goto(XHS_HOME, wait_until='domcontentloaded')
            self._sleep(1.5)
            info = self._read_authenticated_account()
            self._account = DouyinAccountInfo(**info) if info else DouyinAccountInfo()
        except Exception as exc:
            logger.debug('读取小红书账号信息失败: %s', exc)

    def _op_get_account(self) -> DouyinAccountInfo:
        self._extract_account_from_page()
        return self._account

    def _attach_network_listeners(self) -> None:
        if not self._page:
            return

        def on_response(response):
            try:
                url = response.url or ''
                if response.status != 200:
                    return
                profile_keys = (
                    'user/profile', 'passport/web', 'query/user',
                    'im/user', 'account/info', 'user/info', 'selfinfo',
                )
                im_keys = (
                    '/im/', '/message', 'conversation', 'chat',
                    'aweme/v1/web/im', 'im/conversation', 'im/message',
                    'sns/web/v1/im', 'sns/web/v2/im', 'edith.xiaohongshu.com',
                )
                if not any(k in url for k in profile_keys + im_keys):
                    return
                ct = (response.headers.get('content-type') or '').lower()
                if 'json' not in ct:
                    return
                data = response.json()
                self._ingest_api_payload(data)
            except Exception:
                pass

        self._page.on('response', on_response)

    def _ingest_api_payload(self, data: Any) -> None:
        super()._ingest_api_payload(data)
        if not isinstance(data, dict):
            return
        payload = data.get('data', data)
        if not isinstance(payload, dict):
            return

        unread_counts = payload.get('user_chat_unread_counts')
        if isinstance(unread_counts, dict):
            self._xhs_unread_counts = {
                str(uid): int(count or 0) for uid, count in unread_counts.items()
            }

        chats = payload.get('chats')
        if isinstance(chats, list) and chats:
            self._ingest_xhs_chat_rows(chats)
            return

        conv_list = (
            payload.get('chat_list')
            or payload.get('session_list')
            or payload.get('chat_sessions')
            or payload.get('user_chat_list')
        )
        if not isinstance(conv_list, list):
            return
        for item in conv_list:
            if not isinstance(item, dict):
                continue
            user = item.get('user_info') or item.get('user') or item.get('target_user') or item
            nickname = str(
                user.get('nickname') or user.get('nick_name') or item.get('nickname') or ''
            ).strip()
            if not nickname:
                continue
            chat_user_id = str(
                item.get('chat_user_id') or item.get('conversation_id') or item.get('chat_id') or ''
            ).strip()
            cid = chat_user_id or f'friend:{nickname}'
            self._api_conversations[cid] = {
                'conv_id': cid,
                'nickname': nickname,
                'last_message': str(
                    item.get('last_message')
                    or item.get('last_msg_content')
                    or item.get('content')
                    or item.get('preview')
                    or ''
                ),
                'unread': int(
                    self._xhs_unread_counts.get(chat_user_id, 0)
                    or item.get('unread_count')
                    or item.get('unread')
                    or 0
                ),
                'category': 'friend',
                'sender_nickname': '',
            }

    def _wait_for_xhs_conversation_list(
        self, timeout: float = 6.0,
    ) -> tuple[List[Dict[str, Any]], str]:
        """等待私信列表挂载。返回 (rows, state)，state 为 loaded / empty / timeout。"""
        if not self._page or self._abort:
            return [], 'timeout'
        deadline = time.time() + timeout
        last_items: List[Dict[str, Any]] = []
        while time.time() < deadline:
            if self._abort:
                return last_items, 'timeout'
            try:
                panel_state = self._page.evaluate(XHS_CHAT_PANEL_STATE_JS) or {}
            except Exception:
                panel_state = {}
            if panel_state.get('empty'):
                return [], 'empty'
            try:
                last_items = self._page.evaluate(EXTRACT_XHS_CONVERSATIONS_JS) or []
            except Exception:
                last_items = []
            if last_items:
                return last_items, 'loaded'
            if panel_state.get('list_ready'):
                return [], 'empty'
            if self._sleep(0.35):
                return last_items, 'timeout'
        return last_items, 'timeout'

    def _merge_xhs_conversations(
        self, rows: List[Dict[str, Any]], merged: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        bucket = merged if merged is not None else {}
        for item in self._api_conversations.values():
            nick = str(item.get('nickname') or '').strip()
            if not nick:
                continue
            bucket[nick] = {
                'conv_id': item.get('conv_id') or f'friend:{nick}',
                'nickname': nick,
                'last_message': item.get('last_message') or '',
                'unread': int(item.get('unread') or 0),
                'category': item.get('category') or 'friend',
                'sender_nickname': item.get('sender_nickname') or '',
                'last_msg_time': int(item.get('last_msg_time') or 0),
                'max_store_id': int(item.get('max_store_id') or 0),
                'update_time': int(item.get('update_time') or 0),
            }
        for item in rows:
            nick = str(item.get('nickname') or '').strip()
            if not nick:
                continue
            bucket[nick] = {
                'conv_id': item.get('conv_id') or f'friend:{nick}',
                'nickname': nick,
                'last_message': item.get('last_message') or '',
                'unread': int(item.get('unread') or 0),
                'category': item.get('category') or 'friend',
                'sender_nickname': item.get('sender_nickname') or '',
                'last_msg_time': int(item.get('last_msg_time') or 0),
                'max_store_id': int(item.get('max_store_id') or 0),
                'update_time': int(item.get('update_time') or 0),
            }
        return list(bucket.values())

    def _op_navigate_messages(self, fast: bool = False) -> Dict[str, Any]:
        if self._abort:
            return {'ok': False, 'aborted': True}
        self._ensure_browser()
        try:
            if '/chat' not in (self._page.url or ''):
                self._page.goto(XHS_CHAT, wait_until='domcontentloaded')
            self._sleep(0.8 if fast else 2.2)
            if '/chat' not in (self._page.url or ''):
                current_url = self._page.url or ''
                error = ''
                if '/website-login/error' in current_url:
                    query = parse_qs(urlparse(current_url).query)
                    code = (query.get('error_code') or [''])[0]
                    message = (query.get('error_msg') or [''])[0] or '小红书拒绝访问私信页'
                    error = f'小红书私信页访问被拒绝（错误码 {code or "未知"}）：{message}'
                return {'ok': False, 'url': current_url, 'error': error}
            _, panel_state = self._wait_for_xhs_conversation_list(timeout=4.0 if fast else 8.0)
            self._messages_panel_ready = panel_state in ('loaded', 'empty')
            self._conversation_open = False
            return {'ok': True, 'url': self._page.url}
        except Exception as exc:
            logger.warning('进入小红书消息页失败: %s', exc)
            return {'ok': False, 'url': self._page.url or ''}

    def _op_list_conversations(self, quick: bool = False, skip_stranger: bool = False) -> List[Dict[str, Any]]:
        if self._abort:
            return []
        if not self._page or '/chat' not in (self._page.url or ''):
            result = self._op_navigate_messages(fast=quick)
            if not result.get('ok'):
                if result.get('error'):
                    raise RuntimeError(f'XHS_CHAT_BLOCKED:{result["error"]}')
                return []
            self._conversation_open = False

        api_rows = self._fetch_conversations_from_api()
        if api_rows:
            self._messages_panel_ready = True
            return api_rows

        panel_cache: Optional[List[Dict[str, Any]]] = None
        if quick and self._messages_panel_ready and self._page:
            try:
                panel_cache = self._page.evaluate(EXTRACT_XHS_CONVERSATIONS_JS) or []
            except Exception:
                panel_cache = []

        if panel_cache:
            results = self._merge_xhs_conversations(panel_cache)
            self._messages_panel_ready = True
            return results

        rows, panel_state = self._wait_for_xhs_conversation_list(timeout=2.5 if quick else 8.0)
        results = self._merge_xhs_conversations(rows)
        if results:
            self._messages_panel_ready = True
            return results
        if panel_state == 'empty':
            self._messages_panel_ready = True
            return []

        if quick:
            return []

        self._messages_panel_ready = False
        self._conversation_open = False
        if not self._op_navigate_messages(fast=False).get('ok'):
            return []
        api_rows = self._fetch_conversations_from_api()
        if api_rows:
            self._messages_panel_ready = True
            return api_rows
        rows, panel_state = self._wait_for_xhs_conversation_list(timeout=8.0)
        results = self._merge_xhs_conversations(rows)
        self._messages_panel_ready = bool(results) or panel_state == 'empty'
        return results

    def _click_xhs_conversation(self, nickname: str) -> bool:
        try:
            items = self._page.locator('.xhs-im-conv-item')
            for index in range(items.count()):
                item = items.nth(index)
                name_node = item.locator('.xhs-im-conv-item__name')
                if name_node.count() == 0:
                    continue
                if (name_node.inner_text(timeout=2000) or '').strip() != nickname:
                    continue
                item.click(timeout=5000)
                return True
        except Exception:
            pass
        try:
            loc = self._page.get_by_text(nickname, exact=True)
            for index in range(loc.count()):
                item = loc.nth(index)
                if not item.is_visible():
                    continue
                box = item.bounding_box()
                if not box or box['x'] < 140 or box['x'] > self._page.viewport_size['width'] * 0.48:
                    continue
                item.click(timeout=5000)
                return True
        except Exception:
            pass
        return False

    def _op_open_conversation(
        self, nickname: str, category: str = 'friend', from_panel: bool = False,
    ) -> bool:
        if not nickname or self._abort:
            return False
        if '/chat' not in (self._page.url or ''):
            if not self._op_navigate_messages(fast=from_panel).get('ok'):
                return False
        if not self._click_xhs_conversation(nickname):
            return False
        if self._sleep(0.25):
            return False
        if not self._wait_for_chat_editor(timeout=5.0):
            return False
        self._conversation_open = True
        return True

    def _ensure_message_page_for_send(self) -> bool:
        if self._wait_for_chat_editor(timeout=0.15):
            return True
        if '/chat' in (self._page.url or ''):
            return True
        return bool(self._op_navigate_messages(fast=False).get('ok'))

    def _return_to_message_list(self, fast: bool = True) -> None:
        # 小红书是三栏布局，打开会话后列表仍在，无需关闭聊天。
        self._messages_panel_ready = '/chat' in (self._page.url or '')
        self._conversation_open = False

    def _op_read_latest_message(
        self, conv_id: str, nickname: str, category: str = 'friend', sender_nickname: str = '',
    ) -> Optional[Dict[str, Any]]:
        chat_user_id = str(conv_id or '').strip()
        cached = self._api_conversations.get(chat_user_id) or {}
        max_store_id = int(cached.get('max_store_id') or 0)
        if chat_user_id:
            api_latest = self._read_latest_incoming_from_history(chat_user_id, max_store_id)
            if api_latest:
                text = self._normalize_xhs_message_text(api_latest.get('text'))
                if text:
                    return {
                        'conv_id': chat_user_id,
                        'nickname': nickname,
                        'text': text,
                        'is_self': False,
                        'timestamp': int(time.time()),
                    }

        if not self._op_open_conversation(nickname, category=category, from_panel=True):
            return None
        try:
            self._scroll_xhs_chat_to_bottom()
            messages = self._page.evaluate(XHS_CHAT_MESSAGES_JS) or []
            if not messages:
                messages = self._page.evaluate(EXTRACT_CHAT_MESSAGES_JS, 30) or []
            incoming = [
                msg for msg in messages
                if not msg.get('is_self') and self._normalize_xhs_message_text(msg.get('text'))
            ]
            if not incoming:
                return None
            latest = incoming[-1]
            text = self._normalize_xhs_message_text(latest.get('text'))
            if not text:
                return None
            return {
                'conv_id': conv_id or f'friend:{nickname}',
                'nickname': nickname,
                'text': text,
                'is_self': False,
                'timestamp': int(time.time()),
            }
        except Exception:
            return None

    def _outgoing_message_count(self) -> int:
        try:
            return int(self._page.evaluate(XHS_OUTGOING_COUNT_JS) or 0)
        except Exception:
            return 0

    def _outgoing_text_count(self, text: str) -> int:
        try:
            return int(self._page.evaluate(XHS_OUTGOING_TEXT_COUNT_JS, text) or 0)
        except Exception:
            return 0

    def _fill_and_send_message(self, text: str, nickname: str = '') -> bool:
        """小红书单次提交：绝不因气泡渲染延迟再次发送同一内容。"""
        if not self._page or not self._wait_for_chat_editor():
            return False

        before_text_count = self._outgoing_text_count(text)
        watch_token = self._start_send_watch(text)
        try:
            focused = bool(self._page.evaluate(FOCUS_CHAT_EDITOR_JS))
            if not focused:
                return False
            self._page.keyboard.press('Control+a')
            self._page.keyboard.press('Backspace')
            self._page.keyboard.insert_text(text)
            if self._sleep(0.05):
                return False
            self._page.keyboard.press('Enter')
        except Exception as exc:
            logger.debug('小红书单次提交失败: %s', exc)
            return False

        # 小红书发送后的气泡可能延迟数秒出现。等待期间只做观察，不能再按
        # 发送按钮或走 JS 备用提交，否则一次入站消息会产生多条相同回复。
        editor_was_cleared = False
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self._abort:
                return False
            if self._outgoing_text_count(text) > before_text_count:
                return True
            if self._send_watch_succeeded(watch_token):
                return True
            state = self._editor_state()
            if state.get('found') and state.get('empty'):
                editor_was_cleared = True
            if self._sleep(0.2):
                return False

        # 输入框已清空表示页面已接收这次提交。即使气泡校验因网络延迟仍未
        # 完成，也按“已提交”处理以保证 at-most-once，避免下一轮重复发送。
        if editor_was_cleared:
            logger.warning('小红书回复已提交但气泡确认超时，已抑制重复发送: %s', nickname)
            return True
        return False

    def _op_peek_latest_incoming(self, chat_user_id: str, max_store_id: int) -> Optional[Dict[str, Any]]:
        self._remember_xhs_account_uid()
        if '/chat' not in (self._page.url or ''):
            self._op_navigate_messages(fast=True)
        return self._read_latest_incoming_from_history(chat_user_id, max_store_id)

    def _op_fetch_history_debug(self, chat_user_id: str, last_id: int) -> Dict[str, Any]:
        if '/chat' not in (self._page.url or ''):
            self._op_navigate_messages(fast=True)
        url = XHS_HISTORY_API.format(
            chat_user_id=str(chat_user_id or ''),
            last_id=int(last_id or 0),
            limit=10,
        )
        body = self._fetch_xhs_json(url)
        return {
            'url': url,
            'body': body,
            'rows': self._extract_history_messages(body),
        }

    def peek_latest_incoming(self, chat_user_id: str, max_store_id: int) -> Optional[Dict[str, Any]]:
        try:
            return self._call(
                'peek_latest_incoming', timeout=25,
                chat_user_id=str(chat_user_id or ''),
                max_store_id=int(max_store_id or 0),
            )
        except Exception:
            return None

    def _dispatch(self, op: str, **kwargs):
        if op == 'peek_latest_incoming':
            return self._op_peek_latest_incoming(
                str(kwargs.get('chat_user_id') or ''),
                int(kwargs.get('max_store_id') or 0),
            )
        if op == 'fetch_history_debug':
            return self._op_fetch_history_debug(
                str(kwargs.get('chat_user_id') or ''),
                int(kwargs.get('last_id') or 0),
            )
        return super()._dispatch(op, **kwargs)
