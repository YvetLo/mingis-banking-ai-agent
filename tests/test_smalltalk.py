"""
Small-talk (greeting / thanks / goodbye) — 2026-11 (Mingis build)

"你好！" used to be read as an FAQ question: retrieval score ~0.24, the
grounding verifier found nothing to answer with, and the customer was
transferred to a human agent on their very first message (the same thing
happened to "Hi" in October). A bare greeting now gets a canned reply from
the Router's deterministic rule — no LLM call, no ticket, and nothing logged
as unresolved (it isn't a failure, so it must not become a knowledge gap).
"""

import pytest

from backend.src.agent.nodes import SMALLTALK_REPLY, _match_smalltalk


@pytest.mark.parametrize("message, kind, lang", [
    ("你好！", "greeting", "zh"), ("你好", "greeting", "zh"), ("哈囉！！", "greeting", "zh"),
    ("嗨", "greeting", "zh"), ("早安", "greeting", "zh"),
    ("Hi", "greeting", "en"), ("hello!", "greeting", "en"), ("Hi Mingis 😊", "greeting", "en"),
    ("good morning", "greeting", "en"),
    ("謝謝～", "thanks", "zh"), ("謝謝您", "thanks", "zh"), ("Thank you!", "thanks", "en"), ("thanks a lot.", "thanks", "en"),
    ("掰掰", "bye", "zh"), ("Goodbye", "bye", "en"),
])
def test_pure_greetings_thanks_and_goodbyes_are_matched(message, kind, lang):
    assert _match_smalltalk(message) == (kind, lang)


@pytest.mark.parametrize("message", [
    "你好，信用卡年費多少？",              # a greeting AND a question: a real question
    "Hi, what is the annual fee?",
    "謝謝，但我還想問帳單",
    "hello mingis, my card was stolen",   # must never be swallowed — card loss / fraud
    "我要找真人客服",
    "！！！", "",
])
def test_messages_with_real_content_are_not_matched(message):
    assert _match_smalltalk(message) is None


def test_greeting_gets_a_friendly_reply_not_a_transfer(client):
    r = client.post("/chat", json={"message": "你好！", "session_id": "test-smalltalk-hi"})
    assert r.status_code == 200
    d = r.json()
    assert d["response"] == SMALLTALK_REPLY["greeting"]["zh"]
    assert d["is_handoff"] is False
    assert d["handoff_ticket_id"] is None
    assert d["language"] == "zh"


def test_english_greeting_gets_an_english_reply(client):
    d = client.post("/chat", json={"message": "Hi", "session_id": "test-smalltalk-en"}).json()
    assert d["response"] == SMALLTALK_REPLY["greeting"]["en"]
    assert d["is_handoff"] is False
    assert d["language"] == "en"


def test_thanks_and_bye_get_their_own_replies(client):
    t = client.post("/chat", json={"message": "謝謝", "session_id": "test-smalltalk-thanks"}).json()
    b = client.post("/chat", json={"message": "掰掰", "session_id": "test-smalltalk-bye"}).json()
    assert t["response"] == SMALLTALK_REPLY["thanks"]["zh"]
    assert b["response"] == SMALLTALK_REPLY["bye"]["zh"]
    assert not t["is_handoff"] and not b["is_handoff"]


def test_smalltalk_is_not_logged_as_unresolved(client):
    """A greeting is not a failure — it must not feed the knowledge-improvement pipeline."""
    sid = "test-smalltalk-not-logged"
    client.post("/chat", json={"message": "你好！", "session_id": sid})
    unresolved = client.get("/unresolved", params={"limit": 200}).json()
    assert not any(u["session_id"] == sid for u in unresolved)


def test_force_handoff_still_wins_over_a_greeting(client):
    """A customer already stuck three times who then says 你好 still gets a person."""
    d = client.post("/chat", json={"message": "你好", "session_id": "test-smalltalk-force",
                                   "force_handoff": True}).json()
    assert d["is_handoff"] is True


def test_greeting_does_not_interrupt_card_loss_flow(client, customer_headers):
    """Mid-workflow input keeps its in-progress meaning (the workflow check runs first)."""
    sid = "test-smalltalk-workflow"
    first = client.post("/chat", json={"message": "我要掛失信用卡", "session_id": sid, "user_id": "demo_user1"},
                        headers=customer_headers("demo_user1")).json()
    assert first["workflow"]["step"] == 1
    r = client.post("/chat", json={"message": "你好", "session_id": sid, "user_id": "demo_user1",
                                   "workflow": first["workflow"]},
                    headers=customer_headers("demo_user1")).json()
    assert r["response"] != SMALLTALK_REPLY["greeting"]["zh"]
