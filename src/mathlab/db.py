from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Blackboard:
    """Durable source of truth for research state.

    SQLite is intentionally boring: it survives crashes, is easy to inspect, and lets the
    TUI and orchestrator share state without a separate service.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    actor TEXT,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agents (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    island TEXT NOT NULL,
                    task_id TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    updated_at TEXT,
                    last_note TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    action TEXT NOT NULL,
                    island TEXT NOT NULL,
                    priority REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL,
                    parent_id TEXT,
                    created_by TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    island TEXT NOT NULL,
                    created_by TEXT,
                    evidence TEXT NOT NULL DEFAULT '[]',
                    dependencies TEXT NOT NULL DEFAULT '[]',
                    artifact_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    target TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    thread_id TEXT,
                    read_by TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feature_requests (
                    id TEXT PRIMARY KEY,
                    requester TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    acceptance_test TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolution TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    agent_id TEXT,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    cached_input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority DESC);
                CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
                CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);
                """
            )

    def event(self, kind: str, actor: str | None, payload: dict[str, Any] | str) -> int:
        data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO events(ts,kind,actor,payload) VALUES(?,?,?,?)",
                (utcnow(), kind, actor, data),
            )
            return int(cur.lastrowid)

    def recent_events(self, after_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE id>? ORDER BY id ASC LIMIT ?", (after_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_agent(self, agent_id: str, role: str, island: str, task_id: str | None, status: str, note: str = "") -> None:
        now = utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO agents(id,role,island,task_id,status,started_at,updated_at,last_note)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET role=excluded.role,island=excluded.island,
                task_id=excluded.task_id,status=excluded.status,updated_at=excluded.updated_at,
                last_note=CASE WHEN excluded.last_note='' THEN agents.last_note ELSE excluded.last_note END""",
                (agent_id, role, island, task_id, status, now, now, note),
            )

    def update_agent_note(self, agent_id: str, note: str, status: str = "RUNNING") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE agents SET last_note=?,status=?,updated_at=? WHERE id=?",
                (note, status, utcnow(), agent_id),
            )

    def agents(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM agents ORDER BY updated_at DESC").fetchall()]

    def create_task(self, task_id: str, title: str, description: str, action: str = "EXPLORE", island: str = "general", priority: float = 0.5, created_by: str = "system", parent_id: str | None = None) -> None:
        now = utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, title, description, action, island, float(priority), "OPEN", parent_id, created_by, now, now, ),
            )
        self.event("task.created", created_by, {"id": task_id, "title": title, "action": action, "island": island, "priority": priority})

    def update_task(self, task_id: str, status: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, utcnow(), task_id))
        self.event("task.status", "system", {"id": task_id, "status": status})

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def open_tasks(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE status='OPEN' ORDER BY priority DESC, created_at ASC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def create_claim(self, claim_id: str, kind: str, statement: str, status: str, confidence: float, island: str, created_by: str, evidence: list[Any] | None = None, dependencies: list[str] | None = None, artifact_path: str | None = None) -> None:
        now = utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO claims(id,kind,statement,status,confidence,island,created_by,evidence,dependencies,artifact_path,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,statement=excluded.statement,
                status=excluded.status,confidence=excluded.confidence,evidence=excluded.evidence,
                dependencies=excluded.dependencies,artifact_path=excluded.artifact_path,updated_at=excluded.updated_at""",
                (claim_id, kind, statement, status, float(confidence), island, created_by,
                 json.dumps(evidence or [], ensure_ascii=False), json.dumps(dependencies or []), artifact_path, now, now),
            )
        self.event("claim.published", created_by, {"id": claim_id, "kind": kind, "status": status, "confidence": confidence, "statement": statement})

    def update_claim_status(self, claim_id: str, status: str, confidence: float | None = None) -> None:
        with self._lock, self._conn:
            if confidence is None:
                self._conn.execute("UPDATE claims SET status=?,updated_at=? WHERE id=?", (status, utcnow(), claim_id))
            else:
                self._conn.execute("UPDATE claims SET status=?,confidence=?,updated_at=? WHERE id=?", (status, float(confidence), utcnow(), claim_id))
        self.event("claim.status", "system", {"id": claim_id, "status": status, "confidence": confidence})

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        return dict(row) if row else None

    def claims(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM claims ORDER BY confidence DESC, updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search_claims(self, query: str, limit: int = 30) -> list[dict[str, Any]]:
        q = f"%{query}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM claims WHERE statement LIKE ? OR kind LIKE ? ORDER BY confidence DESC, updated_at DESC LIMIT ?",
                (q, q, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def claims_needing_review(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT c.* FROM claims c
                WHERE c.status='PROVISIONAL_PROOF'
                AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.action='REVIEW' AND t.description LIKE '%' || c.id || '%' AND t.status IN ('OPEN','RUNNING'))
                ORDER BY c.confidence DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def send_message(self, msg_id: str, sender: str, target: str, subject: str, body: str, thread_id: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?)",
                (msg_id, sender, target, subject, body, thread_id, "[]", utcnow()),
            )
        self.event("message.sent", sender, {"id": msg_id, "target": target, "subject": subject, "body": body[:400]})

    def unread_messages(self, agent_id: str, island: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM messages ORDER BY created_at ASC").fetchall()
        out = []
        for row in rows:
            d = dict(row)
            read_by = json.loads(d["read_by"] or "[]")
            targets = {agent_id, "all"}
            if island:
                targets.add(f"island:{island}")
            if d["target"] in targets and agent_id not in read_by:
                out.append(d)
        return out

    def mark_messages_read(self, agent_id: str, message_ids: Iterable[str]) -> None:
        with self._lock, self._conn:
            for mid in message_ids:
                row = self._conn.execute("SELECT read_by FROM messages WHERE id=?", (mid,)).fetchone()
                if not row:
                    continue
                readers = set(json.loads(row[0] or "[]"))
                readers.add(agent_id)
                self._conn.execute("UPDATE messages SET read_by=? WHERE id=?", (json.dumps(sorted(readers)), mid))

    def create_feature_request(self, req_id: str, requester: str, title: str, description: str, acceptance_test: str) -> None:
        now = utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO feature_requests VALUES(?,?,?,?,?,?,?,?,?)",
                (req_id, requester, title, description, acceptance_test, "OPEN", "", now, now),
            )
        self.event("feature.requested", requester, {"id": req_id, "title": title, "description": description})

    def feature_requests(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if status:
                rows = self._conn.execute("SELECT * FROM feature_requests WHERE status=? ORDER BY created_at", (status,)).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM feature_requests ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def resolve_feature(self, req_id: str, status: str, resolution: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE feature_requests SET status=?,resolution=?,updated_at=? WHERE id=?",
                (status, resolution, utcnow(), req_id),
            )
        self.event("feature.status", "RA", {"id": req_id, "status": status, "resolution": resolution})

    def record_usage(self, agent_id: str, model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int, estimated_cost_usd: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO usage(ts,agent_id,model,input_tokens,cached_input_tokens,output_tokens,estimated_cost_usd) VALUES(?,?,?,?,?,?,?)",
                (utcnow(), agent_id, model, input_tokens, cached_input_tokens, output_tokens, estimated_cost_usd),
            )

    def total_cost(self) -> float:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(SUM(estimated_cost_usd),0) FROM usage").fetchone()
        return float(row[0])

    def count(self, table: str) -> int:
        if table not in {"events", "agents", "tasks", "claims", "messages", "feature_requests", "usage"}:
            raise ValueError(table)
        with self._lock:
            return int(self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
