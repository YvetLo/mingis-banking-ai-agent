"""
Knowledge improvement pipeline — Sprint 18.

Turns accumulated failure signals into reviewable FAQ drafts:

  gather  → pull unresolved queries (verifier/negative/fallback), low
            CSAT comments, and handoff threads that have a real agent
            reply. Drop signals the current index ALREADY answers well
            (top score ≥ HIGH_CONFIDENCE_THRESHOLD) — an approved topic
            stops surfacing for free this way — and drop ones an agent
            already skipped.
  cluster → one forced-tool-call to Claude groups the survivors into
            named topics, each flagged kb_actionable. A topic is only
            kb_actionable if a self-service article would genuinely
            resolve it; requests that inherently need a human (fee
            waivers, data/security changes, fraud, disputes, complaints)
            are correct escalations, NOT knowledge gaps, and get no draft.
  draft   → per actionable topic, a second forced-tool-call writes a
            reusable FAQ (question/answer/tags) grounded in the agent's
            actual replies, with personal data redacted.

Same tool_choice pattern as intent.py / verifier.py — structured output,
no free-text parsing. Clustering is LLM topic-grouping rather than
embedding k-means: at this scale it's simpler, self-labels each topic,
and stays explainable (see docs/ADR.md ADR-013).

Approving a draft (main.py) writes a kb_entry(source='pipeline') and
reindexes; the before/after retrieval score of representative_query is
the quantified effectiveness signal.
"""

import numpy as np

from ..database import (get_handoff_messages, get_ratings, get_skipped_representative_queries,
                        get_tickets, get_unresolved, get_unresolved_since)
from ..nlp import detect_language
from ..rag.retriever import _get_model
from ..tracing import traced_create

HIGH_CONFIDENCE_THRESHOLD = 0.60   # mirrors nodes.py — at/above this the KB already answers it
SKIP_SIM_THRESHOLD = 0.82          # a new signal this close to a skipped topic is treated as the same
RECURRENCE_SIM_THRESHOLD = 0.62    # a later unresolved query this close counts as the topic recurring
GAP_REASONS = {"verifier_unresolved", "negative_feedback", "fallback_threshold"}
MAX_SIGNALS = 80                   # cap the clustering prompt size (demo-safe)

CLUSTER_TOOL = {
    "name": "cluster_knowledge_gaps",
    "description": "Group similar customer knowledge-gap signals into named topics.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "description": "short topic name, in the topic's own language"},
                        "member_ids": {
                            "type": "array", "items": {"type": "integer"},
                            "description": "0-based indices of the signals belonging to this topic",
                        },
                        "representative_query": {
                            "type": "string",
                            "description": "one natural customer question that captures this topic, in its language",
                        },
                        "kb_actionable": {
                            "type": "boolean",
                            "description": (
                                "true ONLY if adding a self-service knowledge-base article would genuinely "
                                "resolve this — i.e. it is an informational question with a general answer. "
                                "false when it inherently needs a human: fee waivers / exceptions, changing "
                                "sensitive data or security settings, fraud or unauthorized transactions, "
                                "billing disputes, formal complaints, or approvals. Those are correct "
                                "escalations, NOT knowledge gaps."
                            ),
                        },
                        "rationale": {"type": "string", "description": "one short sentence explaining the grouping and the kb_actionable call"},
                    },
                    "required": ["label", "member_ids", "representative_query", "kb_actionable", "rationale"],
                },
            },
        },
        "required": ["topics"],
    },
}

CLUSTER_SYSTEM_PROMPT = """\
You are triaging knowledge gaps for a bank's AI customer-service assistant.
You are given numbered signals — questions the bot couldn't answer well,
low-satisfaction comments, and summaries of conversations a human agent took over.
Call cluster_knowledge_gaps to group them into topics of the same underlying
customer need, and for EACH topic decide kb_actionable per its rule.
Always call the tool — never reply with plain text. Every signal index should
appear in at most one topic; ignore ones too vague to group."""

DRAFT_TOOL = {
    "name": "write_faq_draft",
    "description": "Write one reusable FAQ entry for a knowledge improvement topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "the FAQ question phrased as a customer would ask it, in the topic's language"},
            "answer": {
                "type": "string",
                "description": (
                    "a clear, self-contained answer in the SAME language as the question. Ground it in the "
                    "provided agent replies and facts. Do NOT invent specific fees, rates, or policies that "
                    "are not present in the inputs — if a specific number isn't given, describe the process "
                    "or where to obtain it instead."
                ),
            },
            "tags": {"type": "string", "description": "2-4 comma-separated keyword tags"},
        },
        "required": ["question", "answer"],
    },
}

DRAFT_SYSTEM_PROMPT = """\
You write reusable FAQ entries for a bank, from real customer questions and the
human agent's actual replies. Rules:
- The answer must apply to ANY customer — REDACT and GENERALIZE any personal data
  in the agent replies (names, account numbers, amounts specific to one person).
- Ground the answer in the provided agent replies / facts; do not fabricate
  specific fees, rates, or policies not present in the inputs.
- Write the question and answer in the same language as the source.
Always call write_faq_draft — never reply with plain text."""


def _top_score(retrievers, language: str, query: str) -> float:
    r = retrievers.get(language) if retrievers else None
    if not r or not r.is_ready:
        return 0.0
    hits = r.retrieve(query, top_k=1)
    return hits[0]["score"] if hits else 0.0


def _exclude_skipped(signals: list[dict]) -> list[dict]:
    skipped = get_skipped_representative_queries()
    if not skipped or not signals:
        return signals
    model = _get_model()
    sig_emb = np.array(model.encode([s["text"] for s in signals], normalize_embeddings=True))
    skip_emb = np.array(model.encode(skipped, normalize_embeddings=True))
    return [s for s, e in zip(signals, sig_emb) if (skip_emb @ e).max() < SKIP_SIM_THRESHOLD]


