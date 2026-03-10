"""
Persistent Memory Store — SQLite database for agent memory, papers, plans, hypotheses.
Stored in ./research_data/memory.db
"""

import os
import json
import sqlite3
import asyncio
from datetime import datetime
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "research_data")
DB_PATH = os.path.join(DB_DIR, "memory.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            memory_value TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            arxiv_id TEXT NOT NULL,
            title TEXT NOT NULL,
            authors TEXT DEFAULT '',
            abstract TEXT DEFAULT '',
            published TEXT DEFAULT '',
            url TEXT DEFAULT '',
            pdf_url TEXT DEFAULT '',
            summary_json TEXT DEFAULT '{}',
            read_status TEXT DEFAULT 'fetched',
            cumulative_insights TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            plan_index INTEGER NOT NULL,
            plan_json TEXT NOT NULL,
            selected INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS hypotheses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            hypo_index INTEGER NOT NULL,
            hypo_json TEXT NOT NULL,
            selected INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS research_context (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            context_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_session ON agent_memory(session_id, agent_name);
        CREATE INDEX IF NOT EXISTS idx_papers_session ON papers(session_id);
        CREATE INDEX IF NOT EXISTS idx_plans_session ON plans(session_id);
        CREATE INDEX IF NOT EXISTS idx_hypo_session ON hypotheses(session_id);
    """)
    conn.commit()
    conn.close()


# ── Session ───────────────────────────────────────────────────

def create_session(session_id: str, topic: str):
    conn = _get_conn()
    conn.execute("INSERT OR REPLACE INTO sessions (id, topic, updated_at) VALUES (?, ?, datetime('now'))",
                 (session_id, topic))
    conn.commit()
    conn.close()


# ── Agent Memory ──────────────────────────────────────────────

def save_memory(session_id: str, agent_name: str, key: str, value: str):
    conn = _get_conn()
    # Upsert: delete old then insert
    conn.execute("DELETE FROM agent_memory WHERE session_id=? AND agent_name=? AND memory_key=?",
                 (session_id, agent_name, key))
    conn.execute("INSERT INTO agent_memory (session_id, agent_name, memory_key, memory_value) VALUES (?,?,?,?)",
                 (session_id, agent_name, key, value))
    conn.commit()
    conn.close()


def get_memory(session_id: str, agent_name: str, key: str) -> Optional[str]:
    conn = _get_conn()
    row = conn.execute("SELECT memory_value FROM agent_memory WHERE session_id=? AND agent_name=? AND memory_key=?",
                       (session_id, agent_name, key)).fetchone()
    conn.close()
    return row["memory_value"] if row else None


def get_all_memory(session_id: str, agent_name: str) -> dict:
    conn = _get_conn()
    rows = conn.execute("SELECT memory_key, memory_value FROM agent_memory WHERE session_id=? AND agent_name=?",
                        (session_id, agent_name)).fetchall()
    conn.close()
    return {r["memory_key"]: r["memory_value"] for r in rows}


# ── Papers ────────────────────────────────────────────────────

def save_paper(session_id: str, arxiv_id: str, title: str, authors: str,
               abstract: str, published: str, url: str, pdf_url: str):
    conn = _get_conn()
    conn.execute("""INSERT OR REPLACE INTO papers
        (session_id, arxiv_id, title, authors, abstract, published, url, pdf_url)
        VALUES (?,?,?,?,?,?,?,?)""",
        (session_id, arxiv_id, title, authors, abstract, published, url, pdf_url))
    conn.commit()
    conn.close()


def update_paper_summary(session_id: str, arxiv_id: str, summary_json: str,
                         cumulative_insights: str = ""):
    conn = _get_conn()
    conn.execute("""UPDATE papers SET summary_json=?, read_status='read', cumulative_insights=?
        WHERE session_id=? AND arxiv_id=?""",
        (summary_json, cumulative_insights, session_id, arxiv_id))
    conn.commit()
    conn.close()


def get_papers(session_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM papers WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Plans ─────────────────────────────────────────────────────

def save_plans(session_id: str, plans: list[dict]):
    conn = _get_conn()
    conn.execute("DELETE FROM plans WHERE session_id=?", (session_id,))
    for i, plan in enumerate(plans):
        conn.execute("INSERT INTO plans (session_id, plan_index, plan_json) VALUES (?,?,?)",
                     (session_id, i, json.dumps(plan)))
    conn.commit()
    conn.close()


def select_plan(session_id: str, plan_index: int):
    conn = _get_conn()
    conn.execute("UPDATE plans SET selected=0 WHERE session_id=?", (session_id,))
    conn.execute("UPDATE plans SET selected=1 WHERE session_id=? AND plan_index=?",
                 (session_id, plan_index))
    conn.commit()
    conn.close()


def get_selected_plan(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT plan_json FROM plans WHERE session_id=? AND selected=1",
                       (session_id,)).fetchone()
    conn.close()
    return json.loads(row["plan_json"]) if row else None


# ── Hypotheses ────────────────────────────────────────────────

def save_hypotheses(session_id: str, hypotheses: list[dict]):
    conn = _get_conn()
    conn.execute("DELETE FROM hypotheses WHERE session_id=?", (session_id,))
    for i, hypo in enumerate(hypotheses):
        conn.execute("INSERT INTO hypotheses (session_id, hypo_index, hypo_json) VALUES (?,?,?)",
                     (session_id, i, json.dumps(hypo)))
    conn.commit()
    conn.close()


def select_hypothesis(session_id: str, hypo_index: int):
    conn = _get_conn()
    conn.execute("UPDATE hypotheses SET selected=0 WHERE session_id=?", (session_id,))
    conn.execute("UPDATE hypotheses SET selected=1 WHERE session_id=? AND hypo_index=?",
                 (session_id, hypo_index))
    conn.commit()
    conn.close()


def get_selected_hypothesis(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT hypo_json FROM hypotheses WHERE session_id=? AND selected=1",
                       (session_id,)).fetchone()
    conn.close()
    return json.loads(row["hypo_json"]) if row else None


# ── Research Context ──────────────────────────────────────────

def save_context(session_id: str, context_type: str, content: str):
    conn = _get_conn()
    conn.execute("INSERT INTO research_context (session_id, context_type, content) VALUES (?,?,?)",
                 (session_id, context_type, content))
    conn.commit()
    conn.close()


def get_context(session_id: str, context_type: str = None) -> list[str]:
    conn = _get_conn()
    if context_type:
        rows = conn.execute("SELECT content FROM research_context WHERE session_id=? AND context_type=? ORDER BY id",
                            (session_id, context_type)).fetchall()
    else:
        rows = conn.execute("SELECT content FROM research_context WHERE session_id=? ORDER BY id",
                            (session_id,)).fetchall()
    conn.close()
    return [r["content"] for r in rows]


def get_full_session_context(session_id: str) -> str:
    """Get all accumulated context for a session (for RAG)."""
    conn = _get_conn()
    parts = []

    # Agent memories
    rows = conn.execute("SELECT agent_name, memory_key, memory_value FROM agent_memory WHERE session_id=?",
                        (session_id,)).fetchall()
    for r in rows:
        parts.append(f"[{r['agent_name']}:{r['memory_key']}] {r['memory_value']}")

    # Paper insights
    rows = conn.execute("SELECT title, cumulative_insights FROM papers WHERE session_id=? AND read_status='read'",
                        (session_id,)).fetchall()
    for r in rows:
        if r["cumulative_insights"]:
            parts.append(f"[Paper: {r['title']}] {r['cumulative_insights']}")

    # Research context
    rows = conn.execute("SELECT context_type, content FROM research_context WHERE session_id=?",
                        (session_id,)).fetchall()
    for r in rows:
        parts.append(f"[{r['context_type']}] {r['content']}")

    conn.close()
    return "\n\n".join(parts[-30:])  # Keep last 30 entries to avoid token overflow


# Init on import
init_db()
