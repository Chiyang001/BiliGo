"""评论监控：楼中楼拉取与「回复我的」子评论识别（供 app.py / comment_reply_system 共用）"""
from __future__ import annotations

import json
import time

import bili_wbi


def _member_mid(reply_item: dict) -> int | None:
    m = reply_item.get("member") or {}
    mid = m.get("mid")
    if mid is None:
        return None
    try:
        return int(mid)
    except (TypeError, ValueError):
        return None


def _be_replied_mid(reply_item: dict) -> int | None:
    """楼中楼接口里「被回复者」的 mid（若存在）。"""
    br = reply_item.get("reply")
    if isinstance(br, list) and br:
        br = br[0]
    if isinstance(br, dict):
        mid = br.get("mid")
        if mid is not None:
            try:
                return int(mid)
            except (TypeError, ValueError):
                pass
        m = br.get("member") or {}
        if m.get("mid") is not None:
            try:
                return int(m["mid"])
            except (TypeError, ValueError):
                pass
    return None


def _fetch_sub_pages_legacy(
    session,
    oid: int,
    root: int,
    ps: int,
    bvid: str | None,
    max_pages: int,
    fetch_gap: float,
) -> list[dict]:
    out: list[dict] = []
    headers = {"Origin": "https://www.bilibili.com", "Referer": f"https://www.bilibili.com/video/{bvid}" if bvid else "https://www.bilibili.com/"}
    for pn in range(1, max_pages + 1):
        if pn > 1 and fetch_gap > 0:
            time.sleep(fetch_gap)
        r = session.get(
            "https://api.bilibili.com/x/v2/reply/reply",
            params={
                "type": 1,
                "oid": oid,
                "root": root,
                "pn": pn,
                "ps": min(max(int(ps), 1), 20),
            },
            headers=headers,
            timeout=20,
        )
        if r.status_code != 200:
            break
        try:
            j = r.json()
        except Exception:
            break
        if j.get("code") != 0:
            break
        chunk = (j.get("data") or {}).get("replies") or []
        out.extend(chunk)
        if not chunk:
            break
        if len(chunk) < min(ps, 20):
            break
    return out


def fetch_sub_replies_all(
    session,
    oid: int,
    root: int,
    ps: int,
    bvid: str | None,
    wbi_cache: dict,
    max_pages: int,
    fetch_gap: float,
) -> list[dict]:
    """拉取某条根评论下的全部楼中楼（优先 WBI，失败则回退旧版 reply）。"""
    all_replies: list[dict] = []
    pag = '{"offset":""}'
    for _ in range(max(1, max_pages)):
        if all_replies and fetch_gap > 0:
            time.sleep(fetch_gap)
        try:
            j = bili_wbi.fetch_reply_wbi_reply(session, oid, root, ps, bvid, wbi_cache, pagination_str=pag)
        except Exception:
            break
        if not j or j.get("code") != 0:
            break
        data = j.get("data") or {}
        chunk = data.get("replies") or []
        all_replies.extend(chunk)
        cursor = data.get("cursor") or {}
        pr = cursor.get("pagination_reply") or {}
        nxt = pr.get("next_offset")
        if not nxt or not chunk:
            break
        pag = json.dumps({"offset": nxt}, separators=(",", ":"))
    if all_replies:
        return all_replies
    return _fetch_sub_pages_legacy(session, oid, root, ps, bvid, max_pages, fetch_gap)


def expand_video_comments_for_monitor(
    session,
    wbi_cache: dict,
    video_id: int,
    video_title: str,
    bvid: str | None,
    top_replies: list[dict],
    my_uid: int,
    monitor_sub: bool,
    max_sub_pages: int,
    fetch_gap: float,
    sub_ps: int = 20,
) -> list[dict]:
    """
    在顶层评论列表基础上，合并楼中楼里「直接回复我」的评论条目。
    每条附带 thread_root_rpid、reply_target_rpid，供 /x/v2/reply/add 使用。
    """
    out: list[dict] = []
    oid = int(video_id)

    for tr in top_replies or []:
        root = tr.get("rpid")
        if not root:
            continue
        try:
            root = int(root)
        except (TypeError, ValueError):
            continue

        root_mid = _member_mid(tr)
        if root_mid is None:
            continue

        # 顶层：他人对视频的直评
        if root_mid != my_uid:
            item = dict(tr)
            item["video_id"] = video_id
            item["video_title"] = video_title
            item["thread_root_rpid"] = root
            item["reply_target_rpid"] = root
            out.append(item)

        if not monitor_sub:
            continue

        rcount = int(tr.get("rcount") or 0)
        preview = tr.get("replies") or []
        if rcount <= 0 and not preview:
            continue

        subs = fetch_sub_replies_all(
            session, oid, root, sub_ps, bvid, wbi_cache, max_sub_pages, fetch_gap
        )
        if not subs:
            continue

        author_map: dict[int, int] = {root: root_mid}
        subs_sorted = sorted(subs, key=lambda x: int(x.get("ctime") or 0))

        for sub in subs_sorted:
            srpid = sub.get("rpid")
            if not srpid:
                continue
            try:
                srpid = int(srpid)
            except (TypeError, ValueError):
                continue
            smid = _member_mid(sub)
            if smid is not None:
                author_map[srpid] = smid

        for sub in subs_sorted:
            srpid = sub.get("rpid")
            if not srpid:
                continue
            try:
                srpid = int(srpid)
            except (TypeError, ValueError):
                continue
            smid = _member_mid(sub)
            if smid is None or smid == my_uid:
                continue

            parent = sub.get("parent")
            try:
                parent = int(parent) if parent is not None else None
            except (TypeError, ValueError):
                parent = None

            br_mid = _be_replied_mid(sub)
            if br_mid is not None:
                targets_me = br_mid == my_uid
            elif parent and parent in author_map:
                targets_me = author_map[parent] == my_uid
            else:
                targets_me = False

            if not targets_me:
                continue

            item = dict(sub)
            item["video_id"] = video_id
            item["video_title"] = video_title
            item["thread_root_rpid"] = root
            item["reply_target_rpid"] = srpid
            out.append(item)

    return out


