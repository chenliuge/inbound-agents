"""Agent 07 - 图片制作官：优化图片提示词，生成多工具标准化版本"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from scripts.utils import read_knowledge, read_approved, write_pending, get_client, chat

load_dotenv(override=True)


def main() -> None:
    agent_dir = Path(__file__).parent

    identity    = read_knowledge(str(agent_dir / "IDENTITY.md"))
    rules       = read_knowledge(str(agent_dir / "RULES.md"))
    dataflow    = read_knowledge(str(agent_dir / "DATAFLOW.md"))
    memory      = read_knowledge(str(agent_dir / "MEMORY.md"))
    raw_prompts = read_approved("collaboration/09-image-prompt-pool")

    if not raw_prompts:
        print("警告：09-image-prompt-pool 为空。请先运行 Agent 06 并完成审核。")
        sys.exit(1)

    client = get_client()
    result = chat(
        client,
        system=(
            f"{identity}\n\n{rules}\n\n{dataflow}\n\n"
            f"## 历史记忆\n{memory}"
        ),
        user=(
            "以下是原始图片提示词，请按 DATAFLOW.md 格式优化为标准化多工具版本：\n\n"
            f"{raw_prompts}"
        ),
    )

    output_path = write_pending(
        pool="collaboration/10-image-output-pool",
        content=result,
        agent="07-image-creation",
        tags=["图片提示词", "优化版"],
    )
    print(f"✓ 完成 → {output_path}")


if __name__ == "__main__":
    main()
