"""
AI Banking Customer Assistant — Backend API
Sprint 6: LangGraph state machine (Router → FAQ/Account/CardLoss/Handoff/Logger)
Sprint 13: /chat/stream — token-by-token streaming for the FAQ Node's answer
Sprint 15: /handoff/* — real human-agent conversation once escalated
Sprint 16: /rating — session-level satisfaction score (1-5, + reason on low)
Sprint 17: /kb/* — knowledge-base maintenance + hot reindex (no restart)
Sprint 18: /gap/* — knowledge improvement pipeline (cluster → draft → review → effectiveness)
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Must run before any backend.src import: auth.py reads
# JWT_SECRET_KEY/STAFF_USERNAME/STAFF_PASSWORD from os.environ at module
# import time, so .env has to be loaded into the environment first.
load_dotenv()

from backend.src.agent.graph import build_graph
from backend.src.agent.state import AgentState
from backend.src.card_loss_workflow import resume_prompt
from backend.src.auth import (STAFF_PASSWORD, STAFF_USERNAME, create_customer_token,
                               create_staff_token, get_current_user_id, require_customer,
                               require_staff)
from backend.src.database import (add_handoff_message, add_rating, claim_gap_draft, count_kb_changes_since, create_kb_entry,
                                   get_gap_draft, get_gap_drafts, get_handoff_messages,
                                   get_kb_entries, get_kb_entry, get_llm_cost_summary,
                                   get_ratings, get_ratings_by_session, get_recent_llm_calls, get_session,
                                   get_session_cost, get_stats, get_ticket, get_ticket_by_session,
                                   get_ticket_session_id, get_tickets, get_unresolved_by_session,
                                   get_unresolved, init_db, link_ticket_user, save_session,
                                   set_gap_draft_status, set_kb_entry_status, update_gap_draft,
                                   update_kb_entry, update_ticket_status)
from backend.src.mock_api.api import router as mock_api_router
from backend.src.mock_api.mock_data import get_user_by_id
from backend.src.prompts import KB
from backend.src.tracing import set_trace_context, traced_create, traced_stream
from backend.src.rag.retriever import RAGRetriever

app = FastAPI(
    title="AI Banking Assistant API",
    description="Future Bank AI Customer Service — Sprint 18 (LangGraph agent + CSAT + KB maintenance/hot-reindex + knowledge improvement pipeline: cluster→draft→review→effectiveness)",
    version="18.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(mock_api_router)

# ── Config ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
INDEX_DIR = PROJECT_ROOT / "data" / "faiss_index"
KB_DIR = PROJECT_ROOT / "data" / "knowledge_base"
MAX_TOKENS = int(os.getenv("MAX_TOKENS", 1024))
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", 10))
MODEL = "claude-haiku-4-5"

retrievers: dict[str, RAGRetriever] = {}  # populated at startup
agent_graph = None  # compiled LangGraph, populated at startup

# max_retries is the retry policy docs/architecture.md §5 describes,
# pinned here rather than inherited from the SDK default so an SDK
# upgrade can't silently change it. The SDK already retries connection
# errors, 408/409/429 and 5xx with exponential backoff and honours
# Retry-After — so there is deliberately NO second retry loop in app
# code on top of this. Anything that reaches the handlers below has
# already been retried and still failed.
client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    max_retries=2,
)


def _upstream_error(e: anthropic.APIError, where: str) -> HTTPException:
    """An Anthropic error's string form carries the request id, the model
    name and sometimes a slice of the prompt that triggered it; this used
    to be passed straight through as the HTTP detail, i.e. out to the
    browser. Log the real thing server-side, hand the caller a stable
    string it can localize (§5's "系統暫時無法回應")."""
    print(f"[{where}] anthropic {type(e).__name__}: {e}")
    return HTTPException(status_code=502, detail="AI service temporarily unavailable")

# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    global retrievers, agent_graph
    retrievers = {
        "zh": RAGRetriever("zh", INDEX_DIR),
        "en": RAGRetriever("en", INDEX_DIR),
    }
    agent_graph = build_graph(client, retrievers, KB, MODEL, MAX_TOKENS)
    _warm_suggestion_cache()


def _warm_suggestion_cache() -> None:
    """Score the starter shortcuts once at boot. They're checked against
    the live index before being shown (see agent/suggestions.py), and
    paying for those embeddings on the customer's first page load is the
    one place that cost is visible — everywhere else the cache is already
    warm. Also called after a reindex, where the old scores are dropped."""
    from backend.src.agent.suggestions import starters
    for lang in ("zh", "en"):
        for authenticated in (False, True):
            starters(retrievers.get(lang), lang, authenticated)

# ── Models ─────────────────────────────────────────────────────────────────────
class Message(BaseModel):
    role: str
    content: str

class WorkflowState(BaseModel):
    step: int = 0
    data: dict[str, Any] = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str
    history: list[Message] = []
    user_id: Optional[str] = None
    workflow: WorkflowState = WorkflowState()
    fallback_count: int = 0       # consecutive unresolved turns, tracked by frontend
    force_handoff: bool = False   # frontend sends True when fallback_count >= 3

class ChatResponse(BaseModel):
    response: str
    language: str
    session_id: str
    workflow: WorkflowState = WorkflowState()
    is_negative_feedback: bool = False
    is_handoff: bool = False   # True when this turn's intent routed to the Handoff Node
    handoff_ticket_id: Optional[str] = None  # set when is_handoff — see agent/handoff.py
    rag_sources: list[str] = []  # source file names used for this answer
    suggestions: list[str] = []  # quick-reply follow-ups — see agent/suggestions.py

# ── Staff Auth ─────────────────────────────────────────────────────────────────
class StaffLoginRequest(BaseModel):
    username: str
    password: str

@app.post("/auth/staff-login", summary="Staff/back-office login")
def staff_login(req: StaffLoginRequest):
    """No staff directory in this demo — a single shared credential
    (env STAFF_USERNAME/STAFF_PASSWORD), same posture as the mock
    customer accounts. Gates /tickets, /kb/*, /gap/* — see require_staff."""
    if req.username != STAFF_USERNAME or req.password != STAFF_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid staff credentials")
    return {"token": create_staff_token(req.username)}


# ── Chat Endpoint ──────────────────────────────────────────────────────────────
def _resolve_claimed_user_id(token_user_id: Optional[str], body_user_id: Optional[str]) -> Optional[str]:
    """user_id may no longer come from the request body alone — see
    tests/security/test_authorization.py::test_chat_rejects_unverified_user_id_claim.
    A body-supplied user_id is only honored when it matches a verified
    token's subject; without a token it's an unverified identity claim.

    Shared by /chat, /chat/stream and /rating: any endpoint that lets the
    body name a user has to resolve it the same way, or the strict ones
    are pointless. Returning None (guest) stays legitimate throughout."""
    if body_user_id is None:
        return token_user_id
    if token_user_id is None:
        raise HTTPException(status_code=401, detail="user_id claim requires a valid Authorization token")
    if token_user_id != body_user_id:
        raise HTTPException(status_code=403, detail="user_id does not match authenticated session")
    return token_user_id


def _build_initial_state(req: ChatRequest, user_id: Optional[str]) -> AgentState:
    history = req.history[-(MAX_HISTORY_TURNS * 2):]
    return {
        "user_message": req.message,
        "messages": [{"role": m.role, "content": m.content} for m in history],
        "user_id": user_id,
        "user_authenticated": user_id is not None,
        "session_id": req.session_id,
        "workflow_step": req.workflow.step,
        "workflow_data": req.workflow.data,
        "fallback_count": req.fallback_count,
        "force_handoff": req.force_handoff,
    }


def _persist_session(req: ChatRequest, user_id: Optional[str], result: dict, response_text: str) -> None:
    """Saves the full conversation (not the MAX_HISTORY_TURNS-capped
    slice the LLM sees) so a browser refresh — which drops Streamlit's
    st.session_state entirely, see frontend/app.py's init_session() —
    can restore via GET /session/{session_id} instead of starting over."""
    messages = [{"role": m.role, "content": m.content} for m in req.history] + [
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": response_text},
    ]
    save_session(
        session_id=req.session_id,
        user_id=user_id,
        language=result["language"],
        messages=messages,
        workflow_step=result.get("workflow_step", 0),
        workflow_data=result.get("workflow_data", {}),
        handoff_active=result.get("intent") == "handoff",
        handoff_ticket_id=result.get("handoff_ticket_id"),
    )


def _resume_suffix(result: dict) -> str:
    """After a side question answered mid card-loss (router set
    paused_workflow), point the customer back to the step they paused."""
    if not result.get("paused_workflow"):
        return ""
    return resume_prompt(
        {"step": result.get("workflow_step", 0), "data": result.get("workflow_data", {})},
        result["language"],
    )


def _finish_pending_stream_blocking(pending: dict) -> str:
    """Used by /chat: finish a deferred FAQ answer (see nodes.py
    pending_stream) with a normal blocking call — same latency/behavior
    as before Sprint 13, since /chat's JSON contract can't stream."""
    result = traced_create(
        client, "qa_answer_blocking",
        model=MODEL, max_tokens=pending["max_tokens"], system=pending["system"], messages=pending["messages"],
    )
    return result.content[0].text


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, token_user_id: Optional[str] = Depends(get_current_user_id)):
    user_id = _resolve_claimed_user_id(token_user_id, req.user_id)
    initial_state = _build_initial_state(req, user_id)
    set_trace_context(req.session_id, str(uuid.uuid4()))

    try:
        result = agent_graph.invoke(initial_state)
        response_text = (
            _finish_pending_stream_blocking(result["pending_stream"])
            if "pending_stream" in result
            else result["response"]
        ) + _resume_suffix(result)
    except anthropic.APIError as e:
        raise _upstream_error(e, "chat")

    _persist_session(req, user_id, result, response_text)

    return ChatResponse(
        response=response_text,
        language=result["language"],
        session_id=req.session_id,
        workflow=WorkflowState(step=result.get("workflow_step", 0), data=result.get("workflow_data", {})),
        is_negative_feedback=result.get("is_negative_feedback", False),
        is_handoff=result.get("intent") == "handoff",
        handoff_ticket_id=result.get("handoff_ticket_id"),
        rag_sources=result.get("rag_sources", []),
        suggestions=result.get("suggestions", []),
    )


