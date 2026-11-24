"""
FAQ Node — Sprint 8, Sprint 12 (grounding verifier escalation)

These tests call the real Claude API (via the `client` session fixture),
so assertions are structural (routing, RAG sources, DB side-effects) —
never on the exact wording of an LLM-generated answer. See
docs/design_journal.md Sprint 8 entry for why response *quality* is a
manual checklist item, not a pytest assertion.
"""

from backend.src.agent.nodes import LOGIN_REMINDER, VERIFIER_ESCALATION_MSG, _retrieval_query


def test_retrieval_query_folds_in_prior_user_turn():
    """Sprint 19 RAG fix — see docs/evaluation.md "已知落差". Pure
    function, no LLM/retriever involved, so this stays exact-match."""
    messages = [
        {"role": "user", "content": "信用卡有哪些回饋?"},
        {"role": "assistant", "content": "現金回饋、紅利點數..."},
    ]
    assert _retrieval_query(messages, "那年費呢?") == "信用卡有哪些回饋? 那年費呢?"


def test_retrieval_query_unchanged_on_first_turn():
    assert _retrieval_query([], "信用卡年費多少?") == "信用卡年費多少?"


def test_faq_zh_credit_card_fee(client):
    r = client.post("/chat", json={
        "message": "信用卡年費怎麼算?", "session_id": "test-faq-zh",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["language"] == "zh"
    assert d["response"]
    assert d["is_handoff"] is False
    assert any("credit_card_fees" in s for s in d["rag_sources"])


def test_faq_en_credit_card_fee(client):
    r = client.post("/chat", json={
        "message": "What is the annual fee for the credit card?", "session_id": "test-faq-en",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["language"] == "en"
    assert d["response"]
    assert any("credit_card_fees" in s for s in d["rag_sources"])


def test_negative_feedback_and_verifier_dual_log(client):
    """
    Regression test for the Sprint 6 edge case: a single turn can fire
    BOTH the negative-feedback log entry and a retrieval-quality log
    entry. Sprint 6 deliberately preserved this "one turn, two log rows"
    behavior from the original if/else handler; Sprint 12 replaced the
    retrieval-quality signal (rag_low_similarity, a bare threshold check)
    with verifier_unresolved (an actual groundedness judgment) — see
    docs/design_journal.md Sprint 12 entry — but the dual-log behavior
    itself is unchanged.
    """
    sid = "test-faq-dual-log"
    r = client.post("/chat", json={
        "message": "你搞錯了，這不是我要的答案", "session_id": sid,
    })
    assert r.status_code == 200
    assert r.json()["is_negative_feedback"] is True

    unresolved = client.get("/unresolved", params={"limit": 100}).json()
    reasons = {u["trigger_reason"] for u in unresolved if u["session_id"] == sid}
    assert "negative_feedback" in reasons
    assert "verifier_unresolved" in reasons


def test_ungrounded_faq_escalates_to_handoff(client):
    """
    Full-pipeline regression test for the verifier's escalation path.
    Insurance products are not covered by any knowledge base article —
    the closest chunks are about credit card benefits, which don't
    answer whether the bank even sells insurance. The verifier should
    catch this and escalate instead of returning an ungrounded draft.

    Uses VERIFIER_ESCALATION_MSG, not HANDOFF_MSG — this is the AI
    proactively deciding it can't help, not a reply to a user who asked
    for or complained their way to a human, so the tone is deliberately
    different (see nodes.py).
    """
    sid = "test-faq-verifier-escalation"
    r = client.post("/chat", json={
        "message": "銀行有賣保險產品嗎?", "session_id": sid,
    })
    assert r.status_code == 200
    d = r.json()
    # Guest session (no user_id) — soft login reminder gets appended
    # (2026-08-01 follow-up), see nodes.LOGIN_REMINDER.
    assert d["response"] == f"{VERIFIER_ESCALATION_MSG['zh']}\n\n{LOGIN_REMINDER['zh']}"
    assert d["is_handoff"] is True

    unresolved = client.get("/unresolved", params={"limit": 100}).json()
    matching = [u for u in unresolved if u["session_id"] == sid]
    assert any(u["trigger_reason"] == "verifier_unresolved" for u in matching)


def test_fx_exchange_now_answered_directly(client):
    """
    The diagnostic case study's original finding was that this exact
    question had no matching KB content — three retrieved chunks each
    scored above any reasonable similarity threshold, but none of them
    were actually about foreign currency exchange, and the system
    escalated. A knowledge_base/{zh,en}/foreign_currency_exchange.md
    article was added to close that specific gap; this locks in that
    the fix actually took (the exact original finding is now answered
    directly, not escalated).
    """
    r = client.post("/chat", json={
        "message": "外幣現鈔要去哪裡換，匯率怎麼算?", "session_id": "test-faq-fx-fixed",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["is_handoff"] is False
    assert any("foreign_currency_exchange" in s for s in d["rag_sources"])


def test_live_rate_question_answers_with_url_not_handoff(client):
    """
    "What's the USD rate right now" was still escalating even after the
    FX topic gap was fixed, because the verifier correctly noted the KB
    has no fixed rate number (rates change daily — hardcoding one would
    go stale). The fix isn't a bigger KB article, it's telling the
    verifier that a live-lookup URL is a valid answer for genuinely
    dynamic data, and telling the KB content to always include that URL.
    """
    r = client.post("/chat", json={
        "message": "美金匯率多少？", "session_id": "test-faq-live-rate-url",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["is_handoff"] is False
    assert "future-bank.com.tw/exchange-rate" in d["response"]
