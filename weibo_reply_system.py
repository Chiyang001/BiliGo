"""BiliGo 微博私信自动回复模块。"""
from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from flask import Response, jsonify, request

from app_paths import get_app_root, get_static_root
from ai_conversation_store import ai_conversation_store
from ai_reply_service import platform_enabled
from dashboard_metrics import dashboard_metrics
from ai_handoff_store import ai_handoff_store
from douyin_reply_system import DEFAULT_RULE
from weibo_playwright import WEIBO_MONITOR_ENGINE, WEIBO_SESSION_COOKIES, WeiboBrowserWorker
from xiaohongshu_reply_system import (
    XHS_DEFAULT_CONFIG, XiaohongshuReplySystem, _validate_rules,
    register_platform_config_transfer_routes,
)

WEIBO_DEFAULT_CONFIG = {
    **XHS_DEFAULT_CONFIG,
    'default_reply_message': '感谢您的私信，我会尽快回复~',
}


class WeiboReplySystem(XiaohongshuReplySystem):
    ai_platform_key = 'weibo'
    def __init__(self):
        super().__init__()
        self.config = dict(WEIBO_DEFAULT_CONFIG)
        self._avatar_cache_url = ''
        self._avatar_cache_data = b''
        self._avatar_cache_mimetype = 'image/jpeg'

    def _init_paths(self) -> None:
        root = get_app_root()
        if self.config_file is None:
            self.config_file = os.path.join(root, 'weibo_config.json')
        if self.rules_file is None:
            self.rules_file = os.path.join(root, 'weibo_keywords.json')
        if self.storage_file is None:
            self.storage_file = os.path.join(root, 'weibo_storage.json')
        if self.stats_file is None:
            self.stats_file = os.path.join(root, 'weibo_user_reply_stats.json')

    def _ensure_browser(self, headless: Optional[bool] = None) -> WeiboBrowserWorker:
        self._init_paths()
        if self._browser is None:
            self._browser = WeiboBrowserWorker(
                storage_path=self.storage_file,
                headless=headless if headless is not None else bool(self.config.get('headless', True)),
            )
        elif headless is not None:
            self._browser.set_headless(headless)
        account = self.config.get('account') or {}
        self._browser.set_account_identity(
            uid=str(account.get('uid') or ''), nickname=str(account.get('nickname') or ''),
        )
        return self._browser

    def _storage_has_session_cookies(self) -> bool:
        self._init_paths()
        if not os.path.isfile(self.storage_file or ''):
            return False
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            names = {str(c.get('name') or '') for c in (state.get('cookies') or [])}
            return bool(WEIBO_SESSION_COOKIES & names)
        except Exception:
            return False

    def _has_persistent_profile(self) -> bool:
        profile = os.path.join(get_app_root(), 'weibo_browser_profile')
        return os.path.isdir(profile) and any(
            os.path.exists(os.path.join(profile, marker))
            for marker in ('Local State', 'Default', 'Preferences')
        )

    def load_config(self) -> None:
        super().load_config()
        account = dict(self.config.get('account') or {})
        nickname = str(account.get('nickname') or '')
        has_saved_session = (
            self._storage_has_session_cookies() or self._has_persistent_profile()
        )
        changed = False
        if nickname and not WeiboBrowserWorker._is_valid_nickname(nickname):
            # Older versions could persist a modal's body text as the nickname.
            self.config['account'] = {}
            self.config['login_time'] = ''
            changed = True
        if has_saved_session:
            account = dict(self.config.get('account') or {})
            if account.get('nickname') or account.get('uid'):
                if not self.config.get('logged_in'):
                    self.config['logged_in'] = True
                    changed = True
                if self.config.get('session_expired'):
                    self.config['session_expired'] = False
                    changed = True
        else:
            if self.config.get('account'):
                self.config['account'] = {}
                changed = True
            if self.config.get('login_time'):
                self.config['login_time'] = ''
                changed = True
            if self.config.get('logged_in'):
                self.config['logged_in'] = False
                changed = True
            self.config['session_expired'] = False
        if changed:
            self.save_config()

    def init_on_startup(self) -> None:
        """Restore the Weibo session while keeping monitoring stopped."""
        self.load_config()
        self.load_rules()
        if self.config.get('auto_start_monitoring') is not False:
            self.config['auto_start_monitoring'] = False
            self.save_config()
        if os.path.exists(self.storage_file or '') or self._has_persistent_profile():
            self.verify_session(background=True, quick=True)

    def _mark_session_expired(self) -> None:
        """A rejected Weibo Cookie is expired even while it remains on disk."""
        already_expired = bool(self.config.get('session_expired'))
        self.config['logged_in'] = False
        self.config['session_expired'] = True
        account = dict(self.config.get('account') or {})
        if not WeiboBrowserWorker._is_valid_nickname(str(account.get('nickname') or '')):
            self.config['account'] = {}
        self.save_config()
        if not already_expired:
            self.add_log('登录状态已失效，请重新登录', 'warning')

    def verify_session(self, background: bool = False, quick: bool = False) -> bool:
        """Verify Weibo in the browser; Cookie presence alone is not proof of login."""
        self._init_paths()
        if not os.path.exists(self.storage_file or '') and not self._has_persistent_profile():
            return False
        if self.login_in_progress:
            return False
        if self.monitoring and background:
            return bool(self.config.get('logged_in'))
        if quick and self.config.get('session_expired'):
            return False

        def _verify() -> bool:
            with self._browser_use_lock:
                try:
                    browser = self._ensure_browser(headless=True)
                    browser.set_abort(False)
                    browser.start_worker()
                    if not browser.check_session_valid():
                        self._mark_session_expired()
                        return False
                    account = browser.get_account()
                    info = account.to_dict() if hasattr(account, 'to_dict') else {}
                    nickname = str(info.get('nickname') or '')
                    if nickname and not browser._is_valid_nickname(nickname):
                        info['nickname'] = ''
                    if not self.config.get('login_time'):
                        self.config['login_time'] = datetime.now().isoformat()
                    self._mark_session_valid(info if info.get('uid') or info.get('nickname') else None)
                    browser.save_session()
                    return True
                except Exception as exc:
                    self.add_log(f'会话验证失败: {exc}', 'warning')
                    return False

        if background:
            if self._session_verify_thread and self._session_verify_thread.is_alive():
                return bool(self.config.get('logged_in') and not self.config.get('session_expired'))
            self._session_verify_thread = threading.Thread(target=_verify, daemon=True)
            self._session_verify_thread.start()
            return bool(self.config.get('logged_in') and not self.config.get('session_expired'))
        return _verify()

    def get_login_status(self) -> Dict[str, Any]:
        account = dict(self.config.get('account') or {})
        nickname = str(account.get('nickname') or '')
        if nickname and not WeiboBrowserWorker._is_valid_nickname(nickname):
            account = {}
        has_saved = self._storage_has_session_cookies() or self._has_persistent_profile()
        if has_saved and (account.get('nickname') or account.get('uid')):
            logged_in = not self.config.get('session_expired')
        else:
            logged_in = bool(self.config.get('logged_in')) and not self.config.get('session_expired')
        expired = bool(self.config.get('session_expired')) and not has_saved
        return {
            'login_in_progress': self.login_in_progress,
            'logged_in': logged_in,
            'session_expired': expired,
            'account': account,
            'login_time': self.config.get('login_time', ''),
            'browser_alive': self._browser.is_browser_alive() if self._browser else False,
            'has_saved_session': has_saved,
        }

    def refresh_account_info(self) -> Dict[str, Any]:
        if self.config.get('session_expired'):
            return {'success': False, 'error': '登录状态已失效，请重新登录'}
        try:
            if not self.verify_session(background=False):
                return {'success': False, 'error': '登录状态已失效，请重新登录'}
            account = dict(self.config.get('account') or {})
            return {'success': True, 'account': account}
        except Exception as exc:
            return {'success': False, 'error': str(exc)}

    def get_account_avatar(self) -> tuple[bytes, str]:
        """Fetch the current Weibo avatar server-side to avoid hotlink failures."""
        avatar_url = str((self.config.get('account') or {}).get('avatar') or '').strip()
        if avatar_url.startswith('//'):
            avatar_url = f'https:{avatar_url}'
        parsed = urlparse(avatar_url)
        host = (parsed.hostname or '').lower()
        allowed = host == 'sinaimg.cn' or host.endswith('.sinaimg.cn')
        if parsed.scheme != 'https' or not allowed:
            raise ValueError('头像地址无效')
        if avatar_url == self._avatar_cache_url and self._avatar_cache_data:
            return self._avatar_cache_data, self._avatar_cache_mimetype

        response = requests.get(
            avatar_url,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://weibo.com/',
            },
            timeout=15,
        )
        response.raise_for_status()
        content_type = (response.headers.get('Content-Type') or '').split(';', 1)[0].lower()
        if not content_type.startswith('image/') or not response.content:
            raise ValueError('微博头像响应不是图片')
        if len(response.content) > 5 * 1024 * 1024:
            raise ValueError('微博头像文件过大')
        self._avatar_cache_url = avatar_url
        self._avatar_cache_data = response.content
        self._avatar_cache_mimetype = content_type
        return self._avatar_cache_data, self._avatar_cache_mimetype

    def _my_account_uid(self) -> str:
        return str((self.config.get('account') or {}).get('uid') or '')

    def _is_incoming_contact_message(self, conv) -> bool:
        my_uid = self._my_account_uid()
        sender_id = str(getattr(conv, 'sender_id', '') or '')
        if my_uid and sender_id:
            return sender_id != my_uid
        my_nick = str((self.config.get('account') or {}).get('nickname') or '').strip()
        sender = (getattr(conv, 'sender_nickname', '') or '').strip()
        if my_nick and sender:
            return sender != my_nick
        return True

    def _message_body(self, conv) -> str:
        raw = self._raw_preview(conv)
        if '|' in raw:
            return raw.split('|', 1)[1].strip()
        return raw.strip()

    def _raw_preview(self, conv) -> str:
        message_id = str(getattr(conv, 'message_id', '') or '').strip()
        body = (conv.last_message or '').strip()
        return f'{message_id}|{body}' if message_id else body

    def _should_use_direct_preview(self, conv, has_unread: bool) -> bool:
        # 微博 contacts API 自带 sender_id，不依赖 unread 或聊天页 DOM。
        return True

    def _incoming_text(self, conv) -> str:
        if not self._is_incoming_contact_message(conv):
            return ''
        body = self._message_body(conv)
        sender = (getattr(conv, 'sender_nickname', '') or conv.nickname or '').strip()
        return self._parse_preview_message(body, sender) or body

    def _fallback_incoming_text(self, conv) -> str:
        return self._incoming_text(conv)

    def add_log(self, message: str, log_type: str = 'info', dedupe_seconds: float = 0) -> None:
        # 父类先将“抖音”替换为“小红书”，这里统一为微博。
        normalized = message.replace('抖音', '微博').replace('小红书', '微博')
        super().add_log(normalized, log_type, dedupe_seconds=dedupe_seconds)
        if self.logs:
            self.logs[0]['message'] = self.logs[0]['message'].replace('小红书', '微博')

    def start_monitoring(self) -> Dict[str, Any]:
        result = super().start_monitoring()
        if result.get('success'):
            self.add_log(f'微博监控引擎 {WEIBO_MONITOR_ENGINE} 已就绪', 'info')
        return result

    def build_export_package(self) -> Dict[str, Any]:
        package = super().build_export_package()
        package['app_name'] = 'BiliGo - 微博私信'
        package['platform'] = 'weibo'
        return package

    def reset_all_data(self) -> Dict[str, Any]:
        dashboard_metrics.clear_platform(self.ai_platform_key)
        ai_handoff_store.clear_platform(self.ai_platform_key)
        ai_conversation_store.clear_platform(self.ai_platform_key)
        self.stop_monitoring()
        if self._browser:
            try:
                self._browser.close_browser()
                self._browser.stop_worker()
            except Exception:
                pass
            self._browser = None
        self._init_paths()
        for path in (self.storage_file, self.stats_file):
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        for directory in (
            os.path.join(get_app_root(), 'weibo_browser_profile'),
            os.path.join(get_app_root(), 'weibo_media', 'reply_images'),
        ):
            if os.path.isdir(directory):
                shutil.rmtree(directory, ignore_errors=True)
        self.config = dict(WEIBO_DEFAULT_CONFIG)
        self.rules = [dict(DEFAULT_RULE)]
        self.user_reply_stats = {}
        self.logs = []
        self.last_seen_preview = {}
        self.last_seen_unread = {}
        self.last_seen_message_token = {}
        self._sent_reply_texts = {}
        self._recently_handled_raw = {}
        self._baseline_initialized = False
        self.last_send_time = 0.0
        self.login_in_progress = False
        self.save_config()
        self.save_rules()
        self.save_stats()
        self.precompile_rules()
        self.add_log('所有微博数据已清除，系统已恢复初始设置', 'warning')
        return {'success': True, 'message': '所有微博数据已清除'}


