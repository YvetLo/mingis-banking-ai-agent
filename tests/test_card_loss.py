"""
CardLoss Node — Sprint 8 (workflow), Sprint 9 (Router classification cost)

card_loss_workflow.py itself is pure Python state-machine logic — no
Claude call at any step — so every assertion here is exact-match. As
of Sprint 9, the FIRST message of each flow (the one that triggers the
workflow) now costs one classify_intent() call in the Router before
reaching this node; every subsequent step that answers the step's own
question still skips the classifier, because router_node checks
is_step_input() first. Only a side question mid-flow is classified
(see the side-question tests at the bottom).

Each test uses its own mock user (see mock_api/mock_data.py) so a
completed "block the card" flow in one test never collides with
another test's card state within the same pytest process.
"""


def test_card_loss_full_flow(client, customer_headers, staff_headers):
    sid, uid = "test-cardloss-full", "user_002"  # single active card: card_9012, id_last4 5678
    headers = customer_headers(uid)

    d1 = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": sid, "user_id": uid,
    }, headers=headers).json()
    assert d1["workflow"]["step"] == 1

    d2 = client.post("/chat", json={
        "message": "5678", "session_id": sid, "user_id": uid, "workflow": d1["workflow"],
    }, headers=headers).json()
    assert d2["workflow"]["step"] == 2

    d3 = client.post("/chat", json={
        "message": "1", "session_id": sid, "user_id": uid, "workflow": d2["workflow"],
    }, headers=headers).json()
    assert d3["workflow"]["step"] == 3

    d4 = client.post("/chat", json={
        "message": "確認掛失", "session_id": sid, "user_id": uid, "workflow": d3["workflow"],
    }, headers=headers).json()
    assert d4["workflow"]["step"] == 0
    assert "掛失完成" in d4["response"]

    tickets = client.get("/tickets", params={"user_id": uid}, headers=staff_headers).json()
    assert any(t["type"] == "card_loss" and t["card_id"] == "card_9012" for t in tickets)


def test_card_loss_cancel_mid_flow(client, customer_headers, staff_headers):
    sid, uid = "test-cardloss-cancel", "user_003"
    headers = customer_headers(uid)

    d1 = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": sid, "user_id": uid,
    }, headers=headers).json()
    assert d1["workflow"]["step"] == 1

    d2 = client.post("/chat", json={
        "message": "取消", "session_id": sid, "user_id": uid, "workflow": d1["workflow"],
    }, headers=headers).json()
    assert d2["workflow"] == {"step": 0, "data": {}}
    assert "取消" in d2["response"]

    tickets = client.get("/tickets", params={"user_id": uid}, headers=staff_headers).json()
    assert not any(t["type"] == "card_loss" for t in tickets)


def test_card_loss_requires_login(client):
    r = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": "test-cardloss-noauth",
    })
    d = r.json()
    assert d["workflow"]["step"] == 0
    assert "登入" in d["response"]


def test_card_loss_wrong_id_last4_retries(client, customer_headers):
    sid, uid = "test-cardloss-wrongid", "user_002"  # real id_last4 is 5678
    headers = customer_headers(uid)

    d1 = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": sid, "user_id": uid,
    }, headers=headers).json()
    assert d1["workflow"]["step"] == 1

    d2 = client.post("/chat", json={
        "message": "0000", "session_id": sid, "user_id": uid, "workflow": d1["workflow"],
    }, headers=headers).json()
    assert d2["workflow"]["step"] == 1  # stays on step 1, doesn't advance
    assert "剩" in d2["response"]  # "剩 N 次機會"


# ── Step 3 confirmation gate ──────────────────────────────────────────────────
# Pure-function tests: the gate guards an irreversible action (no
# unblock_card() exists by design), so it gets coverage independent of
# the full flow above. The two "hesitation" cases below were real
# defects — the gate used substring matching over ["確認","是","好","對",...],
# so a user expressing doubt blocked the card they were doubting.

def test_confirm_gate_accepts_only_the_full_phrase():
    from backend.src.card_loss_workflow import _is_confirm

    for phrase in ["確認掛失", "確定掛失", "confirm block", "confirm blocking",
                   "  確認掛失  ", "「確認掛失」", "確認掛失。", "Confirm Block"]:
        assert _is_confirm(phrase), f"should confirm: {phrase!r}"


def test_confirm_gate_rejects_weak_affirmatives():
    from backend.src.card_loss_workflow import _is_confirm

    # Unambiguous on their own, but too easy to say in passing for an
    # action that cannot be undone.
    for phrase in ["好", "是", "對", "ok", "yes", "確認", "confirm"]:
        assert not _is_confirm(phrase), f"should NOT confirm: {phrase!r}"


def test_confirm_gate_rejects_hesitation_and_refusal():
    from backend.src.card_loss_workflow import _is_confirm

    # Regression: these contain "好" / "確認" as substrings and used to
    # block the card.
    for phrase in ["好像不是這張", "我不確認", "不好", "我想確認一下年費",
                   "是這張嗎", "好吧我再想想"]:
        assert not _is_confirm(phrase), f"should NOT confirm: {phrase!r}"


