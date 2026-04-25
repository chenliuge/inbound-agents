"""异步流式 Claude 调用。走 yunwu.ai 中转。"""
from __future__ import annotations
import os
from typing import AsyncGenerator
from openai import AsyncOpenAI


def get_async_client() -> AsyncOpenAI:
    base_url = os.environ.get("ANTHROPIC_BASE_URL") or "https://yunwu.ai/v1"
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 未配置")
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


async def stream_chat(
    system: str,
    user: str,
    model: str = "claude-opus-4-6",
    max_tokens: int = 4096,
) -> AsyncGenerator[str, None]:
    """流式返回 content chunks。"""
    client = get_async_client()
    stream = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        stream=True,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