# ── Streaming Chat Endpoint (Sprint 13) ────────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, token_user_id: Optional[str] = Depends(get_current_user_id)):
    """
    Same graph, same routing/retrieval/verification — only the FAQ
    Node's final answer differs: instead of waiting for the whole
    response then sending one JSON blob (like /chat), tokens are sent
    to the client as Claude generates them. Metadata that /chat returns
    as JSON fields (language, workflow, is_handoff, rag_sources, ...) is
    already fully known before generation starts, so it travels as
    response headers instead of being mixed into the streamed body —
    ASCII-only (json.dumps default) since HTTP headers aren't reliably
    UTF-8 safe.
    """
    user_id = _resolve_claimed_user_id(token_user_id, req.user_id)
    initial_state = _build_initial_state(req, user_id)
    set_trace_context(req.session_id, str(uuid.uuid4()))

    try:
        result = agent_graph.invoke(initial_state)
    except anthropic.APIError as e:
        raise _upstream_error(e, "chat_stream")

    def generate():
        parts: list[str] = []
        if "pending_stream" in result:
            pending = result["pending_stream"]
            with traced_stream(
                client, "qa_answer_stream",
                model=MODEL, max_tokens=pending["max_tokens"], system=pending["system"], messages=pending["messages"],
            ) as stream:
                for chunk in stream.text_stream:
                    parts.append(chunk)
                    yield chunk
        else:
            parts.append(result["response"])
            yield result["response"]
        suffix = _resume_suffix(result)
        if suffix:
            parts.append(suffix)
            yield suffix
        _persist_session(req, user_id, result, "".join(parts))

    headers = {
        "X-Session-Id": req.session_id,
        "X-Language": result["language"],
        "X-Is-Handoff": "true" if result.get("intent") == "handoff" else "false",
        "X-Handoff-Ticket-Id": result.get("handoff_ticket_id") or "",
        "X-Is-Negative-Feedback": "true" if result.get("is_negative_feedback") else "false",
        "X-Workflow": json.dumps({"step": result.get("workflow_step", 0), "data": result.get("workflow_data", {})}),
        "X-Rag-Sources": json.dumps(result.get("rag_sources", [])),
        "X-Suggestions": json.dumps(result.get("suggestions", [])),
    }
    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8", headers=headers)

