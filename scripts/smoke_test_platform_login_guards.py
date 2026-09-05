"""Verify the logged-out monitor controls on every supported platform page."""
from __future__ import annotations

import socket
import sys
import os
import atexit
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


def main() -> None:
    port = _free_port()
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    ).start()
    origin = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(origin + "/", timeout=1).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Flask smoke-test server did not start")

    cases = (
        ("bili_message", "/", "isMessageLoggedIn=false; isMonitoring=false; updateButtonStates()"),
        ("bili_comment", "/comment", "isCommentLoggedIn=false; isCommentMonitoring=false; updateCommentButtonStates()"),
        ("douyin", "/douyin", "updateAccountUI({}, false, null, false)"),
        ("xiaohongshu", "/xiaohongshu", "updateXhsAccount({}, false, null, false)"),
        ("weibo", "/weibo", "updateXhsAccount({}, false, null, false)"),
        ("xianyu", "/xianyu", "updateXhsAccount({}, false, null, false)"),
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        for platform, path, simulate_logout in cases:
            response = page.goto(origin + path, wait_until="networkidle")
            assert response and response.ok, f"{platform}: page request failed"
            page.evaluate(simulate_logout)
            assert page.locator("#start-btn").is_disabled(), f"{platform}: start button is enabled"
            assert page.locator("#stop-btn").is_disabled(), f"{platform}: stop button is enabled"
            hint = page.locator("#login-required-hint")
            assert hint.is_visible(), f"{platform}: login hint is hidden"
            hint.locator("button").click()
            assert page.locator('[data-platform-tab="account"]').get_attribute("aria-selected") == "true", f"{platform}: account link failed"
        browser.close()
    print("All platform login guards passed")


if __name__ == "__main__":
    main()
