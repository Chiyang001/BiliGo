"""Regression checks for AI assignments, comment text-only schema and worker ownership."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


DATA_DIR = tempfile.TemporaryDirectory()
os.environ["BILIGO_DATA_DIR"] = DATA_DIR.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: E402
from douyin_playwright import DouyinBrowserWorker  # noqa: E402
import playwright.sync_api as playwright_sync_api  # noqa: E402


def check_ai_and_comment_apis() -> None:
    client = app.test_client()

    comment_page = client.get("/comment").get_data(as_text=True)
    assert "default-comment-reply-image" not in comment_page
    assert "image-browser-modal" not in comment_page

    created = client.post("/api/ai-knowledge", json={"name": "闲鱼知识", "text": "测试资料"})
    assert created.status_code == 200, created.get_data(as_text=True)
    base_id = created.get_json()["knowledge_base"]["id"]
    saved = client.post(
        "/api/ai-knowledge/settings",
        json={"enabled": True, "platform_assignments": {"xianyu": [base_id]}},
    )
    assert saved.status_code == 200, saved.get_data(as_text=True)
    assert saved.get_json()["platform_assignments"]["xianyu"] == [base_id]

    config = client.get("/api/comment-config").get_json()
    assert "default_comment_reply_type" not in config
    assert "default_comment_reply_image" not in config

    response = client.post(
        "/api/comment-rules",
        json={"rules": [{
            "id": 1, "name": "旧图片规则", "keyword": "图片", "reply": "",
            "reply_type": "image", "reply_image": "D:/old.png", "enabled": True,
        }]},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    rule = client.get("/api/comment-rules").get_json()["rules"][0]
    assert "reply_type" not in rule and "reply_image" not in rule
    assert rule["enabled"] is False


def check_worker_thread_ownership() -> None:
    original = playwright_sync_api.sync_playwright
    entered_threads: list[int] = []

    class FakePlaywrightContext:
        def __enter__(self):
            entered_threads.append(threading.get_ident())
            time.sleep(0.05)
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    playwright_sync_api.sync_playwright = FakePlaywrightContext
    try:
        worker = DouyinBrowserWorker(os.path.join(DATA_DIR.name, "storage.json"))
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(lambda _: worker.is_browser_alive(), range(24)))
        assert results == [False] * 24
        assert len(entered_threads) == 1, f"created {len(entered_threads)} Playwright owner threads"
        try:
            worker._dispatch("is_alive")
        except RuntimeError as exc:
            assert "所属工作线程" in str(exc)
        else:
            raise AssertionError("cross-thread dispatch was not rejected")
        worker.stop_worker()
    finally:
        playwright_sync_api.sync_playwright = original


def main() -> None:
    try:
        check_ai_and_comment_apis()
        check_worker_thread_ownership()
        print("Regression smoke tests passed")
    finally:
        DATA_DIR.cleanup()


if __name__ == "__main__":
    main()