# ── Session Restore (Sprint 19) ─────────────────────────────────────────────
@app.get("/session/{session_id}")
def restore_session(session_id: str):
    """Called once on page load (frontend/app.py) when the URL already
    carries a ?sid= from a prior visit — restores conversation/workflow
    state a browser refresh would otherwise wipe. A fresh customer JWT is
    minted here rather than persisted (the old token itself is never
    stored), so login also survives.

    Trade-off, noted rather than hidden: session_id lives in the URL, not
    an httpOnly cookie — same security model as a session cookie (whoever
    has the id can resume the session), but URLs are more exposure-prone
    (browser history, could be pasted/shared). Acceptable for this
    project's scope; a real deploy would prefer a cookie."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    user = get_user_by_id(session["user_id"]) if session["user_id"] else None
    return {
        "user_id": session["user_id"],
        "user_name": user["name"] if user else None,
        "token": create_customer_token(session["user_id"]) if session["user_id"] else None,
        "language": session["language"],
        "messages": session["messages"],
        "workflow": {"step": session["workflow_step"], "data": session["workflow_data"]},
        "handoff_active": session["handoff_active"],
        "handoff_ticket_id": session["handoff_ticket_id"],
    }


# ── Handoff Conversation Endpoints (Sprint 15) ────────────────────────────────
class HandoffMessageRequest(BaseModel):
    role: str    # "user" | "agent"
    content: str

@app.get("/handoff/tickets")
def list_handoff_tickets(status: str = "open", limit: int = 20, staff=Depends(require_staff)):
    """For the Agent Console page — open handoff tickets waiting to be
    picked up. No customer use case ever calls this (it lists every open
    ticket, not just one), so it's staff-only."""
    return get_tickets(type="handoff", status=status, limit=limit)

