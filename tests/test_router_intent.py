"""
Router intent classification — Sprint 9, Sprint 14 (handoff trigger rules)

Calls classify_intent() directly rather than through /chat, since it's
tested as a pure classification unit — no need to also pay for the
downstream FAQ/Account/CardLoss answering call just to check routing.
classify_intent() now returns (intent, handoff_category).
"""

from backend.main import client, MODEL
from backend.src.agent.intent import classify_intent


def test_classifies_general_question_as_faq():
    intent, _ = classify_intent(client, MODEL, "信用卡年費怎麼算?")
    assert intent == "faq"


def test_classifies_personal_account_question_as_account():
    intent, _ = classify_intent(client, MODEL, "我這個月信用卡帳單多少?")
    assert intent == "account"


def test_classifies_lost_card_as_card_loss():
    intent, _ = classify_intent(client, MODEL, "我的卡不見了")
    assert intent == "card_loss"


def test_classifies_explicit_human_request_as_handoff():
    intent, category = classify_intent(client, MODEL, "我要投訴")
    assert intent == "handoff"
    assert category == "explicit_request"


def test_negative_feedback_not_misrouted_to_handoff():
    """Regression guard: general dissatisfaction with an answer should
    stay faq/account (logged separately as negative_feedback inside the
    QA node), NOT escalate straight to Handoff."""
    intent, _ = classify_intent(client, MODEL, "你搞錯了，這不是我要的答案")
    assert intent != "handoff"


# ── Sprint 14: new handoff trigger rules ────────────────────────────────────

def test_unauthorized_transaction_is_fraud_handoff():
    intent, category = classify_intent(client, MODEL, "我的信用卡有一筆我沒刷過的交易，好像被盜刷了")
    assert intent == "handoff"
    assert category == "fraud_or_security"


def test_refund_dispute_is_handoff():
    intent, category = classify_intent(client, MODEL, "我申請退款已經兩週了還沒收到錢")
    assert intent == "handoff"
    assert category == "dispute_or_refund"


def test_fee_waiver_request_is_approval_handoff():
    intent, category = classify_intent(client, MODEL, "可以幫我減免這期的信用卡年費嗎?")
    assert intent == "handoff"
    assert category == "approval_required"


def test_loan_application_is_approval_handoff():
    intent, category = classify_intent(client, MODEL, "我要申請一筆信用貸款")
    assert intent == "handoff"
    assert category == "approval_required"


def test_loan_rate_question_stays_faq():
    """Boundary guard paired with the test above: asking what the rate
    IS (informational) must stay faq — only asking to actually APPLY
    or requesting an exception should become approval_required."""
    intent, _ = classify_intent(client, MODEL, "信用貸款的利率是多少?")
    assert intent == "faq"


def test_sensitive_data_change_is_handoff():
    intent, category = classify_intent(client, MODEL, "我要修改帳戶預留的手機號碼")
    assert intent == "handoff"
    assert category == "sensitive_data_change"


def test_hostile_urgent_message_is_emotional_distress_handoff():
    intent, category = classify_intent(client, MODEL, "這真的太離譜了，我已經等了一個小時，馬上給我解決!!")
    assert intent == "handoff"
    assert category == "emotional_distress"


def test_cross_account_question_is_complexity_handoff():
    intent, category = classify_intent(client, MODEL, "我要同時處理我先生帳戶的問題跟我自己的信用卡爭議")
    assert intent == "handoff"
    assert category == "cross_account_complexity"
