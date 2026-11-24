"""
Knowledge Base Index Builder — Sprint 5, Sprint 17

Reads Markdown FAQ files, chunks text, generates embeddings via
sentence-transformers, and saves FAISS indexes (one per language).

Sprint 17: the index now also includes active kb_entries (supplementary
knowledge added through the maintenance UI / knowledge improvement pipeline —
see database.get_kb_entries). reindex_all() is callable from the running
app (main.py's POST /kb/reindex) so newly-added knowledge goes live
without a server restart; it reuses the already-loaded embedding model
singleton instead of loading a second copy.

Sprint 21: chunking is heading-aware and CJK-aware. The original splitter
counted `text.split()` "words", which for Chinese — no spaces — made every
zh markdown file exactly ONE chunk. A whole-file vector answers "roughly
what is this document about", not "which passage answers this question",
and retrieval showed it: 跨行轉帳手續費 ranked foreign_currency_exchange.md
above transfer_rules.md, 定存利率 ranked loan_overview.md above
account_services.md. See docs/ADR.md ADR-016.

Usage (initial build / CLI):
    python -m backend.src.rag.build_index

Outputs:
    data/faiss_index/{zh,en}.index        FAISS index (IndexFlatIP)
    data/faiss_index/{zh,en}_meta.json    chunk metadata (source, text, chunk_id, language)
"""

import json
import re
from pathlib import Path

import faiss
import numpy as np

# Default locations (project-root-relative) for the CLI entrypoint. The
# app passes absolute paths into reindex_all() instead of relying on cwd.
DEFAULT_KB_DIR = Path("data/knowledge_base")
DEFAULT_INDEX_DIR = Path("data/faiss_index")
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"

# Size limits are a fallback, not the primary split: sections are cut at
# markdown headings first, and only an oversized section gets windowed.
# Measured in "units" — one CJK character or one Latin word — so the same
# number means roughly the same amount of content in either language
# (Chinese packs far more meaning per character than English per word,
# hence the deliberately modest number).
CHUNK_MAX_UNITS = 320
CHUNK_OVERLAP_UNITS = 60

LANGUAGES = ["zh", "en"]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")


def count_units(text: str) -> int:
    """Length in CJK characters + Latin words. `text.split()` alone
    reports 1 for an entire Chinese document, which is what made every
    zh file a single chunk."""
    cjk = len(_CJK_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", text))
    return cjk + latin


def _window(text: str, max_units: int, overlap_units: int) -> list[str]:
    """Last-resort splitter for a section that's still too long: walks
    whole lines so a table or list never gets cut mid-row."""
    lines = text.split("\n")
    chunks, current, used = [], [], 0
    for line in lines:
        line_units = count_units(line)
        if current and used + line_units > max_units:
            chunks.append("\n".join(current))
            # carry the tail back for overlap, so a fact split across the
            # boundary is still wholly present in one of the two chunks
            carried, carried_units = [], 0
            for prev in reversed(current):
                prev_units = count_units(prev)
                if carried_units + prev_units > overlap_units:
                    break
                carried.insert(0, prev)
                carried_units += prev_units
            current, used = carried, carried_units
        current.append(line)
        used += line_units
    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c.strip()]


def split_markdown(
    text: str,
    max_units: int = CHUNK_MAX_UNITS,
    overlap_units: int = CHUNK_OVERLAP_UNITS,
) -> list[str]:
    """One chunk per `##`/`###` section, each prefixed with its heading trail.

    Two things matter here:

    * **Where the cut goes.** A section in these files is exactly one
      topic ("跨行 ATM 手續費", "年費"), so the heading is a better boundary
      than any character count; only an oversized section falls back to
      size windowing. Cutting at `###` as well as `##` was measured, not
      assumed — it lifted English top-1 retrieval from 89% to 96% and
      pulled more answers above the confidence threshold, at the cost of
      ~3 points of Chinese recall@3 that raising TOP_K to 5 gets back.
    * **The heading trail travels with the body.** "轉帳與匯款說明＞國內轉帳
      ＞轉帳方式與手續費" in front of the text puts the topic words into the
      chunk's own vector — without it, a chunk about 手續費 that never
      repeats "轉帳" competes poorly against a document that says it often.
    """
    lines = text.split("\n")
    doc_title = ""
    sections: list[tuple[list[str], list[str]]] = []   # (heading trail, body lines)
    trail: list[str] = []
    body: list[str] = []

    def flush():
        if trail or any(line.strip() for line in body):
            sections.append((list(trail), list(body)))

    for line in lines:
        match = _HEADING_RE.match(line)
        if not match:
            body.append(line)
            continue
        level, title = len(match.group(1)), match.group(2)
        if level == 1:
            # Not kept in the body: it's prefixed onto every chunk as the
            # first breadcrumb element, and a document whose only preamble
            # is its own title would otherwise produce a chunk containing
            # nothing but that title twice over.
            doc_title = title
            continue
        if level == 2:
            flush()
            trail, body = [title], []
        elif level == 3:
            # its own chunk, but keeps the parent ## in the trail so the
            # breadcrumb still says which topic it belongs to
            flush()
            trail, body = [(trail[0] if trail else ""), title], []
        else:
            # #### and deeper stay inside their section; the text is kept
            # so its wording is still searchable
            body.append(line)
    flush()

    if not sections:                        # no headings at all (e.g. a kb_entry)
        return _window(text, max_units, overlap_units) or [text]

    # Whatever sits above the first `##` is just the document title and a
    # line of preamble. On its own it makes a tiny chunk that says nothing
    # but still competes for retrieval slots, so it rides along with the
    # first real section instead of becoming its own vector.
    if sections and not any(sections[0][0]):
        intro = sections.pop(0)[1]
        if sections:
            sections[0] = (sections[0][0], intro + sections[0][1])
        else:
            sections = [([], intro)]

    chunks: list[str] = []
    for heading_trail, section_lines in sections:
        prefix = "＞".join([p for p in [doc_title] + heading_trail if p])
        section = "\n".join(section_lines).strip()
        if not section:            # a `##` that only introduces `###` children
            continue
        pieces = ([section] if count_units(section) <= max_units
                  else _window(section, max_units, overlap_units))
        for piece in pieces:
            chunks.append(f"{prefix}\n{piece}".strip() if prefix else piece)
    return [c for c in chunks if c.strip()]


