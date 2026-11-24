"""
Intent classification regression — Evaluation Framework.

Runs golden_cases.jsonl's single-turn cases through the real
classify_intent() classifier (same call tests/test_router_intent.py's
hand-picked unit tests use) and reports two of the four v1 metrics in
docs/evaluation.md: Intent accuracy and Handoff precision/recall.
Classifying each case once (cached in _classify) means the per-case
tests and the aggregate tests below don't double the API calls.
"""

import pytest

from backend.main import MODEL, client
from backend.src.agent.intent import classify_intent

from _golden import load_cases

CASES = [c for c in load_cases() if c["category"] != "multi_turn"]

_cache: dict[str, tuple[str, str | None]] = {}


def _classify(case: dict) -> tuple[str, str | None]:
    if case["id"] not in _cache:
        _cache[case["id"]] = classify_intent(client, MODEL, case["query"])
    return _cache[case["id"]]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_intent_matches_golden_case(case):
    intent, category = _classify(case)
    assert intent == case["expected_intent"]
    if case.get("expected_handoff_category"):
        assert category == case["expected_handoff_category"]


def test_aggregate_intent_accuracy_meets_threshold():
    """CI-facing gate: a handful of individually-flaky cases shouldn't
    block, but the aggregate must stay high. See docs/evaluation.md for
    the current baseline and how to update it after a deliberate change."""
    correct = sum(1 for c in CASES if _classify(c)[0] == c["expected_intent"])
    accuracy = correct / len(CASES)
    assert accuracy >= 0.90, f"intent accuracy {accuracy:.0%} below 90% threshold"


def test_aggregate_handoff_precision_recall_meet_threshold():
    """Precision/recall computed over ALL single-turn cases, not just the
    handoff bucket — the faq/account/card_loss cases are exactly the
    negatives (should_handoff=False) that make precision meaningful."""
    tp = fp = fn = 0
    for c in CASES:
        predicted_handoff = _classify(c)[0] == "handoff"
        actual_handoff = c["should_handoff"]
        if predicted_handoff and actual_handoff:
            tp += 1
        elif predicted_handoff and not actual_handoff:
            fp += 1
        elif not predicted_handoff and actual_handoff:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    assert precision >= 0.85, f"handoff precision {precision:.0%} below 85% threshold"
    assert recall >= 0.85, f"handoff recall {recall:.0%} below 85% threshold"
