"""Agent 04 - 内容策略官：三层产出（季度/月度/周度）

触发方式：支持中文自然语言
  季度策略："季度策略""Q1策略""新一季""战略"
  月度计划："月度计划""本月重点""4月方向"
  周度选题："周选题""本周选题""选题计划"

示例：
  python run.py "生成本季度策略"
  python run.py "帮我出本周选题"
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Literal, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from scripts.utils import (
    read_knowledge,
    read_approved,
    read_all_approved,  # 新增：读全部 approved
    write_pending,
    get_client,
    chat,
)

load_dotenv(override=True)

Level = Literal["quarterly", "monthly", "weekly"]


# ============================================================
# 中文 → 层级的意图识别
# ============================================================

LEVEL_KEYWORDS = {
    "quarterly": [
        "季度策略", "季度内容策略", "季度计划", "季度战略", "战略",
        "新一季", "本季度", "这季度", "季度方向",
        "Q1", "Q2", "Q3", "Q4", "q1", "q2", "q3", "q4",
    ],
    "monthly": [
        "月度计划", "月度内容", "月度重点", "月度方向", "月度内容计划",
        "本月", "这月", "月度",
        "1月", "2月", "3月", "4月", "5月", "6月",
        "7月", "8月", "9月", "10月", "11月", "12月",
    ],
    "weekly": [
        "周选题", "本周选题", "选题计划", "周度选题", "周度内容",
        "这周", "本周", "周计划", "选题",
    ],
}


def detect_level(user_input: str) -> Optional[Level]:
    """从自然语言中识别层级。优先级：季度 > 月度 > 周度。"""
    lower = user_input.lower()
    for level in ("quarterly", "monthly", "weekly"):
        for kw in LEVEL_KEYWORDS[level]:
            if kw.lower() in lower:
                return level  # type: ignore
    return None


# "仅触发层级识别"的标准指令模板。若用户指令与这些完全等价，视为"无特别要求"。
_STANDARD_TRIGGERS = {
    "quarterly": [
        "生成本季度策略", "生成季度策略", "做季度策略", "出季度策略", "本季度策略",
        "季度策略", "制定本季度策略", "做本季度战略", "季度战略", "战略",
        "做q1策略", "做q2策略", "做q3策略", "做q4策略",
    ],
    "monthly": [
        "生成本月计划", "生成月度计划", "做月度计划", "出月度计划", "本月计划",
        "月度计划", "制定本月计划", "本月重点", "月度内容计划",
    ],
    "weekly": [
        "做本周选题", "生成周选题", "出周选题", "周选题", "本周选题", "选题计划",
        "帮我出本周选题", "做本周选题计划", "周度选题", "周度内容",
    ],
}


def is_standard_trigger(user_input: str, level: Level) -> bool:
    """判断用户指令是否仅为标准触发词（无特别要求）。"""
    normalized = user_input.strip().lower().replace("  ", " ")
    for trigger in _STANDARD_TRIGGERS.get(level, []):
        if normalized == trigger.lower():
            return True
    # 也放宽一点：如果去掉所有空白/标点后等于某个标准触发
    compact = "".join(c for c in normalized if c.isalnum())
    for trigger in _STANDARD_TRIGGERS.get(level, []):
        if compact == "".join(c for c in trigger.lower() if c.isalnum()):
            return True
    return False


# ============================================================
# 配置加载
# ============================================================

def load_core_config(agent_dir: Path) -> str:
    """加载 Agent 04 核心配置。"""
    required = [
        "IDENTITY.md",
        "RULES.md",
        "PRIORITY.md",
        "CONTENT_PILLARS.md",
        "STAGE_PLAYBOOK.md",
        "MEMORY.md",
        "DATAFLOW.md",
    ]
    optional = ["DECISION_CHAIN.md"]

    contents = []
    for fname in required:
        path = agent_dir / fname
        if path.exists():
            contents.append(f"## {fname}\n\n{read_knowledge(str(path))}")
        else:
            print(f"[warning] 缺失必读配置: {fname}")

    for fname in optional:
        path = agent_dir / fname
        if path.exists():
            contents.append(f"## {fname}\n\n{read_knowledge(str(path))}")

    return "\n\n".join(contents)


def load_shared_knowledge(project_root: Path) -> str:
    """加载公司共享知识库。"""
    shared_dir = project_root / "shared" / "knowledge"
    files = [
        "COMPANY.md",
        "INDUSTRY.md",
        "USER.md",
        "BRAND-VOICE.md",
        "FORBIDDEN.md",
        "PLATFORM-RULES.md",
    ]

    contents = []
    for fname in files:
        path = shared_dir / fname
        if path.exists():
            contents.append(f"## shared/knowledge/{fname}\n\n{read_knowledge(str(path))}")
        else:
            print(f"[warning] 缺失共享知识: {fname}")

    return "\n\n".join(contents)


# ============================================================
# 上层缺失防御
# ============================================================

def check_upstream(level: Level, project_root: Path) -> tuple[bool, str]:
    """检查上层产出是否存在。"""
    collab = project_root / "collaboration"

    if level == "monthly":
        strategy_dir = collab / "04-strategy-pool" / "approved"
        if not strategy_dir.exists() or not any(strategy_dir.glob("*.md")):
            return False, (
                "❌ 当季度策略尚未生成（approved）。\n"
                "请先生成季度策略再做月度计划。\n"
                "在飞书说：'生成本季度策略'"
            )

    if level == "weekly":
        plan_dir = collab / "04-monthly-plan-pool" / "approved"
        if not plan_dir.exists() or not any(plan_dir.glob("*.md")):
            return False, (
                "❌ 当月度计划尚未生成（approved）。\n"
                "请先生成月度计划再做周选题。\n"
                "在飞书说：'生成本月计划'"
            )

    return True, ""


# ============================================================
# 协作池输入读取
# ============================================================

def build_input(level: Level) -> str:
    """根据层级读取协作池输入。

    注意：
    - 本版本读取全部 approved 条目（不做时间窗过滤）
    - 如未来需按"近 N 天"过滤，在 utils.py 加 read_approved_by_days 函数
    """
    collab = "collaboration"

    if level == "quarterly":
        intel = read_all_approved(f"{collab}/01-intel-pool")
        demand = read_all_approved(f"{collab}/demand-pool")
        history = read_all_approved(f"{collab}/04-strategy-pool")

        return (
            f"# 【输入数据】\n\n"
            f"## 1. 行业情报（全部 approved）\n\n{intel or '(暂无)'}\n\n"
            f"## 2. 需求池全部 approved 条目\n\n{demand or '(暂无)'}\n\n"
            f"## 3. 历史季度策略（衔接参考）\n\n{history or '(暂无)'}"
        )

    elif level == "monthly":
        quarter_strategy = read_approved(f"{collab}/04-strategy-pool")  # 只读最新一个
        intel = read_all_approved(f"{collab}/01-intel-pool")
        demand = read_all_approved(f"{collab}/demand-pool")
        last_month = read_approved(f"{collab}/04-monthly-plan-pool")  # 上月只读最新

        return (
            f"# 【输入数据】\n\n"
            f"## 1. 当前季度策略（必读，不可偏离）\n\n{quarter_strategy or '(缺失)'}\n\n"
            f"## 2. 行业情报（全部 approved）\n\n{intel or '(暂无)'}\n\n"
            f"## 3. 需求池 approved 条目\n\n{demand or '(暂无)'}\n\n"
            f"## 4. 上月计划(延续性参考)\n\n{last_month or '(暂无)'}"
        )

    elif level == "weekly":
        month_plan = read_approved(f"{collab}/04-monthly-plan-pool")
        quarter_strategy = read_approved(f"{collab}/04-strategy-pool")
        intel = read_all_approved(f"{collab}/01-intel-pool")
        demand = read_all_approved(f"{collab}/demand-pool")
        recent_topics = read_all_approved(f"{collab}/05-topic-plan-pool")

        return (
            f"# 【输入数据】\n\n"
            f"## 1. 当前月度计划（必读，不可偏离）\n\n{month_plan or '(缺失)'}\n\n"
            f"## 2. 当前季度策略（辅读）\n\n{quarter_strategy or '(缺失)'}\n\n"
            f"## 3. 行业情报（全部 approved）\n\n{intel or '(暂无)'}\n\n"
            f"## 4. 需求池 approved 条目\n\n{demand or '(暂无)'}\n\n"
            f"## 5. 近期历史选题(去重用)\n\n{recent_topics or '(暂无)'}"
        )

    else:
        raise ValueError(f"未知层级: {level}")


# ============================================================
# 用户提示词
# ============================================================

def get_user_prompt(level: Level) -> str:
    prompts = {
        "quarterly": (
            "请生成本季度内容策略。\n\n"
            "要求：\n"
            "1. 严格按 DATAFLOW §4.1 的结构输出\n"
            "2. 必须完成账号阶段诊断，引用 STAGE_PLAYBOOK 对应阶段的配比参数\n"
            "3. 输出季度策略，不得包含月度计划或周度选题\n"
            "4. 产出末尾附'建议写入 MEMORY 的条目'供人工确认"
        ),
        "monthly": (
            "请生成本月内容计划。\n\n"
            "要求：\n"
            "1. 严格按 DATAFLOW §4.2 的结构输出\n"
            "2. 必须基于当前季度策略作为约束框架，不得偏离季度核心方向\n"
            "3. 输出月度计划，不得包含季度策略或周度选题\n"
            "4. 产出末尾附'建议写入 MEMORY 的条目'供人工确认"
        ),
        "weekly": (
            "请生成本周选题计划。\n\n"
            "要求：\n"
            "1. 严格按 DATAFLOW §4.3 的结构输出\n"
            "2. 必须基于当前月度计划作为约束框架，不得偏离月度子方向\n"
            "3. 选题表字段完整：归属支柱、子方向、目标平台、目标决策人、"
            "预期作用、来源类型、来源详情、业务价值、钩子、核心角度\n"
            "4. 输出周选题，不得包含季度策略或月度计划\n"
            "5. 产出末尾附'建议写入 MEMORY 的条目'供人工确认"
        ),
    }
    return prompts[level]


# ============================================================
# 核心执行函数（可被 import 调用）
# ============================================================

def run_agent_04(level: Level, refinement: str = "") -> dict:
    """核心执行函数。

    参数：
        level: "quarterly" / "monthly" / "weekly"
        refinement: 用户本次特别要求（自然语言），会以最高优先级注入

    返回：
        {
            "status": "ok" / "error",
            "message": "...",
            "output_path": "..." (ok 时有),
            "content": "..." (ok 时有)
        }
    """
    agent_dir = Path(__file__).parent
    project_root = agent_dir.parent.parent

    # 1. 防御检查
    ok, msg = check_upstream(level, project_root)
    if not ok:
        return {"status": "error", "message": msg}

    # 2. 加载配置
    print(f"→ 加载 Agent 04 配置...")
    core_config = load_core_config(agent_dir)
    shared_knowledge = load_shared_knowledge(project_root)

    # 3. 构建输入
    print(f"→ 读取协作池输入（层级: {level}）...")
    input_content = build_input(level)

    # 4. 组装 system / user
    system_content = (
        f"# Agent 04 核心配置\n\n{core_config}\n\n"
        f"# 公司共享知识\n\n{shared_knowledge}"
    )

    # 【本期特别要求】块（最高优先级，PRIORITY P1.1）
    refinement_block = ""
    if refinement:
        refinement_block = (
            "# 【本期特别要求 — 最高优先级】\n\n"
            f"用户完整原话：\n> {refinement}\n\n"
            "**解析原则**：\n"
            "- 以上是用户本次的原始输入。其中可能包含框架性触发词（如\"做本周选题\"）和具体调整要求（如\"不要触碰大肠厂\"、\"增加 GEO 比例\"）\n"
            "- 你需要自己识别并提取其中的**具体调整要求**，把框架词忽略\n"
            "- 如果完整原话只是框架触发词（如仅为\"做本周选题\"），按标准模板处理即可\n\n"
            "**执行规则（参见 PRIORITY.md P1.1）**：\n"
            "1. 必须按用户的具体调整要求重做，不得复用任何历史产出或默认模板填充\n"
            "2. 若调整要求与 STAGE_PLAYBOOK/CONTENT_PILLARS 标准配比冲突：本次产出按用户要求，末尾提示\"下期将回归标准配比\"\n"
            "3. 若与 RULES R1-R14 冲突：以 RULES 为准，开头标注冲突和折中方案\n"
            "4. 在产出开头**用一句话**确认你理解的具体调整要求是什么，让用户能快速核对\n\n"
            "---\n\n"
        )

    user_content = f"{refinement_block}{get_user_prompt(level)}\n\n{input_content}"

    # 5. 调用 LLM
    print(f"→ 生成 {level} 产出（调用 LLM，可能需要几十秒）...")
    client = get_client()
    output = chat(client, system=system_content, user=user_content)

    # 6. 写入协作池
    pool_map = {
        "quarterly": "collaboration/04-strategy-pool",
        "monthly": "collaboration/04-monthly-plan-pool",
        "weekly": "collaboration/05-topic-plan-pool",
    }
    tag_map = {
        "quarterly": ["内容策略", "季度策略"],
        "monthly": ["内容策略", "月度计划"],
        "weekly": ["选题计划", "周选题"],
    }

    path = write_pending(
        pool=pool_map[level],
        content=output,
        agent="04-content-strategy",
        tags=tag_map[level],
    )

    print(f"✓ {level} 产出已写入 → {path}")
    print(f"→ 请审核 pending/，通过后移到 approved/")

    return {
        "status": "ok",
        "message": f"{level} 产出已写入 pending，请人工审核",
        "output_path": str(path),
        "content": output,
    }


# ============================================================
# 命令行入口
# ============================================================

def main() -> None:
    if len(sys.argv) < 2:
        print(
            "用法：\n"
            "  python run.py \"中文自然语言\"\n\n"
            "示例：\n"
            "  python run.py \"生成本季度策略\"\n"
            "  python run.py \"做 Q2 战略\"\n"
            "  python run.py \"出本月计划\"\n"
            "  python run.py \"帮我出本周选题\"\n"
        )
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])
    level = detect_level(user_input)

    if level is None:
        print(
            f"❌ 识别不出层级。你输入的是：'{user_input}'\n\n"
            f"请使用以下关键词之一：\n"
            f"  季度策略 → 季度策略 / 战略 / Q1-Q4 / 新一季\n"
            f"  月度计划 → 月度计划 / 本月 / X月方向\n"
            f"  周度选题 → 周选题 / 本周选题 / 选题计划"
        )
        sys.exit(1)

    # 判断用户是仅触发标准模板 还是 附带调整要求
    standard = is_standard_trigger(user_input, level)
    refinement = "" if standard else user_input  # 非标准触发 → 把用户原话完整传入，LLM 自己解析
    print(f"→ 识别到层级: {level}（来自：'{user_input}'）")
    if refinement:
        print(f"→ 本期附带调整要求（原话传 LLM 解析）")
    else:
        print("→ 标准触发词，无特别要求")
    print()

    result = run_agent_04(level, refinement=refinement)

    if result["status"] == "error":
        print(f"\n❌ {result['message']}")
        sys.exit(1)

    print(f"\n✓ {result['message']}")
    print(f"输出路径: {result['output_path']}")


if __name__ == "__main__":
    main()
