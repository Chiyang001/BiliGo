"""Capture XHS IM API response shapes."""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright

PROFILE = os.path.join(ROOT, 'xiaohongshu_browser_profile')
STORAGE = os.path.join(ROOT, 'xiaohongshu_storage.json')
XHS_CHAT = 'https://www.xiaohongshu.com/chat'

captured = []


def main():
    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                PROFILE, channel='chrome', headless=True,
                viewport={'width': 1280, 'height': 800}, locale='zh-CN',
            )
        except Exception:
            ctx = p.chromium.launch_persistent_context(
                PROFILE, headless=True,
                viewport={'width': 1280, 'height': 800}, locale='zh-CN',
            )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if os.path.isfile(STORAGE):
            with open(STORAGE, encoding='utf-8') as f:
                cookies = json.load(f).get('cookies') or []
            if cookies:
                ctx.add_cookies(cookies)

        def on_response(response):
            url = response.url or ''
            if 'edith.xiaohongshu.com/api/im/' not in url:
                return
            if response.status != 200:
                return
            try:
                ct = (response.headers.get('content-type') or '').lower()
                if 'json' not in ct:
                    return
                data = response.json()
            except Exception:
                return
            captured.append({'url': url, 'data': data})

        page.on('response', on_response)
        page.goto(XHS_CHAT, wait_until='domcontentloaded')
        time.sleep(5)
        page.evaluate(r"""() => {
          const el = document.querySelector('.xhs-im-conv-item');
          if (el) el.click();
        }""")
        time.sleep(4)
        out = os.path.join(ROOT, 'tools', 'xhs_im_api_capture.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        print('saved', out, 'entries', len(captured))
        for item in captured:
            print('---', item['url'][:120])
        ctx.close()


if __name__ == '__main__':
    main()
