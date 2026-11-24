"""
Case record endpoints — Dashboard click-through (2026-11)

The Dashboard lists recent unresolved queries and recent tickets; a click now
opens the whole case. Two staff-only reads feed that dialog:

  GET /tickets/{id}/record          — a ticket row
  GET /cases/by-session/{session_id} — an unresolved-query row (only has a
                                       session id; may never have had a ticket)

Setup uses the bill-clarification flow (deterministic, no LLM) to get a real
escalated ticket, and the small-talk rule for a conversation that never was.
"""

ASK_COMPLAINT = "我的帳單金額有問題"
DETAIL = "上週五 XX 超市那一筆多收了"


def make_ticket(client, sid: str) -> str:
    first = client.post("/chat", json={"message": ASK_COMPLAINT, "session_id": sid}).json()
    second = client.post("/chat", json={
        "message": DETAIL, "session_id": sid, "workflow": first["workflow"],
        "history": [{"role": "user", "content": ASK_COMPLAINT},
                    {"role": "assistant", "content": first["response"]}],
    }).json()
    assert second["is_handoff"]
    return second["handoff_ticket_id"]


def test_ticket_record_has_ticket_thread_and_session_logs(client, staff_headers):
    sid = "test-case-record"
    tid = make_ticket(client, sid)
    d = client.get(f"/tickets/{tid}/record", headers=staff_headers).json()
    assert d["ticket"]["id"] == tid
    assert d["session_id"] == sid
    contents = [m["content"] for m in d["messages"]]
    assert ASK_COMPLAINT in contents and DETAIL in contents       # the whole conversation
    assert any(u["trigger_reason"] == "handoff_dispute" for u in d["unresolved"])   # why it's on the list
    assert d["ratings"] == []


def test_record_includes_the_csat_rating_for_the_same_session(client, staff_headers):
    sid = "test-case-record-rating"
    tid = make_ticket(client, sid)
    client.post("/rating", json={"session_id": sid, "score": 2, "comment": "等很久"})
    d = client.get(f"/tickets/{tid}/record", headers=staff_headers).json()
    assert [(r["score"], r["comment"]) for r in d["ratings"]] == [(2, "等很久")]


def test_by_session_finds_the_ticket(client, staff_headers):
    sid = "test-case-by-session"
    tid = make_ticket(client, sid)
    d = client.get(f"/cases/by-session/{sid}", headers=staff_headers).json()
    assert d["ticket"]["id"] == tid
    assert DETAIL in [m["content"] for m in d["messages"]]


def test_by_session_without_a_ticket_returns_the_ai_only_conversation(client, staff_headers):
    sid = "test-case-no-ticket"
    client.post("/chat", json={"message": "你好！", "session_id": sid})
    d = client.get(f"/cases/by-session/{sid}", headers=staff_headers)
    assert d.status_code == 200
    d = d.json()
    assert d["ticket"] is None and d["messages"] == []
    assert [m["content"] for m in d["chat_messages"]][0] == "你好！"


def test_by_session_unknown_session_is_empty_not_an_error(client, staff_headers):
    d = client.get("/cases/by-session/never-existed", headers=staff_headers)
    assert d.status_code == 200
    assert d.json()["ticket"] is None and d.json()["chat_messages"] == []


def test_unknown_ticket_is_404(client, staff_headers):
    assert client.get("/tickets/T-nope/record", headers=staff_headers).status_code == 404


def test_both_endpoints_are_staff_only(client, customer_headers):
    tid = make_ticket(client, "test-case-auth")
    for url in (f"/tickets/{tid}/record", "/cases/by-session/test-case-auth"):
        assert client.get(url).status_code == 401
        assert client.get(url, headers=customer_headers("demo_user1")).status_code == 403