@app.get("/handoff/{ticket_id}/messages")
def get_handoff_thread(ticket_id: str):
    """Read side is left on the ticket_id-possession model, same trade-off
    as GET /session/{session_id} above. That model only holds because
    database.create_ticket() appends a random suffix to the id — the
    date+counter part alone would be trivially enumerable, and then
    possession would prove nothing."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket": ticket, "messages": get_handoff_messages(ticket_id)}

@app.post("/handoff/{ticket_id}/messages")
def post_handoff_message(ticket_id: str, req: HandoffMessageRequest,
                          authorization: str | None = Header(default=None)):
    """Used by BOTH sides once escalated: the customer's own follow-ups
    (role="user", from frontend/app.py once handoff_active locks out the
    AI — left on the ticket_id-possession model, see get_handoff_thread)
    and the human agent's replies (role="agent", from the Agent Console
    page). Only the "agent" role is staff-gated here: the customer side
    rides on holding the (unguessable) ticket_id, but that is not enough
    to speak AS the bank — without this check any caller who obtained a
    ticket_id could inject fake agent replies into a live conversation."""
    if req.role == "agent":
        require_staff(authorization)
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    existing = get_handoff_messages(ticket_id)
    session_id = existing[0]["session_id"] if existing else ticket_id
    add_handoff_message(ticket_id, session_id, req.role, req.content)
    return {"ok": True}

@app.post("/handoff/{ticket_id}/reopen")
def reopen_handoff_ticket(ticket_id: str, staff=Depends(require_staff)):
    """Undo for "mark resolved": resolving used to be one click with no way
    back, so a mis-click made the case vanish from the queue."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    update_ticket_status(ticket_id, "open")
    return {"ok": True}

