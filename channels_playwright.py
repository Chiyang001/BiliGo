"""微信视频号助手私信 Playwright 自动化。

视频号创作者助手 (channels.weixin.qq.com) 的私信接口位于
`/micro/interaction/cgi-bin/mmfinderassistant-bin/private-msg/*`，依赖
`_finder_auth` 登录态。本模块通过 Playwright 持久化浏览器会话完成扫码登录、
会话拉取与文字回复。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from douyin_playwright import (
    DouyinAccountInfo,
    IM_FILL_AND_SEND_JS,
    VERIFY_SENT_MESSAGE_JS,
)
from xiaohongshu_playwright import XiaohongshuBrowserWorker

CHANNELS_ORIGIN = 'https://channels.weixin.qq.com'
CHANNELS_PLATFORM = f'{CHANNELS_ORIGIN}/platform'
CHANNELS_PRIVATE_MSG = f'{CHANNELS_ORIGIN}/platform/private_msg'
CHANNELS_INTERACTION_PRIVATE_MSG = f'{CHANNELS_ORIGIN}/micro/interaction/private_msg'
AUTH_DATA_API = f'{CHANNELS_ORIGIN}/cgi-bin/mmfinderassistant-bin/auth/auth_data'
AUTH_FINDER_LIST_API = f'{CHANNELS_ORIGIN}/cgi-bin/mmfinderassistant-bin/auth/auth_finder_list'
INTERACTION_BASE = f'{CHANNELS_ORIGIN}/micro/interaction/cgi-bin/mmfinderassistant-bin'
# 新版助手主要用 sessionid；旧版/部分环境仍可能出现 _finder_auth
CHANNELS_SESSION_COOKIES = {'_finder_auth', 'sessionid'}
CHANNELS_MONITOR_ENGINE = 'Playwright-private-msg-v1'

CHANNELS_OPEN_CONVERSATION_JS = r"""
(nickname) => {
  const target = String(nickname || '').replace(/\s+/g, ' ').trim();
  if (!target) return { ok: false, reason: 'empty_nickname' };
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    const view = node.ownerDocument?.defaultView || window;
    const style = view.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const iframe = Array.from(document.querySelectorAll('iframe')).find((node) => {
    try {
      return String(node.contentWindow?.location?.href || '').includes('/micro/interaction/');
    } catch {
      return false;
    }
  });
  const doc = iframe?.contentWindow?.document || document;
  const nodes = Array.from(doc.querySelectorAll('div, li, article, section, button, a, span'));
  const candidates = nodes
    .filter((node) => isVisible(node))
    .map((node) => ({ node, text: normalize(node.innerText || node.textContent || '') }))
    .filter((item) => item.text && (item.text === target || item.text.startsWith(target + '\n')));
  const pick = candidates.sort((a, b) => {
    const aScore = a.text === target ? 0 : 1;
    const bScore = b.text === target ? 0 : 1;
    return aScore - bScore;
  })[0];
  if (!pick) return { ok: false, reason: 'conversation_not_found' };
  pick.node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  pick.node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  pick.node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  return { ok: true, text: pick.text.slice(0, 120) };
}
"""

CHANNELS_CLICK_PRIVATE_TAB_JS = r"""
() => {
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    const view = node.ownerDocument?.defaultView || window;
    const style = view.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const iframe = Array.from(document.querySelectorAll('iframe')).find((node) => {
    try {
      return String(node.contentWindow?.location?.href || '').includes('/micro/interaction/');
    } catch {
      return false;
    }
  });
  const doc = iframe?.contentWindow?.document || document;
  const labels = ['私信', '打招呼消息'];
  for (const label of labels) {
    const node = Array.from(doc.querySelectorAll('button, [role="tab"], div, span, a'))
      .filter((item) => isVisible(item) && normalize(item.textContent) === label)[0];
    if (node) {
      node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return { ok: true, label };
    }
  }
  return { ok: false };
}
"""

CHANNELS_CLICK_PRIVATE_TAB_IN_FRAME_JS = r"""
() => {
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const labels = ['私信', '打招呼消息'];
  for (const label of labels) {
    const node = Array.from(document.querySelectorAll('button, [role="tab"], div, span, a'))
      .find((item) => normalize(item.textContent) === label);
    if (node) {
      node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return { ok: true, label };
    }
  }
  return { ok: false };
}
"""

CHANNELS_OPEN_CONVERSATION_IN_FRAME_JS = r"""
(nickname) => {
  const target = String(nickname || '').replace(/\s+/g, ' ').trim();
  if (!target) return { ok: false, reason: 'empty_nickname' };
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const nodes = Array.from(document.querySelectorAll('div, li, span'));
  for (const node of nodes) {
    const text = normalize(node.innerText || node.textContent || '');
    if (!text) continue;
    if (text === target || text.startsWith(target + '\n')) {
      node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return { ok: true, text: text.slice(0, 120) };
    }
  }
  return { ok: false, reason: 'conversation_not_found' };
}
"""

CHANNELS_LIST_CONVERSATIONS_DOM_JS = r"""
() => {
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const body = normalize(document.body?.innerText || '');
  if (body.includes('暂无私信')) return [];
  const timeRe = /(\d{2}月\d{2}日|\d{1,2}:\d{2}|刚刚|\d+分钟前)/;
  const skip = new Set(['私信', '打招呼消息', '全部私信', '私信管理', '发送']);
  const rows = [];
  const seen = new Set();
  for (const node of Array.from(document.querySelectorAll('div, li'))) {
    const lines = (node.innerText || '').split('\n').map((line) => normalize(line)).filter(Boolean);
    if (lines.length < 2 || lines.length > 5) continue;
    const nickname = lines[0];
    if (!nickname || skip.has(nickname) || nickname.startsWith('共')) continue;
    if (!timeRe.test(lines[1])) continue;
    const preview = lines[lines.length - 1];
    if (!preview || preview === nickname) continue;
    if (seen.has(nickname)) continue;
    seen.add(nickname);
    rows.push({
      conv_id: nickname,
      nickname,
      last_message: preview,
      unread: 0,
      category: 'friend',
      sender_nickname: '',
      sender_id: '',
      message_id: '',
      peer_username: '',
      last_msg_time: 0,
    });
  }
  return rows;
}
"""

CHANNELS_SEND_TEXT_IN_FRAME_JS = r"""
(text) => {
  const content = String(text || '').trim();
  if (!content) return { ok: false, reason: 'empty_text' };
  const textarea = document.querySelector('textarea.edit_area') || document.querySelector('textarea');
  if (!textarea) return { ok: false, reason: 'textarea_not_found' };
  textarea.focus();
  textarea.value = content;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));
  const sendBtn = Array.from(document.querySelectorAll('button'))
    .find((node) => (node.innerText || '').trim() === '发送');
  if (!sendBtn) return { ok: false, reason: 'send_button_not_found' };
  sendBtn.click();
  return { ok: true };
}
"""

CHANNELS_VERIFY_SENT_IN_FRAME_JS = r"""
(text) => {
  const target = String(text || '').trim();
  if (!target) return false;
  return (document.body?.innerText || '').includes(target);
}
"""


def _pick_first(data: Any, *keys: str, default: Any = '') -> Any:
    if not isinstance(data, dict):
        return default
    for key in keys:
        value = data.get(key)
        if value not in (None, '', [], {}):
            return value
    return default


def _dig_data(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get('data')
    return data if isinstance(data, dict) else payload


def _is_api_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    err = payload.get('errCode', payload.get('errcode'))
    return err in (0, None, '0')


CHANNELS_FETCH_ACCOUNT_JS = r"""
async () => {
  const payload = {
    timestamp: Date.now(),
    _log_finder_uin: '',
    _log_finder_id: '',
    rawKeyBuff: null,
    pluginSessionId: null,
    scene: 7,
    reqScene: 7,
  };
  const pick = (obj, ...keys) => {
    if (!obj || typeof obj !== 'object') return '';
    for (const key of keys) {
      const value = obj[key];
      if (value !== undefined && value !== null && value !== '') return String(value).trim();
    }
    return '';
  };
  const parse = (data) => {
    const finder = data.finderUser || data.finder || data.finderInfo || data;
    const userAttr = data.userAttr || {};
    const nickname = pick(finder, 'nickname', 'nickName') || pick(userAttr, 'nickname', 'nickName');
    const uid = pick(finder, 'finderUsername', 'uniqId', 'username') || pick(userAttr, 'username', 'uin');
    const avatar = pick(finder, 'headImgUrl', 'headUrl', 'avatar')
      || pick(userAttr, 'headImgUrl', 'headUrl', 'encryptedHeadImage');
    if (!nickname && !uid) return null;
    return { uid: uid || nickname, nickname: nickname || uid, avatar, sec_uid: '' };
  };
  const paths = ['/auth/auth_data', '/auth/get_auth_info'];
  for (const path of paths) {
    try {
      const response = await fetch(`https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin${path}`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json;charset=UTF-8' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) continue;
      const json = await response.json();
      if (json.errCode !== 0 && json.errCode !== '0') continue;
      const info = parse(json.data || json);
      if (info) return info;
    } catch (e) {}
  }
  return null;
}
"""

CHANNELS_EXTRACT_ACCOUNT_DOM_JS = r"""
() => {
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const isVisible = (node) => {
    if (!node || node.nodeType !== 1) return false;
    const view = node.ownerDocument?.defaultView || window;
    const style = view.getComputedStyle(node);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const bodyText = normalize(document.body?.innerText || '');
  const idMatch = bodyText.match(/视频号ID\s*(sph[A-Za-z0-9]+)/i);
  const uid = idMatch ? idMatch[1] : '';
  const imgs = Array.from(document.querySelectorAll('img[src*="qlogo"], img[src*="finder"], img[src*="wx"]'))
    .filter((node) => isVisible(node));
  const avatar = imgs.length ? (imgs[0].currentSrc || imgs[0].src || '').trim() : '';
  const skip = new Set(['首页', '内容管理', '互动管理', '变现', '数据中心', '设置', '通知中心', '私信', '视频号助手']);
  const lines = bodyText.split(/\n+/).map((line) => normalize(line)).filter(Boolean);
  let nickname = '';
  for (const line of lines) {
    if (skip.has(line)) continue;
    if (/^sph[A-Za-z0-9]+$/i.test(line)) continue;
    if (/^\d+$/.test(line)) continue;
    if (line.includes('视频号ID')) continue;
    if (line.length < 2 || line.length > 40) continue;
    nickname = line;
    break;
  }
  if (!nickname && !uid) return null;
  return { uid: uid || nickname, nickname: nickname || uid, avatar, sec_uid: '' };
}
"""


def _message_preview(message: Dict[str, Any]) -> str:
    text = str(_pick_first(message.get('textMsg') or {}, 'content') or '').strip()
    if text:
        return text
    text = str(_pick_first(message, 'rawContent', 'content', 'text') or '').strip()
    if text:
        return text
    msg_type = int(_pick_first(message, 'msgType', 'bizType', default=0) or 0)
    mapping = {2: '[图片]', 3: '[语音]', 4: '[视频]', 5: '[链接]'}
    return mapping.get(msg_type, '[非文字消息]')


def _infer_incoming(message: Dict[str, Any], peer_username: str, self_username: str) -> bool:
    from_username = str(_pick_first(message, 'fromUsername', 'fromUserName') or '').strip()
    to_username = str(_pick_first(message, 'toUsername', 'toUserName') or '').strip()
    if self_username:
        if from_username and from_username == self_username:
            return False
        if to_username and to_username == self_username:
            return True
    if peer_username:
        if from_username and from_username == peer_username:
            return True
        if from_username and from_username != peer_username:
            return False
    from_user_type = int(_pick_first(message, 'fromUserType', 'userType', default=0) or 0)
    if from_user_type == 2:
        return False
    if from_user_type == 1:
        return True
    send_flag = str(_pick_first(message, 'sendMsgFlag', default='') or '').lower()
    if send_flag in {'1', 'true', 'outbound', 'send'}:
        return False
    return True


class ChannelsBrowserWorker(XiaohongshuBrowserWorker):
    PROFILE_DIR_NAME = 'channels_browser_profile'

    def __init__(self, storage_path: str, headless: bool = True):
        super().__init__(storage_path, headless=headless)
        self._last_list_diagnosis = ''
        self._private_msg_cookie = ''
        self._session_cache: Dict[str, Dict[str, Any]] = {}
        self._latest_messages: Dict[str, Dict[str, Any]] = {}
        self._finder_username = ''
        self._auth_profile_cache: Dict[str, Any] = {}
        self._known_conversations: Dict[str, Dict[str, Any]] = {}

    def get_last_list_diagnosis(self) -> str:
        return self._last_list_diagnosis or ''

    def _has_session_cookie(self) -> bool:
        if not self._context:
            return False
        cookies = self._context.cookies()
        for item in cookies:
            name = str(item.get('name') or '')
            value = str(item.get('value') or '')
            host = str(item.get('domain') or '')
            if name not in CHANNELS_SESSION_COOKIES:
                continue
            if not value:
                continue
            if 'channels.weixin.qq.com' in host or host.endswith('weixin.qq.com'):
                return True
        return False

    def _page_looks_logged_in(self) -> bool:
        if not self._page:
            return False
        try:
            url = self._page.url or ''
            return CHANNELS_PLATFORM in url and not self._page_is_login_screen()
        except Exception:
            return False

    def _page_is_login_screen(self) -> bool:
        if not self._page:
            return True
        try:
            url = self._page.url or ''
            if '/login' in url or 'login.html' in url:
                return True
            if CHANNELS_PLATFORM in url or CHANNELS_PRIVATE_MSG in url:
                return False
            for hint in ('扫码登录', '微信扫码', '请先登录', '登录视频号'):
                locator = self._page.get_by_text(hint, exact=False)
                for index in range(min(locator.count(), 4)):
                    item = locator.nth(index)
                    try:
                        if item.is_visible():
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False

    @staticmethod
    def _auth_api_payload(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            'timestamp': int(time.time() * 1000),
            '_log_finder_uin': '',
            '_log_finder_id': '',
            'rawKeyBuff': None,
            'pluginSessionId': None,
            'scene': 7,
            'reqScene': 7,
        }
        if extra:
            payload.update(extra)
        return payload

    def _request_json(self, url: str, payload: Dict[str, Any], referer: str) -> Dict[str, Any]:
        if not self._context:
            return {}
        try:
            response = self._context.request.post(
                url,
                data=json.dumps(payload, ensure_ascii=False),
                headers={
                    'Content-Type': 'application/json;charset=UTF-8',
                    'Accept': 'application/json, text/plain, */*',
                    'Origin': CHANNELS_ORIGIN,
                    'Referer': referer,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                timeout=20000,
            )
            if not response.ok:
                return {}
            data = response.json()
            if not isinstance(data, dict):
                return {}
            if not _is_api_success(data):
                return {}
            return _dig_data(data)
        except Exception:
            return {}

    def _request_auth_api(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = path if path.startswith('http') else f'{CHANNELS_ORIGIN}/cgi-bin/mmfinderassistant-bin{path}'
        return self._request_json(url, payload or self._auth_api_payload(), CHANNELS_PLATFORM)

    def _request_interaction_api(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        suffix = path if path.startswith('/') else f'/{path}'
        url = f'{INTERACTION_BASE}{suffix}'
        return self._request_json(url, payload or {}, CHANNELS_INTERACTION_PRIVATE_MSG)

    def _get_private_msg_frame(self):
        if not self._page:
            return None
        for frame in self._page.frames:
            url = frame.url or ''
            if 'micro/interaction/private_msg' in url:
                return frame
        return None

    def _wait_for_private_msg_frame(self, timeout: float = 12.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame = self._get_private_msg_frame()
            if frame:
                return frame
            if self._sleep(0.35):
                return None
        return None

    def _remember_conversations(self, rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            conv_id = str(row.get('conv_id') or row.get('nickname') or '').strip()
            if not conv_id:
                continue
            self._known_conversations[conv_id] = dict(row)

    def _list_conversations_from_dom(self) -> List[Dict[str, Any]]:
        frame = self._get_private_msg_frame()
        if not frame:
            return []
        try:
            rows = frame.evaluate(CHANNELS_LIST_CONVERSATIONS_DOM_JS)
            if not isinstance(rows, list):
                return []
            result = [row for row in rows if isinstance(row, dict) and row.get('nickname')]
            if result:
                self._remember_conversations(result)
            return result
        except Exception as exc:
            logger.debug('DOM 读取视频号会话列表失败: %s', exc)
            return []

    def _open_conversation_in_frame(self, nickname: str) -> bool:
        frame = self._get_private_msg_frame()
        if not frame:
            return False
        try:
            result = frame.evaluate(CHANNELS_OPEN_CONVERSATION_IN_FRAME_JS, nickname)
            self._sleep(0.8)
            return bool(isinstance(result, dict) and result.get('ok'))
        except Exception as exc:
            logger.debug('打开视频号会话失败: %s', exc)
            return False

    def _send_text_in_frame(self, text: str) -> bool:
        frame = self._get_private_msg_frame()
        if not frame:
            return False
        try:
            result = frame.evaluate(CHANNELS_SEND_TEXT_IN_FRAME_JS, text.strip())
            if not isinstance(result, dict) or not result.get('ok'):
                logger.debug('视频号 iframe 发送失败: %s', (result or {}).get('reason'))
                return False
            self._sleep(1.0)
            return bool(frame.evaluate(CHANNELS_VERIFY_SENT_IN_FRAME_JS, text.strip()))
        except Exception as exc:
            logger.debug('视频号 iframe 发送异常: %s', exc)
            return False

    def _parse_auth_profile_data(self, data: Dict[str, Any]) -> Dict[str, str]:
        if not isinstance(data, dict):
            return {}
        finder = _pick_first(data, 'finderUser', 'finder', 'finderInfo', default={})
        if not isinstance(finder, dict):
            finder = {}
        user_attr = _pick_first(data, 'userAttr', default={})
        if not isinstance(user_attr, dict):
            user_attr = {}
        nickname = str(
            _pick_first(finder, 'nickname', 'nickName')
            or _pick_first(user_attr, 'nickname', 'nickName')
            or ''
        ).strip()
        uid = str(
            _pick_first(finder, 'finderUsername', 'uniqId', 'username')
            or _pick_first(user_attr, 'username', 'uin')
            or ''
        ).strip()
        avatar = str(
            _pick_first(finder, 'headImgUrl', 'headUrl', 'avatar')
            or _pick_first(user_attr, 'headImgUrl', 'headUrl', 'encryptedHeadImage')
            or ''
        ).strip()
        if not nickname and not uid:
            return {}
        return {
            'uid': uid or nickname,
            'nickname': nickname or uid,
            'avatar': avatar,
            'sec_uid': '',
        }

    def _fetch_account_via_page_eval(self) -> Dict[str, str]:
        if not self._page:
            return {}
        try:
            profile = self._page.evaluate(CHANNELS_FETCH_ACCOUNT_JS)
            if isinstance(profile, dict) and (profile.get('nickname') or profile.get('uid')):
                return {
                    'uid': str(profile.get('uid') or ''),
                    'nickname': str(profile.get('nickname') or ''),
                    'avatar': str(profile.get('avatar') or ''),
                    'sec_uid': '',
                }
        except Exception as exc:
            logger.debug('页面内请求视频号账号信息失败: %s', exc)
        try:
            profile = self._page.evaluate(CHANNELS_EXTRACT_ACCOUNT_DOM_JS)
            if isinstance(profile, dict) and (profile.get('nickname') or profile.get('uid')):
                return {
                    'uid': str(profile.get('uid') or ''),
                    'nickname': str(profile.get('nickname') or ''),
                    'avatar': str(profile.get('avatar') or ''),
                    'sec_uid': '',
                }
        except Exception as exc:
            logger.debug('页面 DOM 提取视频号账号信息失败: %s', exc)
        return {}

    def _fetch_authenticated_account(self) -> Dict[str, str]:
        if self._auth_profile_cache:
            parsed = self._parse_auth_profile_data(self._auth_profile_cache)
            if parsed:
                return parsed

        for path in ('/auth/auth_data', '/auth/get_auth_info'):
            data = self._request_auth_api(path, self._auth_api_payload())
            parsed = self._parse_auth_profile_data(data)
            if parsed:
                self._auth_profile_cache = data
                return parsed

        listed = self._request_auth_api('/auth/auth_finder_list', self._auth_api_payload())
        rows = listed.get('finderList') if isinstance(listed, dict) else []
        if isinstance(rows, list) and rows:
            first = rows[0] if isinstance(rows[0], dict) else {}
            parsed = self._parse_auth_profile_data({'finderUser': first})
            if parsed:
                self._auth_profile_cache = {'finderUser': first}
                return parsed

        parsed = self._fetch_account_via_page_eval()
        if parsed:
            return parsed
        return {}

    def _apply_authenticated_account(self, info: Dict[str, str]) -> None:
        self._account = DouyinAccountInfo(
            uid=str(info.get('uid') or ''),
            nickname=str(info.get('nickname') or ''),
            avatar=str(info.get('avatar') or ''),
            sec_uid='',
        )

    def _attach_network_listeners(self) -> None:
        if not self._page:
            return

        def on_response(response):
            try:
                url = response.url or ''
                if 'mmfinderassistant-bin/auth/' not in url:
                    return
                if response.status != 200:
                    return
                content_type = (response.headers.get('content-type') or '').lower()
                if 'json' not in content_type:
                    return
                payload = response.json()
                if not _is_api_success(payload):
                    return
                data = _dig_data(payload)
                parsed = self._parse_auth_profile_data(data)
                if not parsed:
                    return
                self._auth_profile_cache = data
                self._apply_authenticated_account(parsed)
            except Exception:
                pass

        self._page.on('response', on_response)

    def _ensure_on_platform_page(self) -> None:
        if not self._page:
            return
        try:
            current = self._page.url or ''
            if CHANNELS_PLATFORM in current and not self._page_is_login_screen():
                return
            self._page.goto(CHANNELS_PLATFORM, wait_until='domcontentloaded')
            self._sleep(2.0)
        except Exception as exc:
            logger.debug('打开视频号助手首页失败: %s', exc)

    def _ensure_finder_username(self) -> str:
        cached = str(self._finder_username or '').strip()
        if cached:
            return cached
        data = self._request_interaction_api('/private-msg/get-finder-username', {})
        username = str(_pick_first(data, 'finderUsername', 'username', 'finder_username', 'finderUserName') or '').strip()
        if username:
            self._finder_username = username
        return username

    def _fetch_private_messages(self, include_history: bool = False) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        seen = set()
        cookie = self._private_msg_cookie or ''

        def _append_batch(batch: List[Dict[str, Any]]) -> None:
            for item in batch:
                if not isinstance(item, dict):
                    continue
                key = str(_pick_first(item, 'seq', 'svrMsgId', 'msgId', default='') or '')
                fallback = f"{item.get('sessionId')}:{item.get('ts')}:{item.get('rawContent')}"
                dedupe = key or fallback
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                rows.append(item)

        def _pull_messages(endpoint: str, start_cookie: str) -> str:
            current_cookie = start_cookie
            has_more = True
            while has_more:
                data = self._request_interaction_api(endpoint, {'cookie': current_cookie})
                _append_batch(data.get('msg') if isinstance(data.get('msg'), list) else [])
                has_more = bool(data.get('isContinue'))
                next_cookie = str(data.get('cookie') or current_cookie)
                if not has_more or next_cookie == current_cookie:
                    break
                current_cookie = next_cookie
            return current_cookie

        cookie = _pull_messages('/private-msg/get-new-msg', cookie)
        if include_history or not rows:
            _pull_messages('/private-msg/get-history-msg', '')

        self._private_msg_cookie = cookie
        rows.sort(key=lambda item: int(_pick_first(item, 'ts', default=0) or 0))
        return rows

    def _hydrate_session_infos(self, session_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        chunk: List[str] = []
        for session_id in session_ids:
            if not session_id:
                continue
            chunk.append(session_id)
            if len(chunk) < 30:
                continue
            data = self._request_interaction_api('/private-msg/get-session-info', {'sessionId': chunk})
            infos = data.get('sessionInfo') if isinstance(data.get('sessionInfo'), list) else []
            for item in infos:
                if isinstance(item, dict):
                    sid = str(_pick_first(item, 'sessionId') or '')
                    if sid:
                        result[sid] = item
            chunk = []
        if chunk:
            data = self._request_interaction_api('/private-msg/get-session-info', {'sessionId': chunk})
            infos = data.get('sessionInfo') if isinstance(data.get('sessionInfo'), list) else []
            for item in infos:
                if isinstance(item, dict):
                    sid = str(_pick_first(item, 'sessionId') or '')
                    if sid:
                        result[sid] = item
        self._session_cache.update(result)
        return result

    def _collect_conversations(self, include_history: bool = False) -> List[Dict[str, Any]]:
        self_username = self._ensure_finder_username()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for message in self._fetch_private_messages(include_history=include_history):
            session_id = str(_pick_first(message, 'sessionId') or '').strip()
            if not session_id:
                continue
            grouped.setdefault(session_id, []).append(message)

        if not grouped:
            return []

        session_infos = self._hydrate_session_infos(list(grouped.keys()))
        rows: List[Dict[str, Any]] = []
        self._latest_messages = {}

        for session_id, messages in grouped.items():
            messages.sort(key=lambda item: int(_pick_first(item, 'ts', default=0) or 0))
            latest = messages[-1]
            info = session_infos.get(session_id) or self._session_cache.get(session_id) or {}
            peer_username = str(_pick_first(info, 'username', 'userName') or '').strip()
            nickname = str(_pick_first(info, 'nickname', 'nickName', 'name') or peer_username or session_id).strip()
            preview = _message_preview(latest)
            if not nickname or not preview:
                continue
            unread = 0
            try:
                unread = max(0, int(_pick_first(info, 'unreadCount', 'unread', default=0) or 0))
            except (TypeError, ValueError):
                unread = 0
            if not unread and _infer_incoming(latest, peer_username, self_username):
                unread = 1
            sender_id = str(_pick_first(latest, 'fromUsername', 'fromUserName') or '')
            sender_nickname = nickname if _infer_incoming(latest, peer_username, self_username) else ''
            message_id = str(_pick_first(latest, 'svrMsgId', 'msgId', 'seq', default='') or '')
            row = {
                'conv_id': session_id,
                'nickname': nickname,
                'last_message': preview,
                'unread': unread,
                'category': 'friend',
                'sender_nickname': sender_nickname,
                'sender_id': sender_id,
                'message_id': message_id,
                'peer_username': peer_username,
                'last_msg_time': int(_pick_first(latest, 'ts', default=0) or 0),
            }
            rows.append(row)
            self._latest_messages[session_id] = latest

        rows.sort(
            key=lambda item: (
                -int(item.get('unread') or 0),
                -int(item.get('last_msg_time') or 0),
            )
        )
        if rows:
            self._remember_conversations(rows)
        return rows

    def _explain_empty_list(self) -> str:
        if self._abort:
            return '浏览器操作被中断'
        if not self._has_session_cookie() and not self._page_looks_logged_in():
            return '缺少视频号登录 Cookie，请重新登录'
        if self._page_is_login_screen():
            return '页面显示未登录，请重新扫码登录'
        return '私信接口返回空列表（可能暂无新消息或页面结构已变化）'

    def _ensure_on_private_page(self, fast: bool = False) -> bool:
        if self._abort:
            return False
        self._ensure_browser()
        current = self._page.url or ''
        if CHANNELS_PRIVATE_MSG not in current:
            try:
                self._page.goto(CHANNELS_PRIVATE_MSG, wait_until='domcontentloaded')
            except Exception:
                return False
        self._sleep(0.8 if fast else 2.0)
        frame = self._wait_for_private_msg_frame(timeout=8.0 if fast else 12.0)
        if not frame:
            return False
        try:
            frame.evaluate(CHANNELS_CLICK_PRIVATE_TAB_IN_FRAME_JS)
        except Exception:
            try:
                self._page.evaluate(CHANNELS_CLICK_PRIVATE_TAB_JS)
            except Exception:
                pass
        if fast:
            self._sleep(0.35)
        else:
            self._sleep(0.8)
        return (
            CHANNELS_PRIVATE_MSG in (self._page.url or '')
            and not self._page_is_login_screen()
            and self._get_private_msg_frame() is not None
        )

    def _op_check_session(self) -> bool:
        self.headless = True
        self._ensure_browser()
        try:
            self._ensure_on_platform_page()
            if self._page_is_login_screen():
                return False
            info = self._fetch_authenticated_account()
            if not info:
                return False
            self._apply_authenticated_account(info)
            self._ensure_finder_username()
            return True
        except Exception:
            return False

    def _op_open_login(self) -> Dict[str, Any]:
        self.headless = False
        if self._context and self._current_headless is True:
            self._cleanup_browser()
            self._current_headless = None
        self._ensure_browser()
        self._page.goto(CHANNELS_PLATFORM, wait_until='domcontentloaded')
        time.sleep(1.2)
        return {'ok': True, 'message': '请在 Chromium 窗口中使用微信扫码登录视频号助手'}

    def _op_wait_login(self, login_timeout: int) -> Dict[str, str]:
        self._ensure_browser()
        deadline = time.time() + login_timeout
        while time.time() < deadline:
            if self._abort:
                raise RuntimeError('登录操作已取消')
            if self._has_session_cookie() or self._page_looks_logged_in():
                self._ensure_on_platform_page()
                info = self._fetch_authenticated_account()
                if info:
                    self._apply_authenticated_account(info)
                    self._ensure_finder_username()
                    self._op_save_session()
                    return self._account.to_dict()
            time.sleep(1.5)
        raise TimeoutError('登录超时，请重试')

    def _extract_account_from_page(self) -> None:
        self._ensure_on_platform_page()
        if self._page_is_login_screen():
            return
        info = self._fetch_authenticated_account()
        if info:
            self._apply_authenticated_account(info)

    def _op_get_account(self) -> DouyinAccountInfo:
        self._extract_account_from_page()
        return self._account

    def _op_navigate_messages(self, fast: bool = False) -> Dict[str, Any]:
        if self._abort:
            return {'ok': False, 'aborted': True}
        ok = self._ensure_on_private_page(fast=fast)
        self._messages_panel_ready = ok
        self._conversation_open = False
        return {'ok': ok, 'url': self._page.url or ''}

    def _op_list_conversations(
        self, quick: bool = False, skip_stranger: bool = False,
    ) -> List[Dict[str, Any]]:
        if self._abort:
            self._last_list_diagnosis = '操作已中止'
            return []
        if not self._has_session_cookie() and not self._page_looks_logged_in():
            self._last_list_diagnosis = '缺少视频号登录 Cookie'
            return []
        if not self._ensure_on_private_page(fast=quick):
            self._last_list_diagnosis = self._explain_empty_list()
            return []
        if self._page_is_login_screen():
            self._last_list_diagnosis = '页面显示未登录'
            return []

        result = self._collect_conversations(include_history=True)
        if not result:
            result = self._list_conversations_from_dom()
        if not result and self._known_conversations:
            result = list(self._known_conversations.values())

        if result:
            self._last_list_diagnosis = ''
        else:
            self._last_list_diagnosis = self._explain_empty_list()

        self._messages_panel_ready = True
        self._conversation_open = False
        return result

    def _op_open_conversation(
        self, nickname: str, category: str = 'friend', from_panel: bool = False,
    ) -> bool:
        if self._abort:
            return False
        if not self._ensure_on_private_page(fast=from_panel):
            return False
        if self._open_conversation_in_frame(nickname):
            return True
        try:
            result = self._page.evaluate(CHANNELS_OPEN_CONVERSATION_JS, nickname)
            self._sleep(0.8 if from_panel else 1.2)
            return bool(isinstance(result, dict) and result.get('ok'))
        except Exception:
            return False

    def _op_read_latest_message(
        self, conv_id: str, nickname: str, category: str = 'friend', sender_nickname: str = '',
    ) -> Dict[str, Any] | None:
        if self._abort:
            return None
        session_id = str(conv_id or '').strip()
        latest = self._latest_messages.get(session_id)
        if not latest and session_id:
            self._collect_conversations(include_history=True)
            latest = self._latest_messages.get(session_id)
        if not latest:
            return None
        info = self._session_cache.get(session_id) or {}
        peer_username = str(_pick_first(info, 'username', 'userName') or '').strip()
        self_username = self._ensure_finder_username()
        if not _infer_incoming(latest, peer_username, self_username):
            return None
        text = _message_preview(latest)
        if not text or text == '[非文字消息]':
            return None
        return {
            'conv_id': session_id or nickname,
            'nickname': nickname,
            'text': text,
            'is_self': False,
            'timestamp': int(_pick_first(latest, 'ts', default=0) or time.time()),
        }

    def _try_send_via_api(self, session_id: str, text: str) -> bool:
        payload_variants = [
            {'sessionId': session_id, 'textMsg': {'content': text}},
            {'sessionId': session_id, 'content': text, 'textMsg': {'content': text}},
            {'sessionId': session_id, 'msgType': 1, 'textMsg': {'content': text}},
        ]
        endpoints = (
            '/private-msg/send-private-msg',
            '/private-msg/send-text-msg',
            '/private-msg/send-msg',
        )
        for endpoint in endpoints:
            for payload in payload_variants:
                data = self._request_interaction_api(endpoint, payload)
                if not data:
                    continue
                base_resp = data.get('baseResp') if isinstance(data.get('baseResp'), dict) else {}
                if base_resp.get('errcode') in (0, '0'):
                    return True
                if data.get('ret') in (0, '0'):
                    return True
                if data.get('success') is True:
                    return True
                if data.get('svrMsgId') or data.get('msgId'):
                    return True
        return False

    def _op_send_text(
        self, nickname: str, text: str, category: str = 'friend',
        from_panel: bool = False, conversation_open: bool = False,
    ) -> bool:
        if self._abort or not (text or '').strip():
            return False
        session_id = ''
        for row in self._collect_conversations(include_history=True):
            if (row.get('nickname') or '').strip() == (nickname or '').strip():
                session_id = str(row.get('conv_id') or '')
                break
        if not session_id:
            cached = self._known_conversations.get(nickname) or {}
            session_id = str(cached.get('conv_id') or '')

        if not self._ensure_on_private_page(fast=True):
            return False
        if not self._op_open_conversation(nickname, category=category, from_panel=from_panel):
            return False
        if self._send_text_in_frame(text.strip()):
            return True
        if session_id and '@findermsg' in session_id and self._try_send_via_api(session_id, text.strip()):
            return True
        try:
            frame = self._get_private_msg_frame()
            if frame:
                result = frame.evaluate(CHANNELS_SEND_TEXT_IN_FRAME_JS, text.strip())
                if isinstance(result, dict) and result.get('ok'):
                    self._sleep(0.8)
                    return bool(frame.evaluate(CHANNELS_VERIFY_SENT_IN_FRAME_JS, text.strip()))
            result = self._page.evaluate(IM_FILL_AND_SEND_JS, text.strip())
            if isinstance(result, dict) and result.get('ok'):
                self._sleep(0.6)
                if self._page.evaluate(VERIFY_SENT_MESSAGE_JS, text.strip()):
                    return True
        except Exception:
            return False
        return False

    def _op_send_image(
        self, nickname: str, image_path: str, category: str = 'friend',
        from_panel: bool = False, conversation_open: bool = False,
    ) -> bool:
        return False
