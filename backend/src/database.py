"""
SQLite database — tickets and unresolved_queries tables.
Sprint 15 added handoff_messages (a persisted conversation transcript
for escalated tickets — see backend/src/agent/handoff.py) and gave
tickets a real status lifecycle (update_ticket_status) instead of
staying 'open' forever.
Sprint 16 added satisfaction_ratings (session-level CSAT, 1-5 + an
optional reason on low scores) — this is also the "低品質評分" raw
material the planned knowledge improvement pipeline clusters on.
Sprint 17 added kb_entries: supplementary knowledge added through the
maintenance UI (and later the knowledge improvement pipeline), indexed into
FAISS alongside the curated data/knowledge_base markdown files. Kept as
a DB table (not markdown edits) so each entry carries source/status/
timestamps and archiving gives a rollback path.
Sprint 18 added kb_gap_drafts: AI-generated FAQ drafts produced by the
knowledge improvement pipeline (cluster unresolved/negative/handoff signals ->
draft -> agent review). Approving a draft writes a kb_entry (source=
'pipeline') and links it back here for before/after effectiveness.
Sprint 19 added chat_sessions: server-side conversation state (messages,
workflow, user_id, handoff status), keyed by session_id and saved after
every /chat turn — so a browser refresh (which drops Streamlit's own
st.session_state and used to lose everything) can restore instead of
starting over. See frontend/app.py's init_session() for the other half.
Sprint 19 also added llm_calls: cost/latency for every Claude API call,
tagged by session/turn/node — see backend/src/tracing.py, which is the
only writer.
"""

import json
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

