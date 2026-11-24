"""
Every curated shortcut question must pass the grounding verifier — 2026-11 (ADR-020)

Shortcuts ("您可能還想問", the welcome-screen starters) are promised to be answerable: clicking one
must never end in a handoff. FAQ answers are now grounding-checked every time, so a shortcut is only
safe if the verifier agrees the retrieved text answers it. Eight curated follow-ups failed that check
(retrieval put the wrong article first) and were removed; this test keeps the rest honest, and fails
the day a knowledge-base edit or a retrieval change turns one into a dead end.

Calls the real Claude API (one small call per shortcut, in parallel), like test_verifier.py.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.main import MODEL, client
from backend.src.agent import suggestions as S
from backend.src.agent.verifier import verify_chunks_sufficient
from backend.src.rag.retriever import RAGRetriever

INDEX_DIR = Path(__file__).parent.parent / "data" / "faiss_index"
RETRIEVERS = {"zh": RAGRetriever("zh", INDEX_DIR), "en": RAGRetriever("en", INDEX_DIR)}


def _curated() -> set[tuple[str, str]]:
    pool = {(lang, q) for lang, qs in S.FAQ_STARTERS.items() for q in qs}
    for lang, by_source in S.TOPIC_FOLLOWUPS.items():
        for qs in by_source.values():
            pool |= {(lang, q) for q in qs}
    return pool


def _verdict(item):
    lang, question = item
    chunks = RETRIEVERS[lang].retrieve(question)
    sufficient, reason = verify_chunks_sufficient(client, MODEL, question, RETRIEVERS[lang].format_context(chunks))
    return item, sufficient, reason


def test_every_curated_shortcut_passes_the_verifier():
    pool = sorted(_curated())
    assert len(pool) > 50, "the shortcut lists look empty — did the structure change?"
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(_verdict, pool))
    failed = [(item, reason) for item, ok, reason in results if not ok]
    assert not failed, failed


def test_the_seven_removed_shortcuts_stay_removed():
    removed = {
        "國內轉帳的手續費怎麼算？", "跨行提款手續費多少？", "可以兌換哪些外幣？", "晶片金融卡和磁條卡差在哪？",
        "How much is the domestic transfer fee?", "What is a designated account transfer?",
        "What is the maximum loan amount?",
        "外幣換匯手續費怎麼算？",   # retrieval ranks the international-wire fee first; the verifier rejects it every time
    }
    assert not (removed & {q for _, q in _curated()})
