"""微博网页版私信 Playwright 自动化。"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from douyin_playwright import DouyinAccountInfo
from xiaohongshu_playwright import XiaohongshuBrowserWorker

WEIBO_HOME = 'https://weibo.com/'
WEIBO_CHAT = 'https://api.weibo.com/chat/#/chat'
WEIBO_PRIMARY_INFO = 'https://api.weibo.com/webim/query_primary_info.json'
WEIBO_CONTACTS = 'https://api.weibo.com/webim/2/direct_messages/contacts.json?special_source=3'
WEIBO_PUBLIC_CONTACTS = 'https://api.weibo.com/webim/2/direct_messages/public/contacts.json'
WEIBO_CONVERSATION = 'https://api.weibo.com/webim/2/direct_messages/conversation.json'
WEIBO_SEND = 'https://api.weibo.com/webim/2/direct_messages/new.json'
WEIBO_SESSION_COOKIES = {'SUB', 'SUBP'}
WEIBO_INVALID_SESSION_HINTS = (
    '浏览器缓存发生变更',
    '请重新登录',
    '登录微博',
    '扫码登录',
    '帐号登录',
    '账号登录',
)
WEIBO_MONITOR_ENGINE = 'Playwright-contacts-v3'


class WeiboBrowserWorker(XiaohongshuBrowserWorker):
    PROFILE_DIR_NAME = 'weibo_browser_profile'

    def __init__(self, storage_path: str, headless: bool = True):
        super().__init__(storage_path, headless=headless)
        self._last_list_diagnosis = ''

    def get_last_list_diagnosis(self) -> str:
        return self._last_list_diagnosis or ''

    def _has_session_cookie(self) -> bool:
        if not self._context:
            return False
        names = {str(c.get('name') or '') for c in self._context.cookies()}
        return bool(WEIBO_SESSION_COOKIES & names)

    @staticmethod
    def _is_valid_nickname(nickname: str) -> bool:
        """Reject UI copy that can be mistaken for the current account name."""
        nickname = (nickname or '').strip()
        if not nickname or len(nickname) > 30 or '\n' in nickname:
            return False
        bad_phrases = (
            *WEIBO_INVALID_SESSION_HINTS,
            '我知道了', '微博聊天网页版', '已登录用户', '消息',
        )
        return not any(phrase in nickname for phrase in bad_phrases)

    def _page_has_invalid_session_prompt(self) -> bool:
        """Only treat visible login UI as expired — full-page text is too noisy."""
        if not self._page:
            return True
        try:
            url = self._page.url or ''
            if 'passport.weibo' in url:
                return True
            for hint in WEIBO_INVALID_SESSION_HINTS:
                locator = self._page.get_by_text(hint, exact=False)
                for index in range(min(locator.count(), 6)):
                    item = locator.nth(index)
                    try:
                        if item.is_visible():
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False

    def _fetch_authenticated_account(self) -> Dict[str, str]:
        """Ask Weibo's chat bootstrap API for the authenticated user.

        The QR page also creates SUB/SUBP Cookies and contains links to unrelated
        user profiles, so neither is acceptable evidence of a completed login.
        This endpoint returns error_code 21301 when there is no authenticated
        account and a `profile` object only for the current signed-in user.
        """
        if not self._context:
            return {}
        try:
            response = self._context.request.get(
                f'{WEIBO_PRIMARY_INFO}?source=209678993&t={int(time.time() * 1000)}',
                headers={'Referer': 'https://api.weibo.com/chat/'},
                timeout=10000,
            )
            if not response.ok:
                return {}
            data = response.json()
            if not isinstance(data, dict) or data.get('error') or data.get('error_code'):
                return {}
            profile = data.get('profile') or {}
            uid = str(profile.get('id') or '').strip()
            nickname = str(profile.get('screen_name') or '').strip()
            avatar = str(profile.get('profileImageUrl') or '').strip()
            if not uid.isdigit() or not self._is_valid_nickname(nickname):
                return {}
            return {
                'uid': uid,
                'nickname': nickname,
                'avatar': avatar,
                'sec_uid': '',
            }
        except Exception:
            return {}

    def _apply_authenticated_account(self, info: Dict[str, str]) -> None:
        self._account = DouyinAccountInfo(
            uid=str(info.get('uid') or ''),
            nickname=str(info.get('nickname') or ''),
            avatar=str(info.get('avatar') or ''),
            sec_uid='',
        )

    def _request_weibo_json(self, url: str) -> Dict[str, Any]:
        if not self._context:
            return {}
        separator = '&' if '?' in url else '?'
        try:
            response = self._context.request.get(
                f'{url}{separator}source=209678993&t={int(time.time() * 1000)}',
                headers={'Referer': 'https://api.weibo.com/chat/'},
                timeout=15000,
            )
            if not response.ok:
                return {}
            data = response.json()
            if not isinstance(data, dict) or data.get('error') or data.get('error_code'):
                return {}
            return data
        except Exception:
            return {}

    def _request_weibo_post(self, url: str, form: Dict[str, Any]) -> Dict[str, Any]:
        if not self._context:
            return {}
        separator = '&' if '?' in url else '?'
        try:
            response = self._context.request.post(
                f'{url}{separator}source=209678993&t={int(time.time() * 1000)}',
                headers={'Referer': 'https://api.weibo.com/chat/'},
                form=form,
                timeout=15000,
            )
            if not response.ok:
                return {}
            data = response.json()
            if not isinstance(data, dict) or data.get('error') or data.get('error_code'):
                return {}
            return data
        except Exception:
            return {}

    @staticmethod
    def _message_preview(message: Dict[str, Any]) -> str:
        text = str(message.get('text') or '').strip()
        if text:
            return text
        media_type = int(message.get('media_type') or message.get('mediaType') or 0)
        return {
            1: '[图片]', 2: '[语音]', 3: '[视频]', 7: '[文件]',
            13: '[链接]',
        }.get(media_type, '[非文字消息]')

    @classmethod
    def _parse_contacts_payload(
        cls, payload: Dict[str, Any], category: str = 'friend',
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for contact in payload.get('contacts') or []:
            if not isinstance(contact, dict):
                continue
            user = contact.get('user') or {}
            message = contact.get('message') or {}
            uid = str(
                user.get('id') or user.get('idstr') or user.get('idStr') or ''
            ).strip()
            nickname = str(user.get('remark') or user.get('name') or '').strip()
            preview = cls._message_preview(message)
            if not uid or not nickname or not preview:
                continue
            try:
                unread = max(0, int(contact.get('unread_count') or 0))
            except (TypeError, ValueError):
                unread = 0
            rows.append({
                'conv_id': f'{category}:{uid}',
                'nickname': nickname,
                'last_message': preview,
                'unread': unread,
                'category': category,
                'sender_nickname': str(message.get('sender_screen_name') or ''),
                'sender_id': str(message.get('sender_id') or ''),
                'message_id': str(
                    message.get('id') or message.get('mid') or message.get('idstr') or ''
                ),
            })
        return rows

    def _clear_invalid_login_state(self) -> None:
        """Remove the stale auth/cache tuple that makes Weibo loop its modal."""
        if not self._context or not self._page:
            return
        try:
            self._context.clear_cookies()
        except Exception:
            pass
        try:
            cdp = self._context.new_cdp_session(self._page)
            cdp.send('Network.clearBrowserCache')
            cdp.send('Network.clearBrowserCookies')
            for origin in ('https://weibo.com', 'https://api.weibo.com', 'https://passport.weibo.com'):
                cdp.send('Storage.clearDataForOrigin', {
                    'origin': origin,
                    'storageTypes': 'all',
                })
            cdp.detach()
        except Exception:
            pass
        # Do not let the generic browser bootstrap inject the rejected Cookies
        # again when it switches from the visible login window to headless mode.
        try:
            if os.path.isfile(self.storage_path):
                os.remove(self.storage_path)
        except OSError:
            pass
        self._account = DouyinAccountInfo()

    def _collect_conversations(self) -> List[Dict[str, Any]]:
        direct = self._parse_contacts_payload(
            self._request_weibo_json(WEIBO_CONTACTS), category='friend',
        )
        public = self._parse_contacts_payload(
            self._request_weibo_json(WEIBO_PUBLIC_CONTACTS), category='public',
        )
        result: List[Dict[str, Any]] = []
        seen = set()
        for row in direct + public:
            uid = row['conv_id'].split(':', 1)[-1]
            if uid in seen:
                continue
            seen.add(uid)
            result.append(row)
        return result

    def _explain_empty_list(self) -> str:
        if self._abort:
            return '浏览器操作被中断（可能与会话验证冲突）'
        if not self._has_session_cookie():
            return '浏览器缺少 SUB/SUBP 登录 Cookie，请重新登录'
        if not self._page:
            return '浏览器页面未初始化'
        url = self._page.url or ''
        if 'api.weibo.com/chat' not in url:
            return f'未进入微博聊天页（当前: {url or "空白页"}）'
        if self._page_has_invalid_session_prompt():
            return '页面显示登录失效提示，请重新登录'
        direct = self._request_weibo_json(WEIBO_CONTACTS)
        if direct.get('error') or direct.get('error_code'):
            code = direct.get('error_code') or direct.get('error')
            return f'私信 contacts API 报错: {code}'
        public = self._request_weibo_json(WEIBO_PUBLIC_CONTACTS)
        if public.get('error') or public.get('error_code'):
            code = public.get('error_code') or public.get('error')
            return f'公共 contacts API 报错: {code}'
        raw_count = len(direct.get('contacts') or []) + len(public.get('contacts') or [])
        if raw_count == 0:
            return 'API 返回空联系人（会话尚未加载或账号无私信）'
        parsed = self._collect_conversations()
        if not parsed:
            return f'API 返回 {raw_count} 条原始联系人但解析失败（页面结构可能已变化）'
        return '未知原因'

    def _ensure_on_chat_page(self, fast: bool = False) -> bool:
        if self._abort:
            return False
        self._ensure_browser()
        if 'api.weibo.com/chat' not in (self._page.url or ''):
            return self._op_navigate_messages(fast=fast).get('ok')
        if not fast:
            self._sleep(0.35)
        return True

    def _wait_for_conversations(self, timeout: float = 10.0, quick: bool = False) -> List[Dict[str, Any]]:
        deadline = time.time() + timeout
        result: List[Dict[str, Any]] = []
        while time.time() < deadline:
            if self._abort:
                return []
            result = self._collect_conversations()
            if result:
                return result
            self._sleep(0.45 if quick else 0.7)
        return result

    def _op_check_session(self) -> bool:
        self.headless = True
        self._ensure_browser()
        if not self._has_session_cookie():
            return False
        try:
            self._page.goto(WEIBO_CHAT, wait_until='domcontentloaded')
            self._sleep(2.0)
            if self._page_has_invalid_session_prompt():
                return False
            info = self._fetch_authenticated_account()
            if not info:
                return False
            self._apply_authenticated_account(info)
        except Exception:
            return False
        return True

    def _op_open_login(self) -> Dict[str, Any]:
        self.headless = False
        if self._context and self._current_headless is True:
            self._cleanup_browser()
            self._current_headless = None
        self._ensure_browser()
        self._page.goto(WEIBO_HOME, wait_until='domcontentloaded')
        time.sleep(1.5)
        if self._page_has_invalid_session_prompt():
            self._clear_invalid_login_state()
            # The chat page provides Weibo's own QR/password login UI once the
            # rejected session has been fully removed.
            self._page.goto(WEIBO_CHAT, wait_until='domcontentloaded')
            time.sleep(1.0)
        return {'ok': True, 'message': '请在 Chromium 窗口中完成微博登录'}

    def _op_wait_login(self, login_timeout: int) -> Dict[str, str]:
        self._ensure_browser()
        deadline = time.time() + login_timeout
        while time.time() < deadline:
            info = self._fetch_authenticated_account()
            if info:
                self._apply_authenticated_account(info)
                self._op_save_session()
                return self._account.to_dict()
            time.sleep(2)
        raise TimeoutError('登录超时，请重试')

    def _extract_account_from_page(self) -> None:
        info = self._fetch_authenticated_account()
        if info:
            self._apply_authenticated_account(info)
    def _op_get_account(self) -> DouyinAccountInfo:
        if self._has_session_cookie():
            self._extract_account_from_page()
        return self._account

    def _op_navigate_messages(self, fast: bool = False) -> Dict[str, Any]:
        if self._abort:
            return {'ok': False, 'aborted': True}
        self._ensure_browser()
        try:
            if 'api.weibo.com/chat' not in (self._page.url or ''):
                self._page.goto(WEIBO_CHAT, wait_until='domcontentloaded')
            self._sleep(0.5 if fast else 1.8)
            if 'api.weibo.com/chat' not in (self._page.url or ''):
                return {'ok': False, 'url': self._page.url or ''}
            self._messages_panel_ready = True
            self._conversation_open = False
            return {'ok': True, 'url': self._page.url}
        except Exception:
            return {'ok': False, 'url': self._page.url or ''}

    def _op_list_conversations(
        self, quick: bool = False, skip_stranger: bool = False,
    ) -> List[Dict[str, Any]]:
        if self._abort:
            self._last_list_diagnosis = '操作已中止'
            return []
        if not self._has_session_cookie():
            self._last_list_diagnosis = '浏览器缺少 SUB/SUBP 登录 Cookie'
            return []
        if not self._ensure_on_chat_page(fast=quick):
            self._last_list_diagnosis = self._explain_empty_list()
            return []
        if self._page_has_invalid_session_prompt():
            self._last_list_diagnosis = '页面显示登录失效提示'
            return []

        wait_timeout = 4.0 if quick else 12.0
        result = self._wait_for_conversations(timeout=wait_timeout, quick=quick)
        if not result and not quick:
            try:
                self._page.goto(WEIBO_CHAT, wait_until='domcontentloaded')
                self._sleep(1.2)
                result = self._wait_for_conversations(timeout=8.0, quick=False)
            except Exception:
                result = []

        if result:
            self._last_list_diagnosis = ''
        else:
            self._last_list_diagnosis = self._explain_empty_list()

        self._messages_panel_ready = bool(result)
        self._conversation_open = False
        return result

    @staticmethod
    def _peer_uid(conv_id: str) -> str:
        conv_id = (conv_id or '').strip()
        if ':' in conv_id:
            return conv_id.split(':', 1)[-1]
        return conv_id

    def _find_contact_uid(self, nickname: str) -> str:
        nickname = (nickname or '').strip()
        if not nickname:
            return ''
        for row in self._collect_conversations():
            if (row.get('nickname') or '').strip() == nickname:
                return self._peer_uid(str(row.get('conv_id') or ''))
        return ''

    def _op_open_conversation(
        self, nickname: str, category: str = 'friend', from_panel: bool = False,
    ) -> bool:
        return self._ensure_on_chat_page(fast=from_panel)

    def _op_read_latest_message(
        self, conv_id: str, nickname: str, category: str = 'friend', sender_nickname: str = '',
    ) -> Dict[str, Any] | None:
        if self._abort:
            return None
        uid = self._peer_uid(conv_id)
        if not uid:
            return None
        if not self._ensure_on_chat_page(fast=True):
            return None
        my_uid = str(self._account.uid or '')
        if not my_uid:
            info = self._fetch_authenticated_account()
            if info:
                self._apply_authenticated_account(info)
            my_uid = str(self._account.uid or '')
        data = self._request_weibo_json(f'{WEIBO_CONVERSATION}?uid={uid}')
        messages = data.get('direct_messages') or []
        if not messages:
            return None
        incoming = [
            msg for msg in messages
            if str(msg.get('sender_id') or '') and str(msg.get('sender_id') or '') != my_uid
        ]
        if not incoming:
            return None
        latest = incoming[-1]
        text = self._message_preview(latest)
        if not text:
            return None
        return {
            'conv_id': conv_id or f'{category}:{uid}',
            'nickname': nickname,
            'text': text,
            'is_self': False,
            'timestamp': int(time.time()),
        }

    def _op_send_text(
        self, nickname: str, text: str, category: str = 'friend',
        from_panel: bool = False, conversation_open: bool = False,
    ) -> bool:
        if self._abort or not (text or '').strip():
            return False
        if not self._ensure_on_chat_page(fast=True):
            return False
        uid = self._find_contact_uid(nickname)
        if not uid:
            uid = self._peer_uid(nickname)
        if not uid or not uid.isdigit():
            return False
        data = self._request_weibo_post(WEIBO_SEND, {'uid': uid, 'text': text.strip()})
        return bool(data.get('id') or data.get('idstr'))

    def _op_send_image(
        self, nickname: str, image_path: str, category: str = 'friend',
        from_panel: bool = False, conversation_open: bool = False,
    ) -> bool:
        return False