# BANKING_DB_PATH lets tests point at an isolated test.db instead of the
# real demo banking.db (see tests/conftest.py). Must be set before this
# module is first imported — it's read once at import time.
DB_PATH = Path(os.getenv("BANKING_DB_PATH", str(Path(__file__).parent.parent.parent / "data" / "banking.db")))


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS tickets (
            id          TEXT PRIMARY KEY,
            created_at  TEXT NOT NULL,
            user_id     TEXT,
            type        TEXT NOT NULL,
            description TEXT,
            card_id     TEXT,
            status      TEXT DEFAULT 'open',
            priority    TEXT DEFAULT 'normal'
        );

        CREATE TABLE IF NOT EXISTS unresolved_queries (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at     TEXT NOT NULL,
            session_id     TEXT,
            user_query     TEXT NOT NULL,
            language       TEXT,
            intent         TEXT,
            trigger_reason TEXT NOT NULL,
            similarity_score REAL
        );

        CREATE TABLE IF NOT EXISTS handoff_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id   TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            role        TEXT NOT NULL,  -- 'user' | 'assistant' | 'agent'
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS satisfaction_ratings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            user_id     TEXT,
            score       INTEGER NOT NULL,  -- 1..5
            comment     TEXT,              -- optional; prompted on low scores
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kb_entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            language    TEXT NOT NULL,          -- 'zh' | 'en'
            title       TEXT NOT NULL,          -- the question / topic
            content     TEXT NOT NULL,          -- the answer
            tags        TEXT,                   -- comma-separated, optional
            status      TEXT DEFAULT 'active',  -- 'active' | 'archived' (archive = soft delete / rollback)
            source      TEXT DEFAULT 'manual',  -- 'manual' (UI) | 'pipeline' (knowledge improvement flow)
            created_at  TEXT NOT NULL,
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS kb_gap_drafts (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            language             TEXT NOT NULL,
            topic                TEXT NOT NULL,          -- cluster label
            question             TEXT NOT NULL,          -- generated FAQ question
            answer               TEXT NOT NULL,          -- generated FAQ answer
            tags                 TEXT,
            representative_query TEXT NOT NULL,          -- used for retrieval before/after + recurrence
            signal_summary       TEXT,                   -- human-readable "why this is a gap"
            signal_count         INTEGER DEFAULT 0,      -- how many gap signals formed this topic
            status               TEXT DEFAULT 'pending', -- 'pending' | 'approved' | 'skipped'
            pre_score            REAL,                   -- top retrieval score at analysis (the "before")
            kb_entry_id          INTEGER,                -- set on approval (links to the created kb_entry)
            created_at           TEXT NOT NULL,
            updated_at           TEXT
        );

        CREATE TABLE IF NOT EXISTS llm_calls (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    TEXT,
            turn_id       TEXT,
            node          TEXT NOT NULL,  -- call site: classify_intent | qa_answer_blocking |
                                           -- qa_answer_stream | verifier | account_tool_loop |
                                           -- gap_cluster | gap_draft
            model         TEXT NOT NULL,
            input_tokens  INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd      REAL NOT NULL,
            latency_ms    REAL NOT NULL,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id        TEXT PRIMARY KEY,
            user_id           TEXT,
            language          TEXT DEFAULT 'zh',
            messages          TEXT DEFAULT '[]',  -- JSON list of {role, content}
            workflow_step     INTEGER DEFAULT 0,
            workflow_data     TEXT DEFAULT '{}',  -- JSON
            handoff_active    INTEGER DEFAULT 0,
            handoff_ticket_id TEXT,
            updated_at        TEXT NOT NULL
        );
    """)
    c.commit()
    c.close()


def create_ticket(
    type: str,
    user_id: str = None,
    card_id: str = None,
    description: str = "",
    priority: str = "normal",
) -> dict:
    today = datetime.now().strftime("%Y%m%d")
    c = _conn()
    count = c.execute(
        "SELECT COUNT(*) FROM tickets WHERE id LIKE ?", (f"T-{today}-%",)
    ).fetchone()[0]
    # The random suffix is load-bearing, not cosmetic: GET/POST
    # /handoff/{ticket_id}/messages authorize the CUSTOMER side by
    # possession of this id alone (a guest must be able to follow up
    # without logging in — see backend/main.py's post_handoff_message).
    # Without it the id is a sequential "T-YYYYMMDD-NNN" that anyone can
    # enumerate, which makes possession worthless as an authorization
    # signal. The date+counter prefix is kept so tickets stay
    # human-sortable and the LIKE counter above still works.
    #
    # This deliberately merges identifier and secret, which is normally a
    # smell — the cleaner design is a short display id plus a separate
    # per-ticket access token, so the number a customer reads out over
    # the phone isn't the thing that grants access. Not worth the schema
    # + frontend churn at this scale; revisit if tickets ever get a
    # customer-facing lookup screen.
    ticket_id = f"T-{today}-{count + 1:03d}-{secrets.token_hex(4)}"
    created_at = datetime.now().isoformat()

    c.execute(
        "INSERT INTO tickets VALUES (?,?,?,?,?,?,'open',?)",
        (ticket_id, created_at, user_id, type, description, card_id, priority),
    )
    c.commit()
    c.close()

    return {"ticket_id": ticket_id, "created_at": created_at, "status": "open"}


def get_tickets(user_id: str = None, type: str = None, status: str = None, limit: int = 20) -> list[dict]:
    clauses, params = [], []
    if user_id:
        clauses.append("user_id=?")
        params.append(user_id)
    if type:
        clauses.append("type=?")
        params.append(type)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    c = _conn()
    rows = c.execute(
        f"SELECT * FROM tickets {where} ORDER BY created_at DESC LIMIT ?", (*params, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_ticket(ticket_id: str) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def get_ticket_session_id(ticket_id: str) -> str | None:
    """The chat session a ticket was escalated from — recorded on the thread's
    first message (see agent/handoff.py), not on the ticket row itself."""
    c = _conn()
    row = c.execute(
        "SELECT session_id FROM handoff_messages WHERE ticket_id=? ORDER BY id LIMIT 1", (ticket_id,)
    ).fetchone()
    c.close()
    return row["session_id"] if row else None


def get_ticket_by_session(session_id: str) -> dict | None:
    """Latest ticket opened from a chat session, or None if that session was
    never handed to a human (e.g. a low-rated answer the AI gave itself).
    Lets the Dashboard jump from an unresolved query to its case."""
    c = _conn()
    row = c.execute(
        "SELECT t.* FROM tickets t JOIN handoff_messages h ON h.ticket_id = t.id "
        "WHERE h.session_id=? GROUP BY t.id ORDER BY t.created_at DESC LIMIT 1", (session_id,)
    ).fetchone()
    c.close()
    return dict(row) if row else None


def get_unresolved_by_session(session_id: str) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM unresolved_queries WHERE session_id=? ORDER BY created_at", (session_id,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_ratings_by_session(session_id: str) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM satisfaction_ratings WHERE session_id=? ORDER BY created_at", (session_id,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def update_ticket_status(ticket_id: str, status: str) -> None:
    c = _conn()
    c.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
    c.commit()
    c.close()


def link_ticket_user(ticket_id: str, user_id: str) -> bool:
    """Attach an identity to a ticket that was opened by a guest — used
    when a customer logs in mid-handoff (see frontend/app.py). Only
    fills a NULL user_id; never overwrites one already set, so this
    can't be used to reassign a ticket to a different account."""
    c = _conn()
    cur = c.execute("UPDATE tickets SET user_id=? WHERE id=? AND user_id IS NULL", (user_id, ticket_id))
    c.commit()
    linked = cur.rowcount > 0
    c.close()
    return linked