def chunk_text(text: str, max_units: int = CHUNK_MAX_UNITS,
               overlap_units: int = CHUNK_OVERLAP_UNITS) -> list[str]:
    """Kept as the module's entry point for both markdown files and
    kb_entries — the latter carry no headings and normally come out as a
    single chunk."""
    return split_markdown(text, max_units, overlap_units)


def _markdown_docs(language: str, kb_dir: Path) -> list[dict]:
    docs = []
    lang_dir = kb_dir / language
    if not lang_dir.exists():
        return docs
    for md_file in sorted(lang_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        for i, chunk in enumerate(chunk_text(content)):
            docs.append({"source": md_file.name, "chunk_id": i, "text": chunk, "language": language})
    return docs


def _kb_entry_docs(language: str) -> list[dict]:
    """Active kb_entries as index docs. Title + content are embedded
    together (the title carries the question phrasing that helps a user
    query match; the content is what the FAQ Node then grounds on). The
    title also becomes the `source` so it reads naturally in the
    frontend's 參考來源 caption."""
    from ..database import get_kb_entries
    docs = []
    for e in get_kb_entries(language=language, status="active"):
        combined = f"{e['title']}\n{e['content']}"
        for i, chunk in enumerate(chunk_text(combined)):
            docs.append({
                "source": e["title"],
                "chunk_id": i,
                "text": chunk,
                "language": language,
                "kb_entry_id": e["id"],
            })
    return docs


def assemble_docs(language: str, kb_dir: Path = DEFAULT_KB_DIR) -> list[dict]:
    """Everything that should be in the index for a language: curated
    markdown + active supplementary kb_entries."""
    return _markdown_docs(language, kb_dir) + _kb_entry_docs(language)


def _write_index(language: str, docs: list[dict], model, index_dir: Path) -> int:
    texts = [d["text"] for d in docs]
    embeddings = model.encode(texts, normalize_embeddings=True)
    embeddings_np = np.array(embeddings).astype("float32")

    # IndexFlatIP + normalized vectors → cosine similarity scores (0–1)
    index = faiss.IndexFlatIP(embeddings_np.shape[1])
    index.add(embeddings_np)

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / f"{language}.index"))
    (index_dir / f"{language}_meta.json").write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return index.ntotal


def reindex_all(kb_dir: Path = DEFAULT_KB_DIR, index_dir: Path = DEFAULT_INDEX_DIR, model=None) -> dict:
    """Rebuild every language's index from markdown + active kb_entries.
    Reuses the retriever's already-loaded embedding singleton when no
    model is passed, so calling this from the live app is just the
    re-encode cost (fast for a demo-sized KB), not a model reload."""
    if model is None:
        from .retriever import _get_model
        model = _get_model()
    counts = {}
    for lang in LANGUAGES:
        docs = assemble_docs(lang, kb_dir)
        counts[lang] = _write_index(lang, docs, model, index_dir) if docs else 0
    return counts


def main():
    print("=" * 60)
    print("  AI Banking Assistant — Knowledge Base Index Builder")
    print(f"  Model: {EMBEDDING_MODEL}")
    print("=" * 60)

    if not DEFAULT_KB_DIR.exists():
        print(f"ERROR: {DEFAULT_KB_DIR} not found. Run from project root.")
        return

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)
    counts = reindex_all(DEFAULT_KB_DIR, DEFAULT_INDEX_DIR, model=model)
    for lang, n in counts.items():
        print(f"  {lang}: {n} vectors")

    print("\nDone. Index ready for RAG retrieval.")


if __name__ == "__main__":
    main()
