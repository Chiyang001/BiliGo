"""
BiliGo 抖音私信自动回复模块
通过 Playwright 控制 Chromium：手动登录 → 识别账号 → 监控私信 → 关键词回复
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import jsonify, request, send_from_directory, Response

from app_paths import get_app_root, get_static_root
from ai_conversation_store import ai_conversation_store
from ai_handoff_store import ai_handoff_store
from ai_reply_service import (
    build_conversation_context,
    generate_reply_decision as generate_ai_decision,
    platform_enabled,
    record_conversation_exchange,
)
from dashboard_metrics import dashboard_metrics, record_dashboard_event
from douyin_playwright import DouyinBrowserWorker, extract_avatar_from_storage

logger = logging.getLogger(__name__)

STORAGE_SESSION_COOKIES = {
    'sessionid', 'sessionid_ss', 'sid_guard', 'sid_ucp_v1', 'sid_tt', 'ssid_ucp_v1',
}

BROWSER_PROFILE_DIRS = {
    'douyin': 'douyin_browser_profile',
    'xiaohongshu': 'xiaohongshu_browser_profile',
    'weibo': 'weibo_browser_profile',
    'xianyu': 'xianyu_browser_profile',
}
DEFAULT_CONFIG = {
    'default_reply_enabled': False,
    'default_reply_message': '您好，我现在不在，稍后会回复您的消息。',
    'default_reply_type': 'text',
    'default_reply_image': '',
    'message_check_interval': 0.3,
    'send_delay_interval': 0.3,
    'only_reply_new_messages': True,
    'max_replies_per_user': 3,
    'unlimited_replies_per_user': False,
    'headless': True,
    # 监控状态只属于当前进程；后端重启后必须由用户重新手动启动。
    'auto_start_monitoring': False,
    'account': {},
    'logged_in': False,
    'session_expired': False,
    'login_time': '',
}

DEFAULT_RULE = {
    'name': '示例规则',
    'keyword': '你好',
    'reply': '您好！感谢私信，我会尽快回复~',
    'reply_type': 'text',
    'reply_image': '',
    'enabled': True,
}

DOUYIN_EXPORTABLE_CONFIG_KEYS = (
    'default_reply_enabled',
    'default_reply_message',
    'default_reply_type',
    'default_reply_image',
    'message_check_interval',
    'send_delay_interval',
    'only_reply_new_messages',
    'max_replies_per_user',
    'unlimited_replies_per_user',
    'headless',
    'auto_start_monitoring',
)


def _get_app_version() -> str:
    try:
        from app import APP_VERSION
        return APP_VERSION
    except Exception:
        return 'V3 Ultra'


class DouyinReplySystem:
    ai_platform_key = 'douyin'
    image_replies_enabled = False
    def __init__(self):
        self.config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.rules: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self.monitoring = False
        self.login_in_progress = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.program_start_time = int(time.time())
        self.message_cache: Dict[str, bool] = {}
        self.last_message_times: Dict[str, int] = defaultdict(int)
        self.last_seen_preview: Dict[str, str] = {}
        self.last_seen_unread: Dict[str, int] = {}
        self.last_seen_message_token: Dict[str, str] = {}
        self._sent_reply_texts: Dict[str, set] = {}
        self._last_image_reply_at: Dict[str, float] = {}
        self._recently_handled_raw: Dict[str, float] = {}
        self._send_retry_counts: Dict[str, int] = {}
        self._send_retry_after: Dict[str, float] = {}
        self._baseline_initialized = False
        self.user_reply_stats: Dict[str, Any] = {}
        self.rule_matcher_cache: Dict[int, Dict[str, Any]] = {}
        self.last_send_time = 0.0
        self._lock = threading.Lock()
        self._monitor_stop = threading.Event()
        self._session_verify_thread: Optional[threading.Thread] = None
        self._log_dedupe_times: Dict[tuple, float] = {}
        self._browser_use_lock = threading.Lock()
        self._browser: Optional[DouyinBrowserWorker] = None
        self._login_generation = 0
        self._monitor_list_ready = False
        self.config_file: Optional[str] = None
        self.rules_file: Optional[str] = None
        self.storage_file: Optional[str] = None
        self.stats_file: Optional[str] = None

    # ── paths ─────────────────────────────────────────────────────

    def _init_paths(self) -> None:
        root = get_app_root()
        if self.config_file is None:
            self.config_file = os.path.join(root, 'douyin_config.json')
        if self.rules_file is None:
            self.rules_file = os.path.join(root, 'douyin_keywords.json')
        if self.storage_file is None:
            self.storage_file = os.path.join(root, 'douyin_storage.json')
        if self.stats_file is None:
            self.stats_file = os.path.join(root, 'douyin_user_reply_stats.json')

    def _ensure_browser(self, headless: Optional[bool] = None) -> DouyinBrowserWorker:
        self._init_paths()
        if self._browser is None:
            self._browser = DouyinBrowserWorker(
                storage_path=self.storage_file,
                headless=headless if headless is not None else bool(self.config.get('headless', True)),
            )
        elif headless is not None:
            self._browser.set_headless(headless)
        account = self.config.get('account') or {}
        self._browser.set_account_identity(
            uid=str(account.get('uid') or ''),
            nickname=str(account.get('nickname') or ''),
        )
        return self._browser

    # ── persistence ───────────────────────────────────────────────

    def _storage_has_session_cookies(self) -> bool:
        """从已保存的 storage 文件判断是否存在登录会话 Cookie"""
        self._init_paths()
        if not os.path.exists(self.storage_file or ''):
            return False
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            names = {str(c.get('name') or '') for c in (state.get('cookies') or [])}
            return bool(STORAGE_SESSION_COOKIES & names)
        except Exception:
            return False

    def _enrich_account_from_storage(self) -> None:
        """从 storage 文件补全账号头像等信息。"""
        self._init_paths()
        account = dict(self.config.get('account') or {})
        if account.get('avatar'):
            return
        avatar = extract_avatar_from_storage(self.storage_file or '')
        if avatar:
            account['avatar'] = avatar
            self.config['account'] = account

    def load_config(self) -> None:
        self._init_paths()
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                self.config.update(saved)
            except Exception as exc:
                logger.error('加载抖音配置失败: %s', exc)
        if self._storage_has_session_cookies():
            account = self.config.get('account') or {}
            if account.get('nickname') or account.get('uid'):
                self.config['logged_in'] = True
                self.config['session_expired'] = False
            self._enrich_account_from_storage()
        elif not self.config.get('logged_in'):
            self.config['session_expired'] = False
        if self._disable_legacy_image_config():
            self.save_config()

    def _disable_legacy_image_config(self) -> bool:
        """Safely retire saved image replies without affecting Bilibili settings."""
        changed = False
        if self.config.get('default_reply_type') == 'image':
            self.config['default_reply_type'] = 'text'
            self.config['default_reply_enabled'] = False
            changed = True
        if self.config.get('default_reply_image'):
            self.config['default_reply_image'] = ''
            changed = True
        return changed

    def _disable_legacy_image_rules(self) -> bool:
        changed = False
        for rule in self.rules:
            if not isinstance(rule, dict):
                continue
            if rule.get('reply_type') == 'image':
                rule['reply_type'] = 'text'
                rule['reply'] = ''
                rule['enabled'] = False
                changed = True
            if rule.get('reply_image'):
                rule['reply_image'] = ''
                changed = True
        return changed

    def _mark_session_expired(self) -> None:
        if self._storage_has_session_cookies():
            logger.warning('跳过将会话标记为失效：本地仍存在登录 Cookie')
            return
        self.config['logged_in'] = False
        self.config['session_expired'] = True
        self.save_config()
        self.add_log('登录状态已失效，请重新登录', 'warning')

    def _mark_session_valid(self, account: Optional[Dict[str, Any]] = None) -> None:
        self.config['logged_in'] = True
        self.config['session_expired'] = False
        if account:
            self.config['account'] = account
        self._enrich_account_from_storage()
        self.save_config()

    def _abort_session_verify(self) -> None:
        """中止后台会话验证，把浏览器让给监控线程。"""
        if self._browser:
            self._browser.set_abort(True)
        thread = self._session_verify_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=6)
        if self._browser:
            self._browser.set_abort(False)

    def verify_session(self, background: bool = False, quick: bool = False) -> bool:
        """验证已保存的登录态。quick=True 时仅读本地 storage，不占用浏览器。"""
        self._init_paths()
        if not os.path.exists(self.storage_file):
            return False
        if self.monitoring and background:
            return bool(self.config.get('logged_in'))

        def _verify_quick() -> bool:
            if not self._storage_has_session_cookies():
                return False
            self._enrich_account_from_storage()
            was_valid = bool(self.config.get('logged_in')) and not self.config.get('session_expired')
            self._mark_session_valid(self.config.get('account'))
            if not was_valid:
                nick = (self.config.get('account') or {}).get('nickname') or '已登录'
                self.add_log(f'已恢复登录会话：{nick}', 'success')
            return True

        def _verify_browser() -> bool:
            with self._browser_use_lock:
                try:
                    browser = self._ensure_browser(headless=True)
                    browser.set_abort(False)
                    browser.start_worker()
                    if browser.check_session_valid():
                        try:
                            account = browser.get_account()
                            info = account.to_dict() if hasattr(account, 'to_dict') else {}
                            if info.get('nickname') or info.get('uid'):
                                self.config['account'] = info
                        except Exception:
                            pass
                        self._mark_session_valid()
                        nick = (self.config.get('account') or {}).get('nickname') or '已登录'
                        self.add_log(f'已恢复登录会话：{nick}', 'success')
                        return True
                    if self._storage_has_session_cookies():
                        self._mark_session_valid(self.config.get('account'))
                        nick = (self.config.get('account') or {}).get('nickname') or '已登录'
                        self.add_log(f'已恢复本地登录会话：{nick}', 'info')
                        return True
                    self._mark_session_expired()
                    return False
                except Exception as exc:
                    logger.warning('会话验证失败: %s', exc)
                    if self._storage_has_session_cookies():
                        self._mark_session_valid(self.config.get('account'))
                        return True
                    self._mark_session_expired()
                    return False

        def _verify():
            if quick or self._storage_has_session_cookies():
                if _verify_quick():
                    return
            _verify_browser()

        if background:
            if self._session_verify_thread and self._session_verify_thread.is_alive():
                return bool(self.config.get('logged_in'))
            self._session_verify_thread = threading.Thread(target=_verify, daemon=True)
            self._session_verify_thread.start()
            return bool(self.config.get('logged_in'))

        _verify()
        return bool(self.config.get('logged_in') and not self.config.get('session_expired'))

    def init_on_startup(self) -> None:
        """应用启动时加载配置并在后台验证会话，监控始终保持关闭。"""
        self.load_config()
        self.load_rules()
        # 兼容旧版本遗留的自动启动标记。登录状态可以恢复，监控状态不能恢复。
        if self.config.get('auto_start_monitoring') is not False:
            self.config['auto_start_monitoring'] = False
            self.save_config()
        if os.path.exists(self.storage_file or ''):
            self.verify_session(background=True, quick=True)

    def save_config(self) -> None:
        self._init_paths()
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def load_rules(self) -> None:
        self._init_paths()
        if os.path.exists(self.rules_file):
            try:
                with open(self.rules_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.rules = data if isinstance(data, list) else data.get('rules', [])
            except Exception as exc:
                logger.error('加载抖音规则失败: %s', exc)
        else:
            self.rules = [dict(DEFAULT_RULE)]
            self.save_rules()
        if self._disable_legacy_image_rules():
            self.save_rules()
        self.precompile_rules()

    def save_rules(self) -> None:
        self._init_paths()
        with open(self.rules_file, 'w', encoding='utf-8') as f:
            json.dump(self.rules, f, ensure_ascii=False, indent=2)

    def load_stats(self) -> None:
        self._init_paths()
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.user_reply_stats = json.load(f)
            except Exception:
                self.user_reply_stats = {}

    def save_stats(self) -> None:
        self._init_paths()
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.user_reply_stats, f, ensure_ascii=False, indent=2)

    # ── logging ───────────────────────────────────────────────────

    def add_log(self, message: str, log_type: str = 'info', dedupe_seconds: float = 0) -> None:
        auto_dedupe_prefixes = (
            '正在扫描私信会话列表',
            '暂未读取到会话列表',
        )
        if dedupe_seconds <= 0 and any(message.startswith(prefix) for prefix in auto_dedupe_prefixes):
            dedupe_seconds = 90.0
        if dedupe_seconds > 0:
            now = time.time()
            dedupe_key = (message[:100], log_type)
            last_at = self._log_dedupe_times.get(dedupe_key)
            if last_at is not None and (now - last_at) < dedupe_seconds:
                return
            self._log_dedupe_times[dedupe_key] = now

        entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'message': message,
            'type': log_type,
        }
        self.logs.insert(0, entry)
        if len(self.logs) > 200:
            self.logs = self.logs[:200]
        getattr(logger, log_type if log_type in ('info', 'warning', 'error', 'debug') else 'info')(message)
        if log_type == 'error':
            try:
                from app import send_platform_error_notification
                threading.Thread(target=send_platform_error_notification, args=(self.ai_platform_key, message), daemon=True).start()
            except Exception as exc:
                logger.debug('启动平台邮件提醒失败: %s', exc)

    # ── rules ─────────────────────────────────────────────────────

    def precompile_rules(self) -> None:
        self.rule_matcher_cache = {}
        for i, rule in enumerate(self.rules):
            if not rule.get('enabled', True):
                continue
            keyword_str = rule.get('keyword', '')
            keywords = [kw.lower().strip() for kw in keyword_str.replace('，', ',').split(',') if kw.strip()]
            self.rule_matcher_cache[i] = {
                'keywords': keywords,
                'reply': rule.get('reply', ''),
                'reply_type': rule.get('reply_type', 'text'),
                'reply_image': rule.get('reply_image', ''),
                'title': rule.get('name', f'规则{i + 1}'),
            }

    def match_rule(self, message: str) -> Optional[Dict[str, Any]]:
        if not message or not self.rule_matcher_cache:
            return None
        msg = message.lower().strip()
        for rule_data in self.rule_matcher_cache.values():
            for kw in sorted(rule_data['keywords'], key=len, reverse=True):
                if kw and kw in msg:
                    return rule_data
        return None

    def generate_message_id(self, conv_key: str, text: str) -> str:
        digest = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
        return f'{conv_key}_{digest}'

    def get_user_reply_count(self, user_key: str) -> int:
        rec = self.user_reply_stats.get(user_key) or {}
        return int(rec.get('count') or 0)

    def _get_user_reply_limit(self) -> Optional[int]:
        """返回单用户回复上限；None 表示不限制。"""
        if self.config.get('unlimited_replies_per_user') is True:
            return None
        try:
            return max(1, int(self.config.get('max_replies_per_user') or 3))
        except (TypeError, ValueError):
            return 3

    def increment_user_reply_count(self, user_key: str) -> int:
        rec = self.user_reply_stats.setdefault(user_key, {'count': 0, 'last_reply_time': 0})
        rec['count'] = int(rec.get('count') or 0) + 1
        rec['last_reply_time'] = int(time.time())
        self.save_stats()
        return rec['count']

    # ── login ─────────────────────────────────────────────────────

    def start_login(self) -> Dict[str, Any]:
        with self._lock:
            if self.login_in_progress:
                return {'success': False, 'error': '登录窗口已在打开中'}
            if self.monitoring:
                return {'success': False, 'error': '请先停止监控再重新登录'}
            self.login_in_progress = True
            login_generation = self._login_generation

        # A startup/session verification job may still own the same browser and
        # navigate it to the message page. Stop it before presenting a login UI.
        self._abort_session_verify()

        def _login_task():
            try:
                browser = self._ensure_browser(headless=False)
                browser.set_abort(False)
                browser.start_worker()
                self.add_log('正在打开 Chromium 登录窗口，请在浏览器中完成抖音登录…', 'info')
                presentation = browser.open_login_window() or {}
                self.add_log(
                    presentation.get('message') or '请在登录窗口中完成抖音登录',
                    'info',
                )
                account = browser.wait_until_logged_in(timeout=300)
                with self._lock:
                    if login_generation != self._login_generation:
                        raise RuntimeError('登录操作已取消')
                self.config['account'] = account if isinstance(account, dict) else account.to_dict()
                self.config['login_time'] = datetime.now().isoformat()
                self._mark_session_valid(self.config['account'])
                browser.save_session()
                browser.restart_browser(headless=True)
                browser.warmup_messages()
                nick = self.config['account'].get('nickname') or self.config['account'].get('uid') or '未知'
                self.add_log(f'抖音登录成功：{nick}（会话已保存，后续将后台运行）', 'success')
            except Exception as exc:
                with self._lock:
                    cancelled = login_generation != self._login_generation
                if cancelled or str(exc) == '登录操作已取消':
                    self.add_log('抖音登录操作已取消', 'info')
                else:
                    self.add_log(f'抖音登录失败: {exc}', 'error')
            finally:
                with self._lock:
                    self.login_in_progress = False

        threading.Thread(target=_login_task, daemon=True).start()
        return {
            'success': True,
            'message': '已打开 Chromium 窗口，请完成登录（扫码/密码），系统将自动检测',
        }

    def get_login_status(self) -> Dict[str, Any]:
        if not (self.config.get('account') or {}).get('avatar'):
            self._enrich_account_from_storage()
        account = self.config.get('account') or {}
        has_saved = self._storage_has_session_cookies()
        if has_saved and (account.get('nickname') or account.get('uid')):
            logged_in = not self.config.get('session_expired')
        else:
            logged_in = bool(self.config.get('logged_in')) and not self.config.get('session_expired')
        return {
            'login_in_progress': self.login_in_progress,
            'logged_in': logged_in,
            'session_expired': bool(self.config.get('session_expired')) and not has_saved,
            'account': account,
            'login_time': self.config.get('login_time', ''),
            'browser_alive': self._browser.is_browser_alive() if self._browser else False,
            'has_saved_session': os.path.exists(self.storage_file or ''),
        }

    def refresh_account_info(self) -> Dict[str, Any]:
        """重新从浏览器提取账号信息"""
        if self.config.get('session_expired'):
            return {'success': False, 'error': '登录状态已失效，请重新登录'}
        if not self.config.get('logged_in') and not os.path.exists(self.storage_file or ''):
            return {'success': False, 'error': '尚未登录'}
        try:
            with self._browser_use_lock:
                browser = self._ensure_browser(headless=True)
                browser.set_abort(False)
                browser.start_worker()
                if not browser.check_session_valid():
                    if self._storage_has_session_cookies():
                        self._mark_session_valid(self.config.get('account'))
                    else:
                        self._mark_session_expired()
                        return {'success': False, 'error': '登录状态已失效，请重新登录'}
                account = browser.get_account()
            info = account.to_dict() if hasattr(account, 'to_dict') else dict(account or {})
            if not info.get('avatar'):
                avatar = extract_avatar_from_storage(self.storage_file or '')
                if avatar:
                    info['avatar'] = avatar
            self.config['account'] = info
            self.config['logged_in'] = True
            self.save_config()
            nick = info.get('nickname') or info.get('uid') or '未知'
            self.add_log(f'账号信息已刷新：{nick}', 'success')
            return {'success': True, 'account': info}
        except Exception as exc:
            self.add_log(f'刷新账号信息失败: {exc}', 'error')
            return {'success': False, 'error': str(exc)}

    def logout(self) -> Dict[str, Any]:
        self.stop_monitoring()
        self._abort_session_verify()
        with self._lock:
            # Invalidate a concurrently running login task before touching its
            # persistent profile, otherwise it could save cookies again after
            # the user has clicked logout.
            self._login_generation += 1
            self.login_in_progress = False
        if self._browser:
            try:
                self._browser.set_abort(True)
                self._browser.close_browser()
                self._browser.stop_worker()
            except Exception:
                pass
            self._browser = None
        self._init_paths()

        clear_errors = []
        if self.storage_file and os.path.exists(self.storage_file):
            try:
                os.remove(self.storage_file)
            except Exception as exc:
                clear_errors.append(f'会话文件删除失败: {exc}')

        profile_name = BROWSER_PROFILE_DIRS.get(self.ai_platform_key)
        if profile_name:
            app_root = os.path.realpath(get_app_root())
            profile_dir = os.path.realpath(os.path.join(app_root, profile_name))
            if os.path.dirname(profile_dir) != app_root:
                clear_errors.append('浏览器 Profile 路径校验失败')
            elif os.path.isdir(profile_dir):
                last_error = None
                for attempt in range(5):
                    try:
                        shutil.rmtree(profile_dir)
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        time.sleep(0.2 * (attempt + 1))
                if os.path.exists(profile_dir):
                    clear_errors.append(f'浏览器登录数据删除失败: {last_error}')

        self.config['logged_in'] = False
        self.config['session_expired'] = False
        self.config['account'] = {}
        self.config['login_time'] = ''
        self.save_config()
        if clear_errors:
            error = '；'.join(clear_errors)
            self.add_log(f'退出登录时未能完全清除数据：{error}', 'error')
            return {'success': False, 'error': error}
        self.add_log('已退出抖音登录，浏览器登录数据已清除', 'info')
        return {'success': True, 'message': '已退出登录，浏览器登录数据已清除'}

    def reset_all_data(self) -> Dict[str, Any]:
        """清除抖音模块全部数据并恢复初始设置。"""
        self.stop_monitoring()
        dashboard_metrics.clear_platform(self.ai_platform_key)
        ai_handoff_store.clear_platform(self.ai_platform_key)
        ai_conversation_store.clear_platform(self.ai_platform_key)
        if self._browser:
            try:
                self._browser.close_browser()
                self._browser.stop_worker()
            except Exception:
                pass
            self._browser = None

        self._init_paths()
        for path in (self.storage_file, self.stats_file):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as exc:
                    logger.warning('删除文件失败 %s: %s', path, exc)

        profile_dir = os.path.join(get_app_root(), 'douyin_browser_profile')
        if os.path.isdir(profile_dir):
            try:
                shutil.rmtree(profile_dir)
            except Exception as exc:
                logger.warning('清除浏览器 Profile 失败: %s', exc)

        reply_image_dir = os.path.join(get_app_root(), 'douyin_media', 'reply_images')
        if os.path.isdir(reply_image_dir):
            try:
                shutil.rmtree(reply_image_dir)
            except Exception as exc:
                logger.warning('清除抖音回复图片失败: %s', exc)

        self.config = dict(DEFAULT_CONFIG)
        self.rules = [dict(DEFAULT_RULE)]
        self.user_reply_stats = {}
        self.logs = []
        self.message_cache = {}
        self.last_message_times = defaultdict(int)
        self.last_seen_preview = {}
        self.last_seen_unread = {}
        self.last_seen_message_token = {}
        self._sent_reply_texts = {}
        self._last_image_reply_at = {}
        self._recently_handled_raw = {}
        self._send_retry_counts = {}
        self._send_retry_after = {}
        self._baseline_initialized = False
        self._monitor_list_ready = False
        self.rule_matcher_cache = {}
        self.last_send_time = 0.0
        self.login_in_progress = False
        self.program_start_time = int(time.time())

        self.save_config()
        self.save_rules()
        self.save_stats()
        self.precompile_rules()
        self.add_log('所有抖音数据已清除，系统已恢复初始设置', 'warning')
        return {'success': True, 'message': '所有抖音数据已清除，系统已恢复初始设置'}

    # ── monitor ───────────────────────────────────────────────────

    def _parse_preview_message(self, preview: str, sender: str = '') -> str:
        """从会话列表预览解析消息，如「炽阳002: 你好」"""
        preview = (preview or '').strip()
        if not preview:
            return ''
        preview = self._strip_preview_noise(preview)
        sep = ':' if ':' in preview else ('：' if '：' in preview else None)
        if sep:
            parts = preview.split(sep, 1)
            if len(parts) == 2:
                nick, msg = parts[0].strip(), parts[1].strip()
                msg = self._strip_preview_noise(msg)
                if msg and (not sender or nick == sender):
                    return msg
        return preview

    @staticmethod
    def _strip_preview_noise(text: str) -> str:
        text = (text or '').strip()
        patterns = (
            r'^刚刚\s*',
            r'^昨天\s*',
            r'^前天\s*',
            r'^\d+分钟前\s*',
            r'^\d+小时前\s*',
            r'^\d{1,2}:\d{2}\s*',
            r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}\s*',
            r'^\d{1,3}\s+',
            r'\s+\d{1,3}$',
        )
        for _ in range(3):
            before = text
            for pat in patterns:
                text = re.sub(pat, '', text)
            text = text.strip()
            if text == before:
                break
        return text

    def _conv_user_key(self, conv) -> str:
        category = getattr(conv, 'category', 'friend') or 'friend'
        nickname = (conv.nickname or '').strip()
        sender = (getattr(conv, 'sender_nickname', '') or nickname).strip()
        target_nick = sender if category == 'stranger' else nickname
        return str(conv.conv_id or f'{category}:{target_nick}')

    def _raw_preview(self, conv) -> str:
        return (conv.last_message or '').strip()

    @staticmethod
    def _conversation_message_token(conv) -> str:
        """Return the strongest available identity for the latest conversation event."""
        for field in ('message_id', 'max_store_id', 'last_msg_time', 'update_time'):
            value = getattr(conv, field, None)
            if value not in (None, '', 0, '0'):
                return f'{field}:{value}'
        return ''

    def _remember_conversation_state(
        self, user_key: str, conv: Any, raw_preview: Optional[str] = None,
    ) -> None:
        self.last_seen_preview[user_key] = (
            self._raw_preview(conv) if raw_preview is None else raw_preview
        )
        self.last_seen_unread[user_key] = int(getattr(conv, 'unread', 0) or 0)
        token = self._conversation_message_token(conv)
        if token:
            self.last_seen_message_token[user_key] = token

    def _incoming_text(self, conv) -> str:
        sender = (getattr(conv, 'sender_nickname', '') or conv.nickname or '').strip()
        return self._parse_preview_message(self._raw_preview(conv), sender)

    def _should_use_direct_preview(self, conv, has_unread: bool) -> bool:
        """返回 True 时直接使用会话列表预览，不进入聊天页判向。"""
        return bool(has_unread)

    def _message_preview(self, conv) -> str:
        return (getattr(conv, 'last_message', None) or self._raw_preview(conv) or '').strip()

    def _fallback_incoming_text(self, conv) -> str:
        return ''

    def _postprocess_incoming_text(self, conv, msg_text: str, browser: Any = None) -> str:
        return (msg_text or '').strip()

    def _initialize_baseline(self, conversations: List[Any]) -> None:
        """记录启动时会话列表预览，用于「仅回复新消息」。"""
        count = 0
        for conv in conversations:
            nickname = (conv.nickname or '').strip()
            if not nickname or nickname == '陌生人消息':
                continue
            user_key = self._conv_user_key(conv)
            raw = self._raw_preview(conv)
            self._remember_conversation_state(user_key, conv, raw)
            if raw:
                count += 1
        self._baseline_initialized = True
        self.add_log(f'已记录 {count} 个会话基线，仅回复启动后的新消息', 'info')

    def _is_phantom_conversation(self, conv) -> bool:
        """过滤 DOM 误解析出的幽灵会话（如把回复预览当成新会话）。"""
        nickname = (conv.nickname or '').strip()
        if not nickname or nickname == '陌生人消息':
            return True
        if re.fullmatch(r'\d{1,3}', nickname):
            return True
        all_sent = set()
        for texts in self._sent_reply_texts.values():
            all_sent.update(texts)
        if nickname in all_sent:
            return True
        msg = self._incoming_text(conv)
        if msg and re.fullmatch(r'\d{1,3}', msg):
            return True
        return False

    def _preview_contains_reply(self, raw_fp: str, reply_text: str) -> bool:
        reply_text = (reply_text or '').strip()
        raw_fp = (raw_fp or '').strip()
        if not reply_text or not raw_fp:
            return False
        cleaned = self._strip_preview_noise(raw_fp)
        return reply_text in cleaned or reply_text in raw_fp

    @staticmethod
    def _is_image_preview_text(text: str) -> bool:
        text = (text or '').strip()
        if not text:
            return False
        return bool(re.search(
            r'^\[图片\]$|^\[图片回复\]$|^图片$|发送了一张图片|发来一张图片|\[图片\]',
            text,
        ))

    def _note_own_image_reply(self, user_key: str, preview: str = '') -> None:
        """记录本方刚发出的图片回复，避免列表预览「[图片]」被当成对方新消息。"""
        self._last_image_reply_at[user_key] = time.time()
        sent_set = self._sent_reply_texts.setdefault(user_key, set())
        for marker in ('[图片]', '[图片回复]', '图片'):
            sent_set.add(marker)
        preview = (preview or '').strip()
        if preview:
            sent_set.add(preview)

    def _is_likely_own_image_preview(self, user_key: str, raw_fp: str, msg_text: str = '') -> bool:
        """判断列表预览变化是否由本方图片回复引起。"""
        candidates = {
            (raw_fp or '').strip(),
            self._strip_preview_noise(raw_fp or ''),
            (msg_text or '').strip(),
        }
        if not any(self._is_image_preview_text(text) for text in candidates if text):
            return False
        last_at = self._last_image_reply_at.get(user_key)
        if last_at is not None and (time.time() - last_at) < 120:
            return True
        sent = self._sent_reply_texts.get(user_key) or set()
        return bool({'[图片]', '[图片回复]'}.intersection(sent))

    def _mark_reply_handled(
        self, user_key: str, raw_fp: str, reply_text: str, dedupe_key: str,
    ) -> None:
        self.last_seen_preview[user_key] = raw_fp
        self._recently_handled_raw[dedupe_key] = time.time()
        sent_set = self._sent_reply_texts.setdefault(user_key, set())
        sent_set.add(reply_text.strip())

    def _is_own_outgoing_preview(self, user_key: str, raw_fp: str, msg_text: str) -> bool:
        """判断列表预览是否为本方刚发出的回复。"""
        if self._is_likely_own_image_preview(user_key, raw_fp, msg_text):
            return True
        sent = self._sent_reply_texts.get(user_key) or set()
        if msg_text in sent:
            return True
        if raw_fp in sent:
            return True
        for text in sent:
            if text and (text in raw_fp or text in msg_text):
                return True
        return False

    def _prune_stale_monitor_logs(self) -> None:
        stale_prefixes = (
            '正在扫描私信会话列表',
            '暂未读取到会话列表，将继续重试',
        )
        self.logs = [
            entry for entry in self.logs
            if not any(str(entry.get('message') or '').startswith(prefix) for prefix in stale_prefixes)
        ]

    def start_monitoring(self) -> Dict[str, Any]:
        if self.monitoring or (
            self.monitor_thread and self.monitor_thread.is_alive()
        ):
            return {'success': False, 'error': '监控已在运行中'}
        self._log_dedupe_times.clear()
        self._prune_stale_monitor_logs()
        self.load_config()
        if self.config.get('session_expired'):
            return {'success': False, 'error': '登录状态已失效，请重新登录'}
        if not os.path.exists(self.storage_file or ''):
            return {'success': False, 'error': '请先完成抖音登录'}
        if not self.config.get('logged_in'):
            if self._storage_has_session_cookies():
                self.config['logged_in'] = True
                self.config['session_expired'] = False
            elif not self.verify_session(background=False):
                return {'success': False, 'error': '登录状态已失效，请重新登录'}

        self._abort_session_verify()
        if self._session_verify_thread and self._session_verify_thread.is_alive():
            self._session_verify_thread.join(timeout=12)
        self._monitor_stop.clear()
        self.program_start_time = int(time.time())
        self.message_cache = {}
        self.last_seen_preview = {}
        self.last_seen_unread = {}
        self.last_seen_message_token = {}
        self._sent_reply_texts = {}
        self._last_image_reply_at = {}
        self._recently_handled_raw = {}
        self._send_retry_counts = {}
        self._send_retry_after = {}
        self._baseline_initialized = False
        self._monitor_list_ready = False
        self.load_rules()
        self.load_stats()
        self.monitoring = True
        self.config['auto_start_monitoring'] = False
        self.save_config()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.add_log('正在启动私信监控…', 'info')
        self.add_log('抖音私信监控已启动（后台无头模式）', 'success')
        return {'success': True, 'monitor_starting': True}

    def _try_mark_monitor_list_ready(
        self, browser: Any, conversations: List[Any], full_scan: bool,
    ) -> None:
        """Playwright 已成功读取私信会话列表（含空列表）后标记启动完成。"""
        if self._monitor_list_ready:
            return
        if conversations:
            self._monitor_list_ready = True
            return
        if not full_scan:
            return
        try:
            if getattr(browser, '_messages_panel_ready', False):
                self._monitor_list_ready = True
                return
            # Playwright sync objects belong to the browser worker thread. Always
            # query DOM state through its queue; calling the private helper here
            # crosses threads and can terminate Playwright's greenlet dispatcher.
            panel_ready = getattr(browser, 'is_message_panel_ready', None)
            if callable(panel_ready) and panel_ready():
                self._monitor_list_ready = True
        except Exception:
            pass

    def stop_monitoring(self) -> Dict[str, Any]:
        if not self.monitoring and not (
            self.monitor_thread and self.monitor_thread.is_alive()
        ):
            self._monitor_list_ready = False
            return {'success': True, 'message': '监控未在运行'}
        self.monitoring = False
        self._monitor_stop.set()
        self.config['auto_start_monitoring'] = False
        self.save_config()
        if self._browser:
            self._browser.set_abort(True)
        thread = self.monitor_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=12)
            if thread.is_alive():
                self.add_log('监控线程正在结束中，请稍候…', 'warning')
        self.monitor_thread = None
        self._monitor_list_ready = False
        if self._browser:
            self._browser.set_abort(False)
        self.add_log('抖音私信监控已停止', 'warning')
        return {'success': True}

    def _note_manual_reply_sent(
        self, nickname: str, text: str, category: str = 'friend', conv_id: str = '',
    ) -> None:
        """让监控器立即识别人工回复为己方消息，避免重新进入待回队列。"""
        nickname = str(nickname or '').strip()
        text = str(text or '').strip()
        if not nickname or not text:
            return
        fallback_key = f'{category or "friend"}:{nickname}'
        user_keys = {fallback_key}
        if str(conv_id or '').strip():
            user_keys.add(str(conv_id).strip())
        now = time.time()
        for user_key in user_keys:
            self._sent_reply_texts.setdefault(user_key, set()).add(text)
            self._recently_handled_raw[f'{user_key}:{text}'] = now
        # 列表预览可能带“我：”、时间或其他装饰，下一轮仍由
        # _is_own_outgoing_preview 做包含匹配并更新为页面中的真实预览。

    def send_manual_reply(
        self, nickname: str, text: str, category: str = 'friend', conv_id: str = '',
    ) -> Dict[str, Any]:
        nickname = str(nickname or '').strip()
        text = str(text or '').strip()
        if not nickname or not text:
            return {'success': False, 'error': '回复对象和内容不能为空'}
        self.load_config()
        if self.config.get('session_expired') or not self.config.get('logged_in'):
            return {'success': False, 'error': '登录状态已失效，请重新登录'}
        self._abort_session_verify()
        try:
            with self._browser_use_lock:
                browser = self._ensure_browser(headless=True)
                browser.set_abort(False)
                browser.start_worker()
                ok = browser.send_text(
                    nickname, text, category=category or 'friend',
                    from_panel=True, conversation_open=False,
                )
                if ok:
                    # 必须在释放浏览器锁前登记，否则监控线程可能先扫描到
                    # 刚发送的预览，并把它误判成一条新的用户消息。
                    self._note_manual_reply_sent(
                        nickname, text, category=category or 'friend', conv_id=conv_id,
                    )
            if not ok:
                return {'success': False, 'error': '页面未确认消息发送成功，请稍后重试'}
            self.add_log(f'✅ [{nickname}] 人工快速回复已发送', 'success')
            return {'success': True}
        except Exception as exc:
            self.add_log(f'❌ [{nickname}] 人工快速回复失败: {exc}', 'error')
            return {'success': False, 'error': str(exc)}

    def _wait_interval(self, seconds: float) -> bool:
        """可中断等待，返回 True 表示应停止监控"""
        return self._monitor_stop.wait(timeout=max(0.1, seconds))

    def _monitor_loop(self) -> None:
        with self._browser_use_lock:
            browser = self._ensure_browser(headless=True)
            browser.set_abort(False)
            browser.start_worker()
            try:
                browser.navigate_messages()
            except Exception:
                pass
        self.add_log('已进入私信监控循环（后台运行）', 'info')

        if not self._storage_has_session_cookies():
            with self._browser_use_lock:
                if not browser.check_session_valid():
                    self._mark_session_expired()
                    self.monitoring = False
                    return

        interval = max(0.2, float(self.config.get('message_check_interval') or 0.3))
        send_gap = max(0.2, float(self.config.get('send_delay_interval') or 0.3))
        only_new = bool(self.config.get('only_reply_new_messages', True))
        scan_count = 0
        quick_scan = False
        empty_scans = 0

        while self.monitoring and not self._monitor_stop.is_set():
            try:
                if self._monitor_stop.is_set():
                    break
                is_first_scan = only_new and not self._baseline_initialized
                full_scan = scan_count == 0 or (scan_count % 40 == 0)
                with self._browser_use_lock:
                    browser.set_abort(False)
                    conversations = browser.list_conversations(
                        quick=quick_scan and not full_scan,
                        skip_stranger=quick_scan and not full_scan,
                    )
                self._try_mark_monitor_list_ready(browser, conversations, full_scan)
                quick_scan = True
                if self._monitor_stop.is_set():
                    break
                if not conversations:
                    empty_scans += 1
                    if empty_scans == 1:
                        reason = ''
                        getter = getattr(browser, 'get_last_list_diagnosis', None)
                        if callable(getter):
                            reason = (getter() or '').strip()
                        if reason:
                            self.add_log(f'暂未读取到会话列表：{reason}', 'warning')
                        else:
                            self.add_log('暂未读取到会话列表，正在等待私信页加载…', 'warning')
                    elif empty_scans in (5, 15) or empty_scans % 30 == 0:
                        self.add_log(
                            f'暂未读取到会话列表（已连续 {empty_scans} 次），将继续重试…',
                            'warning',
                        )
                        with self._browser_use_lock:
                            browser.set_abort(False)
                            try:
                                browser.navigate_messages()
                            except Exception:
                                pass
                        quick_scan = False
                    wait_time = interval
                    if empty_scans >= 5:
                        wait_time = min(interval * (empty_scans // 5), 15.0)
                    if self._wait_interval(wait_time):
                        break
                    continue
                empty_scans = 0

                scan_count += 1
                if is_first_scan:
                    self._initialize_baseline(conversations)

                if scan_count == 1 or scan_count % 20 == 0:
                    stranger_count = sum(
                        1 for c in conversations if getattr(c, 'category', '') == 'stranger'
                    )
                    self.add_log(
                        f'扫描到 {len(conversations)} 个会话（陌生人 {stranger_count} 个）',
                        'info',
                    )

                conversations = sorted(
                    conversations,
                    key=lambda c: (
                        -(int(getattr(c, 'unread', 0) or 0)),
                        (c.nickname or ''),
                    ),
                )

                had_activity = False
                is_first_scan = only_new and self._baseline_initialized and scan_count == 1

                for conv in conversations:
                    if not self.monitoring or self._monitor_stop.is_set():
                        break

                    nickname = (conv.nickname or '').strip()
                    if not nickname or nickname == '陌生人消息':
                        continue
                    if self._is_phantom_conversation(conv):
                        continue

                    category = getattr(conv, 'category', 'friend') or 'friend'
                    sender = (getattr(conv, 'sender_nickname', '') or nickname).strip()
                    target_nick = sender if category == 'stranger' else nickname
                    user_key = self._conv_user_key(conv)

                    max_replies = self._get_user_reply_limit()
                    if (
                        max_replies is not None
                        and self.get_user_reply_count(user_key) >= max_replies
                    ):
                        continue

                    raw_fp = self._raw_preview(conv)
                    if not raw_fp:
                        continue

                    unread_count = int(getattr(conv, 'unread', 0) or 0)
                    has_unread = unread_count > 0
                    # 首轮扫描只建立快照。未读标记可能来自启动前，不能据此放行旧消息。
                    if is_first_scan:
                        continue

                    prev_raw = self.last_seen_preview.get(user_key)
                    message_token = self._conversation_message_token(conv)
                    prev_token = self.last_seen_message_token.get(user_key, '')
                    prev_unread = self.last_seen_unread.get(user_key, 0)
                    same_message = raw_fp == prev_raw and (
                        not message_token or message_token == prev_token
                    )
                    unread_became_active = unread_count > 0 and prev_unread <= 0
                    if prev_raw is not None and same_message and not unread_became_active:
                        self.last_seen_unread[user_key] = unread_count
                        continue

                    dedupe_key = f'{user_key}:{raw_fp}'
                    retry_after = self._send_retry_after.get(dedupe_key, 0.0)
                    if retry_after > time.time():
                        continue
                    recent_ts = self._recently_handled_raw.get(dedupe_key)
                    if recent_ts and (time.time() - recent_ts) < 20:
                        continue

                    if prev_raw is None and only_new:
                        self._remember_conversation_state(user_key, conv, raw_fp)
                        continue

                    if self._is_likely_own_image_preview(user_key, raw_fp):
                        self._remember_conversation_state(user_key, conv, raw_fp)
                        continue

                    conversation_is_open = False
                    if self._should_use_direct_preview(conv, has_unread):
                        msg_text = self._incoming_text(conv)
                    else:
                        # 无未读标记的预览变化可能是本账号手动发送，进入会话确认方向。
                        with self._browser_use_lock:
                            browser.set_abort(False)
                            latest = browser.read_latest_incoming(
                                str(conv.conv_id or ''), nickname,
                                category=category,
                                sender_nickname=sender if category == 'stranger' else '',
                            )
                        conversation_is_open = bool(latest)
                        if not latest:
                            fallback = self._fallback_incoming_text(conv)
                            if fallback:
                                msg_text = fallback
                            else:
                                # 聊天区可能尚未刷新。不推进快照，下一轮继续确认。
                                continue
                        elif latest.is_self:
                            # 只有聊天区的已方消息与列表预览一致时，才能确认
                            # 这是已方发送。如果聊天区返回了旧消息，保留预览变化继续重试。
                            if self._preview_contains_reply(raw_fp, latest.text or ''):
                                self._remember_conversation_state(user_key, conv, raw_fp)
                            continue
                        else:
                            msg_text = (latest.text or '').strip()
                            preview_text = self._incoming_text(conv)
                            if (
                                preview_text and msg_text
                                and preview_text not in msg_text
                                and msg_text not in preview_text
                            ):
                                # 列表已刷新、聊天区仍是旧内容时不可提前吞掉新消息。
                                continue

                    msg_text = self._postprocess_incoming_text(conv, msg_text, browser)
                    if not msg_text:
                        # 空内容可能是聊天区短暂未完成渲染，下一轮重试。
                        continue

                    if self._is_own_outgoing_preview(user_key, raw_fp, msg_text):
                        self._remember_conversation_state(user_key, conv, raw_fp)
                        continue

                    self.add_log(f'📩 [{target_nick}] 新消息: {msg_text[:80]}', 'info')
                    record_dashboard_event(
                        self.ai_platform_key, 'inbound', dedupe_key,
                        contact_id=user_key,
                    )
                    had_activity = True

                    ai_mode = platform_enabled(self.ai_platform_key)
                    matched = None if ai_mode else self.match_rule(msg_text)
                    reply_text = None
                    reply_type = 'text'
                    reply_image = ''
                    rule_title = None

                    if ai_mode:
                        conversation_context = build_conversation_context(
                            self.ai_platform_key, user_key,
                        )
                        ai_instruction = '请用简洁、友好的中文回复这条用户私信。'
                        if conversation_context:
                            ai_instruction += '\n\n' + conversation_context
                        decision = generate_ai_decision(
                            msg_text, ai_instruction, platform=self.ai_platform_key
                        )
                        if decision.get('needs_human'):
                            reason = decision.get('reason') or 'AI 无法确认可靠回复'
                            ai_handoff_store.add(
                                self.ai_platform_key, dedupe_key, target_nick, user_key,
                                msg_text, reason,
                                {
                                    'nickname': target_nick, 'category': category,
                                    'conv_id': str(getattr(conv, 'conv_id', '') or ''),
                                },
                            )
                            self.add_log(f'🧑‍💼 [{target_nick}] AI 已标记为待人工处理：{reason}', 'warning')
                            self._remember_conversation_state(user_key, conv, raw_fp)
                            self._recently_handled_raw[dedupe_key] = time.time()
                            continue
                        reply_text = decision.get('reply')
                        rule_title = 'AI 自动回复'
                        if not reply_text:
                            self.add_log(f'❌ [{target_nick}] AI 回复生成失败，已跳过', 'error')
                            record_dashboard_event(
                                self.ai_platform_key, 'reply_failure', dedupe_key,
                                contact_id=user_key, reply_mode='ai',
                            )
                            self._remember_conversation_state(user_key, conv, raw_fp)
                            continue
                    elif matched:
                        reply_text = matched.get('reply') or ''
                        reply_type = matched.get('reply_type') or 'text'
                        reply_image = matched.get('reply_image') or ''
                        rule_title = matched['title']
                    elif self.config.get('default_reply_enabled'):
                        reply_text = self.config.get('default_reply_message') or ''
                        reply_type = self.config.get('default_reply_type') or 'text'
                        reply_image = self.config.get('default_reply_image') or ''
                        rule_title = '默认回复'
                    else:
                        self._remember_conversation_state(user_key, conv, raw_fp)
                        continue

                    if reply_type == 'image':
                        self.add_log(
                            f'[{target_nick}] 图片回复功能已暂停，请改为文字回复',
                            'warning', dedupe_seconds=60,
                        )
                        record_dashboard_event(
                            self.ai_platform_key, 'reply_failure', dedupe_key,
                            contact_id=user_key,
                            reply_mode='ai' if ai_mode else ('rule' if matched else 'default'),
                        )
                        self._remember_conversation_state(user_key, conv, raw_fp)
                        continue
                    elif not reply_text.strip():
                        self._remember_conversation_state(user_key, conv, raw_fp)
                        continue
                    else:
                        reply_type = 'text'
                        reply_marker = reply_text

                    elapsed = time.time() - self.last_send_time
                    if elapsed < send_gap:
                        if self._wait_interval(send_gap - elapsed):
                            break

                    if not self.monitoring or self._monitor_stop.is_set():
                        break

                    ok = False
                    send_diagnosis = ''
                    with self._browser_use_lock:
                        browser.set_abort(False)
                        ok = browser.send_text(
                            target_nick, reply_text, category=category,
                            from_panel=not conversation_is_open,
                            conversation_open=conversation_is_open,
                        )
                        if not ok:
                            try:
                                send_diagnosis = browser.get_last_send_error()
                            except Exception:
                                pass
                        # 只有“已执行提交但页面未出现气泡”才需要回列表复核。
                        # 面板或目标会话本身未就绪时再次扫描只会触发另一轮导航，
                        # 过去会让一次失败从数秒拖到约一分钟。
                        if not ok and send_diagnosis.startswith('页面未出现新发送气泡'):
                            refreshed = browser.list_conversations(quick=True, skip_stranger=True)
                            for refreshed_conv in refreshed:
                                if (refreshed_conv.nickname or '').strip() != target_nick:
                                    continue
                                new_raw = self._raw_preview(refreshed_conv)
                                if self._preview_contains_reply(new_raw, reply_text):
                                    ok = True
                                break
                    self.last_send_time = time.time()

                    # 用户主动停止时 send_text 会被中断。不要把这类中断记成消息
                    # 发送失败，更不能因此吞掉尚未回复的消息。
                    if not self.monitoring or self._monitor_stop.is_set():
                        break

                    if ok:
                        self._send_retry_counts.pop(dedupe_key, None)
                        self._send_retry_after.pop(dedupe_key, None)
                        post_raw = raw_fp
                        self._remember_conversation_state(user_key, conv, post_raw)
                        self._mark_reply_handled(user_key, post_raw, reply_marker, dedupe_key)
                        count = self.increment_user_reply_count(user_key)
                        record_dashboard_event(
                            self.ai_platform_key, 'reply_success', dedupe_key,
                            contact_id=user_key,
                            reply_mode='ai' if ai_mode else ('rule' if matched else 'default'),
                        )
                        if ai_mode:
                            record_conversation_exchange(
                                self.ai_platform_key, user_key, msg_text, reply_text,
                                dedupe_key,
                            )
                        limit_text = '不限' if max_replies is None else str(max_replies)
                        if matched:
                            self.add_log(
                                f'✅ [{target_nick}] 匹配「{rule_title}」已发送文字回复 ({count}/{limit_text})',
                                'success',
                            )
                        else:
                            self.add_log(
                                f'✅ [{target_nick}] 默认文字回复已发送 ({count}/{limit_text})',
                                'success',
                            )
                    else:
                        attempt = self._send_retry_counts.get(dedupe_key, 0) + 1
                        self._send_retry_counts[dedupe_key] = attempt
                        diagnosis_text = f'；{send_diagnosis}' if send_diagnosis else ''
                        # 即使页面确认超时，也可能已被抖音接受。先记录本次回复文本，
                        # 下一轮若列表稍后出现该文本，可识别为己方消息而避免重复发送。
                        self._sent_reply_texts.setdefault(user_key, set()).add(reply_text.strip())
                        record_dashboard_event(
                            self.ai_platform_key, 'reply_failure', dedupe_key,
                            contact_id=user_key,
                            reply_mode='ai' if ai_mode else ('rule' if matched else 'default'),
                        )
                        if attempt < 3:
                            retry_delay = 2.0 if attempt == 1 else 6.0
                            self._send_retry_after[dedupe_key] = time.time() + retry_delay
                            self.add_log(
                                f'⚠️ [{target_nick}] 回复发送未确认（{attempt}/3{diagnosis_text}），'
                                f'{retry_delay:.0f} 秒后重试',
                                'warning',
                            )
                        else:
                            self.add_log(
                                f'❌ [{target_nick}] 连续 3 次未能确认回复发送'
                                f'{diagnosis_text}，已停止重试',
                                'error',
                            )
                            # 只在达到重试上限后推进基线，避免单次页面抖动永久漏回。
                            self._remember_conversation_state(user_key, conv, raw_fp)
                            self._recently_handled_raw[dedupe_key] = time.time()
                            self._send_retry_counts.pop(dedupe_key, None)
                            self._send_retry_after.pop(dedupe_key, None)

                    if self._wait_interval(send_gap):
                        break

                poll_wait = 0.15 if had_activity else interval
                if self._wait_interval(poll_wait):
                    break

            except Exception as exc:
                if not self._monitor_stop.is_set():
                    error_text = str(exc)
                    if error_text.startswith('XHS_CHAT_BLOCKED:'):
                        self.add_log(error_text.split(':', 1)[1], 'error')
                        self.add_log('监控已停止。请切换可靠网络后重新登录并再次启动监控', 'warning')
                        self.monitoring = False
                        self._monitor_stop.set()
                        break
                    self.add_log(f'监控循环异常: {exc}', 'error')
                quick_scan = False
                if self._wait_interval(max(interval, 3)):
                    break

        self.monitoring = False
        self._monitor_list_ready = False
        self.add_log('抖音监控线程已退出', 'info')

    # ── config export / import ────────────────────────────────────

    def get_exportable_config(self) -> Dict[str, Any]:
        return {
            key: self.config.get(key, DEFAULT_CONFIG.get(key))
            for key in DOUYIN_EXPORTABLE_CONFIG_KEYS
        }

    def build_export_package(self) -> Dict[str, Any]:
        self.load_config()
        self.load_rules()
        return {
            'version': '1.0',
            'app_version': _get_app_version(),
            'export_time': datetime.now().isoformat(),
            'app_name': 'BiliGo - 抖音私信',
            'config': self.get_exportable_config(),
            'rules': [dict(rule) for rule in self.rules],
        }

    @staticmethod
    def _normalize_imported_rule(rule: Any, index: int) -> Optional[Dict[str, Any]]:
        if not isinstance(rule, dict):
            return None
        keyword = str(rule.get('keyword', '')).strip()
        if not keyword:
            return None
        is_image = rule.get('reply_type') == 'image'
        return {
            'name': str(rule.get('name') or f'导入规则{index + 1}'),
            'keyword': keyword,
            'reply': '' if is_image else str(rule.get('reply', '')),
            'reply_type': 'text',
            'reply_image': '',
            'enabled': False if is_image else bool(rule.get('enabled', True)),
        }

    @classmethod
    def parse_import_payload(cls, data: Any) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
        if isinstance(data, list):
            return {}, [rule for rule in (cls._normalize_imported_rule(item, i) for i, item in enumerate(data)) if rule]
        if not isinstance(data, dict):
            raise ValueError('不支持的文件格式，请使用包含 config 和 rules 的完整配置文件')
        imported_config = data.get('config', {}) if isinstance(data.get('config'), dict) else {}
        raw_rules = data.get('rules', [])
        if raw_rules and not isinstance(raw_rules, list):
            raise ValueError('规则格式错误')
        if not imported_config and not raw_rules:
            raise ValueError('无效的配置文件格式')
        valid_rules = [
            rule for rule in (
                cls._normalize_imported_rule(item, i) for i, item in enumerate(raw_rules or [])
            ) if rule
        ]
        return imported_config, valid_rules

    def apply_imported_config(self, imported_config: Dict[str, Any]) -> int:
        updated = 0
        for key in DOUYIN_EXPORTABLE_CONFIG_KEYS:
            if key not in imported_config:
                continue
            self.config[key] = imported_config[key]
            updated += 1
        if updated:
            self.save_config()
        return updated

    def apply_imported_rules(self, valid_rules: List[Dict[str, Any]], import_mode: str = 'replace') -> int:
        if not valid_rules:
            return 0
        if import_mode == 'append':
            existing_keywords = {str(rule.get('keyword', '')).strip() for rule in self.rules}
            new_rules = [
                rule for rule in valid_rules
                if rule['keyword'] not in existing_keywords
            ]
            self.rules.extend(new_rules)
            imported_count = len(new_rules)
        else:
            self.rules = valid_rules
            imported_count = len(valid_rules)
        self.save_rules()
        self.precompile_rules()
        return imported_count

    def import_config_package(self, data: Any, import_mode: str = 'replace') -> str:
        imported_config, valid_rules = self.parse_import_payload(data)
        config_updated = self.apply_imported_config(imported_config)
        imported_count = self.apply_imported_rules(valid_rules, import_mode)
        parts = []
        if config_updated:
            parts.append('配置已更新')
        if imported_count:
            mode_text = '追加' if import_mode == 'append' else '导入'
            parts.append(f'{mode_text} {imported_count} 条规则')
        if not parts:
            raise ValueError('文件中没有可导入的有效配置或规则')
        message = '，'.join(parts)
        self.add_log(message, 'success')
        return message

    # ── status ────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        has_saved = self._storage_has_session_cookies()
        account = self.config.get('account') or {}
        logged_in = (
            (has_saved and (account.get('nickname') or account.get('uid')))
            or bool(self.config.get('logged_in'))
        ) and not self.config.get('session_expired')
        return {
            'monitoring': self.monitoring,
            'monitor_starting': bool(self.monitoring and not self._monitor_list_ready),
            'logged_in': logged_in,
            'session_expired': bool(self.config.get('session_expired')) and not has_saved,
            'account': self.config.get('account') or {},
            'login_time': self.config.get('login_time', ''),
            'rules_count': len(self.rules),
            'login_in_progress': self.login_in_progress,
            'has_saved_session': os.path.exists(self.storage_file or ''),
        }


douyin_system = DouyinReplySystem()


def register_douyin_routes(app) -> None:
    """向 Flask app 注册抖音私信相关路由。"""

    @app.route('/api/douyin-avatar')
    def douyin_avatar_proxy():
        """代理抖音头像，避免浏览器防盗链导致无法显示。"""
        import requests as http_requests

        url = (request.args.get('url') or '').strip()
        if not url.startswith('https://'):
            return '', 400
        allowed_hosts = ('douyinpic.com', 'byteimg.com', 'douyinvod.com', 'douyin.com')
        if not any(host in url for host in allowed_hosts):
            return '', 403
        try:
            resp = http_requests.get(
                url,
                headers={
                    'Referer': 'https://www.douyin.com/',
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                        '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                    ),
                },
                timeout=12,
            )
            resp.raise_for_status()
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            return Response(
                resp.content,
                mimetype=content_type,
                headers={'Cache-Control': 'private, max-age=3600'},
            )
        except Exception as exc:
            logger.warning('头像代理失败: %s', exc)
            return '', 502

    @app.route('/douyin')
    def douyin_page():
        return send_from_directory(get_static_root(), 'douyin_reply.html')

    @app.route('/api/douyin-config', methods=['GET', 'POST'])
    def douyin_config_api():
        if request.method == 'GET':
            douyin_system.load_config()
            safe = dict(douyin_system.config)
            return jsonify(safe)
        try:
            data = request.get_json() or {}
            if data.get('default_reply_type') == 'image' or data.get('default_reply_image'):
                return jsonify({'success': False, 'error': '抖音图片回复功能已暂停，请使用文字回复'}), 409
            traditional_keys = {'default_reply_enabled', 'default_reply_message', 'default_reply_type', 'default_reply_image'}
            if platform_enabled('douyin') and traditional_keys.intersection(data):
                return jsonify({'success': False, 'error': '已启用AI模式，无法修改默认回复设置'}), 409
            for key in (
                'default_reply_enabled', 'default_reply_message',
                'default_reply_type', 'default_reply_image',
                'message_check_interval', 'send_delay_interval',
                'only_reply_new_messages', 'headless',
            ):
                if key in data:
                    douyin_system.config[key] = data[key]
            douyin_system.config['default_reply_type'] = 'text'
            douyin_system.config['default_reply_image'] = ''
            if douyin_system.config.get('default_reply_type') != 'text':
                return jsonify({'success': False, 'error': '默认回复类型无效'})
            if 'message_check_interval' in data:
                v = float(data['message_check_interval'])
                if v < 0.5:
                    return jsonify({'success': False, 'error': '消息检查间隔不能小于 0.5 秒'})
                douyin_system.config['message_check_interval'] = v
            if 'send_delay_interval' in data:
                v = float(data['send_delay_interval'])
                if v < 0.5:
                    return jsonify({'success': False, 'error': '发送间隔不能小于 0.5 秒'})
                douyin_system.config['send_delay_interval'] = v
            if 'unlimited_replies_per_user' in data:
                if not isinstance(data['unlimited_replies_per_user'], bool):
                    return jsonify({'success': False, 'error': '不限制回复次数选项必须为布尔值'})
                douyin_system.config['unlimited_replies_per_user'] = data['unlimited_replies_per_user']
            if 'max_replies_per_user' in data:
                v = int(data['max_replies_per_user'])
                if v < 1:
                    return jsonify({'success': False, 'error': '单用户最大回复次数不能小于 1'})
                douyin_system.config['max_replies_per_user'] = v
            douyin_system.save_config()
            douyin_system.add_log('抖音配置已保存', 'success')
            return jsonify({'success': True})
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/douyin-reply-image', methods=['POST'])
    def douyin_reply_image_upload():
        return jsonify({
            'success': False,
            'error': '抖音图片回复功能已暂停，请使用文字回复',
        }), 410

    @app.route('/api/douyin-rules', methods=['GET', 'POST'])
    def douyin_rules_api():
        if request.method == 'GET':
            douyin_system.load_rules()
            return jsonify({'rules': douyin_system.rules})
        try:
            if platform_enabled('douyin'):
                return jsonify({'success': False, 'error': '已启用AI模式，无法修改关键词回复'}), 409
            data = request.get_json() or {}
            if 'rules' in data:
                rules = data['rules']
                if not isinstance(rules, list):
                    return jsonify({'success': False, 'error': '规则格式错误'})
                for rule in rules:
                    if not isinstance(rule, dict):
                        return jsonify({'success': False, 'error': '规则格式错误'})
                    if rule.get('reply_type') == 'image' or rule.get('reply_image'):
                        return jsonify({'success': False, 'error': '抖音图片回复功能已暂停，请使用文字回复'}), 409
                    rule['reply_type'] = 'text'
                    rule['reply_image'] = ''
                    if not str(rule.get('reply', '')).strip():
                        return jsonify({'success': False, 'error': '文字回复规则缺少回复内容'})
                douyin_system.rules = rules
                douyin_system.save_rules()
                douyin_system.precompile_rules()
                douyin_system.add_log(f'抖音规则已更新，共 {len(douyin_system.rules)} 条', 'success')
            return jsonify({'success': True})
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/douyin-login/start', methods=['POST'])
    def douyin_login_start():
        result = douyin_system.start_login()
        return jsonify(result)

    @app.route('/api/douyin-login/status', methods=['GET'])
    def douyin_login_status():
        if request.args.get('verify') == '1':
            douyin_system.verify_session(background=True, quick=True)
        return jsonify(douyin_system.get_login_status())

    @app.route('/api/douyin-account/refresh', methods=['POST'])
    def douyin_refresh_account():
        return jsonify(douyin_system.refresh_account_info())

    @app.route('/api/douyin-logout', methods=['POST'])
    def douyin_logout():
        return jsonify(douyin_system.logout())

    @app.route('/api/reset-douyin-data', methods=['POST'])
    def reset_douyin_data():
        try:
            result = douyin_system.reset_all_data()
            return jsonify(result)
        except Exception as exc:
            douyin_system.add_log(f'清除抖音数据失败: {exc}', 'error')
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/douyin-start', methods=['POST'])
    def douyin_start():
        result = douyin_system.start_monitoring()
        return jsonify(result)

    @app.route('/api/douyin-stop', methods=['POST'])
    def douyin_stop():
        result = douyin_system.stop_monitoring()
        return jsonify(result)

    @app.route('/api/douyin-status')
    def douyin_status():
        return jsonify(douyin_system.get_status())

    @app.route('/api/douyin-logs')
    def douyin_logs():
        limit = int(request.args.get('limit', 100))
        return jsonify({'logs': douyin_system.logs[:limit]})

    @app.route('/api/export-douyin-config', methods=['GET'])
    def export_douyin_config():
        try:
            export_dir = os.path.join(get_app_root(), 'export')
            os.makedirs(export_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_data = douyin_system.build_export_package()
            export_filename = f'biligo_douyin_config_{timestamp}.json'
            export_path = os.path.join(export_dir, export_filename)
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            douyin_system.add_log(
                f'导出抖音配置: {len(export_data.get("rules", []))} 条规则，文件已保存到 export/{export_filename}',
                'success',
            )
            return send_from_directory(
                export_dir,
                export_filename,
                as_attachment=True,
                download_name=export_filename,
                mimetype='application/json',
            )
        except Exception as exc:
            douyin_system.add_log(f'导出抖音配置失败: {exc}', 'error')
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/validate-douyin-config-file', methods=['POST'])
    def validate_douyin_config_file():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': '没有选择文件'})
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'error': '没有选择文件'})
            if not file.filename.lower().endswith('.json'):
                return jsonify({'success': False, 'error': '只支持 JSON 格式文件'})
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            if file_size > 5 * 1024 * 1024:
                return jsonify({'success': False, 'error': '文件大小不能超过 5MB'})
            content = file.read().decode('utf-8')
            data = json.loads(content)
            imported_config, valid_rules = douyin_system.parse_import_payload(data)
            raw_rules = data.get('rules', data if isinstance(data, list) else [])
            total_rules = len(raw_rules) if isinstance(raw_rules, list) else 0
            return jsonify({
                'success': True,
                'valid_rules': len(valid_rules),
                'total_rules': total_rules,
                'has_config': bool(imported_config),
            })
        except UnicodeDecodeError:
            return jsonify({'success': False, 'error': '文件编码错误，请使用 UTF-8 编码'})
        except json.JSONDecodeError as exc:
            return jsonify({'success': False, 'error': f'JSON 格式错误: {exc}'})
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)})
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/import-douyin-config', methods=['POST'])
    def import_douyin_config():
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': '没有选择文件'})
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'error': '没有选择文件'})
            if not file.filename.lower().endswith('.json'):
                return jsonify({'success': False, 'error': '只支持 JSON 格式文件'})
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            if file_size > 5 * 1024 * 1024:
                return jsonify({'success': False, 'error': '文件大小不能超过 5MB'})
            content = file.read().decode('utf-8')
            data = json.loads(content)
            import_mode = request.form.get('import_mode', 'replace')
            if import_mode not in ('replace', 'append'):
                import_mode = 'replace'
            message = douyin_system.import_config_package(data, import_mode)
            return jsonify({'success': True, 'message': message})
        except UnicodeDecodeError:
            return jsonify({'success': False, 'error': '文件编码错误，请使用 UTF-8 编码'})
        except json.JSONDecodeError as exc:
            return jsonify({'success': False, 'error': f'JSON 格式错误: {exc}'})
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)})
        except Exception as exc:
            douyin_system.add_log(f'导入抖音配置失败: {exc}', 'error')
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/douyin-import-from-message', methods=['POST'])
    def douyin_import_from_message():
        """从 B 站私信规则导入"""
        try:
            rules_path = os.path.join(get_app_root(), 'keywords.json')
            source_rules = []
            if os.path.exists(rules_path):
                with open(rules_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                source_rules = data if isinstance(data, list) else data.get('rules', [])
            imported = []
            for r in source_rules:
                imported.append({
                    'name': r.get('name', '导入规则'),
                    'keyword': r.get('keyword', ''),
                    'reply': '' if r.get('reply_type') == 'image' else r.get('reply', ''),
                    'reply_type': 'text',
                    'reply_image': '',
                    'enabled': False if r.get('reply_type') == 'image' else r.get('enabled', True),
                })
            douyin_system.rules = imported or [dict(DEFAULT_RULE)]
            douyin_system.save_rules()
            douyin_system.precompile_rules()
            douyin_system.add_log(f'已从 B 站私信导入 {len(imported)} 条规则', 'success')
            return jsonify({'success': True, 'count': len(imported)})
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)})
