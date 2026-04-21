"""Agent 03 - 销售/CS官：分析客户对话，输出话术（Part A）和洞察（Part B）"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from scripts.utils import read_knowledge, read_approved, write_pending, get_client, chat

load_dotenv(override=True)


def main(conversation: str) -> None:
    agent_dir = Path(__file__).parent

    identity = read_knowledge(str(agent_dir / "IDENTITY.md"))
    rules    = read_knowledge(str(agent_dir / "RULES.md"))
    dataflow = read_knowledge(str(agent_dir / "DATAFLOW.md"))
    memory   = read_knowledge(str(agent_dir / "MEMORY.md"))

    knowledge = read_knowledge("shared/knowledge/")
    intel     = read_approved("collaboration/01-intel-pool")
    insight   = read_approved("collaboration/02-insight-pool")

    client = get_client()
    full_output = chat(
        client,
        system=(
            f"{identity}\n\n{rules}\n\n{dataflow}\n\n"
            f"## 历史记忆\n{memory}\n\n"
            f"## 全局知识库\n{knowledge}\n\n"
            f"## 最新行业情报\n{intel}\n\n"
            f"## 最新用户洞察\n{insight}"
        ),
        user=(
            "以下是客户对话原文，请按 DATAFLOW.md 格式输出 Part A 和 Part B，"
            "两部分之间用独立的 --- 分割线隔开：\n\n"
            f"{conversation}"
        ),
    )

    parts = full_output.split("\n---\n", 1)
    part_a = parts[0].strip()
    part_b = parts[1].strip() if len(parts) > 1 else ""

    path_a = write_pending(
        pool="collaboration/03-sales-support-pool",
        content=part_a,
        agent="03-sales-cs",
        tags=["销售话术"],
        output_type="sales-support",
    )
    print(f"✓ Part A（话术）→ {path_a}")

    if part_b:
        path_b = write_pending(
            pool="collaboration/03-sales-insight-pool",
            content=part_b,
            agent="03-sales-cs",
            tags=["客户洞察"],
            output_type="sales-insight",
        )
        print(f"✓ Part B（洞察）→ {path_b}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("粘贴客户对话内容，按 Ctrl+D 结束：")
        conversation = sys.stdin.read().strip()
    else:
        conversation = sys.argv[1]

    if not conversation:
        print("错误：请提供客户对话内容")
        sys.exit(1)

    main(conversation)