@app.post("/handoff/{ticket_id}/resolve")
def resolve_handoff_ticket(ticket_id: str, staff=Depends(require_staff)):
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    update_ticket_status(ticket_id, "resolved")
    return {"ok": True}

class LinkUserRequest(BaseModel):
    user_id: str

@app.post("/handoff/{ticket_id}/link-user")
def link_handoff_ticket_user(ticket_id: str, req: LinkUserRequest,
                              user_id: str = Depends(require_customer)):
    """Called when a guest logs in while their handoff conversation is
    still open (see frontend/app.py's login handler) — attaches their
    identity to the ticket they already opened as a guest, so the agent
    knows who they're talking to without re-verifying from scratch.
    Only fills a NULL user_id (see database.link_ticket_user).

    Requires a customer token whose identity matches req.user_id —
    otherwise anyone who can guess a ticket_id could link an arbitrary
    victim's account to a conversation they don't own."""
    if user_id != req.user_id:
        raise HTTPException(status_code=403, detail="Token does not match user_id")
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    linked = link_ticket_user(ticket_id, req.user_id)
    return {"ok": True, "linked": linked}

# ── Satisfaction Rating Endpoints (Sprint 16) ──────────────────────────────────
class RatingRequest(BaseModel):
    session_id: str
    score: int                          # 1..5
    user_id: Optional[str] = None
    comment: Optional[str] = None       # optional; frontend prompts on low scores

@app.post("/rating")
def submit_rating(req: RatingRequest,
                  token_user_id: Optional[str] = Depends(get_current_user_id)):
    """Deliberately open to guests (a rating is worth having even from a
    session that never logged in), but a body-supplied user_id is still
    an identity claim and gets checked like any other — otherwise anyone
    could attribute ratings to an arbitrary customer. That matters
    beyond the CSAT chart: low scores are a clustering signal for the
    knowledge improvement pipeline (agent/gap_pipeline.py), so unverified input
    here steers what gets drafted into the knowledge base."""
    if not 1 <= req.score <= 5:
        raise HTTPException(status_code=422, detail="score must be between 1 and 5")
    user_id = _resolve_claimed_user_id(token_user_id, req.user_id)
    comment = (req.comment or "").strip() or None
    add_rating(session_id=req.session_id, score=req.score, user_id=user_id, comment=comment)
    return {"ok": True}

@app.get("/ratings")
def list_ratings(limit: int = 50, max_score: Optional[int] = None):
    """max_score lets the Dashboard pull just the low scores (with their
    reason comments) — the raw material for the planned knowledge improvement
    pipeline's clustering."""
    return get_ratings(limit=limit, max_score=max_score)

# ── Knowledge Base Maintenance Endpoints (Sprint 17) ───────────────────────────
class KBEntryRequest(BaseModel):
    language: str          # 'zh' | 'en'
    title: str             # the question / topic
    content: str           # the answer
    tags: Optional[str] = None
    source: str = "manual"

class KBEntryUpdate(BaseModel):
    title: str
    content: str
    tags: Optional[str] = None

