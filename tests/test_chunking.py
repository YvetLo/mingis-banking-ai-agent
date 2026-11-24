"""
Knowledge-base chunking — Sprint 21.

The bug these tests exist to prevent: `chunk_text` used to split on
`text.split()`, so a Chinese document — which has no spaces — counted as
one "word" and became exactly one chunk. A whole-file vector answers
"what is this document about", not "which passage answers this question",
and retrieval showed it (跨行轉帳手續費 ranked the foreign-exchange file
above the transfers file).

These are pure text-processing tests: no embeddings, no index, no LLM.
The retrieval quality that motivated the change is measured separately
against the live index — see docs/design_journal.md Sprint 21.
"""

from pathlib import Path

from backend.src.rag.build_index import CHUNK_MAX_UNITS, count_units, split_markdown

KB_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"


def test_count_units_counts_chinese_characters_not_whitespace_words():
    """The actual regression: `"一二三四五".split()` is 1, which is what
    made every Chinese file a single chunk."""
    chinese = "信用卡年費說明"
    assert len(chinese.split()) == 1
    assert count_units(chinese) == 7


def test_count_units_counts_english_words():
    assert count_units("credit card annual fee") == 4


def test_count_units_handles_mixed_text():
    assert count_units("ATM 每日提款上限") == 1 + 6


def test_chinese_document_splits_into_one_chunk_per_section():
    text = (
        "# 信用卡費用說明\n\n"
        "## 年費\n一般卡年費 NT$800，每年消費滿三筆可申請免年費。\n\n"
        "## 循環利息\n年利率 6.85% 至 15%，依個人信用狀況核定。\n\n"
        "## 跨國交易手續費\n國外刷卡加收交易金額的 1.5%。\n"
    )
    chunks = split_markdown(text)
    assert len(chunks) == 3, "one chunk per ## section"
    assert any("年利率" in c for c in chunks)


def test_each_chunk_carries_its_heading_trail():
    """Without the breadcrumb, a section about 手續費 that never repeats
    the word 轉帳 competes poorly against a document that says it often."""
    text = (
        "# 轉帳與匯款說明\n\n"
        "## 國內轉帳\n\n"
        "### 轉帳方式與手續費\n跨行即時轉帳每筆 NT$15。\n"
    )
    chunk = split_markdown(text)[0]
    assert chunk.startswith("轉帳與匯款說明＞國內轉帳＞轉帳方式與手續費")
    assert "NT$15" in chunk


def test_h3_sections_become_their_own_chunks():
    text = (
        "# 提款說明\n\n## 提款服務\n\n"
        "### 每日提款上限\n每日最高 NT$100,000。\n\n"
        "### 單筆提款限額\n單筆最高 NT$20,000。\n"
    )
    chunks = split_markdown(text)
    assert len(chunks) == 2
    assert any("每日提款上限" in c and "100,000" in c for c in chunks)
    assert any("單筆提款限額" in c and "20,000" in c for c in chunks)


def test_document_preamble_rides_along_instead_of_becoming_its_own_chunk():
    """A chunk holding only the title says nothing but still competes for
    a retrieval slot."""
    text = "# 帳戶服務說明\n本文件說明開戶與存款。\n\n## 開戶\n請攜帶雙證件臨櫃辦理。\n"
    chunks = split_markdown(text)
    assert len(chunks) == 1
    assert "本文件說明開戶與存款" in chunks[0]


def test_oversized_section_falls_back_to_size_windowing():
    body = "\n".join(f"- 第 {i} 條規定，這是一段補充說明文字。" for i in range(120))
    chunks = split_markdown(f"# 規定\n\n## 條文\n{body}\n")
    assert len(chunks) > 1
    assert all(count_units(c) <= CHUNK_MAX_UNITS * 1.5 for c in chunks)


def test_text_without_headings_stays_one_chunk():
    """kb_entries added through the maintenance UI have no markdown
    structure — they must not be mangled."""
    entry = "存摺遺失要怎麼補辦？\n請攜帶身分證與印鑑至任一分行辦理，工本費 NT$50。"
    assert split_markdown(entry) == [entry]


def test_real_knowledge_base_files_produce_multiple_chunks():
    """The end state that matters: no file in either language is still a
    single whole-document vector."""
    for language in ("zh", "en"):
        for path in sorted((KB_DIR / language).glob("*.md")):
            chunks = split_markdown(path.read_text(encoding="utf-8"))
            assert len(chunks) > 1, f"{language}/{path.name} is still one chunk"
