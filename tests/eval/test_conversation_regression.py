"""
Multi-turn conversation regression — Evaluation Framework.

Chains golden_cases.jsonl's multi_turn cases through /chat exactly like
a real client would (turn 1's response + workflow feed into turn 2's
history/workflow — see tests/test_handoff.py's guest_escalate() for the
same pattern), and checks the FINAL turn's behavior: does a short
pronoun-only follow-up ("那年費呢?") still land on the right
topic/tool, not get misrouted by losing context.

Known limitation, not xfail-marked (see docs/evaluation.md "已知落差"):
retriever.retrieve() (backend/src/agent/nodes.py qa_node) embeds only
the CURRENT turn, so a pronoun-only follow-up with no topic word of its
own often lands near/under HIGH_CONFIDENCE_THRESHOLD (0.60) — three of
this file's four cases do (0.475 / 0.620 / 0.592 measured directly
against the retriever). Below that line the verifier's own LLM judgment
decides whether to answer or escalate, and that judgment isn't
perfectly deterministic — repeated full-suite runs showed different
cases failing each time, never the same one twice. An xfail(strict=True)
on any single case is actively wrong here: it assumes a deterministic
failure and errors out the run the model happens to get it right. A
solitary red in this file is expected noise from testing a live LLM's
judgment on a genuinely borderline case, not a regression by itself —
treat it as a regression only if it fails two runs in a row.
"""

import pytest

from _golden import load_cases

CASES = load_cases("multi_turn")


def _run_turns(client, customer_headers, case: dict) -> dict:
    headers = customer_headers(case["user_id"]) if case.get("user_id") else {}
    session_id = f"eval-{case['id']}"
    history = []
    workflow = {"step": 0, "data": {}}
    result = None
    for turn in case["turns"]:
        payload = {"message": turn, "session_id": session_id, "history": history, "workflow": workflow}
        if case.get("user_id"):
            payload["user_id"] = case["user_id"]
        result = client.post("/chat", json=payload, headers=headers).json()
        history.append({"role": "user", "content": turn})
        history.append({"role": "assistant", "content": result["response"]})
        workflow = result["workflow"]
    return result


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_final_turn_matches_expectation(client, customer_headers, case):
    result = _run_turns(client, customer_headers, case)
    assert result["response"]
    assert result["is_handoff"] == (case["expected_intent"] == "handoff")
    if case.get("expected_sources"):
        assert any(
            any(expected in s for s in result["rag_sources"]) for expected in case["expected_sources"]
        )
