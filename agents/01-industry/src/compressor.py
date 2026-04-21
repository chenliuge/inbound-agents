"""Compressor：结果压缩流水线（Phase 1：去重 + 时效过滤 + 分组打标）"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict
from urllib.parse import urlparse
import yaml

from searcher import SearchResult


@dataclass
class IntelItem:
    title: str
    summary: str
    url: str
    published_at: str
    source_tier: str         # tier_1 / tier_2 / tier_3 / tier_4
    line: str                # customer_industry / competitors / ai_industry
    sub_goal: str
    relevance_score: float = 1.0


def _load_tiers(config_path: str | None = None) -> Dict[str, List[str]]:
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "compression.yaml")
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("source_tiers", {})


def _get_tier(url: str, tiers: Dict) -> str:
    """根据 URL 域名判断来源权威等级"""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return "tier_3"

    for tier_key in ["tier_1", "tier_2", "tier_3", "tier_4"]:
        for pattern in tiers.get(tier_key, {}).get("domains", []):
            if pattern.startswith("*."):
                if domain.endswith(pattern[2:]):
                    return tier_key
            elif pattern in domain:
                return tier_key
    return "tier_3"


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.replace("+00:00", "Z"), fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def compress(raw_results: List[SearchResult], default_time_window: int = 14) -> List[IntelItem]:
    """
    Phase 1 压缩流水线：
      Step 1: URL 去重
      Step 4: 时效过滤（按各查询的 time_window_days）
      Step 5: 维度分组 + 来源权威打标
    """
    tiers = _load_tiers()

    # Step 1: URL 去重
    seen_urls: set = set()
    deduped: List[SearchResult] = []
    for r in raw_results:
        if not r.url:
            continue
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            deduped.append(r)

    # Step 4: 时效过滤
    now = datetime.now()
    recent: List[SearchResult] = []
    for r in deduped:
        pub_dt = _parse_date(r.published_at)
        if pub_dt:
            cutoff = now - timedelta(days=default_time_window)
            if pub_dt < cutoff:
                continue  # 丢弃过期内容
        recent.append(r)

    # Step 5: 打标 + 转换
    intel_items: List[IntelItem] = []
    for r in recent:
        tier = _get_tier(r.url, tiers)
        intel_items.append(IntelItem(
            title=r.title,
            summary=r.snippet[:400] if r.snippet else "",
            url=r.url,
            published_at=r.published_at,
            source_tier=tier,
            line=r.line,
            sub_goal=r.sub_goal,
            relevance_score=1.0,
        ))

    print(f"[Compressor] 原始 {len(raw_results)} → 去重后 {len(deduped)} → 时效过滤后 {len(recent)} 条")
    return intel_items
