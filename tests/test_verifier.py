"""
Grounding verifier — Sprint 12

Tests verify_chunks_sufficient() directly (not through /chat) — a pure
unit test of the groundedness judgment, no need to also pay for a full
qa_node flow just to check this one decision. Calls the real Claude
API (verifier has no mock/deterministic mode), so assertions are on
the structural verdict only.
"""

from pathlib import Path

from backend.main import client, MODEL
from backend.src.agent.verifier import verify_chunks_sufficient
from backend.src.rag.retriever import RAGRetriever

INDEX_DIR = Path(__file__).parent.parent / "data" / "faiss_index"
_retriever = RAGRetriever("zh", INDEX_DIR)


def test_grounded_chunks_judged_sufficient():
    question = "信用卡年費怎麼算?"
    chunks = _retriever.retrieve(question)
    chunks_text = _retriever.format_context(chunks)
    sufficient, reason = verify_chunks_sufficient(client, MODEL, question, chunks_text)
    assert sufficient is True


def test_fx_exchange_now_grounded():
    """
    The diagnostic case study's original finding was that no KB article
    covered foreign currency cash exchange — chunks about domestic
    transfer / credit card benefits / ATM limits scored above any
    reasonable similarity threshold for this question, but none of them
    actually answered it. A knowledge_base/{zh,en}/foreign_currency_exchange.md
    article was added to close that specific gap; this locks in that the
    fix actually took (not just that the file exists, but that the
    verifier now judges the retrieved content as sufficient).
    """
    question = "外幣現鈔要去哪裡換，匯率怎麼算?"
    chunks = _retriever.retrieve(question)
    chunks_text = _retriever.format_context(chunks)
    sufficient, reason = verify_chunks_sufficient(client, MODEL, question, chunks_text)
    assert sufficient is True


def test_ungrounded_chunks_judged_insufficient():
    """
    Regression guard for the verifier's core job: insurance products are
    not covered by any knowledge base article (confirmed gap, distinct
    from the now-fixed FX case above) — the closest chunks are about
    credit card benefits, which don't answer whether the bank sells
    insurance at all.
    """
    question = "銀行有賣保險產品嗎?"
    chunks = _retriever.retrieve(question)
    chunks_text = _retriever.format_context(chunks)
    sufficient, reason = verify_chunks_sufficient(client, MODEL, question, chunks_text)
    assert sufficient is False


# ── 2026-11 (ADR-020): a high retrieval score must not be taken as "answered" ────────────────
REFUND_QUESTION = (
    "我已取消了海外網站購物的訂單並退貨成功，為什麼收到帳單後，退款的台幣金額比原本扣款的金額還要少？"
    "而且當初被收的 1.5% 國外交易手續費沒有退還？"
)
FEE_ONLY_CHUNK = (
    "[Source: credit_card_fees.md | Similarity: 0.66] 跨國交易手續費\n"
    "- **國外交易手續費**：交易金額的 1.5%，於帳單上與該筆消費分列顯示\n"
    "- 適用於在國外刷卡、或在海外網站以外幣或台幣結帳的消費"
)
REFUND_SECTION = (
    "\n\n[Source: credit_card_fees.md | Similarity: 0.78] 海外消費退款：金額差異與手續費\n"
    "退回的台幣金額與原本扣款不同：消費日與商家辦理退款當天的國際組織匯率不同，所以重新換算後會有落差。\n"
    "國外交易手續費不退還：依本行規定，原消費產生的 1.5% 國外交易手續費在退款時不予退還。退款本身不會再另收手續費。"
)


def test_fee_text_without_the_refund_rule_is_insufficient_even_though_it_scores_high():
    """The case that exposed the gap: this question scored 0.66 against fee text that says nothing
    about refunds, so the old "only verify below 0.60" rule let the model improvise an answer."""
    sufficient, reason = verify_chunks_sufficient(client, MODEL, REFUND_QUESTION, FEE_ONLY_CHUNK)
    assert sufficient is False, reason


def test_the_same_question_is_sufficient_once_the_refund_rule_is_in_the_chunks():
    sufficient, reason = verify_chunks_sufficient(client, MODEL, REFUND_QUESTION, FEE_ONLY_CHUNK + REFUND_SECTION)
    assert sufficient is True, reason
