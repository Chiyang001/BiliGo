"""抖音网页版私信 — Playwright 浏览器自动化（同步 API + 专用工作线程）。"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DOUYIN_HOME = 'https://www.douyin.com'
DOUYIN_MESSAGES = 'https://www.douyin.com/message'
SESSION_COOKIES = {'sessionid', 'sessionid_ss', 'sid_guard', 'sid_ucp_v1', 'sid_tt', 'ssid_ucp_v1'}
LOGIN_TIMEOUT = 300

AVATAR_URL_PATTERN = re.compile(
    r'"(?:avatarUrl|avatar_url)"\s*:\s*"(https://[^"]+)"',
    re.IGNORECASE,
)


def extract_avatar_from_storage(storage_path: str) -> str:
    """从 Playwright 保存的 storage 文件中提取头像 URL。"""
    if not storage_path or not os.path.exists(storage_path):
        return ''

    def _pick_avatar(obj: Any) -> str:
        if isinstance(obj, dict):
            for key in ('avatarUrl', 'avatar_url', 'avatar'):
                val = str(obj.get(key) or '').strip()
                if val.startswith('https://') and (
                    'douyinpic' in val or 'byteimg' in val or 'aweme-avatar' in val
                ):
                    return val
            thumb = obj.get('avatar_thumb')
            if isinstance(thumb, dict):
                urls = thumb.get('url_list') or []
                if urls and str(urls[0]).startswith('https://'):
                    return str(urls[0])
            for value in obj.values():
                found = _pick_avatar(value)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _pick_avatar(item)
                if found:
                    return found
        elif isinstance(obj, str):
            text = obj.strip()
            if text.startswith('{') or text.startswith('['):
                try:
                    return _pick_avatar(json.loads(text))
                except (json.JSONDecodeError, TypeError):
                    pass
        return ''

    try:
        with open(storage_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        avatar = _pick_avatar(state)
        if avatar:
            return avatar
        with open(storage_path, 'r', encoding='utf-8') as f:
            text = f.read()
        match = AVATAR_URL_PATTERN.search(text)
        if match:
            return match.group(1).replace('\\/', '/').strip()
    except Exception:
        pass
    return ''

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
"""

IM_FILL_AND_SEND_JS = """
(text) => {
  const isVisible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const isSearchBox = (el) => {
    const ph = (el.getAttribute('placeholder') || '') + (el.getAttribute('data-placeholder') || '');
    if (/搜索/.test(ph)) return true;
    return !!el.closest('[class*="search" i], [class*="Search" i]');
  };
  const editors = [...document.querySelectorAll(
    '.public-DraftEditor-content[contenteditable="true"], ' +
    '[contenteditable="true"][role="textbox"], ' +
    '[class*="DraftEditor"] [contenteditable="true"], ' +
    '[data-slate-editor="true"], ' +
    'textarea[placeholder*="发送"], ' +
    'textarea[placeholder*="消息"], ' +
    '[contenteditable="true"]'
  )].filter(el => isVisible(el) && !isSearchBox(el));
  const editor = editors[editors.length - 1];
  if (!editor) return { ok: false, reason: 'editor_not_found' };

  editor.focus();
  try {
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(editor);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand('delete', false, null);
  } catch (e) {}

  let filled = false;
  try {
    filled = document.execCommand('insertText', false, text);
  } catch (e) {}
  if (!filled) {
    try {
      editor.dispatchEvent(new InputEvent('beforeinput', {
        inputType: 'insertText', data: text, bubbles: true, cancelable: true
      }));
      if (editor.textContent !== text) editor.textContent = text;
      editor.dispatchEvent(new InputEvent('input', { bubbles: true, data: text }));
      filled = true;
    } catch (e) {}
  }
  if (!filled) return { ok: false, reason: 'fill_failed' };

  const enter = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
  editor.dispatchEvent(new KeyboardEvent('keydown', enter));
  editor.dispatchEvent(new KeyboardEvent('keypress', enter));
  editor.dispatchEvent(new KeyboardEvent('keyup', enter));
  return { ok: true, method: 'insertText+enter' };
}
"""

VERIFY_SENT_MESSAGE_JS = """
(text) => {
  const target = String(text || '').trim();
  if (!target) return false;
  const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim();
  const targetNorm = norm(target);

  const isSelfNode = (node) => {
    let el = node;
    for (let i = 0; i < 8 && el; i++) {
      const cls = (el.className || '').toString().toLowerCase();
      const style = window.getComputedStyle(el);
      if (/(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$)/.test(cls)) return true;
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
      el = el.parentElement;
    }
    const rect = node.getBoundingClientRect();
    return rect.left > window.innerWidth * 0.52;
  };

  const nodes = document.querySelectorAll(
    '[class*="message"], [class*="Message"], [class*="bubble"], [class*="Bubble"], ' +
    '[class*="im-message"], [class*="chat-item"], [class*="text-content"]'
  );
  const hits = [];
  for (const node of nodes) {
    const t = norm(node.innerText || '');
    if (!t || t.length > 800) continue;
    if (!t.includes(targetNorm) && targetNorm !== t) continue;
    hits.push({ t, is_self: isSelfNode(node) });
  }
  for (let i = hits.length - 1; i >= 0; i--) {
    if (hits[i].is_self && (hits[i].t === targetNorm || hits[i].t.includes(targetNorm))) return true;
  }
  return false;
}
"""

VERIFY_SENT_IN_PREVIEW_JS = """
([nickname, text]) => {
  const nick = String(nickname || '').trim();
  const target = String(text || '').trim();
  if (!nick || !target) return false;
  const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim();
  const targetNorm = norm(target);
  const timeRe = /^(刚刚|\\d{1,2}:\\d{2}|\\d+分钟前|\\d+小时前|\\d{4}[\\/\\-]\\d{1,2}[\\/\\-]\\d{1,2}|昨天|前天)$/;
  const isNoise = (l) => timeRe.test(l) || /^\\d{1,3}$/.test(l);

  const nodes = document.querySelectorAll(
    '[class*="conversation"], [class*="Conversation"], [class*="session"], [class*="Session"], ' +
    '[role="listitem"], li'
  );
  for (const node of nodes) {
    const lines = (node.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length || lines[0] !== nick) continue;
    const preview = lines.slice(1).filter(l => !isNoise(l)).join(' ').trim();
    if (preview && (preview === targetNorm || preview.includes(targetNorm))) return true;
  }
  return false;
}
"""

# A cleared editor is not proof that Douyin accepted a message.  In particular,
# the web client can clear/re-mount the Draft editor when an Enter event is
# swallowed.  Watch the chat DOM before submitting and only accept a *new*
# outgoing bubble containing this attempt's text.
START_SEND_WATCH_JS = """
([token, text]) => {
  const target = String(text || '').replace(/\\s+/g, ' ').trim();
  if (!target) return false;
  if (window.__biligoSendWatch && window.__biligoSendWatch.observer) {
    window.__biligoSendWatch.observer.disconnect();
  }

  const norm = (s) => String(s || '').replace(/\\s+/g, ' ').trim();
  const isEditorTree = (node) => {
    const el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    if (!el || !el.closest) return false;
    const selector = '[contenteditable="true"], [contenteditable="plaintext-only"], textarea, input';
    return !!el.closest(selector) || !!(el.querySelector && el.querySelector(selector));
  };
  const isSelfNode = (node) => {
    let el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    for (let i = 0; i < 8 && el; i++) {
      const cls = (el.className || '').toString().toLowerCase();
      const style = window.getComputedStyle(el);
      if (/(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$)/.test(cls)) return true;
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
      el = el.parentElement;
    }
    const base = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    if (!base || !base.getBoundingClientRect) return false;
    const rect = base.getBoundingClientRect();
    return rect.width > 0 && rect.left > window.innerWidth * 0.52;
  };
  const containsTarget = (node) => {
    let el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    for (let i = 0; i < 7 && el; i++, el = el.parentElement) {
      // Ignore the editor itself and all of its wrappers.  Typing the reply
      // must not satisfy the watcher before the message is submitted.
      if (isEditorTree(el)) continue;
      const value = norm(el.innerText || el.textContent || '');
      if (value && (value === target || value.includes(target)) && isSelfNode(el)) return true;
    }
    return false;
  };

  // MutationObserver may run before a newly inserted bubble has layout. In that
  // moment position-based direction detection can fail and no later mutation is
  // guaranteed. Keep a baseline and rescan after layout while Python polls.
  const matchingOutgoingCount = () => {
    const nodes = document.querySelectorAll(
      '[class*="message"], [class*="Message"], [class*="bubble"], [class*="Bubble"], ' +
      '[class*="im-message"], [class*="chat-item"], [class*="text-content"]'
    );
    let count = 0;
    for (const node of nodes) {
      if (isEditorTree(node)) continue;
      const value = norm(node.innerText || node.textContent || '');
      if (value && (value === target || value.includes(target)) && isSelfNode(node)) count += 1;
    }
    return count;
  };

  const watch = {
    token, target, seen: false, observer: null,
    baselineMatches: matchingOutgoingCount(),
    matchingOutgoingCount,
  };
  watch.observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (containsTarget(mutation.target)) {
        watch.seen = true;
        watch.observer.disconnect();
        return;
      }
      for (const node of mutation.addedNodes || []) {
        if (containsTarget(node)) {
          watch.seen = true;
          watch.observer.disconnect();
          return;
        }
      }
    }
  });
  watch.observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  window.__biligoSendWatch = watch;
  return true;
}
"""

CHECK_SEND_WATCH_JS = """
(token) => {
  const watch = window.__biligoSendWatch;
  if (!watch || watch.token !== token) return false;
  if (!watch.seen && typeof watch.matchingOutgoingCount === 'function') {
    try {
      watch.seen = watch.matchingOutgoingCount() > Number(watch.baselineMatches || 0);
      if (watch.seen && watch.observer) watch.observer.disconnect();
    } catch (e) {}
  }
  return !!watch.seen;
}
"""

OUTGOING_MESSAGE_COUNT_JS = """
() => {
  const roots = new Set();
  const nodes = document.querySelectorAll(
    '[class*="message" i], [class*="bubble" i], [class*="chat-item" i], ' +
    '[class*="contentBox" i], [data-message-id], [role="listitem"]'
  );
  const editors = [...document.querySelectorAll(
    '[contenteditable="true"], [contenteditable="plaintext-only"], ' +
    'textarea[placeholder*="发送"], textarea[placeholder*="消息"]'
  )].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8 && !el.closest('[class*="search" i]');
  });
  const editorRect = editors.length ? editors[editors.length - 1].getBoundingClientRect() : null;

  const isFromMe = (node) => {
    let el = node;
    for (let i = 0; i < 8 && el; i++, el = el.parentElement) {
      const cls = (el.className || '').toString().toLowerCase();
      if (/(isfromme|(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$))/.test(cls)) {
        return true;
      }
      const style = window.getComputedStyle(el);
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
    }
    const rect = node.getBoundingClientRect();
    const center = editorRect
      ? editorRect.left + editorRect.width * 0.55
      : window.innerWidth * 0.55;
    return rect.width > 0 && rect.left + rect.width / 2 > center;
  };

  for (const node of nodes) {
    if (node.closest('[contenteditable], textarea, [class*="search" i]')) continue;
    const rect = node.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8 || (editorRect && rect.top >= editorRect.top)) continue;
    if (!isFromMe(node)) continue;
    const root = node.closest(
      '[data-message-id], [class*="messageBox" i], [class*="bubble" i], ' +
      '[class*="chat-item" i], [role="listitem"]'
    ) || node;
    roots.add(root);
  }
  return roots.size;
}
"""

# Image messages have no stable text to verify.  Start watching before the file
# input is changed and only accept a newly-added image inside an outgoing message
# bubble.  This avoids relying solely on Douyin's frequently changing hashed
# class names (for example MessageBoxContentisFromMe).
START_IMAGE_SEND_WATCH_JS = """
(token) => {
  if (window.__biligoImageSendWatch && window.__biligoImageSendWatch.observer) {
    window.__biligoImageSendWatch.observer.disconnect();
  }

  const isVisible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return r.width >= 24 && r.height >= 24 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const editors = [...document.querySelectorAll(
    '[contenteditable="true"], [contenteditable="plaintext-only"], ' +
    'textarea[placeholder*="发送"], textarea[placeholder*="消息"]'
  )].filter(el => isVisible(el) && !el.closest('[class*="search" i]'));
  const editorRect = editors.length ? editors[editors.length - 1].getBoundingClientRect() : null;
  const mediaSelector = 'img, picture, canvas, [style*="background-image"], [class*="image" i]';
  const baseline = new WeakSet(document.querySelectorAll(mediaSelector));

  const messageRoot = (node) => node.closest && node.closest(
    '[data-message-id], [class*="messageBox" i], [class*="message-item" i], ' +
    '[class*="bubble" i], [class*="chat-item" i], [role="listitem"]'
  );
  const isFromMe = (node) => {
    let el = node;
    for (let i = 0; i < 9 && el; i++, el = el.parentElement) {
      const cls = (el.className || '').toString().toLowerCase();
      if (/(isfromme|(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$))/.test(cls)) {
        return true;
      }
      const style = window.getComputedStyle(el);
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
    }
    const r = node.getBoundingClientRect();
    const center = editorRect
      ? editorRect.left + editorRect.width * 0.55
      : window.innerWidth * 0.55;
    return r.left + r.width / 2 > center;
  };
  const isNewOutgoingMedia = (media) => {
    if (!media || baseline.has(media) || !isVisible(media)) return false;
    if (media.closest('[contenteditable], textarea, button, [class*="search" i]')) return false;
    const root = messageRoot(media);
    if (!root || !isVisible(root)) return false;
    const rect = root.getBoundingClientRect();
    if (editorRect && rect.top >= editorRect.top) return false;
    return isFromMe(root);
  };
  const inspect = (node) => {
    const el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    if (!el) return false;
    if (el.matches && el.matches(mediaSelector) && isNewOutgoingMedia(el)) return true;
    if (!el.querySelectorAll) return false;
    return [...el.querySelectorAll(mediaSelector)].some(isNewOutgoingMedia);
  };

  const watch = { token, seen: false, observer: null };
  watch.observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (inspect(mutation.target) || [...(mutation.addedNodes || [])].some(inspect)) {
        watch.seen = true;
        watch.observer.disconnect();
        return;
      }
    }
  });
  watch.observer.observe(document.body, {
    childList: true, subtree: true, attributes: true,
    attributeFilter: ['src', 'style', 'class'],
  });
  window.__biligoImageSendWatch = watch;
  return true;
}
"""

