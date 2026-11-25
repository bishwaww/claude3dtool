from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import (
    DB_PATH,
    DEFAULT_BLENDERKIT_SOURCE,
    DEFAULT_BUDGET_USD,
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_RENDER_ENGINE,
    detect_blender_executable,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                target_folder TEXT NOT NULL,
                topic TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                storyboard_json TEXT DEFAULT '{}',
                meta_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                operation TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_creation_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


DEFAULT_SETTINGS: dict[str, Any] = {
    "anthropic_api_key": "",
    "claude_model": DEFAULT_CLAUDE_MODEL,
    "extended_thinking": True,
    "thinking_effort": "high",
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
    "elevenlabs_voice_name": "Adam (Default)",
    "blender_path": "",
    "blenderkit_source_path": DEFAULT_BLENDERKIT_SOURCE,
    "blenderkit_api_key": "",
    "huggingface_token": "",
    "render_engine": DEFAULT_RENDER_ENGINE,
    "cycles_samples": 64,
    "budget_limit_usd": DEFAULT_BUDGET_USD,
}


def get_settings() -> dict[str, Any]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        merged = dict(DEFAULT_SETTINGS)
        for row in rows:
            try:
                merged[row["key"]] = json.loads(row["value"])
            except Exception:
                merged[row["key"]] = row["value"]

        if not merged.get("blender_path"):
            detected = detect_blender_executable()
            if detected:
                merged["blender_path"] = detected

        retired_models = {
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
        }
        if merged.get("claude_model") in retired_models:
            merged["claude_model"] = DEFAULT_CLAUDE_MODEL

        return merged
    finally:
        conn.close()


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    conn = get_conn()
    try:
        current = get_settings()
        current.update(payload)
        for k, v in current.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )
        conn.commit()
        return current
    finally:
        conn.close()


def create_project(name: str, target_folder: str, topic: str = "") -> dict[str, Any]:
    pid = str(uuid.uuid4())[:12]
    now = _now_iso()
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO projects(id, name, target_folder, topic, status, storyboard_json, meta_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pid, name, target_folder, topic, "draft", "{}", "{}", now, now),
        )
        conn.commit()
        return get_project(pid)  # type: ignore
    finally:
        conn.close()


def list_projects() -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        return [_row_to_project(r) for r in rows]
    finally:
        conn.close()


def get_project(project_id: str) -> Optional[dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return _row_to_project(row) if row else None
    finally:
        conn.close()


def update_project(
    project_id: str,
    *,
    name: Optional[str] = None,
    target_folder: Optional[str] = None,
    topic: Optional[str] = None,
    status: Optional[str] = None,
    storyboard: Optional[dict[str, Any]] = None,
    meta: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    existing = get_project(project_id)
    if not existing:
        return None
    now = _now_iso()
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE projects
            SET name = ?, target_folder = ?, topic = ?, status = ?, storyboard_json = ?, meta_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name if name is not None else existing["name"],
                target_folder if target_folder is not None else existing["target_folder"],
                topic if topic is not None else existing["topic"],
                status if status is not None else existing["status"],
                json.dumps(storyboard if storyboard is not None else existing["storyboard"]),
                json.dumps(meta if meta is not None else existing["meta"]),
                now,
                project_id,
            ),
        )
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()


def delete_project(project_id: str) -> bool:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def add_message(
    project_id: str, role: str, content: str, metadata: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    now = _now_iso()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO messages(project_id, role, content, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, role, content, json.dumps(metadata or {}), now),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        conn.commit()
        return {
            "id": cur.lastrowid,
            "project_id": project_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "created_at": now,
        }
    finally:
        conn.close()


def get_messages(project_id: str) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "project_id": r["project_id"],
                "role": r["role"],
                "content": r["content"],
                "metadata": json.loads(r["metadata_json"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def log_token_usage(
    *,
    project_id: Optional[str],
    operation: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    cost_usd: float,
) -> dict[str, Any]:
    now = _now_iso()
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO token_usage(
                project_id, operation, model,
                input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                cost_usd, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                operation,
                model,
                input_tokens,
                output_tokens,
                cache_creation_tokens,
                cache_read_tokens,
                round(cost_usd, 6),
                now,
            ),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "project_id": project_id,
            "operation": operation,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cost_usd": round(cost_usd, 6),
            "created_at": now,
        }
    finally:
        conn.close()


def get_token_usage_summary(project_id: Optional[str] = None) -> dict[str, Any]:
    conn = get_conn()
    try:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM token_usage WHERE project_id = ? ORDER BY id DESC LIMIT 100",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM token_usage ORDER BY id DESC LIMIT 200"
            ).fetchall()

        total_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens,
                COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                COALESCE(SUM(cost_usd), 0.0) AS cost_usd
            FROM token_usage
            """
        ).fetchone()

        proj_row = None
        if project_id:
            proj_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens,
                    COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
                    COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                FROM token_usage WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()

        entries = [dict(r) for r in rows]
        settings = get_settings()
        budget_limit = float(settings.get("budget_limit_usd", DEFAULT_BUDGET_USD))

        return {
            "budget_limit_usd": budget_limit,
            "global_totals": dict(total_row) if total_row else {},
            "project_totals": dict(proj_row) if proj_row else {},
            "entries": entries,
        }
    finally:
        conn.close()


def _row_to_project(row: sqlite3.Row) -> dict[str, Any]:
    target = row["target_folder"]
    target_path = Path(target) if target else None
    has_blend = bool(target_path and (target_path / "project.blend").is_file())
    has_audio = bool(target_path and (target_path / "audio" / "narration.mp3").is_file())
    has_final = bool(target_path and (target_path / "final_short.mp4").is_file())
    return {
        "id": row["id"],
        "name": row["name"],
        "target_folder": target,
        "topic": row["topic"],
        "status": row["status"],
        "storyboard": json.loads(row["storyboard_json"] or "{}"),
        "meta": json.loads(row["meta_json"] or "{}"),
        "has_blend": has_blend,
        "has_audio": has_audio,
        "has_final": has_final,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
