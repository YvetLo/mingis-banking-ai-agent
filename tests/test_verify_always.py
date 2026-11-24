"""
FAQ Node: every answer is grounding-checked — 2026-11 (ADR-020)

Stubs the retriever and the verifier, so no model call is made: the point is WHICH retrievals reach the
verifier, not what the verifier says. (Whether the verifier judges correctly is test_verifier.py's job.)
"""

from unittest.mock import patch

from backend.src.agent import nodes


class StubRetriever:
    is_ready = True

    def __init__(self, score: float):
        self._score = score

    def retrieve(self, query, top_k=None):
        return [{"score": self._score, "source": "credit_card_fees.md", "text": "...", "heading": ""}]

    def format_context(self, chunks):
        return "stub context"

    def suggestions_unused(self):  # pragma: no cover
        return []


def _run(score: float, verifier_says: bool, verify_always: bool):
    node = nodes.make_qa_node(client=None, retrievers={"zh": StubRetriever(score)}, kb={"zh": "kb"}, model="m", max_tokens=10)
    state = {"language": "zh", "user_message": "海外退款為什麼比較少？", "messages": [], "user_id": None,
             "user_authenticated": False, "session_id": "s-verify-always"}
    with patch.object(nodes, "VERIFY_ALWAYS", verify_always), \
         patch.object(nodes, "verify_chunks_sufficient", return_value=(verifier_says, "stub")) as verify, \
         patch.object(nodes, "escalate_to_human", return_value="T-stub") as escalate, \
         patch.object(nodes, "suggest_followups", return_value=[]):
        out = node(state)
    return out, verify, escalate


def test_a_high_score_is_still_verified_and_an_insufficient_verdict_hands_off():
    out, verify, escalate = _run(score=0.80, verifier_says=False, verify_always=True)
    verify.assert_called_once()
    escalate.assert_called_once()
    assert out["intent"] == "handoff" and out["handoff_ticket_id"] == "T-stub"


def test_a_high_score_with_a_sufficient_verdict_answers_normally():
    out, verify, escalate = _run(score=0.80, verifier_says=True, verify_always=True)
    verify.assert_called_once()
    escalate.assert_not_called()
    assert "pending_stream" in out


def test_with_the_switch_off_only_low_scores_are_verified():
    _, verify_high, _ = _run(score=0.80, verifier_says=False, verify_always=False)
    verify_high.assert_not_called()
    _, verify_low, _ = _run(score=0.40, verifier_says=False, verify_always=False)
    verify_low.assert_called_once()


def test_the_switch_defaults_to_on():
    assert nodes.VERIFY_ALWAYS is True