def _normalize_arc_item(a: dict) -> dict | None:
    aid = a.get("aid")
    if not aid:
        return None
    return {
        "aid": aid,
        "bvid": a.get("bvid", ""),
        "title": a.get("title", "未知视频"),
    }


def arc_list_page(session, mid: int, pn: int, ps: int = 50) -> tuple[list, int]:
    """返回 (archives 原始列表, 空间投稿总数 page.count)。"""
    r = session.get(
        "https://api.bilibili.com/x/space/arc/list",
        params={
            "mid": mid,
            "pn": pn,
            "ps": min(int(ps), 50),
            "order": "pubdate",
            "tid": 0,
        },
        timeout=15,
    )
    if r.status_code != 200:
        return [], 0
    try:
        j = r.json()
    except Exception:
        return [], 0
    if j.get("code") != 0:
        return [], 0
    d = j.get("data") or {}
    archives = d.get("archives")
    if not archives:
        archives = (d.get("list") or {}).get("vlist") or []
    page = d.get("page") or {}
    try:
        total = int(page.get("count") or len(archives) or 0)
    except (TypeError, ValueError):
        total = len(archives)
    return list(archives or []), total


def get_videos_for_monitor(session, mid: int, max_total: int, strategy: str = "both_ends") -> list[dict]:
    """
    拉取待监控的稿件列表。pubdate 排序下靠前为较新、靠后为较旧。
    - total <= max_total：拉全部分页，不遗漏最旧稿件。
    - total > max_total 且 strategy=newest：只取最新的 max_total 条（最旧永远扫不到）。
    - total > max_total 且 strategy=both_ends：一半从新稿件方向取、一半从最旧稿件方向取，避免只监控新稿。
    """
    ps = 50
    max_total = max(1, int(max_total))
    strategy = (strategy or "both_ends").strip().lower()
    if strategy not in ("newest", "both_ends"):
        strategy = "both_ends"

    archives0, total_count = arc_list_page(session, mid, 1, ps)
    if total_count <= 0 and not archives0:
        return []

    if total_count <= max_total:
        out: list[dict] = []
        pn = 1
        target = total_count if total_count > 0 else None
        while True:
            if target is not None and len(out) >= target:
                break
            arch, _ = arc_list_page(session, mid, pn, ps)
            if not arch:
                break
            for a in arch:
                it = _normalize_arc_item(a)
                if it:
                    out.append(it)
            if len(arch) < ps:
                break
            pn += 1
            if pn > 500:
                break
        seen: set = set()
        deduped = []
        for v in out:
            aid = v.get("aid")
            if aid in seen:
                continue
            seen.add(aid)
            deduped.append(v)
        return deduped

    if strategy == "newest":
        out = []
        pn = 1
        while len(out) < max_total:
            arch, _ = arc_list_page(session, mid, pn, ps)
            if not arch:
                break
            for a in arch:
                it = _normalize_arc_item(a)
                if it:
                    out.append(it)
                if len(out) >= max_total:
                    break
            if len(arch) < ps:
                break
            pn += 1
        return out[:max_total]

    # both_ends
    half = max_total // 2
    rest = max_total - half
    total_pages = max(1, (total_count + ps - 1) // ps)

    newest: list[dict] = []
    pn = 1
    while len(newest) < half and pn <= total_pages:
        arch, _ = arc_list_page(session, mid, pn, ps)
        if not arch:
            break
        for a in arch:
            it = _normalize_arc_item(a)
            if it:
                newest.append(it)
            if len(newest) >= half:
                break
        pn += 1
    newest = newest[:half]

    if total_pages == 1:
        arch1, _ = arc_list_page(session, mid, 1, ps)
        raw = [_normalize_arc_item(a) for a in arch1]
        raw = [x for x in raw if x]
        if len(raw) <= max_total:
            return raw
        tail = raw[-rest:] if rest else []
        head = raw[:half]
        merged = []
        seen2: set = set()
        for v in head + tail:
            aid = v.get("aid")
            if aid in seen2:
                continue
            seen2.add(aid)
            merged.append(v)
        return merged[:max_total]

    oldest: list[dict] = []
    need = rest
    pn_o = total_pages
    while need > 0 and pn_o >= 1:
        arch, _ = arc_list_page(session, mid, pn_o, ps)
        if arch:
            for a in reversed(arch):
                it = _normalize_arc_item(a)
                if not it:
                    continue
                oldest.insert(0, it)
                need -= 1
                if need <= 0:
                    break
        pn_o -= 1

    oldest = oldest[-rest:] if len(oldest) > rest else oldest

    merged2 = []
    seen3: set = set()
    for v in newest + oldest:
        aid = v.get("aid")
        if aid in seen3:
            continue
        seen3.add(aid)
        merged2.append(v)
    return merged2[:max_total]
