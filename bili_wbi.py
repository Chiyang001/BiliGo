"""B 站 Web 接口 WBI 签名（用于 x/v2/reply/wbi/main 等需鉴权接口）"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


def mixin_key_from_strings(img_key: str, sub_key: str) -> str:
    orig = (img_key or "") + (sub_key or "")
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def encode_wbi_params(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = mixin_key_from_strings(img_key, sub_key)
    out = dict(params)
    out["wts"] = int(time.time())
    out = dict(sorted(out.items()))
    filtered = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in out.items()}
    query = urllib.parse.urlencode(filtered)
    filtered["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return filtered


def extract_wbi_keys_from_nav_data(data: dict) -> tuple[str, str]:
    wi = (data or {}).get("wbi_img") or {}
    img_url = wi.get("img_url") or ""
    sub_url = wi.get("sub_url") or (data or {}).get("wbi_sub", {}).get("sub_url", "")
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""
    return img_key, sub_key


def refresh_wbi_keys(session, cache: dict | None) -> tuple[str, str]:
    """cache: 可选 { 'img_key','sub_key','ts' }，约 10 分钟复用"""
    now = time.time()
    if cache and cache.get("img_key") and cache.get("sub_key"):
        if now - float(cache.get("ts") or 0) < 600:
            return cache["img_key"], cache["sub_key"]
    r = session.get("https://api.bilibili.com/x/web-interface/nav", timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"nav: {j.get('code')} {j.get('message', '')}")
    img_key, sub_key = extract_wbi_keys_from_nav_data(j.get("data") or {})
    if not img_key or not sub_key:
        raise RuntimeError("nav 中无 wbi_img 密钥")
    if cache is not None:
        cache["img_key"] = img_key
        cache["sub_key"] = sub_key
        cache["ts"] = now
    return img_key, sub_key


def merge_reply_main_data(reply_data: dict) -> list:
    """合并 wbi/main 返回的 data 中的主评论与置顶（与 app.merge_bilibili_reply_main_block 一致）。"""
    if not reply_data:
        return []
    replies = list(reply_data.get("replies") or [])
    top_obj = reply_data.get("top")
    if isinstance(top_obj, dict):
        top_replies = top_obj.get("upper") or top_obj.get("top") or top_obj.get("admin")
        if isinstance(top_replies, dict):
            top_replies = [top_replies]
        if isinstance(top_replies, list):
            replies = top_replies + replies
    for tr in reply_data.get("top_replies") or []:
        if isinstance(tr, dict) and tr not in replies:
            replies.insert(0, tr)
    return replies


def fetch_reply_wbi_main(
    session,
    oid,
    ps: int = 20,
    bvid: str | None = None,
    wbi_cache: dict | None = None,
    pagination_str: str | None = None,
    mode: int = 3,
):
    """
    调用 Web 端新版评论区接口 GET /x/v2/reply/wbi/main（需 WBI），返回解析后的 JSON dict。
    首屏 pagination_str 为 {\"offset\":\"\"}。
    mode: 2=热度 3=按时间（新评论优先出现在前几页，便于监控）
    """
    img_key, sub_key = refresh_wbi_keys(session, wbi_cache)
    if pagination_str is None:
        pagination_str = '{"offset":""}'
    params = {
        "type": 1,
        "oid": oid,
        "mode": int(mode),
        "pagination_str": pagination_str,
        "plat": 1,
        "web_location": "1315875",
        "ps": min(max(int(ps), 1), 30),
    }
    signed = encode_wbi_params(params, img_key, sub_key)
    q = urllib.parse.urlencode(signed)
    url = "https://api.bilibili.com/x/v2/reply/wbi/main?" + q
    headers = {
        "Origin": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    if bvid:
        headers["Referer"] = f"https://www.bilibili.com/video/{bvid}"
    else:
        headers["Referer"] = "https://www.bilibili.com/"
    r = session.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        try:
            body = r.text[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {r.status_code} {body}")
    return json.loads(r.text)


def fetch_main_comment_replies_paged(
    session,
    oid,
    ps: int,
    bvid: str | None,
    wbi_cache: dict | None,
    mode: int = 3,
    max_pages: int = 15,
    fetch_gap: float = 0,
) -> list:
    """
    分页拉取主评论列表，合并去重（按 rpid）。
    第 1 页含置顶；后续页仅追加 replies，避免重复置顶。
    """
    ps = min(max(int(ps), 1), 30)
    max_pages = max(1, int(max_pages))
    seen: set[int] = set()
    out: list = []
    pag: str | None = '{"offset":""}'
    for page_i in range(max_pages):
        if page_i > 0 and fetch_gap > 0:
            time.sleep(float(fetch_gap))
        try:
            j = fetch_reply_wbi_main(session, oid, ps, bvid, wbi_cache, pagination_str=pag, mode=mode)
        except Exception:
            break
        if not j or j.get("code") != 0:
            break
        data = j.get("data") or {}
        if page_i == 0:
            chunk = merge_reply_main_data(data)
        else:
            chunk = list(data.get("replies") or [])
        for item in chunk:
            if not isinstance(item, dict):
                continue
            rpid = item.get("rpid")
            try:
                ir = int(rpid) if rpid is not None else None
            except (TypeError, ValueError):
                ir = None
            if ir is None:
                continue
            if ir in seen:
                continue
            seen.add(ir)
            out.append(item)
        cursor = data.get("cursor") or {}
        pr = cursor.get("pagination_reply") or {}
        nxt = pr.get("next_offset")
        if not nxt or not chunk:
            break
        pag = json.dumps({"offset": nxt}, separators=(",", ":"))
    return out


def fetch_reply_wbi_reply(
    session,
    oid,
    root,
    ps: int = 20,
    bvid: str | None = None,
    wbi_cache: dict | None = None,
    pagination_str: str | None = None,
):
    """
    楼中楼 GET /x/v2/reply/wbi/reply（需 WBI），参数与 wbi/main 类似，增加 root=根评论 rpid。
    """
    img_key, sub_key = refresh_wbi_keys(session, wbi_cache)
    if pagination_str is None:
        pagination_str = '{"offset":""}'
    params = {
        "type": 1,
        "oid": oid,
        "root": root,
        "mode": 3,
        "pagination_str": pagination_str,
        "plat": 1,
        "web_location": "1315875",
        "ps": min(max(int(ps), 1), 30),
    }
    signed = encode_wbi_params(params, img_key, sub_key)
    q = urllib.parse.urlencode(signed)
    url = "https://api.bilibili.com/x/v2/reply/wbi/reply?" + q
    headers = {
        "Origin": "https://www.bilibili.com",
        "Accept": "application/json, text/plain, */*",
    }
    if bvid:
        headers["Referer"] = f"https://www.bilibili.com/video/{bvid}"
    else:
        headers["Referer"] = "https://www.bilibili.com/"
    r = session.get(url, headers=headers, timeout=20)
    if r.status_code != 200:
        try:
            body = r.text[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {r.status_code} {body}")
    return json.loads(r.text)
