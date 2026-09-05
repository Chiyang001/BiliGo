import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from playwright.sync_api import sync_playwright

PROFILE = os.path.join(ROOT, 'xiaohongshu_browser_profile')
STORAGE = os.path.join(ROOT, 'xiaohongshu_storage.json')
captured = []


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, headless=True, viewport={'width': 1280, 'height': 800}, locale='zh-CN',
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        with open(STORAGE, encoding='utf-8') as f:
            cookies = json.load(f).get('cookies') or []
        if cookies:
            ctx.add_cookies(cookies)

        def on_resp(response):
            url = response.url or ''
            if 'messages/history' in url and response.status == 200:
                try:
                    captured.append({'url': url, 'data': response.json()})
                except Exception:
                    pass

        page.on('response', on_resp)
        page.goto('https://www.xiaohongshu.com/chat', wait_until='domcontentloaded')
        time.sleep(4)
        page.evaluate("() => document.querySelector('.xhs-im-conv-item')?.click()")
        time.sleep(5)
        out = os.path.join(ROOT, 'tools', 'xhs_message_history.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        print('saved', out, 'count', len(captured))
        if captured:
            print(json.dumps(captured[0]['data'], ensure_ascii=False, indent=2)[:15000])
        ctx.close()


if __name__ == '__main__':
    main()
