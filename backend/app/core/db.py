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
                filename         TEXT,
                photos           TEXT,
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

            CREATE TABLE IF NOT EXISTS llm_models (
                model      TEXT PRIMARY KEY,
                base_url   TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(username, id DESC);
            """
        )
        # 已有开发库的补列（CREATE TABLE IF NOT EXISTS 不会改老表结构）
        _ensure_column(conn, "cases", "filename", "filename TEXT")
        _ensure_column(conn, "cases", "photos", "photos TEXT")
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """缺列才补。SQLite 没有 ADD COLUMN IF NOT EXISTS，只能先查 pragma。"""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


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


# ---------------- 问询记录 ----------------

def save_chat_message(username: str, role: str, content: str) -> None:
    """保存一条问询记录（记录跟账号走，未登录不记录）。"""
    if not username:
        return
    conn = get_conn()
    with _lock:
        conn.execute(
            "INSERT INTO chat_history (username, role, content, created_at) VALUES (?, ?, ?, ?)",
            (username, role, content, _now()),
        )
        conn.commit()


def load_chat_history(username: str, limit: int = 50) -> list[dict[str, Any]]:
    """某账号的问询记录（最近 limit 条，按时间正序返回，可直接喂给 chatbot）。"""
    if not username:
        return []
    rows = get_conn().execute(
        """
        SELECT role, content FROM (
            SELECT id, role, content FROM chat_history
            WHERE username = ? ORDER BY id DESC LIMIT ?
        ) ORDER BY id ASC
        """,
        (username, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# ---------------- 模型列表 ----------------

def list_models() -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT model, base_url, created_at FROM llm_models ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def add_model(model: str, base_url: str = "") -> bool:
    """添加模型（重复返回 False）。"""
    conn = get_conn()
    with _lock:
        cur = conn.execute(
            "INSERT OR IGNORE INTO llm_models (model, base_url, created_at) VALUES (?, ?, ?)",
            (model, base_url, _now()),
        )
        conn.commit()
        return cur.rowcount > 0


# ---------------- 案件 ----------------

def upsert_case(
    *,
    task_id: str,
    case_id: str,
    status: str,
    input_text: str = "",
    filename: str = "",
    photos: Optional[list[str]] = None,
    result: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """写入/更新案件记录（完成时把关键结论抽成列，便于列表查询）。"""
    judgment = (result or {}).get("judgment") or {}
    response = (result or {}).get("response") or {}
    responsibility = (judgment.get("responsibility") or {})
    photos_json = json.dumps(photos or [], ensure_ascii=False)
    conn = get_conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO cases (
                task_id, case_id, status, input_text, filename, photos, accident_type,
                responsibility, split, confidence, priority,
                result_json, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status = excluded.status,
                -- 结束时的这次落库不该把创建时记下的文件名/照片冲掉
                filename = CASE WHEN excluded.filename != '' THEN excluded.filename ELSE cases.filename END,
                photos = CASE WHEN excluded.photos != '[]' THEN excluded.photos ELSE cases.photos END,
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
                filename,
                photos_json,
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


def _loads_list(raw: Any) -> list[Any]:
    """解析存成 JSON 文本的列表列（photos）；坏数据当空列表，不让列表接口整个 500。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def list_records(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """车主端「研判记录」：按提交时间倒序，含完整 result，一次拉全。

    和 list_cases 的区别是带 result_json：车主端要直接渲染历史结论，
    逐条再查一次详情就是 N+1 了。
    """
    rows = get_conn().execute(
        """
        SELECT task_id, case_id, status, input_text, filename, photos, accident_type,
               responsibility, split, confidence, priority, result_json, error,
               created_at, updated_at
        FROM cases ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        raw = data.pop("result_json", None)
        data["result"] = json.loads(raw) if raw else None
        data["photos"] = _loads_list(data.get("photos"))
        out.append(data)
    return out


def get_case(task_id: str) -> Optional[dict[str, Any]]:
    """单案件详情（含完整 result）。"""
    row = get_conn().execute("SELECT * FROM cases WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    raw = data.pop("result_json", None)
    data["result"] = json.loads(raw) if raw else None
    data["photos"] = _loads_list(data.get("photos"))
    return data