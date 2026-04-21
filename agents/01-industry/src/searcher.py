"""Searcher：多源并发搜索
支持：DuckDuckGo / Tavily / 抖音 / 小红书 / 微信公众号
"""
from __future__ import annotations
import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import List
import requests
from ddgs import DDGS

from planner import QueryItem

# 社媒 API 统一基础配置（抖音/小红书/公众号均来自 cn8n.com）
_SOCIAL_BASE = "https://cn8n.com"


def _social_headers() -> dict:
    token = os.environ.get("SOCIAL_API_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _has_social_token() -> bool:
    return bool(os.environ.get("SOCIAL_API_TOKEN", ""))


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published_at: str        # ISO 日期字符串，可能为空
    source_api: str          # duckduckgo / tavily / douyin / xhs / wechat
    matched_query_id: str
    line: str                # customer_industry / competitors / ai_industry
    sub_goal: str


# ── DuckDuckGo ───────────────────────────────────────────────────────

def _search_duckduckgo(q: QueryItem, max_results: int = 5) -> List[SearchResult]:
    results = []
    try:
        ddgs = DDGS()
        hits = list(ddgs.text(q.query, max_results=max_results))
        for h in hits:
            results.append(SearchResult(
                title=h.get("title", ""),
                url=h.get("href", ""),
                snippet=h.get("body", ""),
                published_at="",
                source_api="duckduckgo",
                matched_query_id=q.id,
                line=q.line,
                sub_goal=q.sub_goal,
            ))
    except Exception as e:
        print(f"[DDG] 失败: {q.query!r} → {e}")
    return results


# ── Tavily ───────────────────────────────────────────────────────────

def _search_tavily(q: QueryItem, max_results: int = 5) -> List[SearchResult]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return []
    results = []
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": q.query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=20,
        )
        for item in resp.json().get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                published_at=item.get("published_date", ""),
                source_api="tavily",
                matched_query_id=q.id,
                line=q.line,
                sub_goal=q.sub_goal,
            ))
    except Exception as e:
        print(f"[Tavily] 失败: {q.query!r} → {e}")
    return results


# ── 抖音：关键词搜索 ────────────────────────────────────────────────

