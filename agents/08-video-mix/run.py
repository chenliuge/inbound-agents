"""Agent 08 - 视频混剪官：把视频脚本转为可执行的混剪生产规格单"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from scripts.utils import read_knowledge, read_approved, write_pending, get_client, chat

load_dotenv(override=True)


def main() -> None:
    agent_dir = Path(__file__).parent

    identity = read_knowledge(str(agent_dir / "IDENTITY.md"))
    rules    = read_knowledge(str(agent_dir / "RULES.md"))
    dataflow = read_knowledge(str(agent_dir / "DATAFLOW.md"))
    memory   = read_knowledge(str(agent_dir / "MEMORY.md"))
    priority = read_knowledge(str(agent_dir / "PRIORITY.md"))

    # 主输入：最新已审核的视频脚本
    video_script = read_approved("collaboration/08-draft-pool/video")

    if not video_script:
        print("警告：collaboration/08-draft-pool/video/approved/ 为空。")
        print("请先运行 Agent 06 产出视频脚本并完成审核。")
        sys.exit(1)

    # 辅助输入：爆款拆解（可选）
    viral_analysis = read_approved("collaboration/06-viral-analysis-pool")

    # 共享知识：平台规则、品牌语气、禁区（混剪必读）
    platform_rules = read_knowledge("shared/knowledge/PLATFORM-RULES.md")
    brand_voice    = read_knowledge("shared/knowledge/BRAND-VOICE.md")
    forbidden      = read_knowledge("shared/knowledge/FORBIDDEN.md")

    client = get_client()
    result = chat(
        client,
        system=(
            f"{identity}\n\n{rules}\n\n{dataflow}\n\n{priority}\n\n"
            f"## 历史记忆\n{memory}\n\n"
            f"## 平台规则（硬约束）\n{platform_rules}\n\n"
            f"## 品牌语气\n{brand_voice}\n\n"
            f"## 全局禁区\n{forbidden}"
        ),
        user=(
            "请把以下视频脚本转为标准化的混剪生产规格单，严格按 DATAFLOW.md 的 7 个板块输出：\n\n"
            "## 视频脚本原文\n\n"
            f"{video_script}\n\n"
            "---\n\n"
            "## 爆款参考（若有可借鉴的节奏/转场，可引用；若空则忽略）\n\n"
            f"{viral_analysis or '(暂无爆款参考)'}"
        ),
    )

    output_path = write_pending(
        pool="collaboration/11-video-mix-pool",
        content=result,
        agent="08-video-mix",
        tags=["视频混剪", "生产规格"],
    )
    print(f"✓ 完成 → {output_path}")


if __name__ == "__main__":
    main()