CHECK_IMAGE_SEND_WATCH_JS = """
(token) => {
  const watch = window.__biligoImageSendWatch;
  return !!(watch && watch.token === token && watch.seen);
}
"""

# 仅统计聊天消息区里已出现的己方图片气泡，排除输入框/上传预览/toolbar 里的 img。
OUTGOING_CHAT_IMAGE_COUNT_JS = """
() => {
  const isVisible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return r.width >= 24 && r.height >= 24
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const editors = [...document.querySelectorAll(
    '[contenteditable="true"], [contenteditable="plaintext-only"], ' +
    'textarea[placeholder*="发送"], textarea[placeholder*="消息"]'
  )].filter(el => isVisible(el) && !el.closest('[class*="search" i]'));
  const editorRect = editors.length ? editors[editors.length - 1].getBoundingClientRect() : null;

  const isStaging = (el) => !!el.closest(
    '[contenteditable="true"], textarea, input[type="file"], button, ' +
    '[class*="MsgInput" i], [class*="msg-input" i], [class*="msginput" i], ' +
    '[class*="upload" i], [class*="toolbar" i], [class*="draft" i], ' +
    '[class*="editor" i], [class*="preview" i], [class*="action" i]'
  );

  const messageRoot = (node) => node.closest && node.closest(
    '[data-message-id], [class*="messageBox" i], [class*="message-item" i], ' +
    '[class*="bubble" i], [class*="chat-item" i], [role="listitem"]'
  );

  const isFromMe = (node) => {
    let el = node;
    for (let i = 0; i < 9 && el; i++, el = el.parentElement) {
      const cls = (el.className || '').toString().toLowerCase();
      if (/(isfromme|(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$))/.test(cls)) {
        return true;
      }
      const style = window.getComputedStyle(el);
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
    }
    const r = node.getBoundingClientRect();
    const center = editorRect
      ? editorRect.left + editorRect.width * 0.55
      : window.innerWidth * 0.55;
    return r.left + r.width / 2 > center;
  };

  const roots = new Set();
  for (const media of document.querySelectorAll('img, picture img, canvas')) {
    if (!isVisible(media) || isStaging(media)) continue;
    const w = media.naturalWidth || media.width || media.getBoundingClientRect().width;
    const h = media.naturalHeight || media.height || media.getBoundingClientRect().height;
    if (w < 48 || h < 48) continue;
    const root = messageRoot(media);
    if (!root || !isVisible(root) || !isFromMe(root)) continue;
    const rect = root.getBoundingClientRect();
    if (editorRect && rect.top >= editorRect.top - 6) continue;
    roots.add(root);
  }
  return roots.size;
}
"""

NEWEST_OUTGOING_CHAT_IMAGE_SRC_JS = """
() => {
  const isVisible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return r.width >= 24 && r.height >= 24
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const editors = [...document.querySelectorAll(
    '[contenteditable="true"], [contenteditable="plaintext-only"], ' +
    'textarea[placeholder*="发送"], textarea[placeholder*="消息"]'
  )].filter(el => isVisible(el) && !el.closest('[class*="search" i]'));
  const editorRect = editors.length ? editors[editors.length - 1].getBoundingClientRect() : null;
  const isStaging = (el) => !!el.closest(
    '[contenteditable="true"], textarea, input[type="file"], button, ' +
    '[class*="MsgInput" i], [class*="msg-input" i], [class*="msginput" i], ' +
    '[class*="upload" i], [class*="toolbar" i], [class*="draft" i], ' +
    '[class*="editor" i], [class*="preview" i], [class*="action" i]'
  );
  const messageRoot = (node) => node.closest && node.closest(
    '[data-message-id], [class*="messageBox" i], [class*="message-item" i], ' +
    '[class*="bubble" i], [class*="chat-item" i], [role="listitem"]'
  );
  const isFromMe = (node) => {
    let el = node;
    for (let i = 0; i < 9 && el; i++, el = el.parentElement) {
      const cls = (el.className || '').toString().toLowerCase();
      if (/(isfromme|(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$))/.test(cls)) {
        return true;
      }
      const style = window.getComputedStyle(el);
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
    }
    const r = node.getBoundingClientRect();
    const center = editorRect
      ? editorRect.left + editorRect.width * 0.55
      : window.innerWidth * 0.55;
    return r.left + r.width / 2 > center;
  };

  let newest = null;
  let newestTop = -1;
  for (const media of document.querySelectorAll('img, picture img, canvas')) {
    if (!isVisible(media) || isStaging(media)) continue;
    const w = media.naturalWidth || media.width || media.getBoundingClientRect().width;
    const h = media.naturalHeight || media.height || media.getBoundingClientRect().height;
    if (w < 48 || h < 48) continue;
    const root = messageRoot(media);
    if (!root || !isVisible(root) || !isFromMe(root)) continue;
    const rect = root.getBoundingClientRect();
    if (editorRect && rect.top >= editorRect.top - 6) continue;
    if (rect.top > newestTop) {
      newestTop = rect.top;
      newest = media;
    }
  }
  if (!newest) return '';
  return String(newest.currentSrc || newest.src || '').trim();
}
"""

OUTGOING_CHAT_IMAGE_SIGNATURES_JS = """
() => {
  const isVisible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return r.width >= 24 && r.height >= 24
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const editors = [...document.querySelectorAll(
    '[contenteditable="true"], [contenteditable="plaintext-only"], ' +
    'textarea[placeholder*="发送"], textarea[placeholder*="消息"]'
  )].filter(el => isVisible(el) && !el.closest('[class*="search" i]'));
  const editorRect = editors.length ? editors[editors.length - 1].getBoundingClientRect() : null;
  const isStaging = (el) => !!el.closest(
    '[contenteditable="true"], textarea, input[type="file"], button, ' +
    '[class*="MsgInput" i], [class*="msg-input" i], [class*="msginput" i], ' +
    '[class*="upload" i], [class*="toolbar" i], [class*="draft" i], ' +
    '[class*="editor" i], [class*="preview" i], [class*="action" i]'
  );
  const messageRoot = (node) => node.closest && node.closest(
    '[data-message-id], [class*="messageBox" i], [class*="message-item" i], ' +
    '[class*="bubble" i], [class*="chat-item" i], [role="listitem"]'
  );
  const isFromMe = (node) => {
    let el = node;
    for (let i = 0; i < 9 && el; i++, el = el.parentElement) {
      const cls = (el.className || '').toString().toLowerCase();
      if (/(isfromme|(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$))/.test(cls)) {
        return true;
      }
      const style = window.getComputedStyle(el);
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
    }
    const r = node.getBoundingClientRect();
    const center = editorRect
      ? editorRect.left + editorRect.width * 0.55
      : window.innerWidth * 0.55;
    return r.left + r.width / 2 > center;
  };

  const sigs = [];
  for (const media of document.querySelectorAll('img, picture img, canvas')) {
    if (!isVisible(media) || isStaging(media)) continue;
    const w = media.naturalWidth || media.width || media.getBoundingClientRect().width;
    const h = media.naturalHeight || media.height || media.getBoundingClientRect().height;
    if (w < 48 || h < 48) continue;
    const root = messageRoot(media);
    if (!root || !isVisible(root) || !isFromMe(root)) continue;
    const rect = root.getBoundingClientRect();
    if (editorRect && rect.top >= editorRect.top - 6) continue;
    const src = String(media.currentSrc || media.src || '').trim();
    if (!src || src.startsWith('blob:')) continue;
    sigs.push(src.slice(0, 160));
  }
  return sigs;
}
"""

CLICK_IMAGE_PREVIEW_SEND_JS = """
() => {
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return r.width > 8 && r.height > 8 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const panels = [...document.querySelectorAll('div, section, aside')].filter(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 120 || r.height < 80) return false;
    const hasPreviewImg = [...el.querySelectorAll('img')].some(img => {
      const ir = img.getBoundingClientRect();
      return ir.width >= 72 && ir.height >= 72;
    });
    const text = (el.innerText || '').slice(0, 80);
    return hasPreviewImg && /发送|确定/.test(text);
  });
  panels.sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    return (rb.width * rb.height) - (ra.width * ra.height);
  });
  for (const panel of panels) {
    const btns = [...panel.querySelectorAll('button, [role="button"], div, span')].filter(el => {
      if (!isVisible(el)) return false;
      const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
      return t === '发送' || t === '确定' || t === '确认发送';
    });
    if (btns.length) {
      btns[btns.length - 1].click();
      return true;
    }
  }
  return false;
}
"""

CLICK_IMAGE_SEND_CONFIRM_JS = """
() => {
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return r.width > 8 && r.height > 8 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const labels = ['发送', '确认发送', '确定', '发送图片'];
  const candidates = [...document.querySelectorAll(
    'button, [role="button"], [data-apm-action*="发送"], div, span'
  )].filter(el => {
    if (!isVisible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    if (!text) return false;
    return labels.some(label => text === label || text.includes(label));
  });
  // 优先点击预览/弹层里靠后的发送按钮，避免误触顶部导航。
  const target = candidates[candidates.length - 1];
  if (!target) return false;
  target.click();
  return true;
}
"""

VERIFY_IMAGE_SENT_IN_PREVIEW_JS = """
(args) => {
  const [nickname, previousPreview] = args || [];
  const nick = String(nickname || '').trim();
  const prev = String(previousPreview || '').replace(/\\s+/g, ' ').trim();
  if (!nick || !prev) return false;
  const imageRe = /(^|[\\[【（(\\s])图片([\\]】）)\\s]|$)|发送了一张图片|发来一张图片|\\[图片\\]/;
  const hasImage = (p) => imageRe.test(String(p || '').replace(/\\s+/g, ' ').trim());
  const nodes = document.querySelectorAll(
    '[class*="conversation" i], [class*="session" i], [role="listitem"], li'
  );
  for (const node of nodes) {
    const lines = (node.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length || lines[0] !== nick) continue;
    const preview = lines.slice(1).join(' ').replace(/\\s+/g, ' ').trim();
    if (!preview || preview === prev) continue;
    if (!hasImage(preview)) continue;
    return true;
  }
  return false;
}
"""

GET_CONVERSATION_PREVIEW_JS = """
(nickname) => {
  const nick = String(nickname || '').trim();
  if (!nick) return '';
  const nodes = document.querySelectorAll(
    '[class*="conversation" i], [class*="session" i], [role="listitem"], li'
  );
  for (const node of nodes) {
    const lines = (node.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    if (lines.length && lines[0] === nick) return lines.slice(1).join(' ');
  }
  return '';
}
"""

WAIT_FOR_CHAT_EDITOR_JS = """
() => {
  const isVisible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const isSearchBox = (el) => {
    const ph = (el.getAttribute('placeholder') || '') + (el.getAttribute('data-placeholder') || '');
    if (/搜索/.test(ph)) return true;
    return !!el.closest('[class*="search" i], [class*="Search" i]');
  };
  const editors = [...document.querySelectorAll(
    '.public-DraftEditor-content[contenteditable="true"], ' +
    '[contenteditable="true"][role="textbox"], ' +
    '[class*="DraftEditor"] [contenteditable="true"], ' +
    '[data-slate-editor="true"], ' +
    'textarea[placeholder*="发送"], ' +
    'textarea[placeholder*="消息"], ' +
    'div[class*="editor" i][contenteditable], ' +
    '[contenteditable="true"], [contenteditable="plaintext-only"]'
  )].filter(el => isVisible(el) && !isSearchBox(el));
  if (editors.length > 0) return true;
  for (const frame of document.querySelectorAll('iframe')) {
    try {
      const doc = frame.contentDocument;
      if (!doc) continue;
      const inner = [...doc.querySelectorAll('[contenteditable="true"], textarea, [role="textbox"]')]
        .filter(el => isVisible(el));
      if (inner.length) return true;
    } catch (e) {}
  }
  return false;
}
"""

FOCUS_CHAT_EDITOR_JS = """
() => {
  const isVisible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const isSearchBox = (el) => {
    const ph = (el.getAttribute('placeholder') || '') + (el.getAttribute('data-placeholder') || '');
    if (/搜索/.test(ph)) return true;
    return !!el.closest('[class*="search" i], [class*="Search" i]');
  };
  const editors = [...document.querySelectorAll(
    '.public-DraftEditor-content[contenteditable="true"], ' +
    '[contenteditable="true"][role="textbox"], ' +
    '[class*="DraftEditor"] [contenteditable="true"], ' +
    '[data-slate-editor="true"], ' +
    'textarea[placeholder*="发送"], ' +
    'textarea[placeholder*="消息"], ' +
    'div[class*="editor" i][contenteditable], ' +
    '[contenteditable="true"], [contenteditable="plaintext-only"]'
  )].filter(el => isVisible(el) && !isSearchBox(el));
  const editor = editors[editors.length - 1];
  if (!editor) return false;
  editor.focus();
  return true;
}
"""

