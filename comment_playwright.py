"""可选：用真实 Chromium 打开稿件页，监听评论区 XHR（与网页一致，绕过部分直连 API 风控）。"""
from __future__ import annotations

import urllib.parse


def fetch_reply_json_via_browser(bvid: str, sessdata: str, bili_jct: str, timeout_ms: int = 55000):
    """
    返回与 /x/v2/reply 系列接口相近的 dict: { 'code', 'data', ... }，失败返回 None。
    需: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    if not bvid or not str(bvid).upper().startswith("BV"):
        return None

    sess = urllib.parse.unquote(sessdata) if sessdata else ""

    captured = []

    def on_response(resp):
        try:
            u = resp.url
            if "api.bilibili.com/x/v2/reply" not in u or resp.status != 200:
                return
            ct = (resp.headers.get("content-type") or "").lower()
            if "json" not in ct:
                return
            j = resp.json()
            if not isinstance(j, dict) or j.get("code") != 0:
                return
            data = j.get("data") or {}
            if "replies" in data or (data.get("cursor") and "reply" in u):
                captured.append(j)
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
        )
        context.add_cookies(
            [
                {
                    "name": "SESSDATA",
                    "value": sess,
                    "domain": ".bilibili.com",
                    "path": "/",
                },
                {
                    "name": "bili_jct",
                    "value": bili_jct or "",
                    "domain": ".bilibili.com",
                    "path": "/",
                },
            ]
        )
        page = context.new_page()
        page.on("response", on_response)
        page.goto(
            f"https://www.bilibili.com/video/{bvid}",
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        page.wait_for_timeout(6000)
        browser.close()

    if not captured:
        return None
    return captured[-1]
