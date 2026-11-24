"""
Unauthorized-charge wording must route to urgent fraud handling — 2026-11

The incident: a customer wrote "帳單裡有一筆不明款項，我未消費過此筆金額" and it was filed as a routine
billing dispute (not urgent). Measured before the fix, 4 runs each: that sentence → dispute 4/4, and
"I don't recognize this transaction on my bill" → account lookup 4/4; the other ten fraud phrasings were fine.
The classifier prompt now says any charge the customer did not make / does not recognize is fraud_or_security,
and the reverse (a purchase they DID make, charged twice) stays a dispute. temperature=0 keeps it repeatable.

Calls the real Claude API (one small call per sentence, in parallel), like test_verifier.py.
"""
import pytest
from concurrent.futures import ThreadPoolExecutor

from backend.main import MODEL, client
from backend.src.agent.intent import classify_intent

FRAUD = [
    "帳單裡有一筆不明款項，我未消費過此筆金額",
    "我的信用卡有一筆我沒刷過的交易",
    "有一筆刷卡紀錄我完全不認識",
    "I don't recognize this transaction on my bill",
    "I see an unauthorized transaction",
]
NOT_FRAUD = [
    ("我被重複扣款了", ("handoff", "dispute_or_refund")),
    ("商家對我扣了兩次款", ("handoff", "dispute_or_refund")),
    ("這筆退款一直沒收到", ("handoff", "dispute_or_refund")),
    ("我這個月帳單總共多少錢", ("account", None)),
    ("我的信用卡年費多少", ("faq", None)),
]


def _run(messages):
    with ThreadPoolExecutor(max_workers=5) as ex:
        return list(ex.map(lambda m: classify_intent(client, MODEL, m), messages))


def test_unauthorized_charge_wording_is_fraud():
    results = _run(FRAUD)
    wrong = [(m, r) for m, r in zip(FRAUD, results) if r != ("handoff", "fraud_or_security")]
    assert not wrong, wrong


def test_the_customers_own_duplicate_charge_is_not_fraud():
    results = _run([m for m, _ in NOT_FRAUD])
    wrong = [(m, r, exp) for (m, exp), r in zip(NOT_FRAUD, results) if r != exp]
    assert not wrong, wrong