def gather_signals(retrievers) -> list[dict]:
    """Current, un-skipped, still-unanswered gap signals. Each:
    {kind, language, text, agent_reply|None}."""
    raw: list[dict] = []

    for u in get_unresolved(limit=500):
        if u.get("trigger_reason") in GAP_REASONS and u.get("user_query"):
            raw.append({
                "kind": "未解決查詢", "language": u.get("language") or "zh",
                "text": u["user_query"], "agent_reply": None,
            })

    for r in get_ratings(limit=200, max_score=2):
        if r.get("comment"):
            raw.append({
                "kind": "低分回饋", "language": detect_language(r["comment"]),
                "text": r["comment"], "agent_reply": None,
            })

    for t in get_tickets(type="handoff", limit=200):
        msgs = get_handoff_messages(t["id"])
        agent = [m["content"] for m in msgs if m["role"] == "agent"]
        if not agent:
            continue  # no human answer yet → nothing to learn from
        cust = [m["content"] for m in msgs if m["role"] == "user"]
        text = " / ".join(cust) if cust else (t.get("description") or "")
        raw.append({
            "kind": "真人客服對話", "language": detect_language(text) if text else "zh",
            "text": text, "agent_reply": "\n".join(agent),
        })

    # drop what the current index already answers well (approved topics vanish here for free)
    survivors = [s for s in raw if _top_score(retrievers, s["language"], s["text"]) < HIGH_CONFIDENCE_THRESHOLD]
    survivors = _exclude_skipped(survivors)
    return survivors[:MAX_SIGNALS]


def cluster_gaps(client, model: str, signals: list[dict]) -> list[dict]:
    lines = []
    for i, s in enumerate(signals):
        extra = f"  [真人客服回覆摘要：{s['agent_reply'][:200]}]" if s.get("agent_reply") else ""
        lines.append(f"[{i}] ({s['kind']}) {s['text']}{extra}")
    result = traced_create(
        client, "gap_cluster",
        model=model, max_tokens=1500, system=CLUSTER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "Signals:\n" + "\n".join(lines)}],
        tools=[CLUSTER_TOOL], tool_choice={"type": "tool", "name": "cluster_knowledge_gaps"},
    )
    for block in result.content:
        if block.type == "tool_use":
            return block.input.get("topics", [])
    return []


def write_faq_draft(client, model: str, topic_label: str, members: list[dict]) -> dict:
    qs = "\n".join(f"- {m['text']}" for m in members)
    replies = "\n\n".join(m["agent_reply"] for m in members if m.get("agent_reply"))
    ctx = f"Topic: {topic_label}\n\nCustomer questions / signals:\n{qs}"
    if replies:
        ctx += ("\n\nHuman agent's actual replies (ground the answer in these; "
                "redact any personal data):\n" + replies)
    result = traced_create(
        client, "gap_draft",
        model=model, max_tokens=700, system=DRAFT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": ctx}],
        tools=[DRAFT_TOOL], tool_choice={"type": "tool", "name": "write_faq_draft"},
    )
    for block in result.content:
        if block.type == "tool_use":
            b = block.input
            return {"question": b["question"], "answer": b["answer"], "tags": b.get("tags")}
    return {"question": topic_label, "answer": "", "tags": None}


def _signal_summary(members: list[dict]) -> str:
    counts: dict[str, int] = {}
    for m in members:
        counts[m["kind"]] = counts.get(m["kind"], 0) + 1
    return "；".join(f"{k}×{v}" for k, v in counts.items())


def analyze(client, model: str, retrievers) -> dict:
    """Regenerate the pending draft set from current gap signals. Returns
    a small summary for the UI."""
    from ..database import clear_pending_gap_drafts, create_gap_draft
    clear_pending_gap_drafts()

    signals = gather_signals(retrievers)
    if not signals:
        return {"gap_signals": 0, "topics_total": 0, "new_drafts": 0, "excluded_topics": []}

    topics = cluster_gaps(client, model, signals)
    created = 0
    for t in topics:
        if not t.get("kb_actionable"):
            continue
        members = [signals[i] for i in t.get("member_ids", []) if 0 <= i < len(signals)]
        if not members:
            continue
        rep_q = t["representative_query"]
        language = detect_language(rep_q)
        draft = write_faq_draft(client, model, t["label"], members)
        if not draft["answer"].strip():
            continue
        create_gap_draft(
            language=language, topic=t["label"], question=draft["question"], answer=draft["answer"],
            tags=draft.get("tags"), representative_query=rep_q,
            signal_summary=_signal_summary(members), signal_count=len(members),
            pre_score=_top_score(retrievers, language, rep_q),
        )
        created += 1

    # Topics that are correct escalations (policy / needs a person) — no draft by
    # design. Reported so staff can see WHY a topic did not become a draft.
    excluded = [t["label"] for t in topics if not t.get("kb_actionable")]
    return {"gap_signals": len(signals), "topics_total": len(topics), "new_drafts": created,
            "excluded_topics": excluded}


def count_recurrence(representative_query: str, since_iso: str) -> int:
    """How many unresolved queries logged AFTER since_iso are about the
    same topic — the 'did the fix hold?' side of effectiveness."""
    rows = get_unresolved_since(since_iso)
    texts = [r["user_query"] for r in rows if r.get("user_query")]
    if not texts:
        return 0
    model = _get_model()
    rep = np.array(model.encode([representative_query], normalize_embeddings=True))[0]
    embs = np.array(model.encode(texts, normalize_embeddings=True))
    return int((embs @ rep >= RECURRENCE_SIM_THRESHOLD).sum())
