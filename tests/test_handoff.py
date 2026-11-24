"""
Handoff Node — Sprint 8, Sprint 15 (real agent conversation)

handoff_node itself returns a hardcoded template (prompts.HANDOFF_MSG)
— no Claude call there — so the response text is asserted exactly.
As of Sprint 9, reaching this node via keyword-style intent (rather
than force_handoff) costs one small classify_intent() call in the
Router — see test_router_intent.py for why that trade was made.
force_handoff still bypasses the classifier entirely (checked before
classify_intent in router_node), so that path stays zero-cost.

Sprint 15's /handoff/* endpoints are pure DB operations (no LLM call),
so those tests are free regardless of which path created the ticket.

Sprint 15 follow-up (2026-08-01): every handoff reply gets a soft login
reminder appended when the session is a guest (see nodes.LOGIN_REMINDER)
— all of these tests use guest sessions, so the exact-match assertions
below include it.

Sprint 19: a GUEST who explicitly asks for a human is asked for customer
type + a one-line problem description before the ticket opens (see
nodes.handoff_intake_node), so guest escalations here go through
`guest_escalate()` — two turns, not one. Every other path (authenticated
user, force_handoff, fraud/sensitive-data categories) still escalates on
the first turn, and the tests below assert exactly that.
"""

from backend.src.agent.nodes import (INTAKE_DONE, INTAKE_PROMPT, LOGIN_REMINDER,
                                     SENSITIVE_DATA_HANDOFF_MSG)
from backend.src.prompts import HANDOFF_MSG

GUEST_HANDOFF_MSG = f"{HANDOFF_MSG['zh']}\n\n{LOGIN_REMINDER['zh']}"

INTAKE_REPLY = "2，我的信用卡帳單有一筆看不懂"
GUEST_INTAKE_DONE_MSG = (
    f"{INTAKE_DONE['zh'].format(type_label='信用卡客戶')}\n\n{LOGIN_REMINDER['zh']}"
)


def guest_escalate(client, session_id: str, message: str = "我要投訴", reply: str = INTAKE_REPLY):
    """Drive a guest through the Sprint 19 intake to an actual ticket:
    turn 1 asks the two questions, turn 2 answers them and escalates.
    Returns turn 2's response payload."""
    first = client.post("/chat", json={"message": message, "session_id": session_id}).json()
    assert first["is_handoff"] is False, "intake should ask before opening a ticket"
    second = client.post("/chat", json={
        "message": reply,
        "session_id": session_id,
        "workflow": first["workflow"],
        # same as the frontend: the intake Q&A is ordinary conversation
        # history, so it ends up in the seeded thread too
        "history": [{"role": "user", "content": message},
                    {"role": "assistant", "content": first["response"]}],
    })
    assert second.status_code == 200
    return second.json()


def test_guest_explicit_request_collects_intake_before_escalating(client):
    """The reported gap (2026-08-12): a guest typing '我要找真人客服' used
    to open a ticket with no identity and no problem statement, leaving
    the agent to start from zero. Turn 1 must ask, not escalate."""
    sid = "test-handoff-intake-ask"
    r = client.post("/chat", json={"message": "我要找真人客服", "session_id": sid})
    assert r.status_code == 200
    d = r.json()
    assert d["response"] == INTAKE_PROMPT["zh"]
    assert d["is_handoff"] is False
    assert d["handoff_ticket_id"] is None
    assert d["workflow"]["step"] == 1
    assert d["workflow"]["data"]["type"] == "handoff_intake"


def test_guest_intake_answer_escalates_with_collected_context(client):
    sid = "test-handoff-intake-answer"
    d = guest_escalate(client, sid)
    assert d["response"] == GUEST_INTAKE_DONE_MSG
    assert d["is_handoff"] is True
    assert d["handoff_ticket_id"]
    assert d["workflow"]["step"] == 0   # intake flow closed out

    # what the agent picks up: type + description on the queue line, and
    # the same as a structured block inside the thread
    ticket_id = d["handoff_ticket_id"]
    thread = client.get(f"/handoff/{ticket_id}/messages").json()
    assert "信用卡客戶" in thread["ticket"]["description"]
    assert any("客戶類別：信用卡客戶" in m["content"] for m in thread["messages"])
    assert any("我的信用卡帳單有一筆看不懂" in m["content"] for m in thread["messages"])

    unresolved = client.get("/unresolved", params={"limit": 100}).json()
    matching = [u for u in unresolved if u["session_id"] == sid]
    assert any(u["trigger_reason"] == "handoff_intent" for u in matching)


