"""
LLM call tracing — Sprint 19 ("Tracing / 成本 / 延遲監控").

Cost math is a pure function, tested exactly (no LLM call needed).
Session/turn tagging is verified against a real /chat call, since the
whole point is that it survives the actual request path — including
the threadpool hop under /chat/stream's sync generator.
"""

from backend.src.database import get_recent_llm_calls
from backend.src.tracing import PRICING_PER_MTOK, _cost_usd


def test_cost_calculation_matches_pricing_table():
    price = PRICING_PER_MTOK["claude-haiku-4-5"]
    assert _cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == price["input"] + price["output"]
    assert _cost_usd("claude-haiku-4-5", 0, 0) == 0.0
    # 500 input + 200 output tokens at $1/$5 per MTok
    assert _cost_usd("claude-haiku-4-5", 500_000, 200_000) == 0.5 + 1.0


def test_chat_calls_are_traced_with_matching_session_and_turn(client):
    sid = "trace-test-faq"
    r = client.post("/chat", json={"message": "信用卡年費多少?", "session_id": sid})
    assert r.status_code == 200

    calls = [row for row in get_recent_llm_calls(limit=50) if row["session_id"] == sid]
    assert calls, "expected at least one traced LLM call for this session"
    assert all(row["turn_id"] == calls[0]["turn_id"] for row in calls), \
        "every call within one /chat turn should share the same turn_id"
    for row in calls:
        assert row["cost_usd"] > 0
        assert row["latency_ms"] > 0
        assert row["input_tokens"] > 0
