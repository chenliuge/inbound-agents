"""
Move a file from pending/ → approved/, update front-matter, archive previous.

Usage:
    python scripts/approve.py <path-to-pending-file> [--note "备注"] [--reviewer "姓名"]
"""
from __future__ import annotations
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def approve_file(
    pending_path: str,
    note: str = "",
    reviewer: str = "负责人",
) -> Path:
    src = Path(pending_path)
    if not src.exists():
        raise FileNotFoundError(f"文件不存在: {pending_path}")
    if src.parent.name != "pending":
        raise ValueError(f"文件必须在 pending/ 目录: {pending_path}")

    pool_dir = src.parent.parent
    approved_dir = pool_dir / "approved"
    archived_dir = pool_dir / "archived"
    approved_dir.mkdir(exist_ok=True)
    archived_dir.mkdir(exist_ok=True)

    text = src.read_text(encoding="utf-8")

    # Archive existing approved files for same agent
    m = re.search(r"^agent:\s*(.+)$", text, re.MULTILINE)
    if m:
        agent_name = m.group(1).strip()
        for existing in approved_dir.glob(f"*{agent_name}*.md"):
            shutil.move(str(existing), str(archived_dir / existing.name))

    # Patch front-matter
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = re.sub(r"^status: pending$", "status: approved", text, flags=re.MULTILINE)
    text = re.sub(r'^reviewer: ""$', f'reviewer: "{reviewer}"', text, flags=re.MULTILINE)
    text = re.sub(r'^review_note: ""$', f'review_note: "{note}"', text, flags=re.MULTILINE)
    if "reviewed_at:" not in text:
        text = text.replace("review_note:", f"reviewed_at: {now}\nreview_note:", 1)

    dest = approved_dir / src.name
    dest.write_text(text, encoding="utf-8")
    src.unlink()
    return dest


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/approve.py <pending文件路径> [--note '备注'] [--reviewer '姓名']")
        sys.exit(1)
    path = sys.argv[1]
    note = ""
    reviewer = "负责人"
    if "--note" in sys.argv:
        reviewer = sys.argv[sys.argv.index("--note") + 1]
    if "--reviewer" in sys.argv:
        reviewer = sys.argv[sys.argv.index("--reviewer") + 1]
    dest = approve_file(path, note=note, reviewer=reviewer)
    print(f"✓ 审核通过 → {dest}")