# ── Side questions mid-flow ───────────────────────────────────────────────────
# A question the current step can't consume ("我這個月帳單多少" at step 2)
# used to be misread as a card choice and answered with "沒找到符合的卡片".
# Now it's answered as a normal turn, the workflow state is kept, and the
# reply ends with the pointer back to the paused step.

_CARDS = [{"card_id": "c1", "type": "VISA 白金卡 / VISA Platinum", "last4": "1234"},
          {"card_id": "c2", "type": "Master 一般卡 / Master Standard", "last4": "5678"}]


def test_step_input_recognizes_answers_to_the_current_step():
    from backend.src.card_loss_workflow import is_step_input

    assert is_step_input("1234", {"step": 1, "data": {}})
    assert is_step_input("第2張", {"step": 2, "data": {"cards": _CARDS}})
    assert is_step_input("末碼5678那張", {"step": 2, "data": {"cards": _CARDS}})
    assert is_step_input("白金卡", {"step": 2, "data": {"cards": _CARDS}})
    assert is_step_input("確認掛失", {"step": 3, "data": {"selected_card": _CARDS[0]}})
    for cancel in ["取消", "算了", "取消掛失", "算了吧", "cancel", "stop the block"]:
        assert is_step_input(cancel, {"step": 2, "data": {"cards": _CARDS}}), cancel


def test_step_input_rejects_side_questions():
    from backend.src.card_loss_workflow import is_step_input

    assert not is_step_input("我這個月帳單多少", {"step": 1, "data": {}})
    assert not is_step_input("我這個月帳單多少", {"step": 2, "data": {"cards": _CARDS}})
    assert not is_step_input("ATM 每天可以領多少", {"step": 3, "data": {"selected_card": _CARDS[0]}})
    # Carries a new question — not a plain cancel, so the flow isn't thrown away.
    assert not is_step_input("算了先查帳單", {"step": 2, "data": {"cards": _CARDS}})


def test_resume_prompt_points_back_to_the_paused_step():
    from backend.src.card_loss_workflow import resume_prompt

    p2 = resume_prompt({"step": 2, "data": {"cards": _CARDS}}, "zh")
    assert "掛失還沒完成" in p2 and "末碼 1234" in p2 and "末碼 5678" in p2
    p3 = resume_prompt({"step": 3, "data": {"selected_card": _CARDS[1]}}, "zh")
    assert "確認掛失" in p3 and "5678" in p3
    assert resume_prompt({"step": 0, "data": {}}, "zh") == ""


def test_side_question_mid_flow_resumes_step_2(client, customer_headers, staff_headers):
    # user_001 has two active cards (1234, 5678); id_last4 is 1234. The
    # flow is cancelled at the end, so no card is actually blocked.
    sid, uid = "test-cardloss-sidequestion", "user_001"
    headers = customer_headers(uid)

    d1 = client.post("/chat", json={
        "message": "我的卡不見了", "session_id": sid, "user_id": uid,
    }, headers=headers).json()
    d2 = client.post("/chat", json={
        "message": "1234", "session_id": sid, "user_id": uid, "workflow": d1["workflow"],
    }, headers=headers).json()
    assert d2["workflow"]["step"] == 2

    d3 = client.post("/chat", json={
        "message": "我這個月帳單多少", "session_id": sid, "user_id": uid, "workflow": d2["workflow"],
    }, headers=headers).json()
    assert d3["workflow"] == d2["workflow"]           # paused, not lost
    assert "沒找到符合的卡片" not in d3["response"]     # not misread as a card choice
    assert "掛失還沒完成" in d3["response"]             # pointer back to step 2
    assert "末碼 5678" in d3["response"]

    d4 = client.post("/chat", json={
        "message": "2", "session_id": sid, "user_id": uid, "workflow": d3["workflow"],
    }, headers=headers).json()
    assert d4["workflow"]["step"] == 3
    assert d4["workflow"]["data"]["selected_card"]["last4"] == "5678"

    d5 = client.post("/chat", json={
        "message": "取消", "session_id": sid, "user_id": uid, "workflow": d4["workflow"],
    }, headers=headers).json()
    assert d5["workflow"] == {"step": 0, "data": {}}
    tickets = client.get("/tickets", params={"user_id": uid}, headers=staff_headers).json()
    assert not any(t["type"] == "card_loss" for t in tickets)


def test_digits_inside_chinese_sentences_are_recognized():
    # Regression: \b treats CJK as word characters, so these never matched.
    from backend.src.card_loss_workflow import _4digits, _match_card

    assert _4digits("後四碼是5678") == "5678"
    assert _match_card("第2張", _CARDS)["last4"] == "5678"
    assert _match_card("末碼1234那張", _CARDS)["last4"] == "1234"
