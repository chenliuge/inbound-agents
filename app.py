"""FastAPI 入口 · 入境游内容工作台

启动：
    uvicorn app:app --reload --port 8000

访问：
    http://localhost:8000
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from workstation.db import (
    init_db,
    save_session,
    save_output,
    approve_output,
    reject_output,
    list_sessions,
    get_approved_outputs,
    save_feedback,
    get_pending_feedback,
)
from workstation.llm import stream_chat
from workstation.prompts import get_system_prompt, get_upstream_agents


load_dotenv(override=True)
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 入境游内容工作台启动 · http://localhost:8000")
    yield


app = FastAPI(lifespan=lifespan, title="入境游内容工作台")

ROOT = Path(__file__).parent


# ─────────── Request Models ───────────

class RunRequest(BaseModel):
    agent_id: str
    sub_line: Optional[str] = None
    instruction_id: str
    instruction_name: str
    user_prompt: str
    pull_upstream: bool = True


class ReviewRequest(BaseModel):
    output_id: str
    note: str = ""


class FeedbackRequest(BaseModel):
    source_output_id: str
    target_agent_id: str
    note: str


# ─────────── Static ───────────

@app.get("/")
async def index():
    return FileResponse(ROOT / "workstation-demo.html")


# ─────────── Agent 运行 · 流式 ───────────

@app.post("/api/run")
async def run_agent(req: RunRequest):
    # 拉取上游 approved 产出作为上下文
    upstream_context = ""
    if req.pull_upstream:
        upstream_parts = []
        for upstream_id in get_upstream_agents(req.agent_id):
            outputs = get_approved_outputs(upstream_id, limit=2)
            for o in outputs:
                upstream_parts.append(
                    f"### 来自 {upstream_id} · {o['instruction_name']} · {o['created_at']}\n\n{o['content']}"
                )
        upstream_context = "\n\n---\n\n".join(upstream_parts)

    # 拉取 A5 反哺建议
    feedback_parts = []
    for fb in get_pending_feedback(req.agent_id):
        feedback_parts.append(f"- [{fb['created_at']}] {fb['note']}")
    feedback_notes = "\n".join(feedback_parts)

    system = get_system_prompt(
        req.agent_id,
        sub_line=req.sub_line,
        upstream_context=upstream_context,
        feedback_notes=feedback_notes,
    )

    # 建会话
    session_id = save_session(
        req.agent_id, req.sub_line, req.instruction_id, req.instruction_name, req.user_prompt
    )

    async def event_stream():
        full = ""
        try:
            async for chunk in stream_chat(system, req.user_prompt):
                full += chunk
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            # 持久化
            output_id = save_output(session_id, full, tokens=len(full) // 2)
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'output_id': output_id}, ensure_ascii=False)}\n\n"
        except Exception as e:
            err_msg = f"❌ LLM 调用失败：{type(e).__name__}: {str(e)[:200]}"
            yield f"data: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────── 审核 ───────────

@app.post("/api/approve")
async def approve(req: ReviewRequest):
    approve_output(req.output_id, req.note)
    return {"ok": True}


@app.post("/api/reject")
async def reject(req: ReviewRequest):
    reject_output(req.output_id, req.note)
    return {"ok": True}


# ─────────── 会话历史 ───────────

@app.get("/api/sessions")
async def sessions(limit: int = 30):
    return list_sessions(limit=limit)


# ─────────── A5 反哺 ───────────

@app.post("/api/feedback")
async def feedback(req: FeedbackRequest):
    fid = save_feedback(req.source_output_id, req.target_agent_id, req.note)
    return {"ok": True, "id": fid}


# ─────────── 健康检查 ───────────

@app.get("/api/health")
async def health():
    import os
    return {
        "ok": True,
        "api_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "base_url": os.environ.get("ANTHROPIC_BASE_URL") or "https://yunwu.ai/v1",
    }