@app.post("/kb/entries")
def create_kb(req: KBEntryRequest, staff=Depends(require_staff)):
    if req.language not in ("zh", "en"):
        raise HTTPException(status_code=422, detail="language must be 'zh' or 'en'")
    if not req.title.strip() or not req.content.strip():
        raise HTTPException(status_code=422, detail="title and content are required")
    return create_kb_entry(
        language=req.language, title=req.title.strip(), content=req.content.strip(),
        tags=(req.tags or "").strip() or None, source=req.source,
    )

@app.get("/kb/entries")
def list_kb(language: Optional[str] = None, status: str = "active", limit: int = 200,
            staff=Depends(require_staff)):
    return get_kb_entries(language=language, status=status, limit=limit)

@app.put("/kb/entries/{entry_id}")
def edit_kb(entry_id: int, req: KBEntryUpdate, staff=Depends(require_staff)):
    if not get_kb_entry(entry_id):
        raise HTTPException(status_code=404, detail="KB entry not found")
    if not req.title.strip() or not req.content.strip():
        raise HTTPException(status_code=422, detail="title and content are required")
    update_kb_entry(entry_id, req.title.strip(), req.content.strip(), (req.tags or "").strip() or None)
    return {"ok": True}

@app.post("/kb/entries/{entry_id}/archive")
def archive_kb(entry_id: int, staff=Depends(require_staff)):
    if not get_kb_entry(entry_id):
        raise HTTPException(status_code=404, detail="KB entry not found")
    set_kb_entry_status(entry_id, "archived")
    return {"ok": True}

@app.post("/kb/entries/{entry_id}/restore")
def restore_kb(entry_id: int, staff=Depends(require_staff)):
    if not get_kb_entry(entry_id):
        raise HTTPException(status_code=404, detail="KB entry not found")
    set_kb_entry_status(entry_id, "active")
    return {"ok": True}

@app.get("/suggestions")
def list_starter_suggestions(language: str = "zh", authenticated: bool = False, limit: int = 3):
    """Starter shortcuts for the welcome screen (Sprint 20). Separate from
    the per-answer follow-ups that ride along in /chat's response, because
    at this point there's no question to extend from yet."""
    from backend.src.agent.suggestions import starters
    return {"suggestions": starters(retrievers.get(language), language, authenticated, limit)}


def _rebuild_and_swap_index() -> dict:
    """Rebuild both FAISS indexes from markdown + active kb_entries, then
    hot-swap the live retrievers so new knowledge answers immediately —
    no server restart. Safe because make_qa_node looks the retriever up
    from this dict at call time (see agent/nodes.py), so replacing the
    values in place is picked up by the running graph. Shared by
    /kb/reindex and the gap-draft approve flow."""
    from backend.src.agent.suggestions import clear_cache
    from backend.src.rag.build_index import reindex_all
    counts = reindex_all(KB_DIR, INDEX_DIR)
    for lang in ("zh", "en"):
        retrievers[lang] = RAGRetriever(lang, INDEX_DIR)
    clear_cache()   # scores from the old index must not decide what's answerable now
    _warm_suggestion_cache()
    return counts

@app.get("/kb/status")
def kb_status(staff=Depends(require_staff)):
    """How many knowledge changes the live index does not contain yet — what
    the maintenance page shows as "N changes not applied". Measured against
    the index file's own write time, so it survives a backend restart."""
    index_file = INDEX_DIR / "zh.index"
    if not index_file.exists():
        return {"indexed_at": None, "pending_changes": 0}
    indexed_at = datetime.fromtimestamp(index_file.stat().st_mtime).isoformat()
    return {"indexed_at": indexed_at, "pending_changes": count_kb_changes_since(indexed_at)}

@app.post("/kb/reindex")
def kb_reindex(staff=Depends(require_staff)):
    return {"ok": True, "chunk_counts": _rebuild_and_swap_index()}

@app.get("/kb/retrieve")
def kb_retrieve(q: str, language: str = "zh", top_k: int = 3, staff=Depends(require_staff)):
    """Retrieval test tool for the maintenance UI: shows what the live
    index returns for a query (chunks + similarity), so an editor can add
    an entry, reindex, and confirm the previously-missed question now
    retrieves it above the confidence threshold."""
    r = retrievers.get(language)
    if not r or not r.is_ready:
        return {"ready": False, "chunks": []}
    return {"ready": True, "chunks": r.retrieve(q, top_k=top_k)}

