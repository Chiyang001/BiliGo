"""闲鱼消息平台接入。"""
from __future__ import annotations

import os
import shutil
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from flask import Response, jsonify, request, send_from_directory

from app_paths import get_app_root, get_static_root
from ai_conversation_store import ai_conversation_store
from ai_handoff_store import ai_handoff_store
from ai_reply_service import platform_enabled
from dashboard_metrics import dashboard_metrics
from douyin_reply_system import DEFAULT_CONFIG, DEFAULT_RULE, DouyinReplySystem
from xiaohongshu_reply_system import _validate_rules, register_platform_config_transfer_routes
from xianyu_playwright import XianyuBrowserWorker

XIANYU_DEFAULT_CONFIG = {
    **DEFAULT_CONFIG,
    "message_check_interval": 2.0,
    "send_delay_interval": 2.0,
    "headless": False,
    "default_reply_message": "您好，感谢您的消息，我会尽快回复您。",
}


class XianyuReplySystem(DouyinReplySystem):
    ai_platform_key = "xianyu"

    def __init__(self):
        super().__init__()
        self.config = dict(XIANYU_DEFAULT_CONFIG)

    def _init_paths(self) -> None:
        root = get_app_root()
        self.config_file = self.config_file or os.path.join(root, "xianyu_config.json")
        self.rules_file = self.rules_file or os.path.join(root, "xianyu_keywords.json")
        self.storage_file = self.storage_file or os.path.join(root, "xianyu_storage.json")
        self.stats_file = self.stats_file or os.path.join(root, "xianyu_user_reply_stats.json")

    def _ensure_browser(self, headless: Optional[bool] = None) -> XianyuBrowserWorker:
        self._init_paths()
        if self._browser is None:
            self._browser = XianyuBrowserWorker(self.storage_file, headless if headless is not None else bool(self.config.get("headless", False)))
        elif headless is not None:
            self._browser.set_headless(headless)
        account = self.config.get("account") or {}
        self._browser.set_account_identity(str(account.get("uid") or ""), str(account.get("nickname") or ""))
        return self._browser

    def _storage_has_session_cookies(self) -> bool:
        # 闲鱼会向未登录访客写入 Cookie；文件存在不能证明账号已登录。
        # 始终通过消息页做真实登录态检查，避免将游客会话误判为已登录。
        return False

    def get_account_avatar(self) -> tuple[bytes, str]:
        url = str((self.config.get("account") or {}).get("avatar") or "").strip()
        parsed = urlparse(url)
        allowed_hosts = ("alicdn.com", "tbcdn.cn", "taobaocdn.com", "goofish.com")
        if parsed.scheme not in ("http", "https") or not any(
            parsed.hostname == host or (parsed.hostname or "").endswith(f".{host}")
            for host in allowed_hosts
        ):
            raise ValueError("无效的闲鱼头像地址")
        response = requests.get(
            url,
            headers={
                "Referer": "https://www.goofish.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            },
            timeout=12,
        )
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise ValueError("头像地址未返回图片")
        return response.content, content_type

    def add_log(self, message: str, log_type: str = "info", dedupe_seconds: float = 0) -> None:
        super().add_log(message.replace("抖音", "闲鱼"), log_type, dedupe_seconds=dedupe_seconds)

    def start_monitoring(self) -> Dict[str, Any]:
        result = super().start_monitoring()
        for key in ("error", "message"):
            if isinstance(result.get(key), str):
                result[key] = result[key].replace("抖音", "闲鱼")
        return result

    def build_export_package(self) -> Dict[str, Any]:
        data = super().build_export_package()
        data.update({"app_name": "BiliGo - 闲鱼消息", "platform": "xianyu"})
        return data

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
        for path in (self.config_file, self.rules_file, self.storage_file, self.stats_file):
            if path and os.path.isfile(path):
                os.remove(path)
        profile = os.path.join(get_app_root(), "xianyu_browser_profile")
        if os.path.isdir(profile):
            shutil.rmtree(profile, ignore_errors=True)
        self.config = dict(XIANYU_DEFAULT_CONFIG)
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
        self.save_config(); self.save_rules(); self.save_stats(); self.precompile_rules()
        return {"success": True, "message": "闲鱼数据已重置"}


xianyu_system = XianyuReplySystem()


def register_xianyu_routes(app) -> None:
    register_platform_config_transfer_routes(app, "xianyu", "闲鱼", xianyu_system)
    @app.route("/xianyu")
    def xianyu_page():
        return send_from_directory(get_static_root(), "xianyu_reply.html")

    @app.route("/api/xianyu-config", methods=["GET", "POST"])
    def xianyu_config():
        if request.method == "GET":
            xianyu_system.load_config(); return jsonify(xianyu_system.config)
        try:
            data = request.get_json(silent=True) or {}
            traditional_keys = {"default_reply_enabled", "default_reply_message"}
            if platform_enabled("xianyu") and traditional_keys.intersection(data):
                return jsonify({"success": False, "error": "已启用闲鱼 AI 模式，无法修改默认回复设置"}), 409
            allowed = ("default_reply_enabled", "default_reply_message", "message_check_interval", "send_delay_interval", "only_reply_new_messages", "max_replies_per_user", "unlimited_replies_per_user", "headless")
            updated = dict(xianyu_system.config)
            for key in allowed:
                if key in data: updated[key] = data[key]
            check_interval = float(updated.get("message_check_interval") or 0)
            send_interval = float(updated.get("send_delay_interval") or 0)
            max_replies = int(updated.get("max_replies_per_user") or 0)
            if not 0.5 <= check_interval <= 60:
                return jsonify({"success": False, "error": "消息检查间隔必须在 0.5-60 秒之间"}), 400
            if not 0.5 <= send_interval <= 30:
                return jsonify({"success": False, "error": "发送间隔必须在 0.5-30 秒之间"}), 400
            if not updated.get("unlimited_replies_per_user") and max_replies < 1:
                return jsonify({"success": False, "error": "单用户最大回复次数不能小于 1"}), 400
            xianyu_system.config.update(updated)
            xianyu_system.save_config()
            xianyu_system.add_log("闲鱼配置已保存", "success")
            return jsonify({"success": True})
        except (TypeError, ValueError) as exc:
            return jsonify({"success": False, "error": f"配置格式错误: {exc}"}), 400

    @app.route("/api/xianyu-rules", methods=["GET", "POST"])
    def xianyu_rules():
        if request.method == "GET":
            xianyu_system.load_rules(); return jsonify({"rules": xianyu_system.rules})
        if platform_enabled("xianyu"):
            return jsonify({"success": False, "error": "已启用闲鱼 AI 模式，无法修改关键词回复"}), 409
        data = request.get_json(silent=True) or {}
        rules = data.get("rules")
        error = _validate_rules(rules)
        if error: return jsonify({"success": False, "error": error}), 400
        xianyu_system.rules = rules; xianyu_system.save_rules(); xianyu_system.precompile_rules()
        xianyu_system.add_log(f"闲鱼规则已更新，共 {len(rules)} 条", "success")
        return jsonify({"success": True})

    @app.route("/api/xianyu-login/start", methods=["POST"])
    def xianyu_login_start(): return jsonify(xianyu_system.start_login())

    @app.route("/api/xianyu-login/status")
    def xianyu_login_status():
        if request.args.get("verify") == "1" and not xianyu_system.monitoring:
            xianyu_system.verify_session(background=True, quick=True)
        return jsonify(xianyu_system.get_login_status())

    @app.route("/api/xianyu-account/refresh", methods=["POST"])
    def xianyu_account_refresh(): return jsonify(xianyu_system.refresh_account_info())

    @app.route("/api/xianyu-account/avatar")
    def xianyu_account_avatar():
        try:
            data, mimetype = xianyu_system.get_account_avatar()
            response = Response(data, mimetype=mimetype)
            response.headers["Cache-Control"] = "private, max-age=300"
            return response
        except Exception:
            return Response(status=404)

    @app.route("/api/xianyu-logout", methods=["POST"])
    def xianyu_logout(): return jsonify(xianyu_system.logout())

    @app.route("/api/xianyu-reset-all", methods=["POST"])
    def xianyu_reset(): return jsonify(xianyu_system.reset_all_data())

    @app.route("/api/xianyu-start", methods=["POST"])
    def xianyu_start(): return jsonify(xianyu_system.start_monitoring())

    @app.route("/api/xianyu-stop", methods=["POST"])
    def xianyu_stop(): return jsonify(xianyu_system.stop_monitoring())

    @app.route("/api/xianyu-status")
    def xianyu_status(): return jsonify(xianyu_system.get_status())

    @app.route("/api/xianyu-logs")
    def xianyu_logs():
        try:
            limit = min(500, max(1, int(request.args.get("limit", 80))))
        except (TypeError, ValueError):
            limit = 80
        return jsonify({"logs": xianyu_system.logs[:limit]})
