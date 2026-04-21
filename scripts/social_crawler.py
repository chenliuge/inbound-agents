"""国内社媒爬虫统一 Skill（cn8n.com）

封装所有国内社媒接口（小红书/抖音/微信公众号），供各 Agent 统一调用。

## 支持的平台与接口

### 抖音（p2/douyin）
- douyin_search(keyword, ...)          关键词搜索视频（原 general_search）
- douyin_search_sug(keyword)           搜索衍生词（拓展搜索用）
- douyin_aweme_detail(aweme_id)        视频详情（拿完整文案、数据、封面）
- douyin_video_comment(aweme_id, ...)  视频一级评论

### 小红书（p2/xhs）
- xhs_search_note(keyword, ...)        关键词搜索笔记（APP 端 + Web 端自动切换）
- xhs_note_detail(note_id)             笔记详情（拿完整正文）
- xhs_note_comment(note_id, ...)       笔记一级评论
- xhs_user_post(user_id, ...)          用户笔记列表

### 微信公众号（p4/fbmain/monitor/v3）
- wechat_kw_search(keyword, ...)       关键词全局搜索（核心功能）
- wechat_web_search(keyword, ...)      Web 搜索（fallback）
- wechat_hot_typical_search(keyword)   热门典型文章搜索
- wechat_post_history(account_name, ...)  账号历史文章
- wechat_read_zan(article_url)         文章阅读/点赞数

## 基础配置

Base URL: https://cn8n.com
Auth:     Bearer ${SOCIAL_API_TOKEN}（从环境变量读取）

## 使用示例

    from scripts.social_crawler import xhs_search_note, wechat_kw_search

    # 搜小红书
    notes = xhs_search_note("入境游 GEO", max_results=20)
    for n in notes:
        print(n["title"], n["likes"])

    # 搜公众号
    articles = wechat_kw_search("入境游 海外获客", max_results=10)

## 错误处理

- 所有函数遇到错误返回空列表 `[]` 或空字典 `{}`，不抛异常
- 错误信息通过 print 打印（前缀 `[crawler]`）
- 无 SOCIAL_API_TOKEN 环境变量时返回空，不会挂进程
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Optional

import requests


# ============================================================
# 基础配置
# ============================================================

_BASE = "https://cn8n.com"
_TIMEOUT = 20


def _token() -> str:
    return os.environ.get("SOCIAL_API_TOKEN", "")


def _has_token() -> bool:
    return bool(_token())


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    }


def _post(path: str, payload: dict, timeout: int = _TIMEOUT) -> dict:
    """统一 POST 接口。返回响应 JSON，失败时返回 {}。"""
    if not _has_token():
        print(f"[crawler] 无 SOCIAL_API_TOKEN，跳过 {path}")
        return {}
    try:
        resp = requests.post(
            f"{_BASE}{path}",
            headers=_headers(),
            json=payload,
            timeout=timeout,
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[crawler] {path} code={data.get('code')} msg={data.get('msg', '')[:100]}")
        return data
    except Exception as e:
        print(f"[crawler] {path} 异常: {e}")
        return {}


def _ts_to_date(ts: int) -> str:
    """时间戳（秒）→ YYYY-MM-DD 字符串。"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return ""


# ============================================================
# 抖音
# ============================================================

