"""Agent 06 - 内容制作官：生成文案正文 + 图片提示词"""
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
    brand_voice = read_knowledge("shared/knowledge/BRAND-VOICE.md")
    forbidden   = read_knowledge("shared/knowledge/FORBIDDEN.md")
    viral       = read_approved("collaboration/06-viral-analysis-pool")

    if not viral:
        print("警告：06-viral-analysis-pool 为空。请先运行 Agent 05 并完成审核。")
        sys.exit(1)

    client = get_client()
    full_output = chat(
        client,
        system=(
            f"{identity}\n\n{rules}\n\n{dataflow}\n\n"
            f"## 历史记忆\n{memory}\n\n"
            f"## 品牌语气规范\n{brand_voice}\n\n"
            f"## 禁区\n{forbidden}"
        ),
        user=(
            "以下是爆款分析结果，请按 DATAFLOW.md 格式创作文案和图片提示词，"
            "用 ---IMAGE_PROMPTS--- 分隔两部分：\n\n"
            f"{viral}"
        ),
    )

    parts = full_output.split("---IMAGE_PROMPTS---", 1)
    draft   = parts[0].strip()
    prompts = parts[1].strip() if len(parts) > 1 else ""

    path_d = write_pending(
        pool="collaboration/08-draft-pool/xhs",
        content=draft,
        agent="06-content-creation",
        tags=["文案", "小红书"],
    )
    print(f"✓ 文案 → {path_d}")

    if prompts:
        path_p = write_pending(
            pool="collaboration/09-image-prompt-pool",
            content=prompts,
            agent="06-content-creation",
            tags=["图片提示词"],
        )
        print(f"✓ 图片提示词 → {path_p}")


if __name__ == "__main__":
    main()