CHAT_EDITOR_STATE_JS = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const editors = [...document.querySelectorAll(
    '.public-DraftEditor-content[contenteditable="true"], ' +
    '[contenteditable="true"][role="textbox"], ' +
    '[class*="DraftEditor"] [contenteditable="true"], ' +
    '[contenteditable="true"]'
  )].filter(el => visible(el) && !el.closest('[class*="search" i], [class*="Search" i]'));
  const editor = editors[editors.length - 1];
  if (!editor) return { found: false, empty: false };
  const text = String(editor.innerText || editor.textContent || '').replace(/\u200b/g, '').trim();
  return { found: true, empty: !text, text };
}
"""

CLICK_CHAT_SEND_JS = """
() => {
  const nodes = [...document.querySelectorAll('button, [role="button"], div, span')];
  for (const node of nodes) {
    const text = (node.innerText || '').trim();
    const aria = (node.getAttribute('aria-label') || '').trim();
    if (text !== '发送' && aria !== '发送') continue;
    const r = node.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.bottom < 0 || r.top > window.innerHeight) continue;
    node.click();
    return true;
  }
  return false;
}
"""


EXTRACT_PANEL_CONVERSATIONS_JS = """
() => {
  const skipTexts = new Set(['消息', '搜索', '下载', '下载客户端', '实时接收', '投稿', '通知', '充钻石', '客户端', '壁纸']);
  const timeRe = /^(刚刚|\\d{1,2}:\\d{2}|\\d+分钟前|\\d+小时前|\\d{4}[\\/\\-]\\d{1,2}[\\/\\-]\\d{1,2}|昨天|前天)$/;

  const isVisible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
  };

  const hasUnreadDot = (el) => {
    if (!el) return false;
    const candidates = el.querySelectorAll('span, div, i, [class*="dot" i], [class*="badge" i], [class*="unread" i]');
    for (const node of candidates) {
      const r = node.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || r.width > 32 || r.height > 32) continue;
      const s = window.getComputedStyle(node);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') continue;
      const cls = (node.className || '').toString().toLowerCase();
      const text = (node.innerText || '').trim();
      const red = /rgb\\(254|rgb\\(255, 44|rgb\\(254, 44|#fe2c55|#ff2c55/i.test(
        (s.backgroundColor || '') + cls
      );
      if (red || cls.includes('unread') || (/badge|dot/.test(cls) && /^\\d{0,3}$/.test(text))) {
        return true;
      }
    }
    return false;
  };

  const isNoiseLine = (l) => timeRe.test(l) || /^\\d{1,3}$/.test(l);

  const parseRow = (node) => {
    const text = (node.innerText || '').trim();
    if (!text || text.length < 2 || text.length > 400) return null;
    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length) return null;
    const title = lines[0];
    if (skipTexts.has(title) || title.length > 40) return null;

    // “刚刚”只表示时间，己方刚发送的消息同样会出现，不能作为未读依据。
    let unread = hasUnreadDot(node) ? 1 : 0;
    let lastMessage = '';
    let senderNick = '';
    let category = 'friend';
    let nickname = title;

    if (title.includes('陌生人消息')) {
      category = 'stranger_folder';
      nickname = '陌生人消息';
      for (const line of lines.slice(1)) {
        if (line.includes(':') && !line.includes('陌生人')) {
          const idx = line.indexOf(':');
          senderNick = line.slice(0, idx).trim();
          lastMessage = line.slice(idx + 1).trim();
          break;
        }
      }
      return {
        conv_id: 'stranger_folder',
        nickname,
        category,
        sender_nickname: senderNick,
        last_message: lastMessage,
        unread,
      };
    }

    const bodyLines = lines.slice(1).filter(l => !isNoiseLine(l));
    lastMessage = bodyLines.join(' ').trim();
    if (!lastMessage) return null;
    if (lastMessage.includes(':') && category === 'friend') {
      const idx = lastMessage.indexOf(':');
      const maybeNick = lastMessage.slice(0, idx).trim();
      if (maybeNick.length <= 20) {
        senderNick = maybeNick;
        lastMessage = lastMessage.slice(idx + 1).trim();
      }
    }
    if (!lastMessage) return null;

    return {
      conv_id: category + ':' + nickname,
      nickname,
      category,
      sender_nickname: senderNick,
      last_message: lastMessage,
      unread,
    };
  };

  const items = [];
  const seen = new Set();
  const selectors = [
    '[class*="conversation"]',
    '[class*="Conversation"]',
    '[class*="session"]',
    '[class*="Session"]',
    '[class*="list"] [class*="item"]',
    '[class*="List"] [class*="Item"]',
    '[role="listitem"]',
    'li',
  ];
  const nodes = new Set();
  for (const sel of selectors) {
    document.querySelectorAll(sel).forEach(n => { if (isVisible(n)) nodes.add(n); });
  }

  for (const node of nodes) {
    const item = parseRow(node);
    if (!item) continue;
    const key = item.category + '|' + item.nickname + '|' + (item.sender_nickname || '');
    if (seen.has(key)) continue;
    seen.add(key);
    items.push(item);
  }
  return items;
}
"""

FIND_IM_PANEL_ROOT_JS = """
() => {
  const countRows = (root) => {
    const skip = new Set(['消息', '搜索', '下载', '下载客户端', '实时接收', '投稿', '通知']);
    let n = 0;
    const sels = [
      '[class*="conversation"]', '[class*="Conversation"]',
      '[class*="session"]', '[class*="Session"]',
      '[role="listitem"]',
    ];
    for (const sel of sels) {
      root.querySelectorAll(sel).forEach(node => {
        const lines = (node.innerText || '').trim().split('\\n').map(s => s.trim()).filter(Boolean);
        if (lines.length >= 2 && !skip.has(lines[0]) && lines[0].length <= 40) n++;
      });
    }
    return n;
  };
  if (location.pathname.includes('/message')) {
    const rows = countRows(document.body);
    return { found: rows > 0, onMessagePage: true, rowCount: rows };
  }
  const panels = [...document.querySelectorAll('div, section, aside')].filter(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 280 || r.height < 320 || r.height > window.innerHeight) return false;
    if (r.right < window.innerWidth * 0.42) return false;
    const hasSearch = !!el.querySelector('input[placeholder*="搜索"], input[type="search"]');
    const text = (el.innerText || '').slice(0, 300);
    return hasSearch || text.includes('消息');
  });
  panels.sort((a, b) => {
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    return (rb.width * rb.height) - (ra.width * ra.height);
  });
  for (const panel of panels) {
    const rows = countRows(panel);
    if (rows > 0) return { found: true, onMessagePage: false, rowCount: rows };
  }
  return { found: false, onMessagePage: false, rowCount: 0 };
}
"""

CLICK_CONVERSATION_ROW_JS = """
(title) => {
  const skipTexts = new Set(['消息', '搜索', '下载', '下载客户端', '实时接收', '投稿', '通知', '充钻石', '客户端', '壁纸']);
  const isVisible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
  };
  const findRoot = () => {
    if (location.pathname.includes('/message')) return document.body;
    const panels = [...document.querySelectorAll('div, section, aside')].filter(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 280 || r.height < 320) return false;
      if (r.right < window.innerWidth * 0.42) return false;
      const hasSearch = !!el.querySelector('input[placeholder*="搜索"], input[type="search"]');
      const text = (el.innerText || '').slice(0, 300);
      return hasSearch || text.includes('消息');
    });
    panels.sort((a, b) => {
      const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      return (rb.width * rb.height) - (ra.width * ra.height);
    });
    return panels[0] || document.body;
  };
  const root = findRoot();
  const selectors = [
    '[class*="conversation"]',
    '[class*="Conversation"]',
    '[class*="session"]',
    '[class*="Session"]',
    '[class*="list"] [class*="item"]',
    '[class*="List"] [class*="Item"]',
    '[role="listitem"]',
  ];
  const nodes = new Set();
  for (const sel of selectors) {
    root.querySelectorAll(sel).forEach(n => { if (isVisible(n)) nodes.add(n); });
  }
  const candidates = [];
  for (const node of nodes) {
    const text = (node.innerText || '').trim();
    if (!text || text.length < 2) continue;
    const first = text.split('\\n')[0].trim();
    if (first !== title || skipTexts.has(first)) continue;
    const r = node.getBoundingClientRect();
    if (r.height < 34 || r.height > 180 || r.width < 120) continue;
    const cls = String(node.className || '');
    const style = window.getComputedStyle(node);
    let score = 0;
    if (/conversation|session|message.*item|chat.*item/i.test(cls)) score += 10;
    if (node.getAttribute('role') === 'listitem') score += 8;
    if (style.cursor === 'pointer') score += 5;
    if (node.querySelector('img')) score += 4;
    if (text.split('\\n').filter(Boolean).length >= 2) score += 3;
    score -= Math.min(r.height, 180) / 1000;
    candidates.push({ node, r, score });
  }
  const exactNodes = [...root.querySelectorAll('span, p, div, strong')].filter(node => {
    if (!isVisible(node)) return false;
    const own = (node.innerText || '').trim();
    if (own !== title) return false;
    return ![...node.children].some(child => (child.innerText || '').trim() === title);
  });
  for (const leaf of exactNodes) {
    let node = leaf;
    for (let depth = 0; node && node !== root && depth < 8; depth++, node = node.parentElement) {
      const r = node.getBoundingClientRect();
      if (r.height < 42 || r.height > 150 || r.width < 160 || r.width > 620) continue;
      const text = (node.innerText || '').trim();
      const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
      if (!lines.length || lines[0] !== title) continue;
      const cls = String(node.className || '');
      const style = window.getComputedStyle(node);
      let score = 2;
      if (/conversation|session|message.*item|chat.*item/i.test(cls)) score += 10;
      if (node.getAttribute('role') === 'listitem') score += 8;
      if (style.cursor === 'pointer') score += 5;
      if (node.querySelector('img')) score += 5;
      if (lines.length >= 2) score += 4;
      score -= Math.min(r.height, 150) / 1000;
      candidates.push({ node, r, score });
    }
  }
  candidates.sort((a, b) => b.score - a.score || (a.r.width * a.r.height) - (b.r.width * b.r.height));
  const best = candidates[0];
  if (!best) return { found: false, candidateCount: 0, exactTextCount: exactNodes.length };
  const r = best.node.getBoundingClientRect();
  return {
    found: true,
    x: Math.max(r.left + 8, Math.min(r.right - 8, r.left + r.width * 0.55)),
    y: r.top + r.height * 0.5,
    width: Math.round(r.width),
    height: Math.round(r.height),
    score: Math.round(best.score * 10) / 10,
    candidateCount: candidates.length,
    exactTextCount: exactNodes.length,
    tag: best.node.tagName,
    className: String(best.node.className || '').slice(0, 100),
  };
}
"""

EXTRACT_STRANGER_CHATS_JS = """
() => {
  const skip = new Set(['陌生人消息', '消息', '搜索', '返回']);
  const timeRe = /^(刚刚|\\d{1,2}:\\d{2}|\\d+分钟前|\\d+小时前|\\d{4}[\\/\\-]\\d{1,2}[\\/\\-]\\d{1,2})$/;
  const items = [];
  const seen = new Set();
  const nodes = document.querySelectorAll('[class*="item"], [class*="Item"], [role="listitem"], li');

  for (const node of nodes) {
    const text = (node.innerText || '').trim();
    if (!text || text.length < 2 || text.length > 300) continue;
    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length) continue;
    const nickname = lines[0];
    if (skip.has(nickname) || nickname.includes('陌生人消息')) continue;
    if (seen.has(nickname)) continue;

    let lastMessage = '';
    const body = lines.slice(1).filter(l => !timeRe.test(l) && !/^\\d{1,3}$/.test(l));
    lastMessage = body.join(' ').trim();
    if (!lastMessage) continue;

    seen.add(nickname);
    items.push({
      conv_id: 'stranger:' + nickname,
      nickname,
      category: 'stranger',
      sender_nickname: nickname,
      last_message: lastMessage,
      unread: text.includes('刚刚') ? 1 : 0,
    });
  }
  return items;
}
"""

EXTRACT_CHAT_MESSAGES_JS = """
(limit) => {
  const max = Math.max(1, limit || 20);
  const out = [];
  const seen = new Set();

  const roots = [
    document.querySelector('[class*="chat-main"]'),
    document.querySelector('[class*="ChatMain"]'),
    document.querySelector('[class*="message-list"]'),
    document.querySelector('[class*="MessageList"]'),
    document.querySelector('[class*="im-chat"]'),
    document.body,
  ].filter(Boolean);

  const isSelfNode = (node) => {
    let el = node;
    for (let i = 0; i < 6 && el; i++) {
      const cls = (el.className || '').toString().toLowerCase();
      const style = window.getComputedStyle(el);
      if (/(^|[\\s_-])(self|mine|sent|outgoing|right|message-send)([\\s_-]|$)/.test(cls)) return true;
      if (style.textAlign === 'right' || style.justifyContent === 'flex-end') return true;
      el = el.parentElement;
    }
    const rect = node.getBoundingClientRect();
    return rect.left > window.innerWidth * 0.55;
  };

  for (const root of roots) {
    const nodes = root.querySelectorAll(
      '[class*="message"], [class*="Message"], [class*="bubble"], [class*="Bubble"], [class*="text"], [class*="content"]'
    );
    for (const node of nodes) {
      const text = (node.innerText || '').trim();
      if (!text || text.length > 800 || text.length < 1) continue;
      if (/^(发送|搜索|消息|陌生人消息|下载)$/i.test(text)) continue;
      const self = isSelfNode(node);
      const key = text.slice(0, 120) + '|' + (self ? 'self' : 'peer');
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ text, is_self: self });
    }
    if (out.length >= 3) break;
  }
  return out.slice(-max);
}
"""


@dataclass
class DouyinAccountInfo:
    uid: str = ''
    nickname: str = ''
    avatar: str = ''
    sec_uid: str = ''

    def to_dict(self) -> Dict[str, str]:
        return {
            'uid': self.uid,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'sec_uid': self.sec_uid,
        }


@dataclass
class DouyinConversation:
    conv_id: str
    nickname: str
    last_message: str = ''
    unread: int = 0
    category: str = 'friend'  # friend | stranger
    sender_nickname: str = ''
    sender_id: str = ''
    message_id: str = ''
    last_msg_time: int = 0
    max_store_id: int = 0
    update_time: int = 0


@dataclass
class DouyinMessage:
    conv_id: str
    nickname: str
    text: str
    is_self: bool
    timestamp: int = 0


class DouyinBrowserWorker:
    """在单一线程内运行 Playwright，避免跨线程调用问题。"""

    PROFILE_DIR_NAME = 'douyin_browser_profile'

    def __init__(self, storage_path: str, headless: bool = True):
        self.storage_path = storage_path
        self.headless = headless
        self._current_headless: Optional[bool] = None
        self._abort = False
        self._queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        # start_worker can be reached concurrently from a Flask status request,
        # a background session verifier and the monitor loop.  Without a
        # lifecycle lock two owner threads may be created and one of them can
        # pick up the other thread's sync_playwright instance/greenlet.
        self._lifecycle_lock = threading.RLock()
        self._ready = threading.Event()
        self._owner_thread_id: Optional[int] = None
        self._running = False
        self._playwright = None
        self._context = None
        self._page = None
        self._account = DouyinAccountInfo()
        self._api_conversations: Dict[str, Dict[str, Any]] = {}
        self._api_messages: Dict[str, List[Dict[str, Any]]] = {}
        self._messages_panel_ready = False
        self._conversation_open = False
        self._last_send_error = ''
        self._last_conversation_click_debug = ''
        self._last_open_error = ''

    def start_worker(self) -> None:
        with self._lifecycle_lock:
            if self._thread and self._thread.is_alive():
                return
            # Jobs left behind by a terminated owner belong to that lifecycle
            # and must never be executed by a newly-created Playwright thread.
            self._queue = queue.Queue()
            self._running = True
            self._ready.clear()
            owner = threading.Thread(target=self._worker_main, daemon=True)
            self._thread = owner
            owner.start()
            self._ready.wait(timeout=10)
            # Let Playwright's sync dispatcher finish its initial handshake
            # before callers can immediately request shutdown.
            if self._ready.is_set() and self._running and owner.is_alive():
                time.sleep(0.1)

    def stop_worker(self) -> None:
        if self._thread is threading.current_thread():
            self._running = False
            return
        with self._lifecycle_lock:
            self._running = False
            try:
                self._queue.put({'op': 'shutdown'})
            except Exception:
                pass
            owner = self._thread
            if owner and owner.is_alive():
                owner.join(timeout=30)
                if owner.is_alive():
                    logger.warning('Playwright 工作线程未能在 30 秒内退出，继续保留线程引用')
                elif self._thread is owner:
                    self._thread = None

    def _call(self, op: str, timeout: float = 120, **kwargs) -> Any:
        # Playwright's sync API is thread-affine. Avoid queueing a nested call
        # when a handler invokes a public worker method from its owner thread.
        if self._thread is threading.current_thread() and self._running:
            result = self._dispatch(op, **kwargs)
            if isinstance(result, dict) and result.get('error'):
                raise RuntimeError(result['error'])
            return result
        if not self._thread or not self._thread.is_alive():
            self.start_worker()
        resp_q: queue.Queue = queue.Queue()
        cancelled = threading.Event()
        self._queue.put({
            'op': op,
            'kwargs': kwargs,
            'resp_q': resp_q,
            'cancelled': cancelled,
        })
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                cancelled.set()
                if op in ('send_text', 'send_image'):
                    self._abort = True
                raise TimeoutError(f'抖音浏览器操作超时: {op}')
            try:
                result = resp_q.get(timeout=min(0.5, remaining))
                break
            except queue.Empty:
                # A fatal Playwright/greenlet failure can end the owner thread
                # without ever writing a response. Detect it promptly so the
                # monitoring loop can create a fresh worker on its next attempt.
                if not self._thread or not self._thread.is_alive():
                    cancelled.set()
                    raise RuntimeError(f'抖音浏览器工作线程已退出: {op}')
        if isinstance(result, dict) and result.get('error'):
            raise RuntimeError(result['error'])
        return result

    def set_headless(self, headless: bool) -> None:
        self.headless = bool(headless)

    def set_account_identity(self, uid: str = '', nickname: str = '') -> None:
        """注入已登录账号身份，供接口消息缺少显式方向字段时比对发送者。"""
        if uid:
            self._account.uid = str(uid).strip()
        if nickname:
            self._account.nickname = str(nickname).strip()

    def set_abort(self, abort: bool = True) -> None:
        self._abort = abort

    def restart_browser(self, headless: Optional[bool] = None) -> None:
        if headless is not None:
            self.headless = bool(headless)
        try:
            self._call('restart_browser', timeout=25)
        except Exception:
            pass

    def check_session_valid(self) -> bool:
        try:
            return bool(self._call('check_session', timeout=45))
        except Exception:
            return False

    def open_login_window(self) -> Dict[str, Any]:
        self.headless = False
        return self._call('open_login', timeout=LOGIN_TIMEOUT + 30)

    def wait_until_logged_in(self, timeout: int = LOGIN_TIMEOUT) -> DouyinAccountInfo:
        data = self._call('wait_login', timeout=timeout + 30, login_timeout=timeout)
        self._account = DouyinAccountInfo(**data)
        return self._account

    def get_account(self) -> DouyinAccountInfo:
        data = self._call('get_account', timeout=30)
        self._account = DouyinAccountInfo(**data)
        return self._account

    def save_session(self) -> None:
        self._call('save_session', timeout=30)

    def warmup_messages(self) -> None:
        """预加载消息页，缩短启动监控时的等待。"""
        try:
            self._call('warmup_messages', timeout=25)
        except Exception:
            pass

    def navigate_messages(self) -> None:
        self._call('navigate_messages', timeout=60)

    def list_conversations(self, quick: bool = False, skip_stranger: bool = False) -> List[DouyinConversation]:
        timeout = 35 if quick else 60
        rows = self._call(
            'list_conversations', timeout=timeout, quick=quick, skip_stranger=skip_stranger,
        ) or []
        result = []
        for row in rows:
            try:
                result.append(DouyinConversation(**row))
            except TypeError:
                result.append(DouyinConversation(
                    conv_id=str(row.get('conv_id', '')),
                    nickname=str(row.get('nickname', '')),
                    last_message=str(row.get('last_message', '')),
                    unread=int(row.get('unread') or 0),
                    category=str(row.get('category') or 'friend'),
                    sender_nickname=str(row.get('sender_nickname') or ''),
                    sender_id=str(row.get('sender_id') or ''),
                    message_id=str(row.get('message_id') or ''),
                    last_msg_time=int(row.get('last_msg_time') or 0),
                    max_store_id=int(row.get('max_store_id') or 0),
                    update_time=int(row.get('update_time') or 0),
                ))
        return result

    def open_conversation(self, nickname: str) -> bool:
        return bool(self._call('open_conversation', timeout=45, nickname=nickname))

    def read_latest_incoming(
        self, conv_id: str, nickname: str, category: str = 'friend', sender_nickname: str = ''
    ) -> Optional[DouyinMessage]:
        """兼容旧调用；现在返回会话中的最新一条消息，并保留真实收发方向。"""
        data = self._call(
            'read_latest_message', timeout=35,
            conv_id=conv_id, nickname=nickname,
            category=category, sender_nickname=sender_nickname,
        )
        if not data:
            return None
        # 平台 Worker 可以附带 message_id 等用于列表去重的扩展元数据，
        # DouyinMessage 只接收监控循环真正需要的公共字段。显式归一化可避免
        # 某个平台增加字段后让整个监控循环持续抛 TypeError。
        return DouyinMessage(
            conv_id=str(data.get('conv_id') or conv_id or nickname),
            nickname=str(data.get('nickname') or nickname),
            text=str(data.get('text') or ''),
            is_self=bool(data.get('is_self')),
            timestamp=int(data.get('timestamp') or 0),
        )

    def send_text(
        self, nickname: str, text: str, category: str = 'friend', from_panel: bool = False,
        conversation_open: bool = False,
    ) -> bool:
        return bool(self._call(
            # Opening a stale message panel may include one navigation recovery.
            # Keep the caller deadline above that valid recovery path.
            'send_text', timeout=70,
            nickname=nickname, text=text, category=category, from_panel=from_panel,
            conversation_open=conversation_open,
        ))

    def get_last_send_error(self) -> str:
        """Return the last worker-thread send diagnosis without touching Playwright."""
        return self._last_send_error

    def send_image(
        self, nickname: str, image_path: str, category: str = 'friend',
        from_panel: bool = False, conversation_open: bool = False,
    ) -> bool:
        return bool(self._call(
            'send_image', timeout=75,
            nickname=nickname, image_path=image_path, category=category,
            from_panel=from_panel, conversation_open=conversation_open,
        ))

    def close_browser(self) -> None:
        try:
            self._call('close_browser', timeout=20)
        except Exception:
            pass

    def is_browser_alive(self) -> bool:
        try:
            return bool(self._call('is_alive', timeout=5))
        except Exception:
            return False

    def is_message_panel_ready(self) -> bool:
        """Read message-panel DOM state on the Playwright owner thread."""
        try:
            return bool(self._call('is_message_panel_ready', timeout=8))
        except Exception:
            return False

    # ── worker thread ─────────────────────────────────────────────

    def _worker_main(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error('未安装 playwright，请执行: pip install playwright && playwright install chromium')
            self._running = False
            self._ready.set()
            return

        try:
            self._owner_thread_id = threading.get_ident()
            with sync_playwright() as playwright:
                self._playwright = playwright
                self._ready.set()
                while self._running:
                    try:
                        job = self._queue.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    op = job.get('op')
                    resp_q = job.get('resp_q')
                    kwargs = job.get('kwargs') or {}
                    cancelled = job.get('cancelled')
                    try:
                        if cancelled is not None and cancelled.is_set():
                            if resp_q:
                                resp_q.put({'error': f'操作已过期: {op}'})
                            continue
                        if op == 'shutdown':
                            self._cleanup_browser()
                            if resp_q:
                                resp_q.put({'ok': True})
                            break
                        result = self._dispatch(op, **kwargs)
                        if resp_q:
                            resp_q.put(result)
                    except Exception as exc:
                        logger.exception('Douyin worker op=%s failed', op)
                        if resp_q:
                            resp_q.put({'error': str(exc)})
        except BaseException:
            logger.exception('Douyin browser worker terminated unexpectedly')
        finally:
            self._ready.set()
            self._running = False
            self._cleanup_browser()
            self._playwright = None
            self._owner_thread_id = None

    def _dispatch(self, op: str, **kwargs):
        if self._owner_thread_id != threading.get_ident():
            raise RuntimeError('Playwright 操作必须在所属工作线程中执行')
        handlers = {
            'open_login': lambda: self._op_open_login(),
            'wait_login': lambda: self._op_wait_login(kwargs.get('login_timeout', LOGIN_TIMEOUT)),
            'get_account': lambda: self._op_get_account().to_dict(),
            'save_session': lambda: self._op_save_session(),
            'navigate_messages': lambda: self._op_navigate_messages(),
            'warmup_messages': lambda: self._op_warmup_messages(),
            'list_conversations': lambda: self._op_list_conversations(
                bool(kwargs.get('quick')),
                bool(kwargs.get('skip_stranger')),
            ),
            'open_conversation': lambda: self._op_open_conversation(
                kwargs['nickname'],
                kwargs.get('category', 'friend'),
                bool(kwargs.get('from_panel')),
            ),
            'read_latest_incoming': lambda: self._op_read_latest_message(
                kwargs.get('conv_id', ''),
                kwargs.get('nickname', ''),
                kwargs.get('category', 'friend'),
                kwargs.get('sender_nickname', ''),
            ),
            'read_latest_message': lambda: self._op_read_latest_message(
                kwargs.get('conv_id', ''),
                kwargs.get('nickname', ''),
                kwargs.get('category', 'friend'),
                kwargs.get('sender_nickname', ''),
            ),
            'send_text': lambda: self._op_send_text(
                kwargs['nickname'], kwargs['text'],
                kwargs.get('category', 'friend'),
                bool(kwargs.get('from_panel')),
                bool(kwargs.get('conversation_open')),
            ),
            'send_image': lambda: self._op_send_image(
                kwargs['nickname'], kwargs['image_path'],
                kwargs.get('category', 'friend'),
                bool(kwargs.get('from_panel')),
                bool(kwargs.get('conversation_open')),
            ),
            'close_browser': lambda: self._op_close_browser(),
            'restart_browser': lambda: self._op_restart_browser(),
            'check_session': lambda: self._op_check_session(),
            'is_alive': lambda: self._page is not None and not self._page.is_closed(),
            'is_message_panel_ready': lambda: self._is_message_panel_visible(),
        }
        handler = handlers.get(op)
        if not handler:
            raise ValueError(f'未知操作: {op}')
        return handler()

    def _sleep(self, seconds: float) -> bool:
        """可中断等待，返回 True 表示已请求中止"""
        end = time.time() + seconds
        while time.time() < end:
            if self._abort:
                return True
            time.sleep(min(0.25, end - time.time()))
        return self._abort

    def _ensure_browser(self) -> None:
        if self._context and self._page and not self._page.is_closed():
            if self._current_headless == self.headless:
                return
            self._cleanup_browser()
        if not self._playwright:
            raise RuntimeError('Playwright 未初始化')

        launch_args = [
            '--disable-blink-features=AutomationControlled',
        ]
        # Chromium warns that --no-sandbox is unsupported on normal Windows
        # desktops. Keep it only for Linux containers where it may be required.
        if os.name != 'nt':
            launch_args.append('--no-sandbox')
        context_kwargs = {
            'headless': self.headless,
            'args': launch_args,
            'viewport': {'width': 1280, 'height': 800},
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'user_agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
        }

        user_data_dir = os.path.join(os.path.dirname(self.storage_path), self.PROFILE_DIR_NAME)
        os.makedirs(user_data_dir, exist_ok=True)

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel='chrome',
                **context_kwargs,
            )
        except Exception:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                **context_kwargs,
            )

        self._context.add_init_script(STEALTH_SCRIPT)
        self._current_headless = self.headless
        if self._page and not self._page.is_closed():
            pass
        else:
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        self._page.set_default_timeout(30000)
        self._attach_network_listeners()

        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                cookies = state.get('cookies') or []
                if cookies:
                    self._context.add_cookies(cookies)
            except Exception as exc:
                logger.warning('恢复抖音登录态失败: %s', exc)

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
                    'im/user', 'account/info', 'user/info',
                )
                im_keys = (
                    '/im/', '/message', 'conversation', 'chat',
                    'aweme/v1/web/im', 'im/conversation', 'im/message',
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

    @staticmethod
    def _is_valid_uid(uid: str) -> bool:
        uid = (uid or '').strip()
        if not uid or uid.lower() in ('self', 'undefined', 'null'):
            return False
        return uid.isdigit() or (uid.startswith('MS') and len(uid) > 8)

    @staticmethod
    def _is_valid_nickname(nickname: str) -> bool:
        nickname = (nickname or '').strip()
        if not nickname or len(nickname) > 30:
            return False
        bad_phrases = (
            '优质视频', '短视频', '记录美好生活', '抖音', '登录',
            '扫码', '推荐', '热门', '首页',
        )
        return not any(p in nickname for p in bad_phrases)

    def _apply_user_info(self, info: Optional[Dict[str, Any]]) -> None:
        if not info:
            return
        uid = str(info.get('uid') or info.get('user_id') or '').strip()
        nickname = str(info.get('nickname') or info.get('nick_name') or '').strip()
        sec_uid = str(info.get('sec_uid') or info.get('sec_user_id') or '').strip()
        avatar = str(info.get('avatar') or info.get('avatar_url') or info.get('avatarUrl') or '').strip()
        if self._is_valid_uid(uid):
            self._account.uid = uid
        if self._is_valid_nickname(nickname):
            self._account.nickname = nickname
        if sec_uid:
            self._account.sec_uid = sec_uid
        if avatar:
            self._account.avatar = avatar

    def _ingest_api_payload(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        payload = data.get('data', data)
        if isinstance(payload, dict):
            conv_list = (
                payload.get('conversation_list')
                or payload.get('conversations')
                or payload.get('inbox_list')
            )
            if isinstance(conv_list, list):
                for item in conv_list:
                    if not isinstance(item, dict):
                        continue
                    cid = str(
                        item.get('conversation_id')
                        or item.get('conversation_short_id')
                        or item.get('id')
                        or ''
                    )
                    if not cid:
                        continue
                    user = item.get('user_info') or item.get('core_info') or item
                    nickname = (
                        user.get('nickname')
                        or user.get('nick_name')
                        or item.get('nickname')
                        or ''
                    )
                    latest = item.get('last_message') or item.get('last_msg') or item.get('message') or {}
                    if isinstance(latest, dict):
                        latest_text = str(
                            latest.get('content') or latest.get('text')
                            or latest.get('message') or latest.get('msg_content') or ''
                        )
                        message_id = str(
                            latest.get('message_id') or latest.get('msg_id')
                            or latest.get('server_message_id') or latest.get('id') or ''
                        )
                        last_msg_time = int(
                            latest.get('create_time') or latest.get('timestamp')
                            or latest.get('time') or 0
                        )
                    else:
                        latest_text = str(latest or item.get('content') or '')
                        message_id = str(
                            item.get('message_id') or item.get('last_message_id')
                            or item.get('max_message_id') or ''
                        )
                        last_msg_time = int(
                            item.get('last_msg_time') or item.get('update_time') or 0
                        )
                    self._api_conversations[cid] = {
                        'conv_id': cid,
                        'nickname': nickname,
                        'last_message': latest_text,
                        'unread': int(item.get('unread_count') or item.get('unread') or 0),
                        'message_id': message_id,
                        'last_msg_time': last_msg_time,
                        'update_time': int(item.get('update_time') or 0),
                    }
            msg_list = payload.get('messages') or payload.get('message_list')
            if isinstance(msg_list, list) and msg_list:
                cid = str(payload.get('conversation_id') or payload.get('conversation_short_id') or 'unknown')
                self._api_messages[cid] = msg_list

        if isinstance(payload, dict):
            for user_key in ('user', 'user_info', 'account', 'owner'):
                user = payload.get(user_key)
                if isinstance(user, dict):
                    self._apply_user_info(user)
            user_list = payload.get('user_list') or payload.get('users')
            if isinstance(user_list, list) and user_list and isinstance(user_list[0], dict):
                self._apply_user_info(user_list[0])

    def _cleanup_browser(self) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        self._context = None
        self._page = None
        self._messages_panel_ready = False
        self._conversation_open = False

    def _has_session_cookie(self) -> bool:
        if not self._context:
            return False
        names = {c.get('name') for c in self._context.cookies()}
        return bool(SESSION_COOKIES & names)

    def _op_restart_browser(self) -> Dict[str, Any]:
        self._cleanup_browser()
        self._current_headless = None
        return {'ok': True}

    def _op_check_session(self) -> bool:
        """校验登录态。无头模式下 API 可能误报，有会话 Cookie 且未跳转登录页则视为有效。"""
        self.headless = True
        self._ensure_browser()
        if not self._has_session_cookie():
            return False
        try:
            self._page.goto(DOUYIN_HOME, wait_until='domcontentloaded')
            self._sleep(2.5)
        except Exception:
            return self._has_session_cookie()

        if not self._has_session_cookie():
            return False

        try:
            on_login_page = self._page.evaluate(
                """() => {
                  const href = location.href || '';
                  if (/passport|\\/login/i.test(href)) return true;
                  const hints = ['扫码登录', '密码登录', '登录后免费畅享', '登录后即可'];
                  const text = (document.body && document.body.innerText) || '';
                  if (!hints.some(h => text.includes(h))) return false;
                  const loginNodes = [...document.querySelectorAll('button, a, span, div')]
                    .filter(el => (el.innerText || '').trim() === '登录');
                  return loginNodes.length > 0;
                }"""
            )
            if on_login_page:
                return False
        except Exception:
            pass

        try:
            profile = self._page.evaluate(
                """async () => {
                  try {
                    const r = await fetch('/aweme/v1/web/user/profile/self/', { credentials: 'include' });
                    if (!r.ok) return false;
                    const j = await r.json();
                    const u = (j.data && j.data.user) || j.user || j.data;
                    return !!(u && (u.uid || u.nickname));
                  } catch (e) { return false; }
                }"""
            )
            if profile:
                return True
        except Exception:
            pass

        # 有会话 Cookie 且页面未要求登录 — 视为有效（避免无头环境 API 误报）
        return self._has_session_cookie()

    def _op_open_login(self) -> Dict[str, Any]:
        self.headless = False
        if self._context and self._current_headless is True:
            self._cleanup_browser()
            self._current_headless = None
        self._ensure_browser()
        self._page.goto(DOUYIN_HOME, wait_until='domcontentloaded')
        time.sleep(2)
        return {'ok': True, 'message': '请在 Chromium 窗口中完成抖音登录（扫码或密码）'}

    def _op_wait_login(self, login_timeout: int) -> Dict[str, str]:
        self._ensure_browser()
        deadline = time.time() + login_timeout
        while time.time() < deadline:
            if self._abort:
                raise RuntimeError('登录操作已取消')
            if self._has_session_cookie():
                self._extract_account_from_page()
                self._op_save_session()
                return self._account.to_dict()
            time.sleep(2)
        raise TimeoutError('登录超时，请重试')

    def _extract_account_from_page(self) -> None:
        if not self._page:
            return
        try:
            self._page.goto(DOUYIN_HOME, wait_until='domcontentloaded')
            time.sleep(2.5)
        except Exception:
            pass

        try:
            profile = self._page.evaluate(
                """async () => {
                  const pickUser = (obj) => {
                    if (!obj || typeof obj !== 'object') return null;
                    const u = obj.user || obj.user_info || obj.account || obj;
                    const uid = String(u.uid || u.user_id || u.short_id || '').trim();
                    const nickname = String(u.nickname || u.nick_name || u.name || '').trim();
                    const sec_uid = String(u.sec_uid || u.sec_user_id || '').trim();
                    let avatar = '';
                    if (u.avatar_thumb && u.avatar_thumb.url_list) avatar = u.avatar_thumb.url_list[0] || '';
                    else avatar = u.avatar_url || u.avatarUrl || u.avatar || '';
                    if (!uid && !nickname && !avatar) return null;
                    return { uid, nickname, sec_uid, avatar };
                  };

                  const scanValue = (val) => {
                    if (!val) return null;
                    if (Array.isArray(val)) {
                      for (const item of val) {
                        const info = pickUser(item);
                        if (info && (info.uid || info.nickname || info.avatar)) return info;
                      }
                      return null;
                    }
                    return pickUser(val) || pickUser(val.data);
                  };

                  const apiUrls = [
                    '/aweme/v1/web/user/profile/self/',
                    '/aweme/v1/web/query/user/?device_platform=webapp',
                  ];
                  for (const url of apiUrls) {
                    try {
                      const r = await fetch(url, { credentials: 'include' });
                      if (!r.ok) continue;
                      const j = await r.json();
                      const info = pickUser(j) || pickUser(j.data);
                      if (info && info.uid && info.uid !== 'self') return info;
                    } catch (e) {}
                  }

                  try {
                    const el = document.querySelector('#RENDER_DATA');
                    if (el && el.textContent) {
                      const raw = decodeURIComponent(el.textContent);
                      const data = JSON.parse(raw);
                      const str = JSON.stringify(data);
                      const uidMatch = str.match(/"uid"\\s*:\\s*"(\\d{6,})"/);
                      const nickMatch = str.match(/"nickname"\\s*:\\s*"([^"]{1,30})"/);
                      if (uidMatch || nickMatch) {
                        return {
                          uid: uidMatch ? uidMatch[1] : '',
                          nickname: nickMatch ? nickMatch[1] : '',
                          sec_uid: '',
                          avatar: ''
                        };
                      }
                    }
                  } catch (e) {}

                  try {
                    for (const key of Object.keys(localStorage)) {
                      const val = localStorage.getItem(key);
                      if (!val || val.length > 50000) continue;
                      if (!/user|login|account/i.test(key)) continue;
                      try {
                        const j = JSON.parse(val);
                      const info = scanValue(j);
                        if (info && ((info.uid && info.uid !== 'self') || info.nickname || info.avatar)) return info;
                      } catch (e) {}
                    }
                  } catch (e) {}

                  const links = Array.from(document.querySelectorAll('a[href*="/user/"]'));
                  for (const a of links) {
                    const href = a.getAttribute('href') || '';
                    const m = href.match(/\\/user\\/([A-Za-z0-9_-]+)/);
                    if (!m || m[1] === 'self') continue;
                    const text = (a.innerText || a.textContent || '').trim().split('\\n')[0];
                    if (/^\\d+$/.test(m[1])) {
                      return { uid: m[1], nickname: text || '', sec_uid: '', avatar: '' };
                    }
                    if (m[1].startsWith('MS')) {
                      return { uid: '', nickname: text || '', sec_uid: m[1], avatar: '' };
                    }
                  }
                  try {
                    const imgs = Array.from(document.querySelectorAll(
                      'header img[src*="douyinpic"], header img[src*="avatar"], img[src*="aweme-avatar"]'
                    ));
                    for (const img of imgs) {
                      const src = (img.currentSrc || img.src || '').trim();
                      if (src && (src.includes('douyinpic') || src.includes('aweme-avatar'))) {
                        return { uid: '', nickname: '', sec_uid: '', avatar: src };
                      }
                    }
                  } catch (e) {}

                  return null;
                }"""
            )
            self._apply_user_info(profile)
        except Exception as exc:
            logger.debug('API 提取账号信息失败: %s', exc)

        if not self._is_valid_uid(self._account.uid) or not self._is_valid_nickname(self._account.nickname):
            try:
                self._page.goto('https://www.douyin.com/user/self', wait_until='domcontentloaded')
                time.sleep(2)
                final_url = self._page.url or ''
                uid_match = re.search(r'/user/(MS[\w-]+|(\d{6,}))', final_url)
                if uid_match:
                    if uid_match.group(2):
                        self._account.uid = uid_match.group(2)
                    elif uid_match.group(1):
                        self._account.sec_uid = uid_match.group(1)
            except Exception:
                pass

        if not self._is_valid_nickname(self._account.nickname):
            for sel in ('[class*="user-name"]', '[class*="nickname"]', 'header [class*="name"]'):
                try:
                    el = self._page.query_selector(sel)
                    if el:
                        text = (el.inner_text() or '').strip().split('\n')[0]
                        if self._is_valid_nickname(text):
                            self._account.nickname = text
                            break
                except Exception:
                    continue

        if not self._is_valid_uid(self._account.uid) and self._context:
            for cookie in self._context.cookies():
                if cookie.get('name') == 'uid_tt' and cookie.get('value'):
                    val = str(cookie['value']).strip()
                    if val.isdigit():
                        self._account.uid = val
                        break

        if not self._account.avatar:
            avatar = extract_avatar_from_storage(self.storage_path)
            if avatar:
                self._account.avatar = avatar

    def _op_get_account(self) -> DouyinAccountInfo:
        if self._has_session_cookie():
            self._extract_account_from_page()
        elif not self._account.avatar:
            avatar = extract_avatar_from_storage(self.storage_path)
            if avatar:
                self._account.avatar = avatar
        return self._account

    def _op_save_session(self) -> Dict[str, Any]:
        if not self._context:
            return {'ok': False}
        state = self._context.storage_state()
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return {'ok': True, 'path': self.storage_path}

    def _op_warmup_messages(self) -> Dict[str, Any]:
        self._op_navigate_messages(fast=True)
        return {'ok': True}

    def _op_navigate_messages(self, fast: bool = False) -> Dict[str, Any]:
        if self._abort:
            return {'ok': False, 'aborted': True}
        self._ensure_browser()
        wait_after = 0.3 if fast else 1.2
        panel_timeout = 2.0 if fast else 4.0
        navigation_timeout_ms = 8000 if fast else 10000

        def _panel_ready(timeout: float = 0.0) -> bool:
            if timeout > 0:
                panel_items = self._wait_for_conversation_list(timeout=timeout)
            else:
                try:
                    panel_items = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
                except Exception:
                    panel_items = []
            # 接口响应或浮层根节点都会早于 React 会话行挂载。只有真实的
            # 会话行可用时才允许把状态记为“列表就绪”。聊天详情也位于同一
            # 浮层根节点内，不能用根节点可见替代列表就绪。
            ready = bool(panel_items)
            if ready:
                self._messages_panel_ready = True
                self._conversation_open = False
            return ready

        # 优先复用当前页面。首次回复时重复刷新抖音页面既慢，也容易触发超时。
        if _panel_ready():
            return {'ok': True, 'url': self._page.url or ''}
        if self._open_message_panel(fast=True) and _panel_ready(panel_timeout):
            return {'ok': True, 'url': self._page.url or ''}

        urls = (DOUYIN_MESSAGES, DOUYIN_HOME)
        for url in urls:
            if self._abort:
                break
            try:
                try:
                    # 抖音是 SPA；路由提交后等待会话 DOM 比等待整个页面加载更可靠。
                    self._page.goto(
                        url,
                        wait_until='commit',
                        timeout=navigation_timeout_ms,
                    )
                except Exception as exc:
                    # 导航超时后页面可能已经提交，先检查 DOM 再尝试备用地址。
                    logger.debug('抖音私信页导航未及时完成: %s', exc)
                self._sleep(wait_after)
                on_messages = '/message' in (self._page.url or '')
                opened = on_messages or self._open_message_panel(fast=fast)
                if opened and _panel_ready(panel_timeout):
                    return {'ok': True, 'url': self._page.url}

                # /message 有时只完成了路由跳转，列表组件尚未挂载；再主动打开一次。
                if on_messages and self._open_message_panel(fast=fast):
                    if _panel_ready(panel_timeout):
                        return {'ok': True, 'url': self._page.url}
            except Exception:
                continue
        # 不能把失败的导航标为“列表已就绪”，否则后续快速扫描会永久停在错误页面。
        self._messages_panel_ready = False
        self._conversation_open = False
        return {'ok': False, 'url': self._page.url or ''}

    def _open_message_panel(self, fast: bool = False) -> bool:
        """点击顶部导航「消息」打开私信面板"""
        if not self._page or self._abort:
            return False
        click_wait = 0.4 if fast else 1.5
        try:
            for label in ('消息', '私信'):
                if self._abort:
                    return False
                loc = self._page.get_by_text(label, exact=True)
                if loc.count() > 0:
                    loc.first.click(timeout=1200 if fast else 2500)
                    if self._sleep(click_wait):
                        return False
                    return True
        except Exception:
            pass
        try:
            clicked = self._page.evaluate(
                """() => {
                  const labels = ['消息', '私信'];
                  const nodes = document.querySelectorAll('span, div, a, button, p');
                  for (const label of labels) {
                    for (const node of nodes) {
                      const t = (node.innerText || '').trim();
                      if (t !== label) continue;
                      const r = node.getBoundingClientRect();
                      if (r.top > 90 || r.width < 8 || r.height < 8) continue;
                      node.click();
                      return true;
                    }
                  }
                  return false;
                }"""
            )
            if clicked:
                if self._sleep(click_wait):
                    return False
                return True
        except Exception:
            pass
        return False

    def _click_conversation_row(self, nickname: str, fast: bool = False) -> bool:
        """点击私信列表中的会话行（优先点行容器，避免误点预览文字）。"""
        if not nickname or not self._page or self._abort:
            return False
        click_wait = 0.22 if fast else 0.8
        # 优先点击会话列表行。首次启动时页面内常同时存在导航、标题和聊天
        # 头部的同名文本；逐个用 5 秒默认超时尝试会让首次发送阻塞几十秒。
        try:
            point = self._page.evaluate(CLICK_CONVERSATION_ROW_JS, nickname) or {}
            if isinstance(point, dict):
                self._last_conversation_click_debug = (
                    f"候选={point.get('candidateCount', 0)}，精确昵称={point.get('exactTextCount', 0)}，"
                    f"目标={point.get('tag', '-')} {point.get('width', 0)}×{point.get('height', 0)}，"
                    f"评分={point.get('score', 0)}"
                )
            if (
                isinstance(point, dict)
                and point.get('found')
                and isinstance(point.get('x'), (int, float))
                and isinstance(point.get('y'), (int, float))
            ):
                # page.mouse 产生浏览器信任的 pointer/mouse 事件。抖音新版会忽略
                # 对部分 React 会话行直接调用 DOM element.click() 的非信任事件。
                self._page.mouse.click(float(point['x']), float(point['y']))
                if self._sleep(click_wait):
                    return False
                return True
        except Exception:
            pass

        # DOM 结构变化时再退回精确文本，限制候选数量和单次等待时间。
        try:
            loc = self._page.get_by_text(nickname, exact=True)
            for index in range(min(loc.count(), 3)):
                candidate = loc.nth(index)
                if not candidate.is_visible():
                    continue
                candidate.click(timeout=900 if fast else 1500)
                self._last_conversation_click_debug = f'精确文本候选 {index + 1}/{min(loc.count(), 3)}'
                if self._sleep(click_wait):
                    return False
                return True
        except Exception:
            pass
        return self._click_row_by_title(nickname, fast=fast)

    def _wait_for_conversation_list(self, timeout: float = 6.0, min_rows: int = 1) -> List[Dict[str, Any]]:
        """等待私信会话列表挂载（/message 页 DOM 加载常慢于 URL 跳转）。"""
        if not self._page or self._abort:
            return []
        deadline = time.time() + timeout
        last_items: List[Dict[str, Any]] = []
        while time.time() < deadline:
            if self._abort:
                return last_items
            try:
                last_items = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
            except Exception:
                last_items = []
            if len(last_items) >= min_rows:
                return last_items
            if self._sleep(0.25):
                return last_items
        return last_items

    def _wait_for_nickname_in_list(self, nickname: str, timeout: float = 6.0) -> bool:
        if not nickname or not self._page or self._abort:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            try:
                loc = self._page.get_by_text(nickname, exact=True)
                if loc.count() > 0:
                    return True
            except Exception:
                pass
            try:
                items = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
                if any((i.get('nickname') or '') == nickname for i in items):
                    return True
            except Exception:
                pass
            if self._sleep(0.2):
                return False
        return False

    def _is_message_panel_visible(self) -> bool:
        if not self._page or self._page.is_closed():
            return False
        try:
            state = self._page.evaluate(FIND_IM_PANEL_ROOT_JS) or {}
            return bool(state.get('found'))
        except Exception:
            return False

    def _ensure_im_panel_ready(self, fast: bool = True) -> bool:
        """确保私信面板真实可见；内部状态过期时强制重新打开。"""
        existing_items = self._wait_for_conversation_list(timeout=0.12)
        if existing_items:
            self._messages_panel_ready = True
            self._conversation_open = False
            return True
        self._messages_panel_ready = False
        if '/message' not in (self._page.url or ''):
            self._op_navigate_messages(fast=fast)
        else:
            self._wait_for_conversation_list(timeout=4.0 if fast else 8.0)
        items = self._wait_for_conversation_list(timeout=3.0 if fast else 5.0)
        visible = len(items) > 0
        self._messages_panel_ready = visible
        if visible:
            self._conversation_open = False
        return visible

    def _ensure_message_page_for_send(self) -> bool:
        """确保可用的私信面板就绪。

        新版抖音会把 ``/message`` 重定向到 ``/jingxuan``，会话和编辑器都在
        右侧浮层中。强行跳回 ``/message`` 反而会留下一个没有会话 DOM 的空页。
        """
        if not self._page or self._abort:
            return False

        if self._wait_for_chat_editor(timeout=0.15):
            # 页面当前处于聊天详情而非会话列表。记录真实状态，后续先返回
            # 列表再选择目标会话，不能继续在隐藏的列表中查找昵称。
            self._conversation_open = True
            self._messages_panel_ready = False
            return True

        items = self._wait_for_conversation_list(timeout=0.8)
        if items:
            self._messages_panel_ready = True
            self._conversation_open = False
            return True

        # 从主页重新打开消息浮层。_op_navigate_messages 会处理当前抖音版本
        # 实际采用的路由，不再假设最终 URL 必须包含 /message。
        self._messages_panel_ready = False
        self._conversation_open = False
        result = self._op_navigate_messages(fast=False)
        if not result or not result.get('ok'):
            return False
        # 导航方法已确认真实的会话 DOM，无需再额外等待六秒。
        return True

    def _current_chat_matches(self, nickname: str) -> bool:
        """严格确认当前聊天标题，避免在错误联系人窗口中直接发送。"""
        if not nickname or not self._page or self._page.is_closed():
            return False
        try:
            return bool(self._page.evaluate(
                """(nickname) => {
                  const visible = (el) => {
                    const r = el?.getBoundingClientRect();
                    return !!r && r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight;
                  };
                  const editors = [...document.querySelectorAll(
                    '[contenteditable="true"], textarea, div[role="textbox"]'
                  )].filter(el => visible(el) && !el.closest('[class*="search" i]'));
                  const editor = editors[editors.length - 1];
                  if (!editor) return false;
                  let panel = editor.parentElement;
                  while (panel && panel !== document.body) {
                    const r = panel.getBoundingClientRect();
                    if (r.width >= 280 && r.height >= 300 && r.right > innerWidth * .55) break;
                    panel = panel.parentElement;
                  }
                  if (!panel || panel === document.body) return false;
                  const pr = panel.getBoundingClientRect();
                  const nodes = [...panel.querySelectorAll('span, p, div, strong, h1, h2, h3')];
                  return nodes.some(node => {
                    if (!visible(node) || (node.innerText || '').trim() !== nickname) return false;
                    if ([...node.children].some(c => (c.innerText || '').trim() === nickname)) return false;
                    const r = node.getBoundingClientRect();
                    // 只接受聊天容器顶部标题区，绝不使用消息正文中的同名文本。
                    return r.top >= pr.top && r.bottom <= pr.top + Math.min(150, pr.height * .24);
                  });
                }""",
                nickname,
            ))
        except Exception:
            return False

    def _click_row_by_title(self, title: str, fast: bool = False) -> bool:
        if not title or not self._page or self._abort:
            return False
        click_wait = 0.18 if fast else 1.0
        try:
            loc = self._page.get_by_text(title, exact=True)
            if loc.count() > 0:
                loc.first.click(timeout=1500 if fast else 2500)
                if self._sleep(click_wait):
                    return False
                return True
        except Exception:
            pass
        try:
            clicked = bool(self._page.evaluate(
                """(title) => {
                  const nodes = document.querySelectorAll('*');
                  for (const node of nodes) {
                    const text = (node.innerText || '').trim();
                    if (!text) continue;
                    const first = text.split('\\n')[0].trim();
                    if (first === title) {
                      const r = node.getBoundingClientRect();
                      if (r.width > 0 && r.height > 0) {
                        node.click();
                        return true;
                      }
                    }
                  }
                  return false;
                }""",
                title,
            ))
            if clicked:
                if self._sleep(click_wait):
                    return False
            return clicked
        except Exception:
            return False

    def _expand_stranger_folder(self) -> List[Dict[str, Any]]:
        """进入「陌生人消息」子列表并提取会话"""
        if self._abort:
            return []
        if not self._click_row_by_title('陌生人消息'):
            return []
        if self._sleep(1.5):
            return []
        try:
            return self._page.evaluate(EXTRACT_STRANGER_CHATS_JS) or []
        except Exception:
            return []

    def _return_to_message_list(self, fast: bool = True) -> bool:
        """从聊天窗口返回会话列表，便于继续扫描和发送下一条。"""
        if not self._page or self._page.is_closed():
            return False

        def _list_ready(timeout: float = 0.0) -> bool:
            items = self._wait_for_conversation_list(timeout=timeout) if timeout > 0 else []
            if not items:
                try:
                    items = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
                except Exception:
                    items = []
            if items:
                self._messages_panel_ready = True
                self._conversation_open = False
                return True
            return False

        editor_visible = self._wait_for_chat_editor(timeout=0.08)
        if not editor_visible and _list_ready():
            return True

        # 浮层聊天通常可由 Escape 返回/关闭。先用真实键盘事件处理，
        # 若关闭了整个浮层，后面会重新打开消息面板。
        if editor_visible:
            try:
                self._page.keyboard.press('Escape')
                self._sleep(0.18 if fast else 0.35)
                if _list_ready(0.7 if fast else 1.2):
                    return True
            except Exception:
                pass

        try:
            point = self._page.evaluate(
                """() => {
                  const visible = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width >= 8 && r.height >= 8 && r.bottom > 0 && r.top < innerHeight;
                  };
                  const nodes = [...document.querySelectorAll(
                    'button, [role="button"], a, svg, [class*="back" i], [class*="close" i], [class*="arrow-left" i]'
                  )];
                  const candidates = [];
                  for (const node of nodes) {
                    if (!visible(node)) continue;
                    const t = (node.innerText || '').trim();
                    const aria = (node.getAttribute('aria-label') || '') + ' ' +
                      (node.getAttribute('title') || '');
                    const cls = String(node.className?.baseVal || node.className || '');
                    const isBack = t === '返回' || /返回|back|arrow-left/i.test(aria + ' ' + cls);
                    const isClose = t === '关闭' || /关闭|close/i.test(aria + ' ' + cls);
                    if (!isBack && !isClose) continue;
                    const r = node.getBoundingClientRect();
                    if (r.width > 120 || r.height > 120) continue;
                    let score = isBack ? 20 : 8;
                    if (node.matches('button, [role="button"], a')) score += 6;
                    if (r.top < innerHeight * .35) score += 3;
                    candidates.push({node, r, score});
                  }
                  candidates.sort((a, b) => b.score - a.score || a.r.left - b.r.left);
                  const best = candidates[0];
                  if (!best) return {found: false, candidateCount: 0};
                  const r = best.node.getBoundingClientRect();
                  return {
                    found: true, x: r.left + r.width / 2, y: r.top + r.height / 2,
                    candidateCount: candidates.length,
                  };
                }"""
            ) or {}
            if (
                isinstance(point, dict)
                and point.get('found')
                and isinstance(point.get('x'), (int, float))
                and isinstance(point.get('y'), (int, float))
            ):
                self._page.mouse.click(float(point['x']), float(point['y']))
                self._sleep(0.22 if fast else 0.45)
                if _list_ready(0.9 if fast else 1.5):
                    return True
        except Exception:
            pass

        # 如果上一步关闭了整个消息浮层，重新打开后应直接落在会话列表。
        try:
            if self._wait_for_chat_editor(timeout=0.05):
                self._page.keyboard.press('Escape')
                self._sleep(0.12)
            if self._open_message_panel(fast=fast):
                if _list_ready(1.5 if fast else 2.5):
                    return True
        except Exception:
            pass

        self._messages_panel_ready = False
        self._conversation_open = self._wait_for_chat_editor(timeout=0.05)
        return False

    def _op_list_conversations(self, quick: bool = False, skip_stranger: bool = False) -> List[Dict[str, Any]]:
        if self._abort:
            return []
        fast = bool(quick)
        panel_items_cache: Optional[List[Dict[str, Any]]] = None
        if fast and self._messages_panel_ready and self._page and not self._page.is_closed():
            editor_visible = self._wait_for_chat_editor(timeout=0.05)
            if editor_visible or self._conversation_open:
                self._conversation_open = True
                self._messages_panel_ready = False
                if not self._return_to_message_list(fast=True):
                    self._op_navigate_messages(fast=True)
            else:
                # 内部状态可能因页面重绘、弹窗或路由跳转而过期；快速扫描前做一次廉价自检。
                try:
                    panel_items_cache = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
                except Exception:
                    panel_items_cache = []
                # 网络缓存中有会话并不代表页面列表可点击。扫描阶段就恢复
                # 实际面板，避免等发现新消息后才在发送路径里做昂贵恢复。
                if not panel_items_cache:
                    self._messages_panel_ready = False
                    self._op_navigate_messages(fast=True)
                    try:
                        panel_items_cache = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
                    except Exception:
                        panel_items_cache = []
        else:
            self._op_navigate_messages(fast=fast or skip_stranger)
            self._conversation_open = False
        if self._abort:
            return []
        merged: Dict[str, Dict[str, Any]] = {}

        for item in self._api_conversations.values():
            nick = item.get('nickname') or item.get('conv_id')
            if nick:
                category = item.get('category') or 'friend'
                merged[f'{category}:{nick}'] = {
                    'conv_id': item.get('conv_id') or nick,
                    'nickname': nick,
                    'last_message': item.get('last_message') or '',
                    'unread': int(item.get('unread') or 0),
                    'category': category,
                    'sender_nickname': item.get('sender_nickname') or '',
                    'message_id': item.get('message_id') or '',
                    'last_msg_time': int(item.get('last_msg_time') or 0),
                    'update_time': int(item.get('update_time') or 0),
                }

        try:
            panel_items = (
                panel_items_cache
                if panel_items_cache is not None
                else (self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or [])
            )
            for item in panel_items:
                if self._abort:
                    break
                cat = item.get('category') or 'friend'
                if cat == 'stranger_folder':
                    sender = (item.get('sender_nickname') or '').strip()
                    preview = (item.get('last_message') or '').strip()
                    if sender:
                        key = f'stranger:{sender}'
                        merged[key] = {
                            'conv_id': key,
                            'nickname': sender,
                            'last_message': preview,
                            'unread': int(item.get('unread') or 1),
                            'category': 'stranger',
                            'sender_nickname': sender,
                        }
                    if skip_stranger:
                        continue
                    stranger_chats = self._expand_stranger_folder()
                    if self._abort:
                        break
                    for sc in stranger_chats:
                        nick = sc.get('nickname') or sc.get('sender_nickname')
                        if not nick:
                            continue
                        key = f"stranger:{nick}"
                        merged[key] = {
                            'conv_id': key,
                            'nickname': nick,
                            'last_message': sc.get('last_message') or '',
                            'unread': int(sc.get('unread') or 0),
                            'category': 'stranger',
                            'sender_nickname': nick,
                        }
                    self._open_message_panel()
                    if self._sleep(1):
                        break
                    continue

                nick = item.get('nickname')
                if not nick:
                    continue
                key = f"friend:{nick}"
                existing = merged.get(key, {})
                merged[key] = {
                    'conv_id': existing.get('conv_id') or key,
                    'nickname': nick,
                    'last_message': item.get('last_message') or existing.get('last_message') or '',
                    'unread': max(
                        int(existing.get('unread') or 0),
                        int(item.get('unread') or 0),
                    ),
                    'category': 'friend',
                    'sender_nickname': item.get('sender_nickname') or existing.get('sender_nickname') or '',
                    'message_id': existing.get('message_id') or '',
                    'last_msg_time': int(existing.get('last_msg_time') or 0),
                    'update_time': int(existing.get('update_time') or 0),
                }
        except Exception as exc:
            logger.warning('DOM 会话列表提取失败: %s', exc)

        results = list(merged.values())
        if not results:
            # 快速路径为空时执行一次完整恢复，不必等到下一轮继续空扫。
            self._messages_panel_ready = False
            self._conversation_open = False
            self._op_navigate_messages(fast=False)
            self._sleep(0.15)
            try:
                panel_items = self._page.evaluate(EXTRACT_PANEL_CONVERSATIONS_JS) or []
                for item in panel_items:
                    nick = item.get('nickname')
                    if not nick:
                        continue
                    key = f"friend:{nick}"
                    if key not in merged:
                        merged[key] = {
                            'conv_id': key,
                            'nickname': nick,
                            'last_message': item.get('last_message') or '',
                            'unread': int(item.get('unread') or 0),
                            'category': item.get('category') or 'friend',
                            'sender_nickname': item.get('sender_nickname') or '',
                        }
                results = list(merged.values())
            except Exception:
                pass
            self._messages_panel_ready = bool(results)
        logger.info('抖音会话列表: %d 条', len(results))
        return results

    def _op_open_conversation(
        self, nickname: str, category: str = 'friend', from_panel: bool = False,
    ) -> bool:
        self._last_open_error = ''
        if not nickname or self._abort:
            self._last_open_error = '会话昵称为空或操作已取消'
            return False
        fast = bool(from_panel)
        if not from_panel:
            if '/message' not in (self._page.url or ''):
                self._op_navigate_messages(fast=False)
            self._conversation_open = False
        else:
            # 不信任缓存标志。抖音的消息浮层会在 React 重绘后保留编辑器，
            # 但旧代码仍可能认为自己位于会话列表，随后在聊天详情 DOM 中找昵称，
            # 这正是日志里“候选=0、精确昵称=0”的来源。
            editor_visible = self._wait_for_chat_editor(timeout=0.08)
            if editor_visible or self._conversation_open:
                self._conversation_open = True
                self._messages_panel_ready = False
                # 抖音打开消息浮层时可能自动保留上次会话。若标题严格匹配，
                # 直接复用当前编辑器，既更快也避免无意义地退回再进入。
                if editor_visible and self._current_chat_matches(nickname):
                    self._last_open_error = ''
                    return True
                if not self._return_to_message_list(fast=True):
                    self._last_open_error = '聊天窗口已打开，但无法返回会话列表'
                    return False
            if not self._ensure_im_panel_ready(fast=True):
                self._last_open_error = '私信会话列表未就绪'
                return False
            # 面板根节点可见不等于列表已经渲染；发送前必须看到真实会话行。
            if not self._wait_for_conversation_list(timeout=1.5):
                self._last_open_error = '私信面板已打开，但会话列表尚未渲染'
                self._messages_panel_ready = False
                return False
            if self._sleep(0.2):
                return False
        if self._abort:
            return False
        # 新版页面通常停留在 /jingxuan 并使用右侧浮层，因此不能再用 URL
        # 决定是否等待目标行。
        if not self._wait_for_nickname_in_list(nickname, timeout=2.0 if fast else 5.0):
            self._last_open_error = f'会话列表中未出现目标“{nickname}”'
            return False
        if not fast and self._sleep(0.8):
            return False

        editor_wait = 3.0 if fast else 5.0

        def _open_and_verify(click_fn) -> bool:
            if not click_fn():
                self._last_open_error = '页面中未定位到目标会话行'
                return False
            if self._wait_for_chat_editor(timeout=editor_wait):
                self._conversation_open = True
                self._last_open_error = ''
                return True
            self._last_open_error = '已点击候选会话行，但聊天输入框未出现'
            return False

        if category == 'stranger':
            if not _open_and_verify(lambda: self._click_row_by_title('陌生人消息', fast=fast)):
                logger.warning('未找到「陌生人消息」入口')
                return False
            if self._sleep(0.3 if fast else 0.8):
                return False
            if not _open_and_verify(lambda: self._click_conversation_row(nickname, fast=fast)):
                logger.warning('陌生人会话未找到: %s', nickname)
                return False
            return True

        if _open_and_verify(lambda: self._click_conversation_row(nickname, fast=fast)):
            return True

        # 点击后若抖音重绘了浮层，重新确认真实列表状态后只重试一次。
        self._messages_panel_ready = False
        if not self._ensure_message_page_for_send():
            self._conversation_open = False
            return False
        if self._conversation_open and not self._return_to_message_list(fast=False):
            self._last_open_error = '重试前无法恢复会话列表'
            return False
        if not self._wait_for_nickname_in_list(nickname, timeout=3.0):
            self._last_open_error = f'恢复后仍未找到目标会话“{nickname}”'
            return False
        if self._sleep(0.25):
            return False
        if _open_and_verify(lambda: self._click_conversation_row(nickname, fast=False)):
            return True

        self._conversation_open = False
        return False

    def _parse_incoming_from_preview(self, last_message: str, sender_nickname: str) -> Optional[str]:
        """从列表预览解析对方最新消息，如「炽阳002: 你好」"""
        text = (last_message or '').strip()
        if not text:
            return None
        if ':' in text or '：' in text:
            sep = ':' if ':' in text else '：'
            parts = text.split(sep, 1)
            if len(parts) == 2:
                nick_part = parts[0].strip()
                msg_part = parts[1].strip()
                if sender_nickname and nick_part == sender_nickname and msg_part:
                    return msg_part
                if not sender_nickname and msg_part:
                    return msg_part
        return text

    def _message_is_self(self, raw: Dict[str, Any]) -> Optional[bool]:
        """从接口消息判断方向；缺少证据时返回 None，让 DOM 继续判断。"""
        for key in ('is_self', 'is_from_me', 'sender_is_self', 'is_sender'):
            if key in raw:
                value = raw.get(key)
                if isinstance(value, str):
                    return value.strip().lower() in ('1', 'true', 'yes')
                return bool(value)
        sender = str(
            raw.get('sender_uid') or raw.get('sender_id') or raw.get('from_uid')
            or raw.get('from_user_id') or raw.get('user_id') or ''
        ).strip()
        own_uid = str(self._account.uid or '').strip()
        if sender and own_uid:
            return sender == own_uid
        return None

    def _op_read_latest_message(
        self,
        conv_id: str,
        nickname: str,
        category: str = 'friend',
        sender_nickname: str = '',
    ) -> Optional[Dict[str, Any]]:
        if self._abort:
            return None
        target = sender_nickname or nickname
        if not self._op_open_conversation(target, category=category, from_panel=True):
            return None
        if self._sleep(0.18):
            return None

        # 当前聊天 DOM 是最新状态，优先于可能滞后的网络缓存。
        try:
            dom_msgs = self._page.evaluate(EXTRACT_CHAT_MESSAGES_JS, 20) or []
            for msg in reversed(dom_msgs):
                text = (msg.get('text') or '').strip()
                if not text or len(text) > 500:
                    continue
                if text in ('发送', '搜索', '消息', '陌生人消息'):
                    continue
                return {
                    'conv_id': conv_id or target,
                    'nickname': target,
                    'text': text,
                    'is_self': bool(msg.get('is_self')),
                    'timestamp': int(time.time()),
                }
        except Exception as exc:
            logger.debug('DOM 消息提取失败: %s', exc)

        api_msgs = self._api_messages.get(conv_id) or []
        for raw in reversed(api_msgs):
            if not isinstance(raw, dict):
                continue
            text = self._extract_message_text(raw)
            if not text:
                continue
            is_self = self._message_is_self(raw)
            if is_self is None:
                continue
            return {
                'conv_id': conv_id or target,
                'nickname': target,
                'text': text,
                'is_self': is_self,
                'timestamp': int(raw.get('create_time') or raw.get('timestamp') or time.time()),
            }

        return None

    @staticmethod
    def _extract_message_text(raw: Dict[str, Any]) -> str:
        content = raw.get('content')
        if isinstance(content, dict):
            return str(content.get('text') or content.get('content') or '').strip()
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return str(parsed.get('text') or parsed.get('content') or '').strip()
            except (json.JSONDecodeError, TypeError):
                return content.strip()
        return str(
            raw.get('text')
            or raw.get('msg_content')
            or (raw.get('body') or {}).get('text')
            or ''
        ).strip()

    def _wait_for_chat_editor(self, timeout: float = 1.8) -> bool:
        if not self._page:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            try:
                if self._page.evaluate(WAIT_FOR_CHAT_EDITOR_JS):
                    return True
            except Exception:
                pass
            if self._sleep(0.08):
                return False
        return False

    def _verify_message_sent(self, text: str) -> bool:
        try:
            return bool(self._page.evaluate(VERIFY_SENT_MESSAGE_JS, text))
        except Exception:
            return False

    def _verify_sent_in_preview(self, nickname: str, text: str) -> bool:
        try:
            return bool(self._page.evaluate(
                VERIFY_SENT_IN_PREVIEW_JS, [nickname, text],
            ))
        except Exception:
            return False

    def _start_send_watch(self, text: str) -> str:
        token = f'{time.time_ns()}-{threading.get_ident()}'
        try:
            if self._page.evaluate(START_SEND_WATCH_JS, [token, text]):
                return token
        except Exception as exc:
            logger.debug('启动发送结果监听失败: %s', exc)
        return ''

    def _send_watch_succeeded(self, token: str) -> bool:
        if not token:
            return False
        try:
            return bool(self._page.evaluate(CHECK_SEND_WATCH_JS, token))
        except Exception:
            return False

    def _poll_send_success(
        self, nickname: str, text: str, attempts: int = 12, watch_token: str = '',
    ) -> bool:
        for _ in range(attempts):
            if self._send_watch_succeeded(watch_token):
                return True
            if self._sleep(0.12):
                return False
        return False

    def _editor_state(self) -> Dict[str, Any]:
        try:
            return self._page.evaluate(CHAT_EDITOR_STATE_JS) or {}
        except Exception:
            return {}

    def _submission_accepted(self, nickname: str, text: str, watch_token: str) -> bool:
        """必须观察到本次提交新增的己方气泡，输入框清空本身不算成功。"""
        return self._poll_send_success(
            nickname, text, attempts=30, watch_token=watch_token,
        )

    def _fill_and_send_message(self, text: str, nickname: str = '') -> bool:
        """填充并发送，只有观察到本次新增的己方气泡才返回成功。"""
        if not self._page:
            return False
        if not self._wait_for_chat_editor():
            logger.warning('未找到聊天输入框')
            return False

        try:
            watch_token = self._start_send_watch(text)
            focused = bool(self._page.evaluate(FOCUS_CHAT_EDITOR_JS))
            if focused:
                try:
                    self._page.keyboard.press('Control+a')
                    self._page.keyboard.press('Backspace')
                except Exception:
                    pass
                self._page.keyboard.insert_text(text)
                if self._sleep(0.04):
                    return False
                self._page.keyboard.press('Enter')
                if self._submission_accepted(nickname, text, watch_token):
                    return True

                # 某些账号的回车键被配置为换行，改点“发送”按钮。
                state = self._editor_state()
                if state.get('found') and state.get('empty'):
                    # Enter 清空却没有新增气泡：重新填充后明确点击发送。
                    self._page.keyboard.insert_text(text)
                    if self._sleep(0.04):
                        return False
                watch_token = self._start_send_watch(text)
                clicked = bool(self._page.evaluate(CLICK_CHAT_SEND_JS))
                if clicked and self._submission_accepted(nickname, text, watch_token):
                    return True
        except Exception as exc:
            logger.debug('keyboard 发送失败: %s', exc)

        watch_token = self._start_send_watch(text)
        result = self._page.evaluate(IM_FILL_AND_SEND_JS, text)
        if not result or not result.get('ok'):
            logger.warning('JS 填充发送失败: %s', (result or {}).get('reason', 'unknown'))
            if self._submission_accepted(nickname, text, watch_token):
                return True
            return False
        return self._submission_accepted(nickname, text, watch_token)

    def _outgoing_message_count(self) -> int:
        try:
            return int(self._page.evaluate(OUTGOING_MESSAGE_COUNT_JS) or 0)
        except Exception:
            return 0

    def _wait_for_new_outgoing_message(self, before_count: int, timeout: float = 12.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            if self._outgoing_message_count() > before_count:
                return True
            if self._sleep(0.15):
                return False
        return False

    def _start_image_send_watch(self) -> str:
        token = f'image-{time.time_ns()}-{threading.get_ident()}'
        try:
            if self._page.evaluate(START_IMAGE_SEND_WATCH_JS, token):
                return token
        except Exception as exc:
            logger.debug('启动图片发送结果监听失败: %s', exc)
        return ''

    def _image_send_watch_succeeded(self, token: str) -> bool:
        if not token:
            return False
        try:
            return bool(self._page.evaluate(CHECK_IMAGE_SEND_WATCH_JS, token))
        except Exception:
            return False

    def _conversation_preview(self, nickname: str) -> str:
        try:
            return str(self._page.evaluate(GET_CONVERSATION_PREVIEW_JS, nickname) or '').strip()
        except Exception:
            return ''

    def _verify_image_sent_in_preview(
        self, nickname: str, previous_preview: str = '', timeout: float = 2.5,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            try:
                if self._page.evaluate(
                    VERIFY_IMAGE_SENT_IN_PREVIEW_JS, [nickname, previous_preview],
                ):
                    return True
            except Exception:
                pass
            if self._sleep(0.15):
                return False
        return False

    def _outgoing_chat_image_count(self) -> int:
        try:
            return int(self._page.evaluate(OUTGOING_CHAT_IMAGE_COUNT_JS) or 0)
        except Exception:
            return 0

    def _newest_outgoing_chat_image_src(self) -> str:
        try:
            return str(self._page.evaluate(NEWEST_OUTGOING_CHAT_IMAGE_SRC_JS) or '').strip()
        except Exception:
            return ''

    @staticmethod
    def _is_confirmed_image_src(src: str) -> bool:
        src = (src or '').strip().lower()
        if not src or src.startswith('blob:'):
            return False
        return (
            src.startswith('https://')
            or src.startswith('http://')
            or src.startswith('data:image/')
        )

    def _wait_outgoing_image_count_stable(self, timeout: float = 3.0) -> int:
        deadline = time.time() + timeout
        last = -1
        stable_reads = 0
        while time.time() < deadline:
            if self._abort:
                return max(last, 0)
            count = self._outgoing_chat_image_count()
            if count == last:
                stable_reads += 1
                if stable_reads >= 3:
                    return count
            else:
                last = count
                stable_reads = 0
            if self._sleep(0.2):
                return max(last, 0)
        return max(last, 0)

    def _poll_outgoing_chat_image_increase(
        self, before: int, before_newest_src: str = '', timeout: float = 18.0,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            count = self._outgoing_chat_image_count()
            if count > before:
                src = self._newest_outgoing_chat_image_src()
                if self._is_confirmed_image_src(src) and src != (before_newest_src or ''):
                    return True
            if self._sleep(0.25):
                return False
        return False

    def _outgoing_chat_image_signatures(self) -> set:
        try:
            sigs = self._page.evaluate(OUTGOING_CHAT_IMAGE_SIGNATURES_JS) or []
            return {str(s) for s in sigs if s}
        except Exception:
            return set()

    def _click_image_send_confirm(self) -> bool:
        try:
            if bool(self._page.evaluate(CLICK_IMAGE_PREVIEW_SEND_JS)):
                return True
        except Exception as exc:
            logger.debug('点击图片预览发送按钮失败: %s', exc)
        try:
            if bool(self._page.evaluate(CLICK_IMAGE_SEND_CONFIRM_JS)):
                return True
        except Exception as exc:
            logger.debug('点击图片发送确认按钮失败: %s', exc)
        try:
            self._page.keyboard.press('Enter')
        except Exception:
            pass
        return False

    def _poll_new_outgoing_chat_image(
        self, baseline_sigs: set, timeout: float = 18.0,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            current = self._outgoing_chat_image_signatures()
            for sig in current:
                if sig in baseline_sigs:
                    continue
                if self._is_confirmed_image_src(sig):
                    return True
            if self._sleep(0.25):
                return False
        return False

    def _wait_for_image_sent(
        self, watch_token: str, before_count: int, timeout: float,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort:
                return False
            if self._outgoing_chat_image_count() > before_count:
                return True
            if self._sleep(0.2):
                return False
        return False

    @staticmethod
    def _image_input_score(candidate) -> int:
        """优先选择聊天编辑器附近、明确接受图片的文件输入框。"""
        try:
            return int(candidate.evaluate("""
                (el) => {
                  let score = 0;
                  const accept = (el.getAttribute('accept') || '').toLowerCase();
                  if (accept.includes('image') || /\\.(png|jpe?g|gif|webp)/.test(accept)) score += 100;
                  if (accept === '*/*') score += 20;
                  let parent = el.parentElement;
                  for (let depth = 0; depth < 7 && parent; depth++, parent = parent.parentElement) {
                    const cls = (parent.className || '').toString().toLowerCase();
                    const action = (parent.getAttribute('data-apm-action') || '').toLowerCase();
                    if (/msginput|chat|editor|message/.test(cls)) score += 40 - depth;
                    if (/选择文件|上传|图片/.test(action + ' ' + (parent.getAttribute('aria-label') || ''))) {
                      score += 60 - depth;
                    }
                    if (parent.querySelector && parent.querySelector(
                      '[contenteditable="true"], [contenteditable="plaintext-only"], textarea[placeholder*="发送"]'
                    )) score += 50 - depth;
                  }
                  return score;
                }
            """) or 0)
        except Exception:
            return 0

    def _upload_and_send_image(
        self, image_path: str,
        baseline_sigs: Optional[set] = None,
        **_legacy: Any,
    ) -> bool:
        """通过抖音的“选择文件”控件上传图片，以聊天区新增己方图片签名为成功依据。"""
        if not self._page or not os.path.isfile(image_path):
            return False
        if baseline_sigs is None:
            if self._sleep(0.3):
                return False
            baseline_sigs = self._outgoing_chat_image_signatures()
        uploaded = False
        try:
            file_inputs = self._page.locator('input[type="file"]')
            candidates = []
            for index in range(file_inputs.count()):
                candidate = file_inputs.nth(index)
                accept = (candidate.get_attribute('accept') or '').lower()
                accepts_image = (
                    not accept or accept == '*/*' or 'image' in accept
                    or any(ext in accept for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'))
                )
                if not accepts_image:
                    continue
                candidates.append((self._image_input_score(candidate), index, candidate))
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            for _score, _index, candidate in candidates:
                try:
                    candidate.set_input_files(image_path, timeout=10000)
                    uploaded = True
                    break
                except Exception as exc:
                    logger.debug('设置候选图片文件输入失败: %s', exc)
        except Exception as exc:
            logger.debug('直接设置抖音图片文件失败: %s', exc)

        if not uploaded:
            try:
                trigger = self._page.locator(
                    '[data-apm-action="选择文件"], svg.MsgInputFileUploadinputActionIcon'
                ).first
                with self._page.expect_file_chooser(timeout=5000) as chooser_info:
                    trigger.click(timeout=5000)
                chooser_info.value.set_files(image_path)
                uploaded = True
            except Exception as exc:
                logger.warning('未找到抖音图片上传控件: %s', exc)
                return False

        # 选图后常出现本地预览/待发送态，旧逻辑会把其误判为已发送。
        if self._sleep(0.35):
            return False
        self._click_image_send_confirm()
        if self._poll_new_outgoing_chat_image(baseline_sigs, timeout=15.0):
            return True

        self._click_image_send_confirm()
        if self._poll_new_outgoing_chat_image(baseline_sigs, timeout=10.0):
            return True

        logger.warning(
            '图片上传后聊天区未出现新的己方图片（baseline=%s current=%s）',
            len(baseline_sigs),
            len(self._outgoing_chat_image_signatures()),
        )
        return False

    def _op_send_text(
        self, nickname: str, text: str, category: str = 'friend', from_panel: bool = False,
        conversation_open: bool = False,
    ) -> bool:
        started_at = time.monotonic()
        self._last_send_error = ''
        self._last_conversation_click_debug = ''
        if not text.strip() or self._abort:
            self._last_send_error = '发送内容为空或操作已取消'
            return False
        if not conversation_open and not self._ensure_message_page_for_send():
            self._last_send_error = f'私信面板未就绪（{time.monotonic() - started_at:.1f} 秒）'
            logger.warning('无法进入抖音私信页，无法发送')
            return False

        opened = conversation_open
        if not conversation_open:
            opened = self._op_open_conversation(
                nickname, category=category, from_panel=from_panel,
            )
        if not opened:
            open_detail = self._last_open_error or '无法打开目标会话'
            click_detail = (
                f'；{self._last_conversation_click_debug}'
                if self._last_conversation_click_debug else ''
            )
            self._last_send_error = (
                f'{open_detail}（{time.monotonic() - started_at:.1f} 秒{click_detail}）'
            )
            logger.warning('打开发送会话失败: %s (%s)', nickname, category)
            return False

        # Keep the open-conversation state and return the send result immediately.
        # The next list_conversations operation already knows how to close the
        # conversation. Doing that recovery in this call used to turn a successful
        # send into a false 45-second timeout when Douyin's UI was slow.
        self._conversation_open = True
        editor_timeout = 4.5 if from_panel else 3.0
        if not conversation_open:
            if self._sleep(0.28 if from_panel else 0.35):
                return False
            if not self._wait_for_chat_editor(timeout=editor_timeout):
                self._last_send_error = f'聊天输入框未就绪（{time.monotonic() - started_at:.1f} 秒）'
                logger.warning('聊天输入框未就绪: %s', nickname)
                return False
        elif self._sleep(0.04):
            return False

        sent = self._fill_and_send_message(text, nickname=nickname)
        if not sent:
            # _fill_and_send_message 已完成键盘、按钮和 JS 三种发送路径；
            # 不再把空输入框误报为成功，也不在这里重复提交。
            if self._sleep(0.12):
                return False
        if not sent:
            self._last_send_error = f'页面未出现新发送气泡（{time.monotonic() - started_at:.1f} 秒）'
            logger.warning('消息未出现在聊天记录中，发送可能失败: %s', nickname)
        else:
            logger.info('抖音文字回复已确认: %s（%.1f 秒）', nickname, time.monotonic() - started_at)
        return sent

    def _op_send_image(
        self, nickname: str, image_path: str, category: str = 'friend',
        from_panel: bool = False, conversation_open: bool = False,
    ) -> bool:
        image_path = os.path.abspath(os.path.normpath(image_path or ''))
        if not os.path.isfile(image_path) or self._abort:
            return False
        sent = False
        try:
            if not conversation_open and not self._ensure_message_page_for_send():
                logger.warning('无法进入抖音私信面板，无法发送图片')
                return False
            opened = conversation_open
            if not opened:
                opened = self._op_open_conversation(
                    nickname, category=category, from_panel=from_panel,
                )
                if not opened and from_panel:
                    opened = self._op_open_conversation(
                        nickname, category=category, from_panel=False,
                    )
            if not opened:
                logger.warning('打开图片发送会话失败: %s (%s)', nickname, category)
                return False
            if not self._wait_for_chat_editor(timeout=4.5):
                logger.warning('图片发送会话编辑器未就绪: %s', nickname)
                return False
            if self._sleep(0.3):
                return False
            baseline_sigs = self._outgoing_chat_image_signatures()
            sent = self._upload_and_send_image(image_path, baseline_sigs=baseline_sigs)
        finally:
            self._return_to_message_list(fast=True)
            self._messages_panel_ready = self._is_message_panel_visible()

        if not sent:
            logger.warning('图片消息未出现在聊天记录或会话预览中: %s', nickname)
        return sent


    def _op_close_browser(self) -> Dict[str, Any]:
        self._cleanup_browser()
        self._current_headless = None
        return {'ok': True}
