"""
Quick-reply suggestions — Sprint 20.

The feature's whole premise is "a shortcut we show is a shortcut we can
answer", so these tests are mostly about what must NOT be offered:
questions the live index can't answer confidently, and questions that
just repeat what the customer typed.

The retrieval-score filter runs against the real index (same one the
FAQ Node uses) but costs no LLM call, so it's cheap to assert on here.
What is NOT asserted: that a given question is in the shipped list —
the pool is content, and it changes with the knowledge base. Whether
each shipped question actually gets answered rather than escalated is a
live check (see docs/design_journal.md Sprint 20), for the same reason
the reindex and gap-analysis paths stay out of pytest.
"""

import itertools

from backend.src.agent import suggestions as S

THRESHOLD = S.HIGH_CONFIDENCE_THRESHOLD


def _retriever(client, language="zh"):
    """The live retriever the app itself uses — the client fixture's
    startup event has already loaded it."""
    from backend.main import retrievers
    return retrievers[language]


def test_starters_are_all_answerable(client):
    """A welcome-screen shortcut that escalates would make the bot's very
    first suggestion a dead end."""
    r = _retriever(client)
    picked = S.starters(r, "zh", authenticated=False)
    assert picked, "guest should always get starter shortcuts"
    for question in picked:
        assert S._answerable(r, "zh", question), f"{question} would not be answered confidently"


def test_authenticated_starters_lead_with_account_questions(client):
    """Someone who just logged in did it to see their own data — the
    account questions belong first, and they're exempt from the retrieval
    check because the Account Node doesn't use the knowledge base."""
    picked = S.starters(_retriever(client), "zh", authenticated=True)
    assert picked[0] in S.ACCOUNT_SUGGESTIONS["zh"]
    assert any(q in S.FAQ_STARTERS["zh"] for q in picked), "should still surface FAQ topics too"


def test_followups_come_from_the_topic_that_was_retrieved(client):
    """Follow-ups extend the topic the customer is actually in, not a
    generic popular list."""
    picked = S.suggest_followups(
        _retriever(client), "zh", ["credit_card_fees.md"], "信用卡年費多少？",
    )
    assert picked
    assert all(q in S.TOPIC_FOLLOWUPS["zh"]["credit_card_fees.md"] for q in picked)


def test_followups_never_echo_the_question_just_asked(client):
    """Offering back a near-identical question reads like the bot wasn't
    listening — '網銀怎麼開通' must not be answered with '網路銀行要怎麼開通？'."""
    picked = S.suggest_followups(
        _retriever(client), "zh", ["digital_banking.md"], "網銀怎麼開通",
    )
    assert "網路銀行要怎麼開通？" not in picked


def test_followups_fall_back_to_starters_for_a_topic_with_none(client):
    """kb_entries added through the maintenance UI have no curated
    follow-ups (their 'source' is the entry title, not a file) — better a
    working shortcut on another topic than an empty row."""
    picked = S.suggest_followups(
        _retriever(client), "zh", ["存摺遺失要怎麼補辦？"], "存摺掉了",
    )
    assert picked
    assert all(q in S.FAQ_STARTERS["zh"] for q in picked)


def test_unready_retriever_yields_no_suggestions(client):
    """Before the index is built there is nothing we can promise to
    answer, so nothing is offered — not an unchecked list."""
    class NotReady:
        is_ready = False
    assert S.suggest_followups(NotReady(), "zh", ["credit_card_fees.md"], "年費") == []
    assert S.starters(NotReady(), "zh", authenticated=False) == []


def test_every_curated_faq_suggestion_clears_the_threshold(client):
    """The guarantee, asserted over the whole shipped pool: if a knowledge
    base change makes one of these unanswerable, this test says which."""
    r = _retriever(client)
    pool = set(itertools.chain(*S.TOPIC_FOLLOWUPS["zh"].values())) | set(S.FAQ_STARTERS["zh"])
    below = [q for q in sorted(pool) if not S._answerable(r, "zh", q)]
    assert not below, f"below {THRESHOLD} — would escalate instead of answering: {below}"


def test_account_followups_skip_what_was_just_asked(client):
    """There are only three account questions, so the one just answered
    has to go — and the row is topped up from the verified FAQ starters
    rather than left short."""
    picked = S.account_followups(_retriever(client), "zh", "我的帳戶餘額還有多少？")
    assert "我的帳戶餘額還有多少？" not in picked
    assert len(picked) == S.MAX_SUGGESTIONS


def test_starters_endpoint(client):
    r = client.get("/suggestions", params={"language": "zh", "authenticated": False})
    assert r.status_code == 200
    assert r.json()["suggestions"]


def test_chat_response_carries_followups(client):
    """The frontend reads these off /chat (and off X-Suggestions on the
    streaming endpoint) — a FAQ answer should come with somewhere to go next."""
    r = client.post("/chat", json={"message": "信用卡年費多少？", "session_id": "test-suggest-chat"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_handoff"] is False
    assert body["suggestions"], "a confidently answered FAQ should offer follow-ups"