def test_guest_intake_can_be_cancelled(client):
    """Someone who changes their mind mid-form must land back in the
    normal AI conversation, not in a ticket."""
    sid = "test-handoff-intake-cancel"
    first = client.post("/chat", json={"message": "我要找真人客服", "session_id": sid}).json()
    r = client.post("/chat", json={
        "message": "取消", "session_id": sid, "workflow": first["workflow"],
    }).json()
    assert r["is_handoff"] is False
    assert r["handoff_ticket_id"] is None
    assert r["workflow"]["step"] == 0


def test_authenticated_explicit_request_skips_intake(client, customer_headers):
    """A logged-in customer is already identified and their account is
    already on the ticket — asking them to self-classify would be pure
    friction, so they escalate on the first turn as before."""
    r = client.post("/chat", json={
        "message": "我要投訴", "session_id": "test-handoff-intake-skip", "user_id": "demo_user1",
    }, headers=customer_headers("demo_user1"))
    assert r.status_code == 200
    d = r.json()
    assert d["is_handoff"] is True
    assert d["handoff_ticket_id"]
    assert d["response"] == HANDOFF_MSG["zh"]


def test_handoff_force_flag(client):
    """Frontend sets force_handoff=True once fallback_count hits the
    threshold — this must bypass the classifier entirely, not just
    happen to agree with it."""
    r = client.post("/chat", json={
        "message": "隨便問個問題", "session_id": "test-handoff-force", "force_handoff": True,
    })
    assert r.status_code == 200
    d = r.json()
    assert d["response"] == GUEST_HANDOFF_MSG
    assert d["is_handoff"] is True
    assert d["handoff_ticket_id"]


def test_handoff_ticket_seeded_with_conversation_thread(client):
    """The ticket created on escalation should already have the
    triggering message + the bot's own escalation reply in its thread,
    so an agent picking it up has context without asking the customer
    to repeat themselves."""
    sid = "test-handoff-seed"
    ticket_id = guest_escalate(client, sid)["handoff_ticket_id"]

    thread = client.get(f"/handoff/{ticket_id}/messages").json()
    assert thread["ticket"]["id"] == ticket_id
    assert thread["ticket"]["status"] == "open"
    assert thread["ticket"]["type"] == "handoff"

    roles = [m["role"] for m in thread["messages"]]
    assert "user" in roles
    assert "assistant" in roles
    assert any(m["content"] == "我要投訴" for m in thread["messages"])
    assert any(m["content"] == GUEST_INTAKE_DONE_MSG for m in thread["messages"])


def test_handoff_agent_reply_then_resolve(client, staff_headers):
    """Full lifecycle: customer follow-up + agent reply both land in
    the same thread in order, then resolving flips the ticket status —
    this is what frontend/app.py's handoff view and the Agent Console
    page both read/write through. The agent reply and the resolve are
    staff actions (Sprint 19 auth); the customer's own follow-up is not."""
    sid = "test-handoff-lifecycle"
    ticket_id = guest_escalate(client, sid)["handoff_ticket_id"]

    resp = client.post(f"/handoff/{ticket_id}/messages", json={"role": "user", "content": "還有其他問題"})
    assert resp.status_code == 200

    resp = client.post(f"/handoff/{ticket_id}/messages",
                        json={"role": "agent", "content": "您好，我是客服專員"}, headers=staff_headers)
    assert resp.status_code == 200

    thread = client.get(f"/handoff/{ticket_id}/messages").json()
    contents = [m["content"] for m in thread["messages"]]
    assert contents.index("還有其他問題") < contents.index("您好，我是客服專員")
    assert thread["ticket"]["status"] == "open"

    resolve_resp = client.post(f"/handoff/{ticket_id}/resolve", headers=staff_headers)
    assert resolve_resp.status_code == 200

    thread_after = client.get(f"/handoff/{ticket_id}/messages").json()
    assert thread_after["ticket"]["status"] == "resolved"