def log_unresolved(
    session_id: str,
    user_query: str,
    language: str,
    trigger_reason: str,
    intent: str = "unknown",
    similarity_score: float | None = None,
) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO unresolved_queries "
        "(created_at, session_id, user_query, language, intent, trigger_reason, similarity_score) "
        "VALUES (?,?,?,?,?,?,?)",
        (datetime.now().isoformat(), session_id, user_query, language, intent, trigger_reason, similarity_score),
    )
    c.commit()
    c.close()


def get_unresolved(limit: int = 20) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM unresolved_queries ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_unresolved_since(since_iso: str) -> list[dict]:
    """Unresolved queries logged after a timestamp — used for the gap
    pipeline's 'has this topic recurred since we added the KB entry?'
    effectiveness check."""
    c = _conn()
    rows = c.execute(
        "SELECT * FROM unresolved_queries WHERE created_at > ? ORDER BY created_at DESC", (since_iso,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def add_handoff_message(ticket_id: str, session_id: str, role: str, content: str) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO handoff_messages (ticket_id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (ticket_id, session_id, role, content, datetime.now().isoformat()),
    )
    c.commit()
    c.close()


def get_handoff_messages(ticket_id: str) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM handoff_messages WHERE ticket_id=? ORDER BY id", (ticket_id,),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def add_rating(session_id: str, score: int, user_id: str = None, comment: str = None) -> None:
    c = _conn()
    c.execute(
        "INSERT INTO satisfaction_ratings (session_id, user_id, score, comment, created_at) "
        "VALUES (?,?,?,?,?)",
        (session_id, user_id, score, comment, datetime.now().isoformat()),
    )
    c.commit()
    c.close()


def get_ratings(limit: int = 50, max_score: int = None) -> list[dict]:
    """max_score filters to low scores (e.g. <= 2) for the Dashboard's
    "what are people unhappy about" view — those carry the comments the
    planned knowledge improvement pipeline will cluster on."""
    clause = "WHERE score <= ?" if max_score is not None else ""
    params = (max_score, limit) if max_score is not None else (limit,)
    c = _conn()
    rows = c.execute(
        f"SELECT * FROM satisfaction_ratings {clause} ORDER BY created_at DESC LIMIT ?", params,
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Knowledge Base Entries (Sprint 17) ──────────────────────────────────────
def create_kb_entry(
    language: str, title: str, content: str, tags: str = None, source: str = "manual",
) -> dict:
    now = datetime.now().isoformat()
    c = _conn()
    cur = c.execute(
        "INSERT INTO kb_entries (language, title, content, tags, status, source, created_at, updated_at) "
        "VALUES (?,?,?,?,'active',?,?,?)",
        (language, title, content, tags, source, now, now),
    )
    entry_id = cur.lastrowid
    c.commit()
    c.close()
    return {"id": entry_id, "created_at": now}


def get_kb_entries(language: str = None, status: str = "active", limit: int = 200) -> list[dict]:
    clauses, params = [], []
    if language:
        clauses.append("language=?")
        params.append(language)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    c = _conn()
    rows = c.execute(
        f"SELECT * FROM kb_entries {where} ORDER BY created_at DESC LIMIT ?", (*params, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_kb_entry(entry_id: int) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM kb_entries WHERE id=?", (entry_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def update_kb_entry(entry_id: int, title: str, content: str, tags: str = None) -> None:
    c = _conn()
    c.execute(
        "UPDATE kb_entries SET title=?, content=?, tags=?, updated_at=? WHERE id=?",
        (title, content, tags, datetime.now().isoformat(), entry_id),
    )
    c.commit()
    c.close()


def count_kb_changes_since(since_iso: str) -> int:
    """Entries created / edited / archived / restored after `since_iso` (the
    moment the live index was last written) — i.e. changes the index does not
    contain yet. Archived entries count: archiving only takes effect on rebuild."""
    c = _conn()
    n = c.execute(
        "SELECT COUNT(*) FROM kb_entries WHERE COALESCE(updated_at, created_at) > ?", (since_iso,)
    ).fetchone()[0]
    c.close()
    return n


def set_kb_entry_status(entry_id: int, status: str) -> None:
    """archive = soft delete (drops out of the next index rebuild); setting
    back to active is the rollback path."""
    c = _conn()
    c.execute(
        "UPDATE kb_entries SET status=?, updated_at=? WHERE id=?",
        (status, datetime.now().isoformat(), entry_id),
    )
    c.commit()
    c.close()


# ── Knowledge Improvement Drafts (Sprint 18) ────────────────────────────────────────
def create_gap_draft(
    language: str, topic: str, question: str, answer: str,
    representative_query: str, signal_summary: str, signal_count: int,
    pre_score: float, tags: str = None,
) -> dict:
    now = datetime.now().isoformat()
    c = _conn()
    cur = c.execute(
        "INSERT INTO kb_gap_drafts "
        "(language, topic, question, answer, tags, representative_query, signal_summary, "
        " signal_count, status, pre_score, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,'pending',?,?,?)",
        (language, topic, question, answer, tags, representative_query, signal_summary,
         signal_count, pre_score, now, now),
    )
    draft_id = cur.lastrowid
    c.commit()
    c.close()
    return {"id": draft_id}


def get_gap_drafts(status: str = None, limit: int = 200) -> list[dict]:
    where, params = ("WHERE status=?", [status]) if status else ("", [])
    c = _conn()
    rows = c.execute(
        f"SELECT * FROM kb_gap_drafts {where} ORDER BY signal_count DESC, created_at DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


def get_gap_draft(draft_id: int) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM kb_gap_drafts WHERE id=?", (draft_id,)).fetchone()
    c.close()
    return dict(row) if row else None


def update_gap_draft(draft_id: int, question: str, answer: str, tags: str = None) -> None:
    c = _conn()
    c.execute(
        "UPDATE kb_gap_drafts SET question=?, answer=?, tags=?, updated_at=? WHERE id=?",
        (question, answer, tags, datetime.now().isoformat(), draft_id),
    )
    c.commit()
    c.close()


def set_gap_draft_status(draft_id: int, status: str, kb_entry_id: int = None) -> None:
    c = _conn()
    if kb_entry_id is not None:
        c.execute(
            "UPDATE kb_gap_drafts SET status=?, kb_entry_id=?, updated_at=? WHERE id=?",
            (status, kb_entry_id, datetime.now().isoformat(), draft_id),
        )
    else:
        c.execute(
            "UPDATE kb_gap_drafts SET status=?, updated_at=? WHERE id=?",
            (status, datetime.now().isoformat(), draft_id),
        )
    c.commit()
    c.close()


def claim_gap_draft(draft_id: int) -> bool:
    """Atomically take a pending draft for approval: True for exactly one caller.

    Approval used to be check-then-act (look at the status, write the entry, reindex —
    seconds — and only then mark the draft approved), so a second request arriving during
    those seconds still saw "pending" and wrote a second, duplicate knowledge entry. One
    conditional UPDATE decides the winner in the database instead."""
    c = _conn()
    cur = c.execute(
        "UPDATE kb_gap_drafts SET status='approved', updated_at=? WHERE id=? AND status='pending'",
        (datetime.now().isoformat(), draft_id),
    )
    c.commit()
    won = cur.rowcount == 1
    c.close()
    return won


def clear_pending_gap_drafts() -> None:
    """Analysis regenerates the pending set each run; approved/skipped
    drafts persist so they don't reappear (skipped is remembered, and an
    approved topic no longer surfaces because its query now retrieves)."""
    c = _conn()
    c.execute("DELETE FROM kb_gap_drafts WHERE status='pending'")
    c.commit()
    c.close()


def get_skipped_representative_queries() -> list[str]:
    c = _conn()
    rows = c.execute(
        "SELECT representative_query FROM kb_gap_drafts WHERE status='skipped'"
    ).fetchall()
    c.close()
    return [r[0] for r in rows]


def get_stats() -> dict:
    c = _conn()
    total_tickets = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    open_tickets = c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
    done_tickets = c.execute("SELECT COUNT(*) FROM tickets WHERE status IN ('resolved','closed')").fetchone()[0]
    total_unresolved = c.execute("SELECT COUNT(*) FROM unresolved_queries").fetchone()[0]
    by_reason_rows = c.execute(
        "SELECT trigger_reason, COUNT(*) FROM unresolved_queries GROUP BY trigger_reason"
    ).fetchall()
    rating_count = c.execute("SELECT COUNT(*) FROM satisfaction_ratings").fetchone()[0]
    avg_rating = c.execute("SELECT AVG(score) FROM satisfaction_ratings").fetchone()[0]
    dist_rows = c.execute(
        "SELECT score, COUNT(*) FROM satisfaction_ratings GROUP BY score"
    ).fetchall()
    c.close()
    return {
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "done_tickets": done_tickets,
        "total_unresolved": total_unresolved,
        "unresolved_by_reason": {r[0]: r[1] for r in by_reason_rows},
        "rating_count": rating_count,
        "avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
        # keys are strings 1..5 so it survives JSON round-trips unchanged
        "rating_distribution": {str(r[0]): r[1] for r in dist_rows},
    }


def save_session(
    session_id: str,
    user_id: str | None,
    language: str,
    messages: list[dict],
    workflow_step: int,
    workflow_data: dict,
    handoff_active: bool,
    handoff_ticket_id: str | None,
) -> None:
    """Upsert — called after every /chat turn (backend/main.py) so a
    browser refresh has somewhere to restore from. Overwrites the whole
    row each time; last write wins, which matches a single browser tab
    driving one conversation (no concurrent-writer case to reconcile)."""
    c = _conn()
    c.execute(
        """INSERT INTO chat_sessions
               (session_id, user_id, language, messages, workflow_step, workflow_data,
                handoff_active, handoff_ticket_id, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(session_id) DO UPDATE SET
               user_id=excluded.user_id, language=excluded.language, messages=excluded.messages,
               workflow_step=excluded.workflow_step, workflow_data=excluded.workflow_data,
               handoff_active=excluded.handoff_active, handoff_ticket_id=excluded.handoff_ticket_id,
               updated_at=excluded.updated_at""",
        (session_id, user_id, language, json.dumps(messages, ensure_ascii=False),
         workflow_step, json.dumps(workflow_data, ensure_ascii=False),
         int(handoff_active), handoff_ticket_id, datetime.now().isoformat()),
    )
    c.commit()
    c.close()


def get_session(session_id: str) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM chat_sessions WHERE session_id=?", (session_id,)).fetchone()
    c.close()
    if not row:
        return None
    d = dict(row)
    d["messages"] = json.loads(d["messages"])
    d["workflow_data"] = json.loads(d["workflow_data"])
    d["handoff_active"] = bool(d["handoff_active"])
    return d


def record_llm_call(
    session_id: str | None,
    turn_id: str | None,
    node: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: float,
    created_at: str,
) -> None:
    """Called by backend/src/tracing.py after every Claude API call —
    never called directly elsewhere."""
    c = _conn()
    c.execute(
        """INSERT INTO llm_calls
               (session_id, turn_id, node, model, input_tokens, output_tokens,
                cost_usd, latency_ms, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (session_id, turn_id, node, model, input_tokens, output_tokens,
         cost_usd, latency_ms, created_at),
    )
    c.commit()
    c.close()


def get_llm_cost_summary(since: str | None = None) -> dict:
    """Aggregate cost/latency, overall and broken down by call site
    ("node"). `since` (ISO timestamp) restricts to calls at or after it."""
    c = _conn()
    where = "WHERE created_at >= ?" if since else ""
    params = (since,) if since else ()
    total = c.execute(
        f"SELECT COUNT(*), SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), AVG(latency_ms) "
        f"FROM llm_calls {where}", params,
    ).fetchone()
    by_node = c.execute(
        f"SELECT node, COUNT(*), SUM(cost_usd), AVG(latency_ms) FROM llm_calls {where} "
        f"GROUP BY node ORDER BY SUM(cost_usd) DESC", params,
    ).fetchall()
    c.close()
    return {
        "call_count": total[0] or 0,
        "total_cost_usd": round(total[1], 6) if total[1] else 0.0,
        "total_input_tokens": total[2] or 0,
        "total_output_tokens": total[3] or 0,
        "avg_latency_ms": round(total[4], 1) if total[4] else 0.0,
        "by_node": [
            {"node": r[0], "call_count": r[1], "cost_usd": round(r[2], 6), "avg_latency_ms": round(r[3], 1)}
            for r in by_node
        ],
    }


def get_session_cost(session_id: str) -> dict:
    c = _conn()
    row = c.execute(
        "SELECT COUNT(*), SUM(cost_usd), SUM(input_tokens), SUM(output_tokens), SUM(latency_ms) "
        "FROM llm_calls WHERE session_id=?", (session_id,),
    ).fetchone()
    c.close()
    return {
        "call_count": row[0] or 0,
        "total_cost_usd": round(row[1], 6) if row[1] else 0.0,
        "total_input_tokens": row[2] or 0,
        "total_output_tokens": row[3] or 0,
        "total_latency_ms": round(row[4], 1) if row[4] else 0.0,
    }


def get_recent_llm_calls(limit: int = 50) -> list[dict]:
    c = _conn()
    rows = c.execute("SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