def douyin_search(
    keyword: str,
    max_results: int = 10,
    sort_type: str = "0",      # 0=综合 1=最新 2=最热
    publish_time: str = "0",   # 0=不限 1=一天内 7=一周内 30=一月内
    content_type: str = "0",   # 0=全部 1=视频 2=图文
) -> list[dict]:
    """抖音关键词搜索视频。

    返回 list[dict]，每条：
      {
        "aweme_id": "...",
        "desc": "视频文案",
        "url": "https://www.douyin.com/video/...",
        "cover": "封面URL",
        "author": {"nickname": "...", "uid": "..."},
        "stats": {"digg": 点赞, "comment": 评论, "share": 分享, "collect": 收藏},
        "create_date": "YYYY-MM-DD",
        "duration": 时长秒,
        "raw": 原始 API 返回（调试用）,
      }
    """
    data = _post("/p2/douyin/general_search", {
        "keyword": keyword,
        "sort_type": sort_type,
        "publish_time": publish_time,
        "content_type": content_type,
    })
    if data.get("code") != 0:
        return []

    results = []
    items = data.get("data", {}).get("data", [])[:max_results]
    for item in items:
        aweme = item.get("aweme_info", {})
        aweme_id = aweme.get("aweme_id", "")
        stats = aweme.get("statistics", {})
        author = aweme.get("author", {})

        results.append({
            "aweme_id": aweme_id,
            "desc": aweme.get("desc", ""),
            "url": f"https://www.douyin.com/video/{aweme_id}",
            "cover": aweme.get("video", {}).get("cover", {}).get("url_list", [""])[0] if aweme.get("video") else "",
            "author": {
                "nickname": author.get("nickname", ""),
                "uid": author.get("uid", ""),
            },
            "stats": {
                "digg": stats.get("digg_count", 0),
                "comment": stats.get("comment_count", 0),
                "share": stats.get("share_count", 0),
                "collect": stats.get("collect_count", 0),
            },
            "create_date": _ts_to_date(aweme.get("create_time", 0)),
            "duration": aweme.get("duration", 0) // 1000 if aweme.get("duration") else 0,
            "raw": aweme,
        })
    return results


def douyin_search_sug(keyword: str) -> list[str]:
    """抖音搜索衍生词（用于扩大搜索范围）。

    返回衍生词列表：["入境游 GEO", "入境游 AI搜索", ...]
    """
    data = _post("/p2/douyin/search_sug", {"keyword": keyword})
    if data.get("code") != 0:
        return []

    sug_list = (
        data.get("data", {}).get("sug_list")
        or data.get("data", {}).get("suggestions")
        or data.get("data", {}).get("list")
        or []
    )
    results = []
    for s in sug_list:
        if isinstance(s, str):
            results.append(s)
        elif isinstance(s, dict):
            results.append(s.get("word") or s.get("keyword") or s.get("content", ""))
    return [r for r in results if r]


def douyin_aweme_detail(aweme_id: str) -> dict:
    """获取抖音视频详情（完整文案、数据、播放地址）。"""
    data = _post("/p2/douyin/aweme_detail", {"aweme_id": aweme_id})
    if data.get("code") != 0:
        return {}

    aweme = data.get("data", {}).get("aweme_detail") or data.get("data", {}).get("aweme") or data.get("data", {})
    if not aweme:
        return {}

    stats = aweme.get("statistics", {})
    return {
        "aweme_id": aweme.get("aweme_id", aweme_id),
        "desc": aweme.get("desc", ""),
        "url": f"https://www.douyin.com/video/{aweme.get('aweme_id', aweme_id)}",
        "author": aweme.get("author", {}),
        "stats": {
            "digg": stats.get("digg_count", 0),
            "comment": stats.get("comment_count", 0),
            "share": stats.get("share_count", 0),
            "collect": stats.get("collect_count", 0),
        },
        "create_date": _ts_to_date(aweme.get("create_time", 0)),
        "duration": aweme.get("duration", 0) // 1000 if aweme.get("duration") else 0,
        "music": aweme.get("music", {}).get("title", "") if aweme.get("music") else "",
        "video_url": (
            aweme.get("video", {}).get("play_addr", {}).get("url_list", [""])[0]
            if aweme.get("video") else ""
        ),
        "cover": (
            aweme.get("video", {}).get("cover", {}).get("url_list", [""])[0]
            if aweme.get("video") else ""
        ),
        "raw": aweme,
    }


def douyin_video_comment(aweme_id: str, cursor: int = 0, count: int = 20) -> list[dict]:
    """获取抖音视频一级评论。

    返回 list[dict]：[{"cid": "...", "text": "...", "digg": 点赞, "user": {...}, "create_date": "..."}]
    """
    data = _post("/p2/douyin/video_comment", {
        "aweme_id": aweme_id,
        "cursor": cursor,
        "count": count,
    })
    if data.get("code") != 0:
        return []

    comments = data.get("data", {}).get("comments") or data.get("data", {}).get("list") or []
    results = []
    for c in comments:
        results.append({
            "cid": c.get("cid", ""),
            "text": c.get("text", ""),
            "digg": c.get("digg_count", 0),
            "user": {
                "nickname": (c.get("user") or {}).get("nickname", ""),
                "uid": (c.get("user") or {}).get("uid", ""),
            },
            "create_date": _ts_to_date(c.get("create_time", 0)),
            "raw": c,
        })
    return results


