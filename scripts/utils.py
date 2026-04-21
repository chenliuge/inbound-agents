from __future__ import annotations
from pathlib import Path
from datetime import datetime
import os
from openai import OpenAI


def get_client() -> OpenAI:
    """Return an OpenAI-compatible client, supporting third-party base URLs."""
    base_url = os.environ.get("ANTHROPIC_BASE_URL") or "https://yunwu.ai/v1"
    return OpenAI(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        base_url=base_url,
    )


def chat(client: OpenAI, system: str, user: str, model: str = "claude-opus-4-6", max_tokens: int = 4096) -> str:
    """Send a single system+user message and return the text response."""
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content


def read_knowledge(path: str) -> str:
    """Read a .md file, or concatenate all .md files in a directory."""
    p = Path(path)
    if not p.exists():
        return ""
    if p.is_file():
        return p.read_text(encoding="utf-8")
    parts = []
    for md in sorted(p.glob("*.md")):
        parts.append(f"## {md.name}\n\n{md.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def read_approved(pool_path: str) -> str:
    """Return content of the most recently modified approved file."""
    approved_dir = Path(pool_path) / "approved"
    if not approved_dir.exists():
        return ""
    files = sorted(
        approved_dir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files[0].read_text(encoding="utf-8") if files else ""


def read_all_approved(pool_path: str) -> str:
    """读取指定 pool 的 approved/ 下所有 .md 文件，拼接返回。与 read_approved 的区别：
    - read_approved：只读最新一个文件
    - read_all_approved：读全部文件，按修改时间倒序（最新在前）

    参数：
        pool_path: 协作池路径，如 "collaboration/01-intel-pool"

    返回：
        拼接后的所有 md 文本，用 "\\n\\n---\\n\\n" 分隔。
        如果 approved/ 不存在或为空，返回空字符串。
    """
    approved_dir = Path(pool_path) / "approved"
    if not approved_dir.exists():
        return ""

    md_files = sorted(
        approved_dir.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,  # 最新在前
    )

    if not md_files:
        return ""

    contents = []
    for f in md_files:
        contents.append(f"### 来源文件：{f.name}\n\n{f.read_text(encoding='utf-8')}")

    return "\n\n---\n\n".join(contents)


def write_pending(
    pool: str,
    content: str,
    agent: str,
    tags: list,
    output_type: str = "",
) -> Path:
    """Write content + YAML front-matter to pending/. Returns the created path."""
    pending_dir = Path(pool) / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    stem = f"{timestamp}-{agent}"
    filepath = pending_dir / f"{stem}.md"

    version = 2
    while filepath.exists():
        filepath = pending_dir / f"{stem}-v{version}.md"
        version += 1

    tags_str = ", ".join(tags)
    ot_line = f"output_type: {output_type}\n" if output_type else ""
    header = (
        "---\n"
        f"agent: {agent}\n"
        f"created_at: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        "status: pending\n"
        "version: 1\n"
        f"{ot_line}"
        f"tags: [{tags_str}]\n"
        'reviewer: ""\n'
        'review_note: ""\n'
        "---\n\n"
    )
    filepath.write_text(header + content, encoding="utf-8")
    return filepath
