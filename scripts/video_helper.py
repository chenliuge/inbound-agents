"""视频下载 + Whisper 转写 Skill

档 2 能力：给一个视频 URL，下载下来，转成文字稿。

依赖：
    pip install yt-dlp

环境变量：
    ANTHROPIC_API_KEY  或  OPENAI_API_KEY（Whisper 用）
    ANTHROPIC_BASE_URL 或  OPENAI_BASE_URL（若代理）

使用：
    from scripts.video_helper import download_video, transcribe_video
    path = download_video("https://www.douyin.com/video/xxx")
    text = transcribe_video(path)
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Optional


DEFAULT_DOWNLOAD_DIR = Path(__file__).parent.parent / "downloads"


def ensure_yt_dlp() -> bool:
    """检查 yt-dlp 是否可用。"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def download_video(
    url: str,
    output_dir: Optional[Path] = None,
    max_height: int = 720,
    timeout: int = 120,
) -> Optional[str]:
    """下载视频到本地，返回文件绝对路径。

    支持平台：抖音 / TikTok / YouTube / Bilibili / 视频号（部分）

    参数：
        url: 视频链接
        output_dir: 下载目录（默认 <项目根>/downloads/）
        max_height: 最高清晰度（720 省空间，处理更快）
        timeout: 下载超时秒数

    返回：
        成功 → 文件路径字符串
        失败 → None
    """
    if not ensure_yt_dlp():
        print("[video_helper] yt-dlp 未安装，执行 `pip install yt-dlp`")
        return None

    output_dir = output_dir or DEFAULT_DOWNLOAD_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # 输出文件名模板：<id>.<ext>
    output_template = str(output_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-f", f"best[height<={max_height}]/best",
        "-o", output_template,
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--print", "after_move:filepath",  # 下载完成后打印文件路径
        url,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"[video_helper] yt-dlp 失败 rc={result.returncode}: {result.stderr[:200]}")
            return None
        filepath = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else None
        if filepath and Path(filepath).exists():
            return filepath
        # Fallback: 在目录里找最新文件
        files = sorted(output_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return str(files[0])
        return None
    except subprocess.TimeoutExpired:
        print(f"[video_helper] 下载超时：{url}")
        return None
    except Exception as e:
        print(f"[video_helper] 下载异常：{e}")
        return None


def transcribe_video(
    video_path: str,
    model: str = "whisper-1",
    language: str = "zh",
) -> Optional[str]:
    """用 Whisper 把视频转成文字稿。

    前置条件：
    - 视频文件存在
    - 配好 OPENAI_API_KEY（或 ANTHROPIC_API_KEY 到支持 Whisper 的代理）

    返回：
        成功 → 文字稿字符串
        失败 → None
    """
    if not os.path.exists(video_path):
        print(f"[video_helper] 文件不存在：{video_path}")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        print("[video_helper] 需要安装 openai: pip install openai")
        return None

    # 优先用独立的 OpenAI Key（更稳），回退到 ANTHROPIC_API_KEY（yunwu.ai 代理）
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL", "https://yunwu.ai/v1")

    if not api_key:
        print("[video_helper] 无 API Key（OPENAI_API_KEY / ANTHROPIC_API_KEY）")
        return None

    client = OpenAI(api_key=api_key, base_url=base_url)

    try:
        with open(video_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                model=model,
                file=f,
                language=language,
            )
        # OpenAI 的返回是对象，有 .text 属性
        text = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
        return text
    except Exception as e:
        print(f"[video_helper] Whisper 转写失败：{e}")
        return None


def download_and_transcribe(url: str) -> dict:
    """一站式：下载 + 转写。返回 {"path": ..., "transcript": ..., "error": ...}"""
    result = {"url": url, "path": None, "transcript": None, "error": None}

    path = download_video(url)
    if not path:
        result["error"] = "下载失败"
        return result

    result["path"] = path

    text = transcribe_video(path)
    if not text:
        result["error"] = "转写失败（视频已下载）"
        return result

    result["transcript"] = text
    return result


def cleanup_downloads(keep_days: int = 7) -> int:
    """清理 downloads/ 目录中超过 keep_days 天的文件。返回删除数量。"""
    if not DEFAULT_DOWNLOAD_DIR.exists():
        return 0
    import time
    cutoff = time.time() - keep_days * 86400
    deleted = 0
    for f in DEFAULT_DOWNLOAD_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted


# ============================================================
# CLI 测试入口
# ============================================================

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法：python3 scripts/video_helper.py <视频 URL>")
        print("  会下载并转写，输出文字稿")
        sys.exit(1)

    from dotenv import load_dotenv
    load_dotenv()

    url = sys.argv[1]
    print(f"→ 下载并转写: {url}")
    result = download_and_transcribe(url)
    print(f"\n结果：")
    print(f"  文件：{result['path']}")
    if result["error"]:
        print(f"  错误：{result['error']}")
    if result["transcript"]:
        print(f"\n文字稿：\n{result['transcript'][:500]}...")
