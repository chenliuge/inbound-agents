"""SQLite 存储层：sessions / outputs / feedback 三表。"""
from __future__ import annotations
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional
from contextlib import contextmanager


DB_PATH = Path(__file__).parent.parent / "sessions.db"


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    """建表 · 幂等。"""
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           TEXT PRIMARY KEY,
            agent_id     TEXT NOT NULL,
            sub_line     TEXT,
            instruction_id TEXT NOT NULL,
            instruction_name TEXT,
            user_prompt  TEXT NOT NULL,
            created_at   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outputs (
            id             TEXT PRIMARY KEY,
            session_id     TEXT NOT NULL,
            content        TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'pending',
            review_note    TEXT,
            tokens_approx  INTEGER,
            created_at     TEXT NOT NULL,
            reviewed_at    TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id         TEXT PRIMARY KEY,
            source_output_id TEXT,
            target_agent_id TEXT NOT NULL,
            note       TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_outputs_session ON outputs(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id, created_at DESC);
        """)


# ─────────── Sessions ───────────

def save_session(
    agent_id: str,
    sub_line: Optional[str],
    instruction_id: str,
    instruction_name: str,
    user_prompt: str,
) -> str:
    session_id = f"s_{uuid.uuid4().hex[:10]}"
    with conn() as c:
        c.execute(
            "INSERT INTO sessions (id, agent_id, sub_line, instruction_id, instruction_name, user_prompt, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, agent_id, sub_line, instruction_id, instruction_name, user_prompt, _now()),
        )
    return session_id


def list_sessions(limit: int = 30) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT s.id, s.agent_id, s.sub_line, s.instruction_name, s.created_at, "
            "o.status, o.id AS output_id "
            "FROM sessions s "
            "LEFT JOIN outputs o ON o.session_id = s.id "
            "ORDER BY s.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────── Outputs ───────────

def save_output(session_id: str, content: str, tokens: int) -> str:
    output_id = f"o_{uuid.uuid4().hex[:10]}"
    with conn() as c:
        c.execute(
            "INSERT INTO outputs (id, session_id, content, status, tokens_approx, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (output_id, session_id, content, tokens, _now()),
        )
    return output_id


def approve_output(output_id: str, note: str = "") -> None:
    with conn() as c:
        c.execute(
            "UPDATE outputs SET status = 'approved', review_note = ?, reviewed_at = ? WHERE id = ?",
            (note, _now(), output_id),
        )


def reject_output(output_id: str, note: str = "") -> None:
    with conn() as c:
        c.execute(
            "UPDATE outputs SET status = 'rejected', review_note = ?, reviewed_at = ? WHERE id = ?",
            (note, _now(), output_id),
        )


def get_approved_outputs(agent_id: str, limit: int = 5) -> list[dict]:
    """拉取某 Agent 最近 approved 的产出，用于下游 Agent 的上下文。"""
    with conn() as c:
        rows = c.execute(
            "SELECT o.id, o.content, s.instruction_name, o.created_at "
            "FROM outputs o JOIN sessions s ON s.id = o.session_id "
            "WHERE s.agent_id = ? AND o.status = 'approved' "
            "ORDER BY o.created_at DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────── Feedback（A5 反哺）───────────

def save_feedback(source_output_id: str, target_agent_id: str, note: str) -> str:
    fid = f"f_{uuid.uuid4().hex[:10]}"
    with conn() as c:
        c.execute(
            "INSERT INTO feedback (id, source_output_id, target_agent_id, note, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (fid, source_output_id, target_agent_id, note, _now()),
        )
    return fid


def get_pending_feedback(target_agent_id: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT note, created_at FROM feedback "
            "WHERE target_agent_id = ? ORDER BY created_at DESC LIMIT 5",
            (target_agent_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────── Utils ───────────

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
