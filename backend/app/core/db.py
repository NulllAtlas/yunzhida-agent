"""
SQLite 轻量存储（D7）：用户账号 + 案件记录。

MVP 阶段用标准库 sqlite3，零额外依赖；后续可平滑替换为 PostgreSQL / Redis。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    """惰性建立连接（FastAPI 多线程环境下用 check_same_thread=False + 全局锁）。"""
    global _conn
    if _conn is None:
        path = Path(settings.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db() -> None:
    """建表（幂等，可重复调用）。"""
    conn = get_conn()
    with _lock:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'owner',
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cases (
                task_id          TEXT PRIMARY KEY,
                case_id          TEXT,
                status           TEXT NOT NULL,
                input_text       TEXT,
                accident_type    TEXT,
                responsibility   TEXT,
                split            TEXT,
                confidence       REAL,
                priority         INTEGER,
                result_json      TEXT,
                error            TEXT,
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cases_created ON cases(created_at DESC);
            """
        )
        conn.commit()


# ---------------- 用户 ----------------

def create_user(username: str, password_hash: str, role: str = "owner") -> dict[str, Any]:
    conn = get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, role, _now()),
        )
        conn.commit()
    return {"username": username, "role": role}


def get_user(username: str) -> Optional[dict[str, Any]]:
    row = get_conn().execute(
        "SELECT username, password_hash, role FROM users WHERE username = ?", (username,)
    ).fetchone()
    return dict(row) if row else None


# ---------------- 案件 ----------------

def upsert_case(
    *,
    task_id: str,
    case_id: str,
    status: str,
    input_text: str = "",
    result: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """写入/更新案件记录（完成时把关键结论抽成列，便于列表查询）。"""
    judgment = (result or {}).get("judgment") or {}
    response = (result or {}).get("response") or {}
    responsibility = (judgment.get("responsibility") or {})
    conn = get_conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO cases (
                task_id, case_id, status, input_text, accident_type,
                responsibility, split, confidence, priority,
                result_json, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status = excluded.status,
                accident_type = excluded.accident_type,
                responsibility = excluded.responsibility,
                split = excluded.split,
                confidence = excluded.confidence,
                priority = excluded.priority,
                result_json = excluded.result_json,
                error = excluded.error,
                updated_at = excluded.updated_at
            """,
            (
                task_id,
                case_id,
                status,
                input_text,
                response.get("accident_type"),
                responsibility.get("party_1"),
                responsibility.get("split"),
                judgment.get("confidence"),
                response.get("priority"),
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                error,
                _now(),
                _now(),
            ),
        )
        conn.commit()


def list_cases(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """交警端案件列表（不含完整 result，仅摘要）。"""
    rows = get_conn().execute(
        """
        SELECT task_id, case_id, status, input_text, accident_type,
               responsibility, split, confidence, priority, created_at, updated_at
        FROM cases ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def get_case(task_id: str) -> Optional[dict[str, Any]]:
    """单案件详情（含完整 result）。"""
    row = get_conn().execute("SELECT * FROM cases WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    raw = data.pop("result_json", None)
    data["result"] = json.loads(raw) if raw else None
    return data