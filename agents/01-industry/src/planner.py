"""Planner：根据运行频率筛选本次要执行的查询"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
import yaml


@dataclass
class QueryItem:
    id: str
    query: str
    line: str               # customer_industry / competitors / ai_industry
    sub_goal: str           # 子目标标签
    frequency: str          # daily / weekly / monthly
    sources: List[str]      # 该查询走哪些源
    time_window_days: int


# 频率层级：weekly 包含 daily，monthly 包含 daily+weekly
_FREQ_HIERARCHY = {
    "daily":   {"daily"},
    "weekly":  {"daily", "weekly"},
    "monthly": {"daily", "weekly", "monthly"},
}


def get_queries(frequency: str = "weekly", config_path: str | None = None) -> List[QueryItem]:
    """返回本次运行应执行的查询列表。"""
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "queries.yaml")

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    valid_freqs = _FREQ_HIERARCHY.get(frequency, {"weekly"})
    queries: List[QueryItem] = []

    for line_key, line_data in config.get("lines", {}).items():
        for sub_goal_key, sg_data in line_data.get("sub_goals", {}).items():
            if sg_data.get("frequency", "weekly") not in valid_freqs:
                continue
            for idx, query_str in enumerate(sg_data.get("queries", [])):
                queries.append(QueryItem(
                    id=f"{line_key}__{sub_goal_key}__{idx:03d}",
                    query=query_str,
                    line=line_key,
                    sub_goal=sub_goal_key,
                    frequency=sg_data["frequency"],
                    sources=sg_data.get("sources", ["duckduckgo"]),
                    time_window_days=sg_data.get("time_window_days", 14),
                ))

    print(f"[Planner] frequency={frequency} → {len(queries)} 条查询")
    return queries
