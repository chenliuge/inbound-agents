"""Agent 02 - 用户洞察官：搜索用户行为动态，生成洞察报告"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from ddgs import DDGS
from scripts.utils import read_knowledge, write_pending, get_client, chat

load_dotenv(override=True)

SEARCH_QUERIES = [
    "inbound tourists China experience 2026",
    "foreign tourists China trip review",
    "入境游客 体验 吐槽 攻略",
    "Japan Korea Europe tourists China visit",
    "China travel tips foreigners 2026",
]


def search_web(queries: list, max_results: int = 5) -> str:
    results = []
    ddgs = DDGS()
    for q in queries:
        try:
            hits = list(ddgs.text(q, max_results=max_results))
            for h in hits:
                results.append(f"**{h['title']}**\n来源: {h['href']}\n{h['body']}")
        except Exception as e:
            results.append(f"[搜索失败: {q}] {e}")
    return "\n\n---\n\n".join(results)


def main() -> None:
    agent_dir = Path(__file__).parent

    identity = read_knowledge(str(agent_dir / "IDENTITY.md"))
    rules    = read_knowledge(str(agent_dir / "RULES.md"))
    dataflow = read_knowledge(str(agent_dir / "DATAFLOW.md"))
    memory   = read_knowledge(str(agent_dir / "MEMORY.md"))
    company  = read_knowledge("shared/knowledge/COMPANY.md")
    user     = read_knowledge("shared/knowledge/USER.md")

    print("正在搜索用户动态...")
    search_results = search_web(SEARCH_QUERIES)

    print("正在生成洞察报告...")
    client = get_client()
    result = chat(
        client,
        system=(
            f"{identity}\n\n{rules}\n\n{dataflow}\n\n"
            f"## 历史记忆\n{memory}\n\n"
            f"## 公司背景\n{company}\n\n"
            f"## 客户画像\n{user}"
        ),
        user=(
            "以下是本次从网络抓取的用户相关信息，请按 DATAFLOW.md 格式生成用户洞察报告：\n\n"
            f"{search_results}"
        ),
    )

    output_path = write_pending(
        pool="collaboration/02-insight-pool",
        content=result,
        agent="02-user-insight",
        tags=["用户洞察", "周报"],
    )
    print(f"✓ 完成 → {output_path}")


if __name__ == "__main__":
    main()
