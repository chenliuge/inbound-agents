"""Agent 01 - 行业监控官：多源并发搜索 + 三维情报简报"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

# 项目根目录加入路径
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# src 模块路径
SRC = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC))

from dotenv import load_dotenv
from scripts.utils import read_knowledge, write_pending

load_dotenv(override=True)

from planner import get_queries
from searcher import search_all
from compressor import compress
from summarizer import summarize
from reporter import to_markdown


def _detect_low_perf_queries(queries, raw_results) -> list[str]:
    """找出零结果的查询词（用于查询健康度提醒）"""
    matched_query_ids = {r.matched_query_id for r in raw_results}
    low_perf = []
    for q in queries:
        if q.id not in matched_query_ids:
            low_perf.append(q.query)
    return low_perf


def main() -> None:
    agent_dir = Path(__file__).parent

    # ── 加载知识文件 ────────────────────────────────────────────────
    identity = read_knowledge(str(agent_dir / "IDENTITY.md"))
    rules    = read_knowledge(str(agent_dir / "RULES.md"))
    priority = read_knowledge(str(agent_dir / "PRIORITY.md"))
    memory   = read_knowledge(str(agent_dir / "MEMORY.md"))
    company  = read_knowledge(str(ROOT / "shared/knowledge/COMPANY.md"))
    industry = read_knowledge(str(ROOT / "shared/knowledge/INDUSTRY.md"))

    # ── 确定运行频率 ────────────────────────────────────────────────
    frequency = os.environ.get("RUN_FREQUENCY", "weekly")
    time_window = int(os.environ.get("TIME_WINDOW_DAYS", "14"))
    focus = os.environ.get("RUN_FOCUS", "").strip()
    print(f"▶ 运行频率：{frequency} | 时间窗口：{time_window}天" + (f" | 聚焦：{focus}" if focus else ""))

    # ── Step 1: 查询规划 ────────────────────────────────────────────
    queries = get_queries(
        frequency=frequency,
        config_path=str(agent_dir / "config" / "queries.yaml"),
    )

    if not queries:
        print("❌ 没有匹配的查询，退出")
        return

    query_count = len(queries)
    print(f"▶ 本期查询：{query_count} 条")

    # ── Step 2: 多源并发搜索 ────────────────────────────────────────
    print("▶ 开始并发搜索...")
    raw_results = asyncio.run(search_all(queries))
    raw_count = len(raw_results)

    if not raw_results:
        print("❌ 搜索无结果，退出")
        return

    # ── Step 2.5: 检测低效查询 ─────────────────────────────────────
    low_perf_queries = _detect_low_perf_queries(queries, raw_results)
    if low_perf_queries:
        print(f"⚠️  零结果查询（{len(low_perf_queries)} 条）：{low_perf_queries[:5]}")

    # ── Step 3: 压缩流水线 ─────────────────────────────────────────
    intel_items = compress(raw_results, default_time_window=time_window)

    if not intel_items:
        print("❌ 压缩后无有效情报，退出")
        return

    # ── Step 4: LLM 分组总结 ───────────────────────────────────────
    print("▶ 正在生成情报简报...")
    briefing_text = summarize(
        intel_items=intel_items,
        identity=identity,
        rules=rules,
        priority=priority,
        memory=memory,
        knowledge=f"{company}\n\n{industry}",
        focus=focus,
    )

    # ── Step 5: 格式化输出（含数据透明度） ────────────────────────
    output = to_markdown(
        briefing_text=briefing_text,
        intel_items=intel_items,
        frequency=frequency,
        query_count=query_count,
        raw_count=raw_count,
        low_perf_queries=low_perf_queries,
    )

    # ── 写入协作池 ─────────────────────────────────────────────────
    output_path = write_pending(
        pool="collaboration/01-intel-pool",
        content=output,
        agent="01-industry",
        tags=["行业情报", frequency, "三维监控"],
    )
    print(f"✓ 完成 → {output_path}")


if __name__ == "__main__":
    main()
