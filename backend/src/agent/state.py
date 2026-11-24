"""
Agent State — Sprint 6 (LangGraph)
See docs/agent_design.md §2 for the field-by-field spec this mirrors.
"""

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Conversation
    messages: list[dict]          # prior turns, {"role": "user"/"assistant", "content": str}
    user_message: str             # current turn's raw input

    # Intent & language
    intent: str                   # "faq" / "account" / "card_loss" / "handoff"
    language: str                 # "zh" or "en"

    # Identity
    user_authenticated: bool
    user_id: Optional[str]

    # Card-loss workflow (0=not started, 1=verify, 2=select card, 3=confirm, 4=done)
    workflow_step: int
    workflow_data: dict[str, Any]
    paused_workflow: bool         # this turn answered a side question mid card-loss; workflow kept

    # Escalation
    fallback_count: int
    force_handoff: bool
    handoff_reason: str            # set by Router, consumed by Handoff Node
    smalltalk_kind: str            # "greeting" / "thanks" / "bye" — set by Router, consumed by Small-talk Node

    # Session
    session_id: str

    # RAG
    rag_sources: list[str]

    # Sprint 20 — quick-reply shortcuts the frontend renders under the
    # answer ("您可能還想問"). Drawn from the KB's own FAQ lines, not
    # generated, so every one is answerable — see agent/suggestions.py.
    suggestions: list[str]

    # Logger Node input — each dict: {trigger_reason, intent, similarity_score?}
    log_entries: list[dict]

    # Outputs
    response: str
    is_negative_feedback: bool
    handoff_ticket_id: str        # set by handoff_node/qa_node escalation — see agent/handoff.py

    # Sprint 13 — set instead of `response` when the final answer hasn't
    # been generated yet: {"system": str, "messages": list[dict]}, ready
    # to hand to client.messages.create() (blocking, /chat) or
    # client.messages.stream() (streaming, /chat/stream). Lets the graph
    # stay synchronous (classify/verify/tool-calling still block) while
    # deferring only the user-facing generation call to whichever
    # endpoint the caller used.
    pending_stream: dict
