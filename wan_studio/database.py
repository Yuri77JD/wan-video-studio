from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from .config import DB_PATH


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_task_id TEXT,
                mode TEXT NOT NULL,
                prompt TEXT NOT NULL,
                config_json TEXT NOT NULL,
                media_json TEXT NOT NULL,
                request_json TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT DEFAULT '',
                output_path TEXT DEFAULT '',
                output_url TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def create_task(mode: str, prompt: str, config: dict[str, Any], media: list[dict[str, Any]], request: dict[str, Any], status: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks(remote_task_id,mode,prompt,config_json,media_json,request_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            ("", mode, prompt, json.dumps(config, ensure_ascii=False), json.dumps(media, ensure_ascii=False), json.dumps(request, ensure_ascii=False), status, now, now),
        )
        return int(cur.lastrowid)


def update_task(local_id: int, **fields: Any) -> None:
    allowed = {"remote_task_id", "status", "message", "output_path", "output_url", "request_json"}
    values = {k: v for k, v in fields.items() if k in allowed}
    values["updated_at"] = datetime.now().isoformat(timespec="seconds")
    assignments = ",".join(f"{k}=?" for k in values)
    with connect() as conn:
        conn.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*values.values(), local_id))


def get_task(local_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (local_id,)).fetchone()
    return dict(row) if row else None


def list_tasks(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def pending_tasks() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM tasks WHERE status IN ('PENDING','RUNNING') ORDER BY id").fetchall()
    return [dict(row) for row in rows]

