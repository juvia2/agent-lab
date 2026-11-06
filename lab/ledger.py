"""실험 대장(SQLite). 연구실의 영속 상태는 모두 여기와 experiments/ 폴더에 있다."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

STATUSES = ("queued", "planning", "awaiting_approval", "running", "analyzing",
            "done", "failed", "stopped", "paused")
ACTIVE = ("planning", "running", "analyzing")
PHASE_STATUS = {"consult": "planning", "plan": "planning", "build": "running", "execute": "running",
                "analyze": "analyzing", "interpret": "analyzing", "report": "analyzing"}
PHASES = ["consult", "plan", "build", "execute", "analyze", "interpret", "report"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  phase TEXT NOT NULL DEFAULT 'consult',
  priority INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  thread_id INTEGER,
  channel_id INTEGER,
  requester_id INTEGER,
  request_md TEXT NOT NULL,
  plan_json TEXT,
  approved INTEGER NOT NULL DEFAULT 0,
  approval_reasons TEXT,
  tokens_used INTEGER NOT NULL DEFAULT 0,
  token_budget INTEGER NOT NULL,
  error TEXT,
  summary TEXT,
  meta_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exp_id TEXT NOT NULL,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_exp ON events(exp_id, id);
"""


class Ledger:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # ---- 생성/조회 ----
    def create_experiment(self, *, title: str, request_md: str, priority: int = 0,
                          thread_id: int | None = None, channel_id: int | None = None,
                          requester_id: int | None = None, token_budget: int,
                          meta: dict | None = None) -> str:
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM experiments ORDER BY CAST(SUBSTR(id, 5) AS INTEGER) DESC LIMIT 1").fetchone()
            n = int(row["id"][4:]) + 1 if row else 1
            exp_id = f"EXP-{n:03d}"
            now = time.time()
            self._db.execute(
                "INSERT INTO experiments (id,title,status,phase,priority,created_at,updated_at,thread_id,"
                "channel_id,requester_id,request_md,token_budget,meta_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (exp_id, title, "queued", "consult", priority, now, now, thread_id, channel_id,
                 requester_id, request_md, token_budget, json.dumps(meta or {}, ensure_ascii=False)))
            self._db.commit()
        self.add_event(exp_id, "submitted", f"접수: {title}")
        return exp_id

    def get(self, exp_id: str) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM experiments WHERE id=?", (exp_id.upper(),)).fetchone()
        return dict(r) if r else None

    def list(self, status: str | None = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM experiments"
        args: tuple = ()
        if status:
            q += " WHERE status=?"
            args = (status,)
        q += " ORDER BY CAST(SUBSTR(id, 5) AS INTEGER) DESC LIMIT ?"
        with self._lock:
            rows = self._db.execute(q, args + (limit,)).fetchall()
        return [dict(r) for r in rows]

    def find_by_thread(self, thread_id: int) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM experiments WHERE thread_id=? ORDER BY created_at DESC LIMIT 1",
                                 (thread_id,)).fetchone()
        return dict(r) if r else None

    # ---- 갱신 ----
    def update(self, exp_id: str, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock:
            self._db.execute(f"UPDATE experiments SET {cols} WHERE id=?", (*fields.values(), exp_id))
            self._db.commit()

    def add_tokens(self, exp_id: str, n: int) -> int:
        with self._lock:
            self._db.execute("UPDATE experiments SET tokens_used=tokens_used+?, updated_at=? WHERE id=?",
                             (n, time.time(), exp_id))
            self._db.commit()
            r = self._db.execute("SELECT tokens_used FROM experiments WHERE id=?", (exp_id,)).fetchone()
        return int(r["tokens_used"])

    def add_event(self, exp_id: str, kind: str, message: str) -> None:
        with self._lock:
            self._db.execute("INSERT INTO events (exp_id, ts, kind, message) VALUES (?,?,?,?)",
                             (exp_id, time.time(), kind, message[:4000]))
            self._db.commit()

    def events(self, exp_id: str, limit: int = 15) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM events WHERE exp_id=? ORDER BY id DESC LIMIT ?",
                                    (exp_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---- 대기열 ----
    def claim_next(self) -> dict | None:
        """대기 중인 실험 하나를 원자적으로 가져와 진행 상태로 바꾼다."""
        with self._lock:
            r = self._db.execute(
                "SELECT * FROM experiments WHERE status='queued' ORDER BY priority DESC, created_at ASC LIMIT 1"
            ).fetchone()
            if not r:
                return None
            exp = dict(r)
            status = PHASE_STATUS.get(exp["phase"], "running")
            self._db.execute("UPDATE experiments SET status=?, updated_at=? WHERE id=?",
                             (status, time.time(), exp["id"]))
            self._db.commit()
            exp["status"] = status
            return exp

    def reset_interrupted(self) -> list[str]:
        """재시작 시, 진행 중이던 실험을 대기열로 되돌린다(phase 는 유지)."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT id FROM experiments WHERE status IN ({','.join('?' * len(ACTIVE))})", ACTIVE).fetchall()
            ids = [r["id"] for r in rows]
            for i in ids:
                self._db.execute("UPDATE experiments SET status='queued', updated_at=? WHERE id=?",
                                 (time.time(), i))
            self._db.commit()
        for i in ids:
            self.add_event(i, "recovered", "연구실 재시작으로 중단되어 대기열로 복구됨")
        return ids
