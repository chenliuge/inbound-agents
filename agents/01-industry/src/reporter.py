"""Reporter：格式化最终简报输出，附加数据透明度和查询健康度"""
from __future__ import annotations
from datetime import datetime
from typing import List, Dict

from compressor import IntelItem


def _build_transparency_section(
    query_count: int,
    raw_count: int,
    intel_items: List[IntelItem],
    low_perf_queries: List[str],
) -> str:
    """生成"📊 本周数据透明度"和"🔄 查询健康度提醒"两节（程序生成，不经过LLM）"""
    tier_counts: Dict[str, int] = {}
    line_counts: Dict[str, int] = {}
    for item in intel_items:
        tier_counts[item.source_tier] = tier_counts.get(item.source_tier, 0) + 1
        line_counts[item.line] = line_counts.get(item.line, 0) + 1

    t1 = tier_counts.get("tier_1", 0)
    t2 = tier_counts.get("tier_2", 0)
    t3 = tier_counts.get("tier_3", 0)
    t4 = tier_counts.get("tier_4", 0)

    comp_count = line_counts.get("competitors", 0)
    cust_count = line_counts.get("customer_industry", 0)
    ai_count   = line_counts.get("ai_industry", 0)

    transparency = (
        "---\n\n"
        "📊 **本周数据透明度**\n\n"
        f"| 指标 | 数值 |\n"
        f"|------|------|\n"
        f"| 执行查询 | {query_count} 条 |\n"
        f"| 原始结果 | {raw_count} 条 |\n"
        f"| 有效情报 | {len(intel_items)} 条（去重+时效过滤后）|\n"
        f"| 来源分布 | 官方 {t1} / 专业媒体 {t2} / 自媒体 {t3} / 社交 {t4} |\n"
        f"| 维度分布 | 竞对 {comp_count} / 客户行业 {cust_count} / AI行业 {ai_count} |\n"
    )

    if low_perf_queries:
        health = (
            "\n🔄 **查询健康度提醒**\n\n"
            "以下查询本期零结果，建议检查关键词或数据源：\n\n"
        )
        for q in low_perf_queries:
            health += f"- `{q}`\n"
    else:
        health = "\n🔄 **查询健康度**：所有查询均有返回结果 ✅\n"

    return transparency + health


def to_markdown(
    briefing_text: str,
    intel_items: List[IntelItem],
    frequency: str = "weekly",
    query_count: int = 0,
    raw_count: int = 0,
    low_perf_queries: List[str] | None = None,
) -> str:
    """将 LLM 生成的简报加上元数据头部和数据透明度尾部，输出完整 Markdown"""
    if low_perf_queries is None:
        low_perf_queries = []

    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    freq_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(frequency, "周报")

    # 头部元数据（YAML front matter 格式，供协作池解析）
    header = (
        f"---\n"
        f"title: 企业情报{freq_label} · {date_str}\n"
        f"agent: 01-industry\n"
        f"frequency: {frequency}\n"
        f"generated_at: {time_str}\n"
        f"intel_count: {len(intel_items)}\n"
        f"---\n\n"
        f"# 📊 情报{freq_label} · {date_str}\n\n"
        f"> 生成时间：{time_str} ｜ 频率：{freq_label} ｜ 有效情报：{len(intel_items)} 条\n\n"
        f"---\n\n"
    )

    # 数据透明度尾部（程序生成，不经 LLM）
    transparency = _build_transparency_section(
        query_count=query_count,
        raw_count=raw_count,
        intel_items=intel_items,
        low_perf_queries=low_perf_queries,
    )

    return header + briefing_text + "\n\n" + transparency
