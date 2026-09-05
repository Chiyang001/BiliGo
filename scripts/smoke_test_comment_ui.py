"""Exercise Bilibili comment saves in a real browser and catch JS regressions."""
from __future__ import annotations

import atexit
import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


_data_dir = tempfile.TemporaryDirectory()
atexit.register(_data_dir.cleanup)
os.environ["BILIGO_DATA_DIR"] = _data_dir.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.load(response)


def main() -> None:
    external_origin = os.environ.get("BILIGO_TEST_ORIGIN", "").strip().rstrip("/")
    if external_origin:
        origin = external_origin
    else:
        port = _free_port()
        threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
            daemon=True,
        ).start()
        origin = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(origin + "/comment", timeout=1).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Flask smoke-test server did not start")

    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        response = page.goto(origin + "/comment", wait_until="networkidle")
        assert response and response.ok, "comment page request failed"
        page.locator('[data-platform-tab="reply"]').click()

        default_message = '默认评论 <测试> & "安全"'
        page.locator("#default-comment-reply-enabled").check()
        page.locator("#default-comment-reply-message").fill(default_message)
        with page.expect_response(
            lambda item: item.url.endswith("/api/comment-config")
            and item.request.method == "POST"
        ) as response_info:
            page.get_by_role("button", name="保存默认回复设置").click()
        save_response = response_info.value
        assert save_response.ok, save_response.text()
        assert save_response.json().get("success") is True
        page.locator(".toast.success", has_text="默认评论回复设置已保存").wait_for()

        saved_config = _read_json(origin + "/api/comment-config")
        assert saved_config["default_comment_reply_enabled"] is True
        assert saved_config["default_comment_reply_message"] == default_message

        unsafe_title = '<img id="comment-xss-marker" src=x onerror="window.__commentXss=true">'
        page.locator("#comment-rule-title").fill(unsafe_title)
        page.locator("#comment-keywords").fill("测试")
        page.locator("#comment-reply").fill("安全回复 <b>正文</b>")
        with page.expect_response(
            lambda item: item.url.endswith("/api/comment-rules")
            and item.request.method == "POST"
        ) as response_info:
            page.get_by_role("button", name="添加评论回复规则").click()
        rule_response = response_info.value
        assert rule_response.ok, rule_response.text()
        assert rule_response.json().get("success") is True
        page.locator('[data-platform-tab="rules"]').click()
        page.locator("#comment-rules-list", has_text=unsafe_title).wait_for()
        assert page.locator("#comment-rules-list #comment-xss-marker").count() == 0
        assert page.evaluate("window.__commentXss !== true")

        page.evaluate("addCommentLog('<img id=log-xss-marker src=x>', 'success')")
        assert page.locator("#logs-container #log-xss-marker").count() == 0

        page.locator('[data-platform-tab="reply"]').click()
        page.route(
            "**/api/comment-rules",
            lambda route: route.fulfill(
                status=409,
                content_type="application/json",
                body=json.dumps({"success": False, "error": "模拟保存失败"}),
            ),
            times=1,
        )
        page.locator("#comment-rule-title").fill("不会假成功")
        page.locator("#comment-keywords").fill("失败")
        page.locator("#comment-reply").fill("保留输入")
        page.get_by_role("button", name="添加评论回复规则").click()
        page.locator(".toast.error", has_text="模拟保存失败").wait_for()
        assert page.evaluate("commentRules.length") == 1
        assert page.locator("#comment-rule-title").input_value() == "不会假成功"
        assert not page_errors, f"JavaScript page errors: {page_errors}"
        browser.close()

    print("Bilibili comment UI smoke test passed")


if __name__ == "__main__":
    main()