def test_handoff_tickets_list_filters_by_status(client, staff_headers):
    sid = "test-handoff-list-filter"
    ticket_id = guest_escalate(client, sid)["handoff_ticket_id"]

    open_tickets = client.get("/handoff/tickets", params={"status": "open", "limit": 100},
                               headers=staff_headers).json()
    assert any(t["id"] == ticket_id for t in open_tickets)

    client.post(f"/handoff/{ticket_id}/resolve", headers=staff_headers)

    open_tickets_after = client.get("/handoff/tickets", params={"status": "open", "limit": 100},
                                     headers=staff_headers).json()
    assert not any(t["id"] == ticket_id for t in open_tickets_after)

    resolved_tickets = client.get("/handoff/tickets", params={"status": "resolved", "limit": 100},
                                   headers=staff_headers).json()
    assert any(t["id"] == ticket_id for t in resolved_tickets)


def test_handoff_message_to_unknown_ticket_404s(client):
    resp = client.post("/handoff/T-NOPE-999/messages", json={"role": "user", "content": "hi"})
    assert resp.status_code == 404


def test_sensitive_data_handoff_uses_dedicated_message(client):
    """2026-08-01 manual-testing fix: sensitive_data_change previously
    fell through to the generic apologetic HANDOFF_MSG, which read like
    the AI had failed to answer — it hasn't, this is policy (identity
    changes always need a human). Guest session, so the login reminder
    is still appended on top of the dedicated message."""
    sid = "test-handoff-sensitive-data"
    r = client.post("/chat", json={"message": "我要修改帳戶預留的手機號碼", "session_id": sid})
    assert r.status_code == 200
    d = r.json()
    assert d["response"] == f"{SENSITIVE_DATA_HANDOFF_MSG['zh']}\n\n{LOGIN_REMINDER['zh']}"
    assert d["is_handoff"] is True


def test_authenticated_handoff_has_no_login_reminder(client, customer_headers):
    """The login reminder is only useful (and only shown) for guests —
    an already-logged-in user doesn't need to be told to log in."""
    r = client.post("/chat", json={
        "message": "我要投訴", "session_id": "test-handoff-authenticated", "user_id": "demo_user1",
    }, headers=customer_headers("demo_user1"))
    assert r.status_code == 200
    assert r.json()["response"] == HANDOFF_MSG["zh"]


def test_link_user_attaches_identity_to_guest_ticket(client, customer_headers):
    """Mirrors frontend/app.py's login handler: a guest escalates, then
    logs in while the handoff conversation is still open — the ticket
    should pick up their user_id without needing a new ticket. Sprint 19
    requires the caller's token to match the user_id being linked."""
    sid = "test-handoff-link-user"
    ticket_id = guest_escalate(client, sid)["handoff_ticket_id"]

    thread = client.get(f"/handoff/{ticket_id}/messages").json()
    assert thread["ticket"]["user_id"] is None

    link_resp = client.post(f"/handoff/{ticket_id}/link-user", json={"user_id": "demo_user1"},
                             headers=customer_headers("demo_user1"))
    assert link_resp.status_code == 200
    assert link_resp.json()["linked"] is True

    thread_after = client.get(f"/handoff/{ticket_id}/messages").json()
    assert thread_after["ticket"]["user_id"] == "demo_user1"


def test_link_user_does_not_overwrite_existing_identity(client, customer_headers):
    """Safety guard: linking must never reassign an already-identified
    ticket to a different account."""
    r = client.post("/chat", json={
        "message": "我要投訴", "session_id": "test-handoff-link-existing", "user_id": "demo_user2",
    }, headers=customer_headers("demo_user2"))
    ticket_id = r.json()["handoff_ticket_id"]

    link_resp = client.post(f"/handoff/{ticket_id}/link-user", json={"user_id": "demo_user1"},
                             headers=customer_headers("demo_user1"))
    assert link_resp.status_code == 200
    assert link_resp.json()["linked"] is False

    thread = client.get(f"/handoff/{ticket_id}/messages").json()
    assert thread["ticket"]["user_id"] == "demo_user2"


def test_link_user_to_unknown_ticket_404s(client, customer_headers):
    resp = client.post("/handoff/T-NOPE-999/link-user", json={"user_id": "demo_user1"},
                        headers=customer_headers("demo_user1"))
    assert resp.status_code == 404
