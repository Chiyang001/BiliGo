"""Local smoke test for the Xianyu Flask page and browser-side initialization."""
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
    url = f"http://127.0.0.1:{port}/xianyu"
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=1).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Flask smoke-test server did not start")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        response = page.goto(url, wait_until="networkidle")
        assert response and response.ok, f"Xianyu page returned {response.status if response else 'no response'}"
        assert page.title() == "BiliGo - 闲鱼消息自动回复"
        assert page.locator(".platform-tab-button").count() == 5
        assert not page_errors, f"Browser errors: {page_errors}"
        page.evaluate("updateXhsAccount({}, false, null, false)")
        assert page.locator("#login-required-hint").is_visible()
        page.locator("#login-required-hint button").click()
        assert page.locator('[data-platform-tab="account"]').get_attribute("aria-selected") == "true"
        browser.close()
    print("Xianyu page smoke test passed")


if __name__ == "__main__":
    main()
