"""Summarizer：将压缩后情报按维度分组，调 LLM 生成结构化情报简报"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scripts.utils import get_client, chat

from compressor import IntelItem


_TIER_LABEL = {
    "tier_1": "【官方】",
    "tier_2": "【专业媒体】",
    "tier_3": "【自媒体】",
    "tier_4": "【社交】",
}

_TIER_CITATION = {
    "tier_1": "（官方来源，可直接陈述为事实）",
    "tier_2": "（专业媒体，可直接陈述为事实）",
    "tier_3": '（需标注"据XX报道"）',
    "tier_4": '（需标注"用户反馈显示"或"社交数据显示"）',
}

_LINE_ORDER = ["competitors", "customer_industry", "ai_industry"]

_LINE_HEADER = {
    "competitors": "## 竞对维度（最优先）",
    "customer_industry": "## 客户行业维度",
    "ai_industry": "## AI行业维度",
}


def _group_by_line(items: List[IntelItem]) -> Dict[str, List[IntelItem]]:
    groups: Dict[str, List[IntelItem]] = {k: [] for k in _LINE_ORDER}
    for item in items:
        if item.line in groups:
            groups[item.line].append(item)
    return groups


def _format_items_for_prompt(items: List[IntelItem]) -> str:
    if not items:
        return "（本期无相关内容）"
    lines = []
    for i, item in enumerate(items, 1):
        label = _TIER_LABEL.get(item.source_tier, "【自媒体】")
        citation_note = _TIER_CITATION.get(item.source_tier, "")
        lines.append(
            f"{i}. {label} {item.title}\n"
            f"   摘要：{item.summary}\n"
            f"   来源：{item.url}\n"
            f"   发布时间：{item.published_at or '未知'}\n"
            f"   引用规则：{citation_note}"
        )
    return "\n\n".join(lines)


_FORMAT_TEMPLATE = """
## 输出格式模板（严格遵守）

---

🌟 本周核心判断
（基于所有维度的整体判断，150-250字。必须包含：最重要的1个变化、对我们业务的直接影响、本周最值得关注的方向）

---

## 竞对维度（最优先）

### 信号[N]: [信号标题]
【核心观点】一句话结论（≤30字）
【论述】2-3句展开
  - 证据A：[具体事实]（来源：tier_1/tier_2，[日期]，[URL]）
  - 证据B：据[媒体名]报道，[具体内容]（[URL]）
【评估】威胁等级：🔴高/🟡中/🟢低 | 时效：🔴本周可用/🟡1-3个月跟踪/🔵长期关注

（竞对维度输出2-4条信号，信号不足时如实标注"本期信号不足"）

---

## 客户行业维度

### 信号[N]: [信号标题]
【核心观点】一句话结论（≤30字）
【论述】2-3句展开
  - 证据A：[具体内容]（[URL]）
【评估】影响程度：🔴直接影响/🟡间接影响/🟢背景趋势 | 时效：🔴本周可用/🟡1-3个月跟踪/🔵长期关注

（客户行业维度输出2-4条信号）

---

## AI行业维度

### 信号[N]: [信号标题]
【类型】🔧工具更新/📚落地案例/💰融资/🧭趋势
【核心观点】一句话结论（≤30字）
【论述】2-3句展开，重点说明对我们的可借鉴性
  - 证据A：[具体内容]（[URL]）
【评估】可借鉴性：🔴立即可用/🟡需适配/🟢长期关注 | 时效：🔴本周可用/🟡1-3个月跟踪/🔵长期关注

（AI行业维度输出2-3条信号）

---

🎬 本周行动建议
1. 【立即行动】（本周内）[具体行动，说明触发原因]
2. 【规划项目】（本月内）[具体行动，说明触发原因]
3. 【持续跟踪】（长期）[跟踪什么，跟踪频率]

---
"""

_SCORING_RULES = """
## 信号筛选评分规则（LLM内部执行，不输出分数）

从所有情报中，按以下权重评分后选出最高分信号：
- 重要性 40%：直接影响业务的优先；tier_1/tier_2来源加权
- 新颖性 25%：首次出现的信息 > 已知趋势的延续
- 可行动性 20%：能在本周/本月转化为具体行动的优先
- 证据强度 15%：多源交叉验证 > 单一来源

评分低于阈值的内容不输出（不需要解释为何不输出）。
"""

_CITATION_RULES = """
## 引用规则（必须遵守）

- tier_1（官方来源）：可直接陈述为事实，如"XXX官方公告显示"
- tier_2（专业媒体）：可直接陈述为事实，如"据环球旅讯报道"
- tier_3（自媒体）：必须标注"据XX报道"或"XX称"
- tier_4（社交）：必须标注"用户反馈显示"或"社交数据显示"
- 每条信号必须附至少1个原文URL
- 无URL的信息不得输出
"""

_PROHIBITIONS = """
## 禁止事项

- 禁止输出无URL来源的信息
- 禁止输出与入境游无关的出境游/国内游数据
- 禁止引用超过30天的旧信息（除非有重大新进展）
- 禁止在正文中输出数据统计（由系统自动追加）
- 禁止在末尾重复说"以上是本期简报"等废话
- 禁止编造或推测未经证实的信息
- 禁止输出"查询健康度"或"数据透明度"部分（由系统生成）
"""


def summarize(
    intel_items: List[IntelItem],
    identity: str,
    rules: str,
    priority: str,
    memory: str,
    knowledge: str,
    focus: str = "",
) -> str:
    """调用 LLM 生成结构化情报简报，返回 Markdown 字符串"""
    groups = _group_by_line(intel_items)

    # 按维度格式化情报输入
    sections = []
    for line in _LINE_ORDER:
        header = _LINE_HEADER[line]
        items_text = _format_items_for_prompt(groups[line])
        sections.append(f"{header}\n\n{items_text}")

    intel_block = "\n\n---\n\n".join(sections)

    # 聚焦指令（最高优先级，覆盖默认行为）
    focus_block = ""
    if focus:
        focus_block = (
            f"## ⚡ 本期聚焦指令（最高优先级）\n"
            f"{focus}\n\n"
            f"请在分析所有情报时，优先围绕以上聚焦点展开，相关信号排在各维度首位。\n\n"
        )

    user_prompt = (
        "你是企业情报官，以下是本期三条监控线的压缩后情报原料。\n\n"
        "【情报原料】\n\n"
        f"{intel_block}\n\n"
        "---\n\n"
        "请按照上方格式模板，从情报原料中筛选并提炼高价值信号，生成本期情报简报。\n"
        "严格遵守：引用规则、禁止事项、评分规则（内部执行不输出分数）。\n"
        '输出内容从"🌟 本周核心判断"开始，到"🎬 本周行动建议"结束。\n'
        "不要输出任何格式说明、数据统计或结尾废话。"
    )

    system_prompt = (
        f"{focus_block}"
        f"{identity}\n\n"
        f"{rules}\n\n"
        f"## 优先级规则\n{priority}\n\n"
        f"## 历史记忆\n{memory}\n\n"
        f"## 背景知识\n{knowledge}\n\n"
        f"{_FORMAT_TEMPLATE}\n\n"
        f"{_SCORING_RULES}\n\n"
        f"{_CITATION_RULES}\n\n"
        f"{_PROHIBITIONS}"
    )

    client = get_client()
    result = chat(client, system_prompt, user_prompt, max_tokens=4096)
    print(f"[Summarizer] 简报生成完成（约 {len(result)} 字符）")
    return result