# ── Knowledge Improvement Pipeline Endpoints (Sprint 18) ───────────────────────────────
class GapDraftUpdate(BaseModel):
    question: str
    answer: str
    tags: Optional[str] = None

@app.post("/gap/analyze")
def gap_analyze(staff=Depends(require_staff)):
    """Cluster current gap signals and generate FAQ drafts for review.
    LLM-heavy, so it's an explicit action, not run on page load."""
    from backend.src.agent.gap_pipeline import analyze
    try:
        return analyze(client, MODEL, retrievers)
    except anthropic.APIError as e:
        raise _upstream_error(e, "gap_analyze")

@app.get("/gap/drafts")
def list_gap_drafts(status: Optional[str] = None, limit: int = 200, staff=Depends(require_staff)):
    return get_gap_drafts(status=status, limit=limit)

@app.put("/gap/drafts/{draft_id}")
def edit_gap_draft(draft_id: int, req: GapDraftUpdate, staff=Depends(require_staff)):
    if not get_gap_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    if not req.question.strip() or not req.answer.strip():
        raise HTTPException(status_code=422, detail="question and answer are required")
    update_gap_draft(draft_id, req.question.strip(), req.answer.strip(), (req.tags or "").strip() or None)
    return {"ok": True}

@app.post("/gap/drafts/{draft_id}/skip")
def skip_gap_draft(draft_id: int, staff=Depends(require_staff)):
    if not get_gap_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    set_gap_draft_status(draft_id, "skipped")
    return {"ok": True}

@app.post("/gap/drafts/{draft_id}/restore")
def restore_gap_draft(draft_id: int, staff=Depends(require_staff)):
    """Undo a 略過: a mis-click used to be permanent — the topic was remembered as skipped, so even
    re-running the analysis would never bring it back."""
    draft = get_gap_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "skipped":
        raise HTTPException(status_code=409, detail="Only a skipped draft can be restored")
    set_gap_draft_status(draft_id, "pending")
    return {"ok": True}

@app.post("/gap/drafts/{draft_id}/approve")
def approve_gap_draft(draft_id: int, staff=Depends(require_staff)):
    """One-click review → KB: write the draft as a kb_entry(source=
    'pipeline'), reindex + hot-swap, and return the representative query's
    retrieval score before vs after — the quantified effectiveness."""
    from backend.src.agent.gap_pipeline import HIGH_CONFIDENCE_THRESHOLD, _top_score
    draft = get_gap_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    # Claim first, write second: the claim is one atomic UPDATE, so two clicks (or two
    # requests) can never both get past it and write the entry twice.
    if not claim_gap_draft(draft_id):
        raise HTTPException(status_code=409, detail="Draft already approved or not pending")
    try:
        entry = create_kb_entry(
            language=draft["language"], title=draft["question"], content=draft["answer"],
            tags=draft.get("tags"), source="pipeline",
        )
    except Exception:
        set_gap_draft_status(draft_id, "pending")      # nothing was written: let it be approved again
        raise
    set_gap_draft_status(draft_id, "approved", kb_entry_id=entry["id"])
    _rebuild_and_swap_index()
    post_score = _top_score(retrievers, draft["language"], draft["representative_query"])
    return {
        "ok": True, "kb_entry_id": entry["id"],
        "pre_score": draft["pre_score"], "post_score": post_score,
        "threshold": HIGH_CONFIDENCE_THRESHOLD,
    }

