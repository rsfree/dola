#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务存储（sqlite）—— 受理/查询/归属。

纪律（承 jimeng）：
- Key 只存 HMAC 指纹，明文永不落库；
- 「不存在」与「不属于你」合并为同一个 404（防枚举）；
- 只删终态任务。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id      TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,            -- image | video
    key_fp       TEXT NOT NULL,            -- API key HMAC 指纹
    status       TEXT NOT NULL,            -- queued|running|succeeded|failed
    prompt       TEXT NOT NULL,
    model        TEXT NOT NULL DEFAULT '',
    account      TEXT NOT NULL DEFAULT 'default',  -- 创建账号（轮询亲和：必须用同一账号读链）
    conv_id      TEXT NOT NULL DEFAULT '',  -- 上游会话 id
    upstream     TEXT NOT NULL DEFAULT '{}',-- 上游回执 JSON（产物/错误）
    error        TEXT NOT NULL DEFAULT '',
    created_at   REAL NOT NULL,
    finished_at  REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_key ON tasks(key_fp, created_at DESC);
"""


def key_fingerprint(api_key: str) -> str:
    """Key 的 HMAC 指纹。HMAC key 用服务启动时的固定盐（防彩虹表）。"""
    salt = b"dola-service-key-fp-v1"
    return "hmac:" + __import__("hmac").new(
        salt, api_key.encode(), hashlib.sha256).hexdigest()[:16]


class TaskStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)
            # 旧库迁移：account 列（幂等）
            cols = [r[1] for r in self._db.execute("PRAGMA table_info(tasks)")]
            if "account" not in cols:
                self._db.execute(
                    "ALTER TABLE tasks ADD COLUMN account TEXT NOT NULL DEFAULT 'default'")
            self._db.commit()

    def create(self, kind: str, key_fp: str, prompt: str, model: str = "",
               account: str = "default") -> str:
        task_id = uuid.uuid4().hex
        with self._lock:
            self._db.execute(
                "INSERT INTO tasks(task_id,kind,key_fp,status,prompt,model,account,"
                "created_at) VALUES(?,?,?,?,?,?,?,?)",
                (task_id, kind, key_fp, "queued", prompt, model, account,
                 time.time()))
            self._db.commit()
        return task_id

    def _get(self, task_id: str) -> sqlite3.Row | None:
        return self._db.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()

    def get(self, task_id: str) -> dict[str, Any] | None:
        """task_id 即凭据（UUID 不可猜）。"""
        row = self._get(task_id)
        if row is None:
            return None
        return dict(row)

    def list_owned(self, key_fp: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM tasks WHERE key_fp=? ORDER BY created_at DESC LIMIT ?",
            (key_fp, limit)).fetchall()
        return [dict(r) for r in rows]

    def update(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        sets, vals = [], []
        for k, v in fields.items():
            if k in ("upstream",) and not isinstance(v, str):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            vals.append(v)
        if "status" in fields and fields["status"] in ("succeeded", "failed"):
            sets.append("finished_at=?")
            vals.append(time.time())
        vals.append(task_id)
        with self._lock:
            self._db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE task_id=?",
                             vals)
            self._db.commit()

    def delete_finished(self, task_id: str) -> bool:
        row = self._get(task_id)
        if row is None:
            return False
        if row["status"] not in ("succeeded", "failed"):
            return False
        with self._lock:
            self._db.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            self._db.commit()
        return True

    def close(self) -> None:
        self._db.close()