weibo_system = WeiboReplySystem()


def register_weibo_routes(app) -> None:
    register_platform_config_transfer_routes(app, 'weibo', '微博', weibo_system)
    @app.route('/weibo')
    def weibo_page():
        path = os.path.join(get_static_root(), 'xiaohongshu_reply.html')
        with open(path, 'r', encoding='utf-8') as f:
            html = f.read()
        html = html.replace(
            '<button class="platform-switcher-item active" disabled>小红书私信 <span class="check">✓</span></button>',
            '__XHS_MENU__',
        ).replace(
            '<button class="platform-switcher-item" onclick="location.href=\'/weibo\'">微博私信</button>',
            '__WEIBO_MENU__',
        )
        html = html.replace('xiaohongshu_theme.css', 'weibo_theme.css')
        html = html.replace('/dashboard?from=xiaohongshu', '/dashboard?from=weibo')
        html = html.replace('data-api-prefix="xiaohongshu"', 'data-api-prefix="weibo"')
        html = html.replace('data-platform-name="小红书"', 'data-platform-name="微博"')
        html = html.replace('xiaohongshu-seeklogo.png', 'sina-weibo-seeklogo.png')
        html = html.replace('小红书', '微博')
        html = html.replace('__XHS_MENU__', '<button class="platform-switcher-item" onclick="location.href=\'/xiaohongshu\'">小红书私信</button>')
        html = html.replace('__WEIBO_MENU__', '<button class="platform-switcher-item active" disabled>微博私信 <span class="check">✓</span></button>')
        return Response(html, mimetype='text/html')

    @app.route('/api/weibo-config', methods=['GET', 'POST'])
    def weibo_config_api():
        if request.method == 'GET':
            weibo_system.load_config()
            return jsonify(dict(weibo_system.config))
        try:
            data = request.get_json() or {}
            if data.get('default_reply_type') == 'image' or data.get('default_reply_image'):
                return jsonify({'success': False, 'error': '微博图片回复功能已暂停，请使用文字回复'}), 409
            traditional_keys = {'default_reply_enabled', 'default_reply_message', 'default_reply_type', 'default_reply_image'}
            if platform_enabled('weibo') and traditional_keys.intersection(data):
                return jsonify({'success': False, 'error': '已启用AI模式，无法修改默认回复设置'}), 409
            allowed = (
                'default_reply_enabled', 'default_reply_message', 'default_reply_type',
                'default_reply_image', 'message_check_interval', 'send_delay_interval',
                'only_reply_new_messages', 'max_replies_per_user',
                'unlimited_replies_per_user', 'headless',
            )
            for key in allowed:
                if key in data:
                    weibo_system.config[key] = data[key]
            weibo_system.config['default_reply_type'] = 'text'
            weibo_system.config['default_reply_image'] = ''
            if weibo_system.config.get('default_reply_type') != 'text':
                return jsonify({'success': False, 'error': '默认回复类型无效'})
            if float(weibo_system.config.get('message_check_interval') or 0) < 0.5:
                return jsonify({'success': False, 'error': '消息检查间隔不能小于 0.5 秒'})
            if float(weibo_system.config.get('send_delay_interval') or 0) < 0.5:
                return jsonify({'success': False, 'error': '发送间隔不能小于 0.5 秒'})
            if int(weibo_system.config.get('max_replies_per_user') or 0) < 1:
                return jsonify({'success': False, 'error': '单用户最大回复次数不能小于 1'})
            weibo_system.save_config()
            weibo_system.add_log('微博配置已保存', 'success')
            return jsonify({'success': True})
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/weibo-rules', methods=['GET', 'POST'])
    def weibo_rules_api():
        if request.method == 'GET':
            weibo_system.load_rules()
            return jsonify({'rules': weibo_system.rules})
        if platform_enabled('weibo'):
            return jsonify({'success': False, 'error': '已启用AI模式，无法修改关键词回复'}), 409
        rules = (request.get_json() or {}).get('rules', [])
        error = _validate_rules(rules)
        if error:
            return jsonify({'success': False, 'error': error})
        weibo_system.rules = rules
        weibo_system.save_rules()
        weibo_system.precompile_rules()
        weibo_system.add_log(f'微博规则已更新，共 {len(rules)} 条', 'success')
        return jsonify({'success': True})

    @app.route('/api/weibo-reply-image', methods=['POST'])
    def weibo_reply_image_upload():
        return jsonify({
            'success': False,
            'error': '微博图片回复功能已暂停，请使用文字回复',
        }), 410

    @app.route('/api/weibo-login/start', methods=['POST'])
    def weibo_login_start():
        return jsonify(weibo_system.start_login())

    @app.route('/api/weibo-login/status')
    def weibo_login_status():
        if request.args.get('verify') == '1' and not weibo_system.monitoring:
            weibo_system.verify_session(background=True, quick=True)
        return jsonify(weibo_system.get_login_status())

    @app.route('/api/weibo-account/refresh', methods=['POST'])
    def weibo_account_refresh():
        return jsonify(weibo_system.refresh_account_info())

    @app.route('/api/weibo-account/avatar')
    def weibo_account_avatar():
        try:
            data, mimetype = weibo_system.get_account_avatar()
            response = Response(data, mimetype=mimetype)
            response.headers['Cache-Control'] = 'private, max-age=300'
            return response
        except Exception:
            return Response(status=404)

    @app.route('/api/weibo-logout', methods=['POST'])
    def weibo_logout():
        return jsonify(weibo_system.logout())

    @app.route('/api/weibo-reset-all', methods=['POST'])
    def weibo_reset_all():
        return jsonify(weibo_system.reset_all_data())

    @app.route('/api/weibo-start', methods=['POST'])
    def weibo_start():
        return jsonify(weibo_system.start_monitoring())

    @app.route('/api/weibo-stop', methods=['POST'])
    def weibo_stop():
        return jsonify(weibo_system.stop_monitoring())

    @app.route('/api/weibo-status')
    def weibo_status():
        return jsonify(weibo_system.get_status())

    @app.route('/api/weibo-logs')
    def weibo_logs():
        limit = min(500, max(1, int(request.args.get('limit', 80))))
        return jsonify({'logs': weibo_system.logs[:limit]})