def _search_douyin(q: QueryItem, max_results: int = 5) -> List[SearchResult]:
    if not _has_social_token():
        return []
    results = []
    try:
        resp = requests.post(
            f"{_SOCIAL_BASE}/p2/douyin/general_search",
            headers=_social_headers(),
            json={
                "keyword": q.query,
                "sort_type": "0",      # 综合排序
                "publish_time": "0",   # 不限时间（由 compressor 做时效过滤）
                "content_type": "0",   # 全部（视频+图文）
            },
            timeout=20,
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[抖音] API 错误: {data.get('msg')} (code={data.get('code')})")
            return []

        items = data.get("data", {}).get("data", [])[:max_results]
        for item in items:
            aweme = item.get("aweme_info", {})
            aweme_id = aweme.get("aweme_id", "")
            desc = aweme.get("desc", "")
            stats = aweme.get("statistics", {})
            create_ts = aweme.get("create_time", 0)
            pub_date = datetime.fromtimestamp(create_ts).strftime("%Y-%m-%d") if create_ts else ""

            results.append(SearchResult(
                title=desc[:80] or f"抖音视频 {aweme_id}",
                url=f"https://www.douyin.com/video/{aweme_id}",
                snippet=(
                    f"{desc}\n"
                    f"👍{stats.get('digg_count', 0)}  "
                    f"💬{stats.get('comment_count', 0)}  "
                    f"🔗{stats.get('share_count', 0)}  "
                    f"⭐{stats.get('collect_count', 0)}"
                ),
                published_at=pub_date,
                source_api="douyin",
                matched_query_id=q.id,
                line=q.line,
                sub_goal=q.sub_goal,
            ))
    except Exception as e:
        print(f"[抖音] 搜索失败: {q.query!r} → {e}")
    return results


# ── 小红书：笔记搜索 ────────────────────────────────────────────────

def _search_xhs(q: QueryItem, max_results: int = 5) -> List[SearchResult]:
    if not _has_social_token():
        return []
    results = []
    try:
        resp = requests.post(
            f"{_SOCIAL_BASE}/p2/xhs/search_note_app",
            headers=_social_headers(),
            json={
                "keyword": q.query,
                "page": 1,
                "sort": "general",     # 综合排序
                "note_time": "week",   # 近一周
            },
            timeout=20,
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[小红书] API 错误: {data.get('msg')} (code={data.get('code')})")
            return []

        # 兼容多种响应结构
        raw_items = (
            data.get("data", {}).get("items")
            or data.get("data", {}).get("notes")
            or data.get("data", {}).get("data", {}).get("items")
            or []
        )

        for item in raw_items[:max_results]:
            note_id = item.get("id") or item.get("note_id", "")
            card = item.get("note_card") or item.get("card") or item
            title = card.get("title") or card.get("display_title", "")
            desc = card.get("desc", "")
            interact = card.get("interact_info") or card.get("interaction_info") or {}
            user = card.get("user") or card.get("author") or {}

            results.append(SearchResult(
                title=title or desc[:60] or f"小红书笔记 {note_id}",
                url=f"https://www.xiaohongshu.com/explore/{note_id}",
                snippet=(
                    f"{desc[:200]}\n"
                    f"❤️{interact.get('liked_count', interact.get('like_count', 0))}  "
                    f"💬{interact.get('comment_count', 0)}  "
                    f"⭐{interact.get('collected_count', interact.get('collect_count', 0))}  "
                    f"作者：{user.get('nickname', '')}"
                ),
                published_at="",
                source_api="xhs",
                matched_query_id=q.id,
                line=q.line,
                sub_goal=q.sub_goal,
            ))
    except Exception as e:
        print(f"[小红书] 搜索失败: {q.query!r} → {e}")
    return results


# ── 微信公众号：账号历史文章监控 ─────────────────────────────────────

def _fetch_wechat_account(q: QueryItem, max_articles: int = 5) -> List[SearchResult]:
    """
    q.query = 公众号名称或微信ID（如 "入境游营销助手"）
    获取该公众号最新文章列表，并附加阅读/点赞数据。
    """
    if not _has_social_token():
        return []
    results = []
    try:
        # Step 1: 获取历史文章
        resp = requests.post(
            f"{_SOCIAL_BASE}/p4/fbmain/monitor/v3/post_history",
            headers=_social_headers(),
            json={"name": q.query, "page": "1"},
            timeout=20,
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"[公众号] 获取文章失败: {q.query!r} → code={data.get('code')} {data.get('msg', '')}")
            return []

        articles = (
            data.get("data", {}).get("articles")
            or data.get("data", {}).get("list")
            or []
        )[:max_articles]

        for art in articles:
            art_url = art.get("url", "")
            title = art.get("title", "")
            digest = art.get("digest", "")
            pub_time = art.get("post_time_str") or art.get("post_time", "")

            # Step 2: 获取文章阅读/点赞数（有 URL 才调用）
            read_count, zan_count = 0, 0
            if art_url:
                try:
                    rz = requests.post(
                        f"{_SOCIAL_BASE}/p4/fbmain/monitor/v3/read_zan",
                        headers=_social_headers(),
                        json={"url": art_url},
                        timeout=10,
                    )
                    rz_data = rz.json()
                    if rz_data.get("code") == 0:
                        read_count = rz_data.get("data", {}).get("read", 0)
                        zan_count = rz_data.get("data", {}).get("zan", 0)
                except Exception:
                    pass

            results.append(SearchResult(
                title=title,
                url=art_url,
                snippet=(
                    f"[公众号：{q.query}] {digest}\n"
                    f"👁️阅读 {read_count}  👍点赞 {zan_count}"
                ),
                published_at=str(pub_time),
                source_api="wechat",
                matched_query_id=q.id,
                line=q.line,
                sub_goal=q.sub_goal,
            ))
    except Exception as e:
        print(f"[公众号] 失败: {q.query!r} → {e}")
    return results


# ── 统一分发 ────────────────────────────────────────────────────────

def _search_one(q: QueryItem, source: str) -> List[SearchResult]:
    if source == "duckduckgo":
        return _search_duckduckgo(q)
    elif source == "tavily":
        return _search_tavily(q)
    elif source == "douyin":
        return _search_douyin(q)
    elif source == "xhs":
        return _search_xhs(q)
    elif source == "wechat":
        return _fetch_wechat_account(q)
    print(f"[Searcher] 未知 source: {source}")
    return []


# ── 并发入口 ────────────────────────────────────────────────────────

async def search_all(queries: List[QueryItem], max_workers: int = 8) -> List[SearchResult]:
    """并发执行所有查询，返回原始结果列表。"""
    loop = asyncio.get_event_loop()
    task_pairs = [(q, src) for q in queries for src in q.sources]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            loop.run_in_executor(executor, _search_one, q, src)
            for q, src in task_pairs
        ]
        results_nested = await asyncio.gather(*futures, return_exceptions=True)

    results: List[SearchResult] = []
    for r in results_nested:
        if isinstance(r, list):
            results.extend(r)
        elif isinstance(r, Exception):
            print(f"[Searcher] 任务异常: {r}")

    # 来源统计
    from collections import Counter
    src_counts = Counter(r.source_api for r in results)
    print(f"[Searcher] 原始结果 {len(results)} 条 | 来源分布: {dict(src_counts)}")
    return results