# ============================================================
# 小红书
# ============================================================

def xhs_search_note(
    keyword: str,
    max_results: int = 20,
    sort: str = "general",    # general / time_descending / popularity_descending
    note_time: str = "all",   # all / day / week / half_year
    prefer: str = "app",      # app / web（先试 app，失败回退 web）
) -> list[dict]:
    """小红书关键词搜索笔记。

    自动在 APP 端和 Web 端接口间切换：
      prefer="app" → 先试 /p2/xhs/search_note_app，失败切换 /p2/xhs/search_note_web
      prefer="web" → 先试 web，失败切换 app

    返回 list[dict]：
      {
        "note_id": "...",
        "title": "标题",
        "desc": "正文摘要",
        "url": "https://www.xiaohongshu.com/explore/...",
        "cover": "封面URL",
        "author": {"nickname": "...", "user_id": "..."},
        "stats": {"like": 点赞, "collect": 收藏, "comment": 评论, "share": 分享},
        "note_type": "normal"/"video",
        "raw": 原始返回,
      }
    """
    endpoints = (
        ["/p2/xhs/search_note_app", "/p2/xhs/search_note_web"]
        if prefer == "app"
        else ["/p2/xhs/search_note_web", "/p2/xhs/search_note_app"]
    )

    for ep in endpoints:
        data = _post(ep, {
            "keyword": keyword,
            "page": 1,
            "sort": sort,
            "note_time": note_time,
        })
        if data.get("code") == 0:
            return _parse_xhs_notes(data, max_results)
    return []


def _parse_xhs_notes(data: dict, max_results: int) -> list[dict]:
    """解析小红书搜索响应为标准格式。"""
    d = data.get("data", {})
    # 兼容多种响应结构：data 可能是 dict 或 list
    if isinstance(d, list):
        raw_items = d
    else:
        inner = d.get("data", {}) if isinstance(d, dict) else {}
        raw_items = (
            d.get("items")
            or d.get("notes")
            or (inner.get("items") if isinstance(inner, dict) else None)
            or []
        )

    results = []
    for item in raw_items[:max_results]:
        note_id = item.get("id") or item.get("note_id", "")
        card = item.get("note_card") or item.get("card") or item
        interact = card.get("interact_info") or card.get("interaction_info") or {}
        user = card.get("user") or card.get("author") or {}
        image_list = card.get("image_list") or card.get("images") or []
        cover = ""
        if image_list:
            first = image_list[0]
            cover = (first.get("url") or first.get("url_default") or first.get("url_pre", "")) if isinstance(first, dict) else str(first)

        results.append({
            "note_id": note_id,
            "title": card.get("title") or card.get("display_title", ""),
            "desc": card.get("desc", ""),
            "url": f"https://www.xiaohongshu.com/explore/{note_id}",
            "cover": cover,
            "author": {
                "nickname": user.get("nickname") or user.get("nick_name", ""),
                "user_id": user.get("user_id") or user.get("userid", ""),
            },
            "stats": {
                "like": int(interact.get("liked_count") or interact.get("like_count") or 0),
                "collect": int(interact.get("collected_count") or interact.get("collect_count") or 0),
                "comment": int(interact.get("comment_count") or 0),
                "share": int(interact.get("share_count") or interact.get("shared_count") or 0),
            },
            "note_type": card.get("type") or card.get("note_type", "normal"),
            "raw": item,
        })
    return results


def xhs_note_detail(note_id: str) -> dict:
    """获取小红书笔记详情（完整正文）。"""
    data = _post("/p2/xhs/note_detail", {"note_id": note_id})
    if data.get("code") != 0:
        return {}

    note = data.get("data", {}).get("note") or data.get("data", {}).get("note_card") or data.get("data", {})
    if not note:
        return {}

    interact = note.get("interact_info") or note.get("interaction_info") or {}
    user = note.get("user") or note.get("author") or {}

    return {
        "note_id": note_id,
        "title": note.get("title") or note.get("display_title", ""),
        "desc": note.get("desc", ""),            # 完整正文
        "content": note.get("desc", ""),          # 别名
        "url": f"https://www.xiaohongshu.com/explore/{note_id}",
        "author": {
            "nickname": user.get("nickname") or user.get("nick_name", ""),
            "user_id": user.get("user_id", ""),
        },
        "stats": {
            "like": int(interact.get("liked_count") or interact.get("like_count") or 0),
            "collect": int(interact.get("collected_count") or interact.get("collect_count") or 0),
            "comment": int(interact.get("comment_count") or 0),
            "share": int(interact.get("share_count") or 0),
        },
        "tags": note.get("tag_list") or note.get("tags", []),
        "images": note.get("image_list") or note.get("images", []),
        "raw": note,
    }


