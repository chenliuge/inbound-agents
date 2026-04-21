"""批量导入 demand-pool 需求条目

输入：一份 markdown 表格文件（默认 scripts/demands_input.md）
输出：在 collaboration/demand-pool/pending/ 批量生成 demand-YYYY-MM-NNNN.md

表格格式（必须完全匹配列头，顺序可换）：
| 原始描述 | 选题方向 | 支柱 | 子方向 | 决策人 | 来源类型 | tags | 备注 |

字段说明：
- 原始描述    必填  人类语言描述，支持多句
- 选题方向    必填  一句话提炼成可做成选题的方向
- 支柱        必填  市场与趋势判断 / 获客方法论 / 案例与数据证据 / 立场与人格
- 子方向      选填  如"2a 海外社媒"或"4a 行业观察"
- 决策人      选填  老板 / 营销负责人 / 执行，默认"老板"
- 来源类型    选填  平台热点 / 用户评论 / 客户咨询 / 行业观察 / 销售对话 / 爆款观察，默认"平台热点"
- tags        选填  逗号分隔，如"小红书,入境游"
- 备注        选填  其他上下文

用法：
  python3 scripts/import_demands.py [输入文件]
  python3 scripts/import_demands.py                       # 默认读 scripts/demands_input.md
  python3 scripts/import_demands.py my_demands.md
  python3 scripts/import_demands.py --dry-run             # 只预览不写文件
  python3 scripts/import_demands.py --start-id 10         # 从编号 0010 开始
"""
from __future__ import annotations
import argparse
import re
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
POOL_DIR = PROJECT_ROOT / "collaboration" / "demand-pool"
PENDING_DIR = POOL_DIR / "pending"
APPROVED_DIR = POOL_DIR / "approved"
ARCHIVED_DIR = POOL_DIR / "archived"
DEFAULT_INPUT = Path(__file__).parent / "demands_input.md"

# 合法支柱取值
VALID_PILLARS = [
    "市场与趋势判断",
    "获客方法论",
    "案例与数据证据",
    "立场与人格",
]

REQUIRED_COLUMNS = {"原始描述", "选题方向", "支柱"}
OPTIONAL_COLUMNS = {"子方向", "决策人", "来源类型", "tags", "备注"}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


def parse_markdown_table(md_text: str) -> list[dict]:
    """解析 Markdown 表格为 list of dict"""
    lines = [ln.rstrip() for ln in md_text.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        raise ValueError("输入里找不到 Markdown 表格（应以 | 开头）")

    # 解析列头
    header_line = lines[0]
    headers = [c.strip() for c in header_line.strip("|").split("|")]

    # 验证列
    missing = REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ValueError(f"缺少必填列：{missing}")
    unknown = set(headers) - ALL_COLUMNS
    if unknown:
        print(f"[warn] 忽略未知列：{unknown}")

    # 找到第一行数据（跳过表头和分隔行）
    rows = []
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        # 跳过分隔行（---|---|---）
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) != len(headers):
            print(f"[warn] 跳过列数不匹配的行：{ln[:60]}")
            continue
        row = dict(zip(headers, cells))
        # 过滤空行
        if not row.get("原始描述"):
            continue
        rows.append(row)

    return rows


def next_id(start: int | None = None) -> int:
    """根据已有 demand 文件，计算下一个编号。"""
    if start is not None:
        return start
    existing_ids = []
    for d in (PENDING_DIR, APPROVED_DIR, ARCHIVED_DIR):
        if not d.exists():
            continue
        for f in d.glob("demand-*.md"):
            m = re.match(r"demand-\d{4}-\d{2}-(\d{4})\.md$", f.name)
            if m:
                existing_ids.append(int(m.group(1)))
    return (max(existing_ids) + 1) if existing_ids else 1


def build_demand_md(row: dict, demand_id: str, today: str) -> str:
    """生成单条 demand 文件内容。"""
    pillar = row.get("支柱", "").strip()
    if pillar and pillar not in VALID_PILLARS:
        print(f"[warn] 支柱取值非法：{pillar!r}（合法：{VALID_PILLARS}）")

    source_type = row.get("来源类型", "").strip() or "平台热点"
    decision_maker = row.get("决策人", "").strip() or "老板"
    sub_direction = row.get("子方向", "").strip()
    tags_raw = row.get("tags", "").strip()
    tags = [t.strip() for t in re.split(r"[,，]", tags_raw) if t.strip()]
    tags_yaml = ", ".join(tags) if tags else ""
    note = row.get("备注", "").strip()

    front_matter = (
        "---\n"
        f"id: {demand_id}\n"
        f"created_at: {today}\n"
        "source_agent: manual\n"
        f"source_type: {source_type}\n"
        f"tags: [{tags_yaml}]\n"
        "status: pending\n"
        "used_count: 0\n"
        "last_used: null\n"
        "---\n\n"
    )

    body_parts = [
        "## 原始描述",
        row["原始描述"],
        "",
        "## 提炼的选题方向",
        row["选题方向"],
        "",
        "## 适用支柱",
        pillar + (f"（{sub_direction}）" if sub_direction else ""),
        "",
        "## 适用决策人",
        decision_maker,
    ]
    if note:
        body_parts += ["", "## 备注", note]

    return front_matter + "\n".join(body_parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="批量导入 demand-pool 需求")
    parser.add_argument("input_file", nargs="?", default=str(DEFAULT_INPUT),
                        help=f"输入 markdown 文件（默认：{DEFAULT_INPUT}）")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    parser.add_argument("--start-id", type=int, default=None,
                        help="起始编号（默认自动取当前最大+1）")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"❌ 找不到输入文件：{input_path}")
        print(f"   可选：\n   1. 在 {input_path} 粘贴表格\n   2. 或指定其他文件路径")
        sys.exit(1)

    md_text = input_path.read_text(encoding="utf-8")
    try:
        rows = parse_markdown_table(md_text)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if not rows:
        print("⚠️  没解析到任何有效行")
        sys.exit(0)

    print(f"→ 解析到 {len(rows)} 条需求")

    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    yyyy_mm = date.today().strftime("%Y-%m")
    start_n = next_id(args.start_id)

    created = []
    for i, row in enumerate(rows):
        n = start_n + i
        demand_id = f"demand-{yyyy_mm}-{n:04d}"
        filename = f"{demand_id}.md"
        filepath = PENDING_DIR / filename

        content = build_demand_md(row, demand_id, today)

        if args.dry_run:
            print(f"\n[dry-run] 将创建 {filepath}")
            print(content[:300] + ("..." if len(content) > 300 else ""))
        else:
            if filepath.exists():
                print(f"[warn] 已存在，跳过：{filename}")
                continue
            filepath.write_text(content, encoding="utf-8")
            created.append(filename)
            print(f"  ✓ {filename}（{row['选题方向'][:40]}）")

    if args.dry_run:
        print(f"\n[dry-run] 预览模式，未实际写入")
    else:
        print(f"\n✅ 已创建 {len(created)} 条需求到 pending/")
        print(f"→ 下一步：审核通过后，把文件挪到 approved/")
        print(f"   例：mv {PENDING_DIR}/demand-*.md {APPROVED_DIR}/")


if __name__ == "__main__":
    main()