@app.get("/gap/drafts/{draft_id}/effectiveness")
def gap_effectiveness(draft_id: int, staff=Depends(require_staff)):
    """Live effectiveness for an approved draft: representative query's
    retrieval score now vs the pre-approval snapshot, plus how many gap
    signals on this topic have recurred since the entry went live."""
    from backend.src.agent.gap_pipeline import HIGH_CONFIDENCE_THRESHOLD, _top_score, count_recurrence
    draft = get_gap_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    live_score = _top_score(retrievers, draft["language"], draft["representative_query"])
    recurrence = None
    if draft.get("kb_entry_id"):
        entry = get_kb_entry(draft["kb_entry_id"])
        if entry:
            recurrence = count_recurrence(draft["representative_query"], entry["created_at"])
    return {
        "pre_score": draft["pre_score"], "live_score": live_score,
        "threshold": HIGH_CONFIDENCE_THRESHOLD, "recurrence_since_live": recurrence,
    }

# ── Data Endpoints ─────────────────────────────────────────────────────────────
@app.get("/tickets")
def list_tickets(user_id: Optional[str] = None, limit: int = 20, staff=Depends(require_staff)):
    return get_tickets(user_id=user_id, limit=limit)

def _case_record(ticket: dict | None, session_id: str | None) -> dict:
    """Everything the back office knows about one case: the ticket, its full
    conversation thread, and what else was logged against the same chat
    session (why it was marked unresolved, any CSAT rating)."""
    messages = get_handoff_messages(ticket["id"]) if ticket else []
    chat_messages = []
    if not ticket and session_id:
        session = get_session(session_id)
        chat_messages = [{"role": m["role"], "content": m["content"]} for m in (session["messages"] if session else [])]
    return {
        "ticket": ticket,
        "session_id": session_id,
        "messages": messages,             # human-handoff thread (empty if never escalated)
        "chat_messages": chat_messages,   # the AI-only conversation, when there is no ticket
        "unresolved": get_unresolved_by_session(session_id) if session_id else [],
        "ratings": get_ratings_by_session(session_id) if session_id else [],
    }


@app.get("/tickets/{ticket_id}/record")
def get_ticket_record(ticket_id: str, staff=Depends(require_staff)):
    """Full case record for the Dashboard's ticket list. Staff-only: unlike
    GET /handoff/{id}/messages (customer-side, ticket_id possession) this
    also returns session ids, unresolved logs and ratings."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _case_record(ticket, get_ticket_session_id(ticket_id))


@app.get("/cases/by-session/{session_id}")
def get_case_by_session(session_id: str, staff=Depends(require_staff)):
    """Case behind an unresolved query: its ticket if the session was handed
    to a human, otherwise just the AI-only conversation (nothing to reply to)."""
    return _case_record(get_ticket_by_session(session_id), session_id)


@app.get("/unresolved")
def list_unresolved(limit: int = 20):
    return get_unresolved(limit=limit)

@app.get("/stats")
def stats():
    return get_stats()

# ── Tracing / Cost / Latency (Sprint 19) ────────────────────────────────────
@app.get("/cost/summary")
def cost_summary(since: Optional[str] = None, staff=Depends(require_staff)):
    """Aggregate cost + latency across all traced Claude API calls
    (backend/src/tracing.py), broken down by call site. `since` is an
    ISO timestamp; omit for all-time."""
    return get_llm_cost_summary(since=since)

@app.get("/cost/session/{session_id}")
def cost_for_session(session_id: str, staff=Depends(require_staff)):
    return get_session_cost(session_id)

@app.get("/cost/recent")
def recent_llm_calls(limit: int = 50, staff=Depends(require_staff)):
    return get_recent_llm_calls(limit=limit)

@app.get("/health")
def health():
    rag_status = {
        lang: retrievers[lang].is_ready if lang in retrievers else False
        for lang in ["zh", "en"]
    }
    return {
        "status": "ok",
        "sprint": 18,
        "mode": "LangGraph agent + CSAT + KB maintenance (hot reindex) + knowledge improvement pipeline (cluster->draft->review->effectiveness)",
        "rag_index_ready": rag_status,
    }
