"""闲鱼消息网页自动化 Worker。

闲鱼没有稳定的个人消息开放 API，这里复用项目现有的 Playwright 线程模型，
通过 goofish.com/im 页面完成登录、会话读取和文字发送。
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from douyin_playwright import DouyinAccountInfo, DouyinBrowserWorker


XIANYU_ACCOUNT_JS = r"""
() => {
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!(el instanceof HTMLElement)) return false;
    const r = el.getBoundingClientRect();
    const css = getComputedStyle(el);
    return r.width >= 16 && r.height >= 16 && css.display !== 'none' &&
      css.visibility !== 'hidden' && Number(css.opacity || 1) > 0;
  };
  const normalizeUrl = value => {
    let url = clean(value).replace(/&amp;/g, '&');
    if (url.startsWith('//')) url = `https:${url}`;
    if (!/^https?:\/\//i.test(url)) return '';
    if (/logo|qrcode|qr-code|sprite|iconfont|favicon|banner/i.test(url)) return '';
    return url;
  };
  const first = (obj, keys) => {
    for (const key of keys) {
      if (obj && obj[key] != null && typeof obj[key] !== 'object') {
        const value = clean(obj[key]);
        if (value) return value;
      }
    }
    return '';
  };
  const avatarFrom = obj => {
    const direct = first(obj, [
      'avatar', 'avatarUrl', 'avatar_url', 'headImg', 'headImgUrl',
      'head_img', 'userAvatar', 'user_avatar', 'portrait', 'portraitUrl'
    ]);
    if (normalizeUrl(direct)) return normalizeUrl(direct);
    for (const key of ['avatar', 'avatarInfo', 'headImg', 'portrait']) {
      const nested = obj?.[key];
      if (!nested || typeof nested !== 'object') continue;
      const url = first(nested, ['url', 'src', 'avatarUrl', 'url_100x100', 'urlList']);
      if (normalizeUrl(url)) return normalizeUrl(url);
      if (Array.isArray(nested.urlList) && normalizeUrl(nested.urlList[0])) {
        return normalizeUrl(nested.urlList[0]);
      }
    }
    return '';
  };

  const candidates = [];
  const seen = new WeakSet();
  const visit = (obj, path = '', depth = 0) => {
    if (!obj || typeof obj !== 'object' || depth > 7 || seen.has(obj)) return;
    seen.add(obj);
    if (!Array.isArray(obj)) {
      const nickname = first(obj, [
        'nickname', 'nickName', 'nick', 'userNick', 'user_name',
        'displayName', 'display_name'
      ]);
      const uid = first(obj, [
        'userId', 'user_id', 'userid', 'userNumId', 'idleUserId', 'uid'
      ]);
      const avatar = avatarFrom(obj);
      if (nickname || uid || avatar) {
        let score = (nickname ? 18 : 0) + (uid ? 16 : 0) + (avatar ? 24 : 0);
        if (/(current|login|account|profile|mine|my|self|owner|userInfo)/i.test(path)) score += 45;
        if (/(conversation|message|chat|contact|buyer|seller|item|goods|recommend)/i.test(path)) score -= 35;
        candidates.push({nickname, uid, avatar, score});
      }
    }
    const entries = Array.isArray(obj) ? obj.slice(0, 80).entries() : Object.entries(obj).slice(0, 160);
    for (const [key, value] of entries) {
      if (value && typeof value === 'object') visit(value, `${path}.${key}`, depth + 1);
    }
  };

  const roots = [
    ['__INITIAL_STATE__', window.__INITIAL_STATE__], ['__INIT_DATA__', window.__INIT_DATA__],
    ['__NEXT_DATA__', window.__NEXT_DATA__], ['__APOLLO_STATE__', window.__APOLLO_STATE__],
    ['__NUXT__', window.__NUXT__], ['__GLOBAL_DATA__', window.__GLOBAL_DATA__],
    ['__data__', window.__data__]
  ];
  for (const [name, root] of roots) visit(root, `window.${name}`);
  for (const selector of ['#__NEXT_DATA__', '#__NUXT_DATA__', 'script[type="application/json"]']) {
    for (const node of document.querySelectorAll(selector)) {
      const raw = node.textContent || '';
      if (!raw || raw.length > 3000000) continue;
      try { visit(JSON.parse(raw), `script.${selector}`); } catch (e) {}
    }
  }
  const storages = [];
  try { storages.push(window.localStorage); } catch (e) {}
  try { storages.push(window.sessionStorage); } catch (e) {}
  for (const storage of storages) {
    try {
      for (let i = 0; i < storage.length; i += 1) {
        const key = storage.key(i) || '';
        const raw = storage.getItem(key) || '';
        if (!raw || raw.length > 1000000 || !/(user|login|account|profile|member)/i.test(`${key} ${raw.slice(0, 500)}`)) continue;
        try { visit(JSON.parse(raw), `storage.${key}`); } catch (e) {}
      }
    } catch (e) {}
  }
  candidates.sort((a, b) => b.score - a.score);
  const structured = candidates.find(item => item.score >= 38) || {};

  const imageCandidates = [...document.images].filter(visible).map(img => {
    const src = normalizeUrl(img.currentSrc || img.src || img.getAttribute('src'));
    if (!src) return null;
    const r = img.getBoundingClientRect();
    const context = clean([
      img.alt, img.title, img.className,
      img.parentElement?.className, img.closest('header, nav, [class*="header" i]')?.className,
      img.parentElement?.innerText
    ].join(' '));
    let score = 0;
    if (/avatar|head|user|member|头像/i.test(context)) score += 55;
    if (img.closest('header, nav, [class*="header" i], [class*="navbar" i]')) score += 38;
    if (r.top < 150) score += 25;
    if (r.left > innerWidth * .55) score += 12;
    if (r.width >= 24 && r.width <= 160 && Math.abs(r.width - r.height) <= Math.max(r.width, r.height) * .3) score += 20;
    if (/alicdn|tbcdn|taobaocdn|goofish/i.test(src)) score += 8;
    if (/conversation|message|chat|goods|item|product|商品/i.test(context)) score -= 65;
    return {src, score, context, top: r.top};
  }).filter(Boolean).sort((a, b) => b.score - a.score);

  const domAvatar = imageCandidates.find(item => item.score >= 35)?.src || '';
  let domNickname = '';
  const nameSelectors = [
    'header [data-nickname]', 'header [class*="nickname" i]',
    'header [class*="user-name" i]', 'nav [class*="nickname" i]',
    '[class*="header" i] [class*="nickname" i]', '[data-nickname]'
  ];
  for (const selector of nameSelectors) {
    const node = [...document.querySelectorAll(selector)].find(visible);
    const value = clean(node?.getAttribute('data-nickname') || node?.innerText);
    if (value && value.length <= 40 && !/登录|消息|首页|闲鱼/.test(value)) {
      domNickname = value;
      break;
    }
  }
  return {
    nickname: structured.nickname || domNickname,
    uid: structured.uid || '',
    avatar: structured.avatar || domAvatar,
  };
}
"""

# The homepage account entry is a reliable DOM fallback for the two dedicated
# current-user APIs. Limit matching to the top bar and uploaded user images so
# product cards, contacts and the fixed "orders" icon can never be selected.
XIANYU_HEADER_ACCOUNT_JS = r"""
() => {
  const visible = el => {
    const r = el?.getBoundingClientRect();
    const css = el ? getComputedStyle(el) : null;
    return !!r && r.width >= 20 && r.height >= 20 && r.top >= 0 && r.top < 100 &&
      css.display !== 'none' && css.visibility !== 'hidden';
  };
  const excluded = /^(订单|消息|首页|登录|注册|搜索|发布闲置|我的)$/;
  const rows = [...document.images].filter(img => {
    const src = img.currentSrc || img.src || '';
    const r = img.getBoundingClientRect();
    return visible(img) && r.width <= 80 && r.height <= 80 &&
      Math.abs(r.width - r.height) <= 8 && /\/bao\/uploaded\//i.test(src);
  }).map(img => {
    const host = img.closest('a, button, [class*="item" i]') || img.parentElement;
    const nickname = String(host?.innerText || '').replace(/\s+/g, ' ').trim();
    const r = img.getBoundingClientRect();
    let src = img.currentSrc || img.src || '';
    if (src.startsWith('//')) src = `https:${src}`;
    if (src.startsWith('http://')) src = `https://${src.slice(7)}`;
    let score = r.left > innerWidth * .55 ? 30 : 0;
    if (nickname && nickname.length <= 40 && !excluded.test(nickname)) score += 80;
    return {nickname, avatar: src, score};
  }).filter(row => row.score >= 80).sort((a, b) => b.score - a.score);
  return rows[0] || {nickname: '', avatar: ''};
}
"""


class XianyuBrowserWorker(DouyinBrowserWorker):
    PROFILE_DIR_NAME = "xianyu_browser_profile"

    def __init__(self, storage_path: str, headless: bool = True):
        super().__init__(storage_path, headless=headless)
        self._xianyu_account_capture: Dict[str, str] = {}

    def _attach_network_listeners(self) -> None:
        super()._attach_network_listeners()
        if not self._page:
            return

        def on_response(response) -> None:
            try:
                if response.status != 200:
                    return
                url = (response.url or "").lower()
                is_profile = "mtop.idle.web.user.page.nav" in url
                is_login_user = "mtop.taobao.idlemessage.pc.loginuser.get" in url
                if not is_profile and not is_login_user:
                    return
                payload = response.json() or {}
                data = payload.get("data") or {}
                if is_login_user:
                    uid = str(data.get("userId") or data.get("user_id") or "").strip()
                    if uid:
                        self._xianyu_account_capture["uid"] = uid
                if is_profile:
                    module = data.get("module") or {}
                    base = module.get("base") or data.get("base") or {}
                    nickname = str(base.get("displayName") or "").strip()
                    avatar = self._valid_avatar_url(base.get("avatar"))
                    if nickname:
                        self._xianyu_account_capture["nickname"] = nickname[:40]
                    if avatar:
                        self._xianyu_account_capture["avatar"] = avatar
            except Exception:
                pass

        self._page.on("response", on_response)

    @staticmethod
    def _valid_avatar_url(value: Any) -> str:
        url = str(value or "").strip().replace("&amp;", "&")
        if url.startswith("//"):
            url = f"https:{url}"
        if url.startswith("http://"):
            url = f"https://{url[7:]}"
        if not url.startswith(("https://", "http://")):
            return ""
        lowered = url.lower()
        if any(word in lowered for word in ("logo", "qrcode", "qr-code", "favicon", "sprite")):
            return ""
        return url

    def _read_account_from_current_page(self) -> Dict[str, str]:
        try:
            data = self._page.evaluate(XIANYU_HEADER_ACCOUNT_JS) or {}
        except Exception:
            data = {}
        return {
            "nickname": str(data.get("nickname") or "").strip()[:40],
            "uid": "",
            "avatar": self._valid_avatar_url(data.get("avatar")),
        }

    def _extract_account_from_page(self) -> None:
        if not self._page:
            return
        # The IM page usually emits loginuser.get before the homepage profile
        # request. Preserve that authoritative ID across the navigation.
        captured_uid = str(self._xianyu_account_capture.get("uid") or "").strip()
        self._xianyu_account_capture = {"uid": captured_uid} if captured_uid else {}
        try:
            self._page.goto("https://www.goofish.com/", wait_until="domcontentloaded", timeout=30000)
            self._sleep(2.5)
        except Exception:
            pass

        # Network responses are authoritative. The narrowly scoped top-bar
        # lookup only fills missing visual fields and never scans page cards.
        info = dict(self._xianyu_account_capture)
        dom_info = self._read_account_from_current_page()
        for key in ("nickname", "avatar"):
            if not info.get(key) and dom_info.get(key):
                info[key] = dom_info[key]

        # Discard stale values produced by older broad heuristics. It is safer
        # to show no avatar than another user's avatar or the orders icon.
        self._account = DouyinAccountInfo(
            uid=str(info.get("uid") or ""),
            nickname=str(info.get("nickname") or ""),
            avatar=self._valid_avatar_url(info.get("avatar")),
        )

    def _op_get_account(self) -> DouyinAccountInfo:
        if self._op_check_session():
            self._extract_account_from_page()
        return self._account

    def _op_open_login(self) -> Dict[str, Any]:
        self._ensure_browser()
        self._page.goto("https://www.goofish.com/", wait_until="domcontentloaded", timeout=30000)
        self._messages_panel_ready = False
        return {"ok": True}

    def _op_check_session(self) -> bool:
        try:
            self._ensure_browser()
            # 持久化浏览器经常恢复到闲鱼首页。首页已登录不代表消息页已经
            # 就绪，因此只要当前不在 /im 就必须进入消息页再判断。
            if "/im" not in (self._page.url or ""):
                self._page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=20000)
                self._sleep(1.2)
            text = (self._page.locator("body").inner_text(timeout=5000) or "")[:12000]
            login_words = ("扫码登录", "请登录", "立即登录", "短信登录", "登录闲鱼")
            login_dialog = self._page.locator('[class*=login i]:visible, [class*=qrcode i]:visible').count() > 0
            return (
                "/im" in (self._page.url or "")
                and len(text.strip()) >= 20
                and "非法访问" not in text
                and not login_dialog
                and not any(word in text for word in login_words)
            )
        except Exception:
            return False

    def _op_wait_login(self, login_timeout: int) -> Dict[str, str]:
        deadline = time.time() + login_timeout
        account_read_attempts = 0
        while time.time() < deadline and not self._abort:
            if self._op_check_session():
                self._page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=30000)
                self._sleep(1.5)
                self._extract_account_from_page()
                if not self._account.nickname or not self._account.uid:
                    account_read_attempts += 1
                    if account_read_attempts >= 3:
                        raise RuntimeError("已检测到闲鱼登录，但未能读取当前账号资料，请重试")
                    self._sleep(1)
                    continue
                return self._account.to_dict()
            self._sleep(2)
        raise TimeoutError("等待闲鱼登录超时")

    def _op_navigate_messages(self, fast: bool = False) -> Dict[str, Any]:
        self._ensure_browser()
        self._page.goto("https://www.goofish.com/im", wait_until="domcontentloaded", timeout=30000)
        self._sleep(0.8 if fast else 2)
        conversations = self._extract_xianyu_conversations()
        panel_count = self._page.locator('[role=listitem], [class*=conversation-item i], [class*=session-item i], [class*=chat-item i]').count()
        body_text = (self._page.locator("body").inner_text(timeout=3000) or "")[:4000]
        self._messages_panel_ready = bool(conversations) or panel_count > 0 or "暂无消息" in body_text
        return {"ok": self._messages_panel_ready, "url": self._page.url}

    def _extract_xianyu_conversations(self) -> List[Dict[str, Any]]:
        script = """
        () => {
          const out = [], seen = new Set();
          const selectors = [
            '[role=listitem]', '[class*=conversation-item i]', '[class*=session-item i]',
            '[class*=chat-item i]', '[class*=message-item i]'
          ];
          const nodes = [...document.querySelectorAll(selectors.join(','))];
          for (const node of nodes) {
            const r = node.getBoundingClientRect();
            if (r.width < 180 || r.height < 36 || r.top < 70 || r.right > innerWidth * .55) continue;
            const countNode = node.querySelector(
              '.ant-badge-count, [class*=unread-count i], [class*=badge-count i], [aria-label*=未读]'
            );
            const countVisible = countNode && countNode.getBoundingClientRect().width > 0;
            const unreadText = countVisible ? (countNode.textContent || '').trim() : '';
            let unread = 0;
            if (unreadText) {
              const match = unreadText.match(/\\d+/);
              unread = match ? Math.max(1, parseInt(match[0], 10)) : 1;
            } else {
              const dot = node.querySelector('.ant-badge-dot, [class*=unread-dot i], [aria-label*=未读]');
              if (dot && dot.getBoundingClientRect().width > 0) unread = 1;
            }
            const lines = (node.innerText || '').split('\\n').map(x => x.trim()).filter(Boolean);
            // Ant Design 会把未读数字放在 innerText 第一行，昵称随之移到第二行。
            if (unread && unreadText && lines[0] === unreadText) lines.shift();
            if (lines.length < 2) continue;
            const nickname = lines[0].trim();
            const content = lines.slice(1).filter(x => !/^(刚刚|昨天|前天|\\d{1,2}:\\d{2}|\\d+[分小]钟前|\\d{2}-\\d{2}|\\d{4}-\\d{2}-\\d{2})$/.test(x));
            const preview = content.join(' ').slice(0, 500);
            if (!nickname || /^(消息|通知消息|闲鱼号)$/.test(nickname) || seen.has(nickname)) continue;
            if (!preview) continue;
            const convId = node.getAttribute('data-conversation-id') || node.getAttribute('data-session-id') || node.getAttribute('data-id') || nickname;
            const messageId = node.getAttribute('data-message-id') || '';
            seen.add(convId);
            out.push({conv_id: convId, nickname, last_message: preview, unread, category: 'friend', message_id: messageId});
          }
          return out.slice(0, 100);
        }
        """
        try:
            return self._page.evaluate(script) or []
        except Exception:
            return []

    def _op_list_conversations(self, quick: bool = False, skip_stranger: bool = False) -> List[Dict[str, Any]]:
        if not self._messages_panel_ready:
            self._op_navigate_messages(fast=quick)
        return self._extract_xianyu_conversations()

    def _op_open_conversation(self, nickname: str, category: str = "friend", from_panel: bool = False) -> bool:
        if not self._messages_panel_ready:
            self._op_navigate_messages(fast=True)
        try:
            loc = self._page.get_by_text(nickname, exact=True)
            visible = next((loc.nth(i) for i in range(min(loc.count(), 20)) if loc.nth(i).is_visible()), None)
            if visible is not None:
                visible.click(timeout=3000)
            else:
                candidates = self._page.locator('[role=listitem], [class*=conversation-item i], [class*=session-item i], [class*=chat-item i]').filter(has_text=nickname)
                visible = next((candidates.nth(i) for i in range(min(candidates.count(), 20)) if candidates.nth(i).is_visible()), None)
                if visible is None:
                    return False
                visible.click(timeout=3000)
            self._sleep(0.8)
            self._conversation_open = True
            return True
        except Exception:
            return False

    def _op_read_latest_message(self, conv_id: str, nickname: str, category: str = "friend", sender_nickname: str = "") -> Dict[str, Any] | None:
        if not self._conversation_open:
            if not self._op_open_conversation(nickname, category):
                return None
        try:
            result = self._page.evaluate("""
            () => {
              const selectors = [
                '[data-message-id]', '[class*=message-item i]', '[class*=message-row i]',
                '[class*=bubble i]'
              ];
              const all = [...document.querySelectorAll(selectors.join(','))]
                .filter(node => {
                  const r = node.getBoundingClientRect();
                  return r.width > 20 && r.height > 12 && r.top > 60;
                });
              const leaves = all.filter(node => !all.some(other => other !== node && node.contains(other)));
              const node = leaves.at(-1);
              if (!node) return null;
              const text = (node.innerText || node.textContent || '').trim();
              if (!text) return null;
              const cls = `${node.className || ''} ${node.parentElement?.className || ''}`.toLowerCase();
              const rect = node.getBoundingClientRect();
              const isSelf = /(^|[-_ ])(self|mine|right|send|outgoing)([-_ ]|$)/.test(cls)
                || rect.left + rect.width / 2 > innerWidth * .58
                || /^(我|我说)[:：]/.test(text);
              return {text: text.replace(/^(我|我说)[:：]\\s*/, ''), is_self: isSelf,
                message_id: node.getAttribute('data-message-id') || ''};
            }
            """)
            if not result:
                return None
            return {"conv_id": conv_id or nickname, "nickname": nickname,
                    "text": result["text"], "is_self": bool(result["is_self"]),
                    "message_id": result.get("message_id", ""), "timestamp": int(time.time())}
        except Exception:
            return None

    def _op_send_text(self, nickname: str, text: str, category: str = "friend", from_panel: bool = False, conversation_open: bool = False) -> bool:
        if not conversation_open and not self._conversation_open:
            if not self._op_open_conversation(nickname, category):
                self._last_send_error = "无法打开闲鱼会话"
                return False
        try:
            editors = self._page.locator('textarea:visible, [contenteditable="true"]:visible')
            if not editors.count():
                self._last_send_error = "未找到闲鱼消息输入框"
                return False
            editor = editors.last
            try:
                editor.fill(text)
            except Exception:
                editor.click()
                editor.press("Control+A")
                editor.press_sequentially(text, delay=8)
            editor.press("Enter")
            self._sleep(0.8)
            try:
                remaining = (editor.input_value(timeout=1000) if editor.evaluate("el => el.tagName === 'TEXTAREA'") else editor.inner_text(timeout=1000)).strip()
                if remaining == text:
                    self._last_send_error = "消息提交后输入框未清空"
                    return False
            except Exception:
                pass
            self._last_send_error = ""
            return True
        except Exception as exc:
            self._last_send_error = str(exc)
            return False
