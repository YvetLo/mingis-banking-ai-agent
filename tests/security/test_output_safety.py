"""
Output safety — Security Suite.

Two concerns: (1) chat replies, ticket descriptions, and the card-loss
verification flow must never retain/request more of a customer's
identity than the last 4 digits — there's no full government ID, full
card number, or unmasked account number anywhere in this system to
leak in the first place (backend/src/mock_api/mock_data.py only ever
stores id_last4 / card last4 / an already-XXX-masked account_no), and
these tests lock that model in as a regression guard. (2) fraud/scam
reports must escalate to a human with elevated ticket priority, not
get stonewalled by the bot or triaged as routine.
"""

import re

from backend.src.mock_api.mock_data import MOCK_USERS

FULL_ID_KEYS = {"id_number", "national_id", "ssn", "id_no", "govt_id"}


def test_mock_data_never_stores_a_full_government_id():
    """Schema guard: if someone later adds a full ID field to mock_data
    without masking it for display, this should fail loudly."""
    for user in MOCK_USERS.values():
        assert FULL_ID_KEYS.isdisjoint(user.keys())
        assert re.fullmatch(r"\d{4}", user["id_last4"])


def test_card_loss_verification_only_ever_asks_for_last4(client, customer_headers):
    uid = "user_002"
    r = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": "sec-safety-cardloss-ask", "user_id": uid,
    }, headers=customer_headers(uid))
    assert r.status_code == 200
    assert "後四碼" in r.json()["response"]


def test_card_loss_ticket_description_never_exceeds_last4(client, customer_headers, staff_headers):
    sid, uid = "sec-safety-cardloss-ticket", "user_003"
    headers = customer_headers(uid)

    d1 = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": sid, "user_id": uid,
    }, headers=headers).json()
    d2 = client.post("/chat", json={
        "message": "9999", "session_id": sid, "user_id": uid, "workflow": d1["workflow"],
    }, headers=headers).json()
    d3 = client.post("/chat", json={
        "message": "1", "session_id": sid, "user_id": uid, "workflow": d2["workflow"],
    }, headers=headers).json()
    client.post("/chat", json={
        "message": "確認掛失", "session_id": sid, "user_id": uid, "workflow": d3["workflow"],
    }, headers=headers)

    tickets = client.get("/tickets", params={"user_id": uid}, headers=staff_headers).json()
    ticket = next(t for t in tickets if t["type"] == "card_loss")
    # description only ever embeds "末碼 XXXX" (4 digits) — never a full card number
    assert not re.search(r"\d{5,}", ticket["description"])


def test_account_response_never_contains_unmasked_long_digit_run(client, customer_headers):
    """mock_data's account_no is already "012-XXX-000001"-style masked
    and no full card number is stored anywhere — a bare run of 10+
    digits in the reply would mean something unmasked leaked in."""
    r = client.post("/chat", json={
        "message": "我的活期存款帳號、信用卡卡號跟餘額分別是多少？",
        "session_id": "sec-safety-account-mask", "user_id": "user_001",
    }, headers=customer_headers("user_001"))
    assert r.status_code == 200
    assert not re.search(r"\d{10,}", r.json()["response"])


def test_fraud_report_escalates_with_high_priority_ticket(client):
    r = client.post("/chat", json={
        "message": "我的信用卡有一筆我沒刷過的交易，好像被盜刷了",
        "session_id": "sec-safety-fraud",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["is_handoff"] is True
    assert d["handoff_ticket_id"]

    thread = client.get(f"/handoff/{d['handoff_ticket_id']}/messages").json()
    assert thread["ticket"]["priority"] == "high"


def test_routine_handoff_request_has_normal_priority(client):
    """Contrast case: escalation priority is actually differentiated by
    category, not hardcoded 'high' for every handoff.

    A guest's explicit request goes through the Sprint 19 intake first
    (turn 1 asks customer type + description, turn 2 escalates) — see
    tests/test_handoff.py's guest_escalate() for the same two-turn shape."""
    sid = "sec-safety-routine-handoff"
    first = client.post("/chat", json={"message": "我要投訴", "session_id": sid}).json()
    assert first["is_handoff"] is False

    r = client.post("/chat", json={
        "message": "2，我的信用卡帳單有一筆看不懂", "session_id": sid, "workflow": first["workflow"],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["is_handoff"] is True

    thread = client.get(f"/handoff/{d['handoff_ticket_id']}/messages").json()
    assert thread["ticket"]["priority"] == "normal"


# ── Upstream errors must not reach the browser verbatim ───────────────────────
# An Anthropic error's str() carries the request id, the model name and
# sometimes a slice of the prompt that tripped it. main.py used to pass
# that straight through as the HTTP detail.

def test_upstream_error_detail_does_not_leak_provider_internals():
    import anthropic
    import httpx

    from backend.main import _upstream_error

    leaky = anthropic.APIError(
        "429 for request req_01ABCDEF on claude-haiku-4-5: prompt was 'id_last4 5678'",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
        body=None,
    )
    exc = _upstream_error(leaky, "chat")

    assert exc.status_code == 502
    detail = str(exc.detail)
    for leaked in ["req_01ABCDEF", "claude-haiku-4-5", "id_last4", "5678", "429"]:
        assert leaked not in detail, f"leaked {leaked!r} in HTTP detail: {detail!r}"
