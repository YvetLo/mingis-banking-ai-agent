"""
LLM call tracing — Sprint 19 ("Tracing / 成本 / 延遲監控" on the roadmap).

Every Claude API call in this app goes through traced_create()/
traced_stream() instead of calling client.messages.* directly, so cost
and latency are measurable per call, per turn, and per session — not
just guessed at from the Anthropic Console's aggregate billing view.

Session/turn identity rides a contextvar (set once per incoming /chat
request in backend/main.py's set_trace_context()) rather than being
threaded through every function signature — call sites deep in the
graph (verifier.py, intent.py, gap_pipeline.py) never see a session_id
argument and don't need to.
"""

import contextvars
import time
from contextlib import contextmanager
from datetime import datetime

from backend.src.database import record_llm_call

# USD per 1M tokens. Only the model(s) this app actually calls need an
# entry here — see the claude-api skill's pricing table (cached
# 2026-06-24 as of writing). A model with no entry raises KeyError
# loudly rather than silently recording a wrong cost.
PRICING_PER_MTOK = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}

_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_session_id", default=None
)
_current_turn_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_turn_id", default=None
)


def set_trace_context(session_id: str | None, turn_id: str | None) -> None:
    """Called once per incoming /chat or /chat/stream request
    (backend/main.py) — every traced_create()/traced_stream() call made
    while handling that request is tagged with these ids."""
    _current_session_id.set(session_id)
    _current_turn_id.set(turn_id)


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = PRICING_PER_MTOK[model]
    return input_tokens * price["input"] / 1_000_000 + output_tokens * price["output"] / 1_000_000


def _record(node: str, model: str, input_tokens: int, output_tokens: int, latency_ms: float) -> None:
    record_llm_call(
        session_id=_current_session_id.get(),
        turn_id=_current_turn_id.get(),
        node=node,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_cost_usd(model, input_tokens, output_tokens),
        latency_ms=latency_ms,
        created_at=datetime.now().isoformat(),
    )


def traced_create(client, node: str, **kwargs):
    """Drop-in replacement for client.messages.create(**kwargs). `node`
    names the call site (e.g. "classify_intent", "qa_answer_blocking",
    "verifier", "account_tool_loop", "gap_cluster", "gap_draft") so cost
    and latency can be broken down by what the call was for."""
    start = time.monotonic()
    result = client.messages.create(**kwargs)
    latency_ms = (time.monotonic() - start) * 1000
    _record(node, kwargs["model"], result.usage.input_tokens, result.usage.output_tokens, latency_ms)
    return result


@contextmanager
def traced_stream(client, node: str, **kwargs):
    """Drop-in replacement for `with client.messages.stream(**kwargs) as
    stream:`. Only records on a clean exit — an error partway through
    the stream is not traced (see nodes.py's own error handling for
    that path); this is a cost/latency ledger, not an error log."""
    start = time.monotonic()
    with client.messages.stream(**kwargs) as stream:
        yield stream
        final = stream.get_final_message()
    latency_ms = (time.monotonic() - start) * 1000
    _record(node, kwargs["model"], final.usage.input_tokens, final.usage.output_tokens, latency_ms)
