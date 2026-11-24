"""
Bill-problem clarification — 2026-11 (Mingis test build)

"我的帳單金額有問題" used to go straight to a human agent with nothing
else on the ticket. Now the bot asks WHICH item on the bill is wrong first
(BILL_CLARIFY_PROMPT), and only after the customer answers does it open
the ticket — with that answer on the queue line and in the thread.

Both turns are deterministic: the vague-complaint check runs in the Router
BEFORE classify_intent (the classifier flips between `account` and a
dispute handoff on this very sentence), and the second turn continues an
in-progress workflow. So none of these tests touch the LLM.
"""

import pytest

from backend.src.agent.nodes import (BILL_CLARIFY_PROMPT, LOGIN_REMINDER, _is_vague_bill_complaint)

ASK = "請詳細說明帳單內容哪一筆有問題？讓客服人員能立即了解您的問題及需求。（輸入「取消」可結束）"


def test_prompt_wording_is_the_one_the_business_asked_for():
    assert BILL_CLARIFY_PROMPT["zh"] == ASK


@pytest.mark.parametrize("message", [
    "我的帳單金額有問題", "帳單金額有問題", "我的信用卡帳單金額怪怪的", "my bill amount is wrong",
])
def test_vague_bill_complaints_are_detected(message):
    assert _is_vague_bill_complaint(message)


@pytest.mark.parametrize("message", [
    "我這個月帳單多少",                       # a lookup, not a complaint
    "請問帳單日是幾號",                        # FAQ
    "我的帳單有一筆我沒刷過的消費",              # fraud: must not wait behind a question
    "我被重複扣款了",                          # already names the problem
    "我的帳單有一筆 3,200 元的消費不對",         # already names the item
    "帳單分期手續費怎麼算",                     # FAQ about a fee
])
def test_specific_or_non_complaint_messages_are_not_intercepted(message):
    assert not _is_vague_bill_complaint(message)


def test_vague_bill_complaint_asks_before_escalating(client):
    r = client.post("/chat", json={"message": "我的帳單金額有問題", "session_id": "test-bill-ask"})
    assert r.status_code == 200
    d = r.json()
    assert d["response"] == ASK
    assert d["is_handoff"] is False
    assert d["handoff_ticket_id"] is None
    assert d["workflow"]["step"] == 1
    assert d["workflow"]["data"]["type"] == "bill_clarify"


def test_customer_answer_then_escalates_with_the_detail_on_the_ticket(client):
    sid = "test-bill-answer"
    complaint = "我的帳單金額有問題"
    first = client.post("/chat", json={"message": complaint, "session_id": sid}).json()
    detail = "11/03 在 XX 百貨的消費，金額跟我刷的不一樣"
    second = client.post("/chat", json={
        "message": detail,
        "session_id": sid,
        "workflow": first["workflow"],
        "history": [{"role": "user", "content": complaint},
                    {"role": "assistant", "content": first["response"]}],
    }).json()

    assert second["is_handoff"] is True
    assert second["handoff_ticket_id"]
    assert second["workflow"]["step"] == 0           # clarification closed out
    assert "真人客服" in second["response"]
    assert LOGIN_REMINDER["zh"] in second["response"]   # guest: soft login nudge as on every handoff

    thread = client.get(f"/handoff/{second['handoff_ticket_id']}/messages").json()
    assert "帳單問題" in thread["ticket"]["description"]
    assert "XX 百貨" in thread["ticket"]["description"]
    contents = [m["content"] for m in thread["messages"]]
    assert complaint in contents                       # the original complaint
    assert ASK in contents                             # what Mingis asked
    assert detail in contents                          # what the customer answered
    assert any("客戶描述：" + detail in c for c in contents)   # structured block for the agent

    unresolved = client.get("/unresolved", params={"limit": 100}).json()
    assert any(u["session_id"] == sid and u["trigger_reason"] == "handoff_dispute" for u in unresolved)


def test_customer_can_cancel_the_clarification(client):
    sid = "test-bill-cancel"
    first = client.post("/chat", json={"message": "我的帳單金額有問題", "session_id": sid}).json()
    r = client.post("/chat", json={"message": "取消", "session_id": sid, "workflow": first["workflow"]}).json()
    assert r["is_handoff"] is False
    assert r["handoff_ticket_id"] is None
    assert r["workflow"]["step"] == 0


def test_too_short_answer_is_asked_once_more_then_escalates_anyway(client):
    """Same rule as the guest intake: never trap a customer who wants a
    person in a question loop — one re-ask, then it goes through."""
    sid = "test-bill-short"
    first = client.post("/chat", json={"message": "我的帳單金額有問題", "session_id": sid}).json()
    second = client.post("/chat", json={"message": "嗯", "session_id": sid, "workflow": first["workflow"]}).json()
    assert second["is_handoff"] is False
    assert second["workflow"]["step"] == 1
    third = client.post("/chat", json={"message": "嗯", "session_id": sid, "workflow": second["workflow"]}).json()
    assert third["is_handoff"] is True
    assert third["handoff_ticket_id"]


def test_force_handoff_still_skips_the_question(client):
    """A customer who has already been stuck three times must reach a
    person, not another question."""
    r = client.post("/chat", json={
        "message": "我的帳單金額有問題", "session_id": "test-bill-force", "force_handoff": True,
    }).json()
    assert r["is_handoff"] is True
    assert r["handoff_ticket_id"]