def xhs_note_comment(note_id: str, cursor: str = "", max_results: int = 20) -> list[dict]:
    """获取小红书笔记一级评论。"""
    data = _post("/p2/xhs/note_comment", {
        "note_id": note_id,
        "cursor": cursor,
    })
    if data.get("code") != 0:
        return []

    comments = data.get("data", {}).get("comments") or data.get("data", {}).get("list") or []
    results = []
    for c in comments[:max_results]:
        user = c.get("user") or {}
        results.append({
            "comment_id": c.get("id") or c.get("comment_id", ""),
            "text": c.get("content", ""),
            "like": c.get("like_count", 0),
            "user": {
                "nickname": user.get("nickname", ""),
                "user_id": user.get("user_id", ""),
            },
            "create_date": _ts_to_date(c.get("create_time", 0)),
            "raw": c,
        })
    return results


def xhs_user_post(user_id: str, max_results: int = 20, use_v2: bool = True) -> list[dict]:
    """获取小红书用户的笔记列表。

    use_v2=True → 调 user_post2（新版），失败回退 user_post
    """
    endpoints = (
        ["/p2/xhs/user_post2", "/p2/xhs/user_post"]
        if use_v2
        else ["/p2/xhs/user_post", "/p2/xhs/user_post2"]
    )

    for ep in endpoints:
        data = _post(ep, {"user_id": user_id, "cursor": ""})
        if data.get("code") == 0:
            return _parse_xhs_notes(data, max_results)
    return []


# ============================================================
# 微信公众号
# ============================================================

def wechat_kw_search(keyword: str, max_results: int = 10, page: int = 1) -> list[dict]:
    """公众号关键词全局搜索（核心功能，可以跨账号搜）。

    返回 list[dict]：
      {
        "title": "文章标题",
        "url": "文章URL",
        "account_name": "公众号名",
        "digest": "摘要",
        "publish_date": "YYYY-MM-DD",
        "read_count": 阅读数（若 API 直接返回）,
        "zan_count": 点赞数,
        "raw": 原始返回,
      }

    注：若 API 直接返回不含阅读/点赞数，需调 wechat_read_zan(url) 二次获取。
    """
    data = _post("/p4/fbmain/monitor/v3/kw_search", {
        "keyword": keyword,
        "page": str(page),
    })
    if data.get("code") != 0:
        return []

    return _parse_wechat_articles(data, max_results)


def wechat_web_search(keyword: str, max_results: int = 10, page: int = 1) -> list[dict]:
    """公众号 Web 搜索（当 kw_search 结果不够时作为补充）。"""
    data = _post("/p4/fbmain/monitor/v3/web_search", {
        "keyword": keyword,
        "page": str(page),
    })
    if data.get("code") != 0:
        return []

    return _parse_wechat_articles(data, max_results)


def wechat_hot_typical_search(keyword: str, max_results: int = 10) -> list[dict]:
    """公众号热门典型文章搜索（返回的是被验证过的高互动文章）。

    推荐作为爆款分析的主要数据源。
    """
    data = _post("/p4/fbmain/monitor/v3/hot_typical_search", {
        "keyword": keyword,
    })
    if data.get("code") != 0:
        return []

    return _parse_wechat_articles(data, max_results)


