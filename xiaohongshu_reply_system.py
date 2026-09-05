"""BiliGo 小红书私信自动回复模块。"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Any, Dict, Optional

from flask import jsonify, request, send_from_directory

from app_paths import get_app_root, get_static_root
from ai_conversation_store import ai_conversation_store
from ai_reply_service import platform_enabled
from ai_handoff_store import ai_handoff_store
from dashboard_metrics import dashboard_metrics
from douyin_reply_system import DEFAULT_CONFIG, DEFAULT_RULE, DouyinReplySystem
from xiaohongshu_playwright import XiaohongshuBrowserWorker

XHS_DEFAULT_CONFIG = {
    **DEFAULT_CONFIG,
    'default_reply_message': '感谢您的私信，我会尽快回复~',
    'message_check_interval': 1.0,
    'send_delay_interval': 1.0,
}


class XiaohongshuReplySystem(DouyinReplySystem):
    ai_platform_key = 'xiaohongshu'
    def __init__(self):
        super().__init__()
        self.config = dict(XHS_DEFAULT_CONFIG)

    def _init_paths(self) -> None:
        root = get_app_root()
        if self.config_file is None:
            self.config_file = os.path.join(root, 'xiaohongshu_config.json')
        if self.rules_file is None:
            self.rules_file = os.path.join(root, 'xiaohongshu_keywords.json')
        if self.storage_file is None:
            self.storage_file = os.path.join(root, 'xiaohongshu_storage.json')
        if self.stats_file is None:
            self.stats_file = os.path.join(root, 'xiaohongshu_user_reply_stats.json')

    def _ensure_browser(self, headless: Optional[bool] = None) -> XiaohongshuBrowserWorker:
        self._init_paths()
        if self._browser is None:
            self._browser = XiaohongshuBrowserWorker(
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
        # 小红书会给未登录访客同样写入 web_session。这个 Cookie 只能说明
        # 浏览器访问过站点，不能证明用户已经登录。登录态必须由浏览器中的
        # selfinfo 接口验证，因此这里不能沿用抖音的“有 Cookie 即登录”逻辑。
        return False

    def _enrich_account_from_storage(self) -> None:
        return

    def _raw_preview(self, conv) -> str:
        preview = (conv.last_message or '').strip()
        msg_time = int(getattr(conv, 'last_msg_time', 0) or 0)
        store_id = int(getattr(conv, 'max_store_id', 0) or 0)
        update_time = int(getattr(conv, 'update_time', 0) or 0)
        parts = [preview]
        if store_id:
            parts.append(f'id:{store_id}')
        elif msg_time:
            parts.append(f'ts:{msg_time}')
        elif update_time:
            parts.append(f'ut:{update_time}')
        return '|'.join(parts)

    def _incoming_text(self, conv) -> str:
        sender = (getattr(conv, 'sender_nickname', '') or conv.nickname or '').strip()
        text = self._parse_preview_message(self._message_preview(conv), sender)
        if text in {'表情', '[表情]'}:
            return '[表情]'
        return text

    def _should_use_direct_preview(self, conv, has_unread: bool) -> bool:
        if has_unread:
            return True
        preview = self._message_preview(conv)
        return preview in {'[表情]', '表情'}

    def _postprocess_incoming_text(self, conv, msg_text: str, browser: Any = None) -> str:
        msg_text = (msg_text or '').strip()
        if msg_text != '[表情]' or browser is None:
            return msg_text
        chat_user_id = str(getattr(conv, 'conv_id', '') or '').strip()
        store_id = int(getattr(conv, 'max_store_id', 0) or 0)
        if chat_user_id and hasattr(browser, 'peek_latest_incoming'):
            try:
                row = browser.peek_latest_incoming(chat_user_id, store_id)
                if row and row.get('text'):
                    return str(row.get('text') or '').strip()
            except Exception:
                pass
        return msg_text

    def add_log(self, message: str, log_type: str = 'info', dedupe_seconds: float = 0) -> None:
        super().add_log(message.replace('抖音', '小红书'), log_type, dedupe_seconds=dedupe_seconds)

    def build_export_package(self) -> Dict[str, Any]:
        package = super().build_export_package()
        package['app_name'] = 'BiliGo - 小红书私信'
        package['platform'] = 'xiaohongshu'
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
            os.path.join(get_app_root(), 'xiaohongshu_browser_profile'),
            os.path.join(get_app_root(), 'xiaohongshu_media', 'reply_images'),
        ):
            if os.path.isdir(directory):
                shutil.rmtree(directory, ignore_errors=True)
        self.config = dict(XHS_DEFAULT_CONFIG)
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
        self.add_log('所有小红书数据已清除，系统已恢复初始设置', 'warning')
        return {'success': True, 'message': '所有小红书数据已清除'}


xiaohongshu_system = XiaohongshuReplySystem()


def _validate_rules(rules: Any) -> Optional[str]:
    if not isinstance(rules, list):
        return '规则格式错误'
    for rule in rules:
        if not isinstance(rule, dict) or not str(rule.get('keyword', '')).strip():
            return '规则格式错误'
        if rule.get('reply_type') == 'image' or rule.get('reply_image'):
            return '图片回复功能已暂停，请使用文字回复'
        rule['reply_type'] = 'text'
        rule['reply_image'] = ''
        if not str(rule.get('reply', '')).strip():
            return '文字回复规则缺少回复内容'
    return None


def register_platform_config_transfer_routes(app, prefix: str, label: str, system: DouyinReplySystem) -> None:
    def export_config():
        package = system.build_export_package()
        response = jsonify(package)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response.headers['Content-Disposition'] = (
            f'attachment; filename="biligo_{prefix}_config_{timestamp}.json"'
        )
        return response

    def import_config():
        if platform_enabled(prefix):
            return jsonify({'success': False, 'error': f'已启用{label}AI模式，请先关闭后再导入传统配置'}), 409
        upload = request.files.get('file')
        if not upload or not upload.filename:
            return jsonify({'success': False, 'error': '请选择配置文件'}), 400
        mode = str(request.form.get('import_mode') or 'replace')
        if mode not in ('replace', 'append'):
            return jsonify({'success': False, 'error': '导入模式无效'}), 400
        try:
            raw = upload.read(5 * 1024 * 1024 + 1)
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError('配置文件不能超过 5 MB')
            data = json.loads(raw.decode('utf-8-sig'))
            message = system.import_config_package(data, mode)
            return jsonify({'success': True, 'message': message})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400

    app.add_url_rule(
        f'/api/{prefix}-export-config', f'{prefix}_export_config', export_config, methods=['GET']
    )
    app.add_url_rule(
        f'/api/{prefix}-import-config', f'{prefix}_import_config', import_config, methods=['POST']
    )


def register_xiaohongshu_routes(app) -> None:
    register_platform_config_transfer_routes(app, 'xiaohongshu', '小红书', xiaohongshu_system)
    @app.route('/xiaohongshu')
    def xiaohongshu_page():
        return send_from_directory(get_static_root(), 'xiaohongshu_reply.html')

    @app.route('/api/xiaohongshu-config', methods=['GET', 'POST'])
    def xiaohongshu_config_api():
        if request.method == 'GET':
            xiaohongshu_system.load_config()
            return jsonify(dict(xiaohongshu_system.config))
        try:
            data = request.get_json() or {}
            if data.get('default_reply_type') == 'image' or data.get('default_reply_image'):
                return jsonify({'success': False, 'error': '小红书图片回复功能已暂停，请使用文字回复'}), 409
            traditional_keys = {'default_reply_enabled', 'default_reply_message', 'default_reply_type', 'default_reply_image'}
            if platform_enabled('xiaohongshu') and traditional_keys.intersection(data):
                return jsonify({'success': False, 'error': '已启用AI模式，无法修改默认回复设置'}), 409
            allowed = (
                'default_reply_enabled', 'default_reply_message', 'default_reply_type',
                'default_reply_image', 'message_check_interval', 'send_delay_interval',
                'only_reply_new_messages', 'max_replies_per_user',
                'unlimited_replies_per_user', 'headless',
            )
            for key in allowed:
                if key in data:
                    xiaohongshu_system.config[key] = data[key]
            xiaohongshu_system.config['default_reply_type'] = 'text'
            xiaohongshu_system.config['default_reply_image'] = ''
            if xiaohongshu_system.config.get('default_reply_type') != 'text':
                return jsonify({'success': False, 'error': '默认回复类型无效'})
            if float(xiaohongshu_system.config.get('message_check_interval') or 0) < 0.5:
                return jsonify({'success': False, 'error': '消息检查间隔不能小于 0.5 秒'})
            if float(xiaohongshu_system.config.get('send_delay_interval') or 0) < 0.5:
                return jsonify({'success': False, 'error': '发送间隔不能小于 0.5 秒'})
            if int(xiaohongshu_system.config.get('max_replies_per_user') or 0) < 1:
                return jsonify({'success': False, 'error': '单用户最大回复次数不能小于 1'})
            xiaohongshu_system.save_config()
            xiaohongshu_system.add_log('小红书配置已保存', 'success')
            return jsonify({'success': True})
        except Exception as exc:
            return jsonify({'success': False, 'error': str(exc)})

    @app.route('/api/xiaohongshu-rules', methods=['GET', 'POST'])
    def xiaohongshu_rules_api():
        if request.method == 'GET':
            xiaohongshu_system.load_rules()
            return jsonify({'rules': xiaohongshu_system.rules})
        if platform_enabled('xiaohongshu'):
            return jsonify({'success': False, 'error': '已启用AI模式，无法修改关键词回复'}), 409
        rules = (request.get_json() or {}).get('rules', [])
        error = _validate_rules(rules)
        if error:
            return jsonify({'success': False, 'error': error})
        xiaohongshu_system.rules = rules
        xiaohongshu_system.save_rules()
        xiaohongshu_system.precompile_rules()
        xiaohongshu_system.add_log(f'小红书规则已更新，共 {len(rules)} 条', 'success')
        return jsonify({'success': True})

    @app.route('/api/xiaohongshu-reply-image', methods=['POST'])
    def xiaohongshu_reply_image_upload():
        return jsonify({
            'success': False,
            'error': '小红书图片回复功能已暂停，请使用文字回复',
        }), 410

    @app.route('/api/xiaohongshu-login/start', methods=['POST'])
    def xiaohongshu_login_start():
        return jsonify(xiaohongshu_system.start_login())

    @app.route('/api/xiaohongshu-login/status')
    def xiaohongshu_login_status():
        if request.args.get('verify') == '1' and not xiaohongshu_system.monitoring:
            xiaohongshu_system.verify_session(background=True, quick=True)
        return jsonify(xiaohongshu_system.get_login_status())

    @app.route('/api/xiaohongshu-account/refresh', methods=['POST'])
    def xiaohongshu_account_refresh():
        return jsonify(xiaohongshu_system.refresh_account_info())

    @app.route('/api/xiaohongshu-logout', methods=['POST'])
    def xiaohongshu_logout():
        return jsonify(xiaohongshu_system.logout())

    @app.route('/api/xiaohongshu-reset-all', methods=['POST'])
    def xiaohongshu_reset_all():
        return jsonify(xiaohongshu_system.reset_all_data())

    @app.route('/api/xiaohongshu-start', methods=['POST'])
    def xiaohongshu_start():
        return jsonify(xiaohongshu_system.start_monitoring())

    @app.route('/api/xiaohongshu-stop', methods=['POST'])
    def xiaohongshu_stop():
        return jsonify(xiaohongshu_system.stop_monitoring())

    @app.route('/api/xiaohongshu-status')
    def xiaohongshu_status():
        return jsonify(xiaohongshu_system.get_status())

    @app.route('/api/xiaohongshu-logs')
    def xiaohongshu_logs():
        limit = min(500, max(1, int(request.args.get('limit', 80))))
        return jsonify({'logs': xiaohongshu_system.logs[:limit]})
