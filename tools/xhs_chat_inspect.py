"""Inspect Xiaohongshu chat DOM for sticker/emoji message structure."""
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

INSPECT_JS = r"""
() => {
  const sample = (el, maxDepth = 4) => {
    const walk = (node, depth) => {
      if (!node || depth > maxDepth) return null;
      const tag = node.tagName ? node.tagName.toLowerCase() : '';
      const cls = String(node.className || '').slice(0, 120);
      const r = node.getBoundingClientRect ? node.getBoundingClientRect() : {width:0,height:0,x:0,y:0};
      const item = {
        tag, cls,
        text: (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120),
        alt: node.getAttribute ? (node.getAttribute('alt') || '') : '',
        src: node.getAttribute ? String(node.getAttribute('src') || '').slice(0, 160) : '',
        box: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
      };
      const kids = [];
      for (const child of (node.children || [])) {
        const sub = walk(child, depth + 1);
        if (sub) kids.push(sub);
      }
      if (kids.length) item.children = kids;
      return item;
    };
    return walk(el, 0);
  };

  const convItems = [...document.querySelectorAll('.xhs-im-conv-item, [class*="conv-item" i], [class*="im-conv" i]')].slice(0, 5);
  const bubbles = [...document.querySelectorAll('.chat-item__bubble, .chat-item__bubble--other, .chat-item__bubble--me, [class*="bubble" i]')].slice(0, 20);
  const imgs = [...document.querySelectorAll('img')].slice(0, 40).map(img => ({
    alt: img.getAttribute('alt') || '',
    title: img.getAttribute('title') || '',
    src: String(img.src || '').slice(0, 180),
    cls: String(img.className || '').slice(0, 120),
    box: (() => { const r = img.getBoundingClientRect(); return {x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height)}; })(),
    parentCls: String(img.parentElement?.className || '').slice(0, 120),
  }));

  return {
    url: location.href,
    title: document.title,
    bodySnippet: (document.body?.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 800),
    convCount: convItems.length,
    convSamples: convItems.map(el => ({
      text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200),
      html: el.innerHTML.slice(0, 600),
      tree: sample(el, 3),
    })),
    bubbleCount: bubbles.length,
    bubbleSamples: bubbles.map(el => ({
      text: (el.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200),
      html: el.innerHTML.slice(0, 800),
      cls: String(el.className || ''),
      tree: sample(el, 4),
    })),
    imgs,
    apiHints: performance.getEntriesByType('resource')
      .map(e => e.name)
      .filter(u => /im|chat|message|conv|session|sns\/web/i.test(u))
      .slice(-30),
  };
}
"""


def main():
    os.makedirs(PROFILE, exist_ok=True)
    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                PROFILE, channel='chrome', headless=False,
                viewport={'width': 1280, 'height': 800}, locale='zh-CN',
            )
        except Exception:
            ctx = p.chromium.launch_persistent_context(
                PROFILE, headless=False,
                viewport={'width': 1280, 'height': 800}, locale='zh-CN',
            )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if os.path.isfile(STORAGE):
            try:
                with open(STORAGE, encoding='utf-8') as f:
                    cookies = json.load(f).get('cookies') or []
                if cookies:
                    ctx.add_cookies(cookies)
            except Exception as exc:
                print('cookie load failed:', exc)

        page.goto(XHS_CHAT, wait_until='domcontentloaded')
        time.sleep(4)
        print('URL:', page.url)

        # click first conversation if any
        clicked = page.evaluate(r"""() => {
          const items = [...document.querySelectorAll('.xhs-im-conv-item, [class*="conv-item" i]')];
          for (const el of items) {
            const r = el.getBoundingClientRect();
            if (r.width > 50 && r.height > 40) { el.click(); return (el.innerText||'').slice(0,80); }
          }
          return '';
        }""")
        if clicked:
            print('Clicked conv:', clicked)
            time.sleep(3)

        data = page.evaluate(INSPECT_JS)
        out = os.path.join(ROOT, 'tools', 'xhs_chat_inspect_result.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print('Saved:', out)
        print('convCount:', data.get('convCount'), 'bubbleCount:', data.get('bubbleCount'))
        print('bodySnippet:', data.get('bodySnippet', '')[:300])
        for i, b in enumerate((data.get('bubbleSamples') or [])[:5]):
            print(f'--- bubble {i} cls={b.get("cls")} text={b.get("text")!r}')
            print('html:', (b.get('html') or '')[:300])
        ctx.close()


if __name__ == '__main__':
    main()