def _parse_wechat_articles(data: dict, max_results: int) -> list[dict]:
    """解析公众号文章搜索响应为标准格式。"""
    raw_items = (
        data.get("data", {}).get("articles")
        or data.get("data", {}).get("list")
        or data.get("data", {}).get("items")
        or data.get("data", [])
        or []
    )

    results = []
    for item in raw_items[:max_results]:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url") or item.get("link", ""),
            "account_name": (
                item.get("nickname")
                or item.get("account_name")
                or item.get("account")
                or item.get("biz_name", "")
            ),
            "digest": item.get("digest") or item.get("summary", ""),
            "publish_date": (
                item.get("post_time_str")
                or item.get("publish_date")
                or str(item.get("post_time", "")) or ""
            ),
            "read_count": int(item.get("read_count") or item.get("read") or 0),
            "zan_count": int(item.get("zan_count") or item.get("zan") or item.get("like_count") or 0),
            "cover": item.get("cover") or item.get("cover_img", ""),
            "raw": item,
        })
    return results


def wechat_post_history(account_name: str, page: int = 1, max_articles: int = 10) -> list[dict]:
    """按账号名获取公众号历史文章。"""
    data = _post("/p4/fbmain/monitor/v3/post_history", {
        "name": account_name,
        "page": str(page),
    })
    if data.get("code") != 0:
        return []

    return _parse_wechat_articles(data, max_articles)


def wechat_read_zan(article_url: str) -> dict:
    """获取公众号单篇文章的阅读/点赞数。

    返回 {"read": 阅读数, "zan": 点赞数}
    """
    data = _post("/p4/fbmain/monitor/v3/read_zan", {"url": article_url})
    if data.get("code") != 0:
        return {"read": 0, "zan": 0}

    d = data.get("data", {})
    return {
        "read": int(d.get("read", 0)),
        "zan": int(d.get("zan", 0)),
    }


# ============================================================
# 便捷工具
# ============================================================

def enrich_wechat_articles(articles: list[dict]) -> list[dict]:
    """为公众号文章列表补全阅读/点赞数（如果原始返回没有）。

    用法：
      articles = wechat_kw_search("入境游")
      articles = enrich_wechat_articles(articles)  # 补全阅读/点赞
    """
    enriched = []
    for a in articles:
        if a.get("read_count") or a.get("zan_count"):
            enriched.append(a)
            continue
        if not a.get("url"):
            enriched.append(a)
            continue
        rz = wechat_read_zan(a["url"])
        a["read_count"] = rz["read"]
        a["zan_count"] = rz["zan"]
        enriched.append(a)
    return enriched


def expand_keywords_by_douyin(keyword: str, max_expand: int = 10) -> list[str]:
    """用抖音搜索衍生词扩展关键词（用于四层搜索策略的 Layer 2/3）。

    返回包含原词 + 衍生词的列表。
    """
    suggestions = douyin_search_sug(keyword)
    expanded = [keyword] + suggestions[:max_expand - 1]
    # 去重
    seen = set()
    out = []
    for k in expanded:
        if k not in seen and k:
            seen.add(k)
            out.append(k)
    return out


# ============================================================
# 自检
# ============================================================

if __name__ == "__main__":
    """运行 `python3 scripts/social_crawler.py` 做基本连通性自检。"""
    print("=" * 60)
    print("社媒爬虫 Skill 自检")
    print("=" * 60)
    print(f"Base URL: {_BASE}")
    print(f"Token 已配置: {_has_token()}")

    if not _has_token():
        print("\n⚠️  SOCIAL_API_TOKEN 未配置，跳过接口测试")
        exit(0)

    print("\n[1/3] 测试小红书搜索 'GEO'...")
    notes = xhs_search_note("GEO", max_results=3)
    print(f"  → 返回 {len(notes)} 条")
    if notes:
        print(f"  → 第一条: {notes[0]['title'][:40]}... (like={notes[0]['stats']['like']})")

    print("\n[2/3] 测试抖音搜索 '入境游'...")
    videos = douyin_search("入境游", max_results=3)
    print(f"  → 返回 {len(videos)} 条")
    if videos:
        print(f"  → 第一条: {videos[0]['desc'][:40]}... (digg={videos[0]['stats']['digg']})")

    print("\n[3/3] 测试公众号关键词搜 '入境游 海外获客'...")
    articles = wechat_kw_search("入境游 海外获客", max_results=3)
    print(f"  → 返回 {len(articles)} 条")
    if articles:
        print(f"  → 第一条: {articles[0]['title'][:40]}... (account={articles[0]['account_name']})")

    print("\n✓ 自检完成")
