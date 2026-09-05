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
            PROFILE, headless=False, viewport={'width': 1280, 'height': 800}, locale='zh-CN',
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        with open(STORAGE, encoding='utf-8') as f:
            cookies = json.load(f).get('cookies') or []
        if cookies:
            ctx.add_cookies(cookies)

        def on_resp(r):
            u = r.url or ''
            if 'edith.xiaohongshu.com/api/im/' in u and r.status == 200:
                try:
                    captured.append({'url': u, 'data': r.json()})
                except Exception:
                    pass

        page.on('response', on_resp)
        page.goto('https://www.xiaohongshu.com/chat', wait_until='domcontentloaded')
        time.sleep(4)
        page.locator('.xhs-im-conv-item').first.click()
        time.sleep(6)
        out = os.path.join(ROOT, 'tools', 'xhs_im_full_capture.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        print('saved', out, 'count', len(captured))
        for item in captured:
            if 'messages/history' in item['url'] or 'v3/chats' in item['url']:
                print('---', item['url'][:140])
                print(json.dumps(item['data'], ensure_ascii=False)[:2500])
        ctx.close()


if __name__ == '__main__':
    main()
