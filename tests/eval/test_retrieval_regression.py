"""
Retrieval hit-rate regression — Evaluation Framework.

Runs golden_cases.jsonl's FAQ (and multi-turn's final-turn) queries
directly against the live FAISS retriever — bypassing the LLM entirely,
so this is fast and free, and isolates retrieval quality from
generation quality. Mirrors how qa_node actually retrieves
(backend/src/agent/nodes.py: retriever.retrieve(message) embeds only
the current turn's raw text, never conversation history) — that's why
multi-turn cases here test only their final turn's text too, not the
accumulated context.
"""

from pathlib import Path

import pytest

from backend.src.rag.retriever import TOP_K, RAGRetriever

from _golden import load_cases

INDEX_DIR = Path(__file__).parent.parent.parent / "data" / "faiss_index"
RETRIEVERS = {"zh": RAGRetriever("zh", INDEX_DIR), "en": RAGRetriever("en", INDEX_DIR)}

CASES = [c for c in load_cases() if c.get("expected_sources")]


def _query_for(case: dict) -> str:
    return case["turns"][-1] if case["category"] == "multi_turn" else case["query"]


def _hit(case: dict) -> bool:
    query = _query_for(case)
    chunks = RETRIEVERS[case["language"]].retrieve(query)
    sources = [c["source"] for c in chunks]
    return any(any(expected in s for s in sources) for expected in case["expected_sources"])


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_expected_source_in_top_k(case):
    assert _hit(case), (
        f"none of top-{TOP_K} sources for {_query_for(case)!r} matched {case['expected_sources']!r}"
    )


def test_aggregate_retrieval_hit_rate_meets_threshold():
    """CI-facing gate — see docs/evaluation.md for the current baseline."""
    hits = sum(1 for c in CASES if _hit(c))
    rate = hits / len(CASES)
    assert rate >= 0.90, f"retrieval hit rate {rate:.0%} below 90% threshold"
