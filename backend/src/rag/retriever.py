"""
RAG Retriever — Sprint 5
Loads FAISS indexes and retrieves top-k relevant chunks for a query.
Falls back gracefully if indexes are not built yet.

Sprint 21: TOP_K went 3 → 5 alongside heading-aware chunking. A chunk
used to be a whole document; it's now a single `##`/`###` section, so
three of them carry a fraction of the context three of the old ones did.
Measured on the retrieval benchmark: the right section is in the top 3
for 92% of Chinese questions but in the top 5 for 97% — and five sections
is still far less text than three whole documents ever was.
"""

import json
from pathlib import Path

EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"
TOP_K = 5

# Shared model instance (loaded once on first retrieve call)
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print("[RAG] Loading embedding model...")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        print("[RAG] Model ready.")
    return _model


class RAGRetriever:
    def __init__(self, language: str, index_dir: Path):
        self.language = language
        self.index_dir = index_dir
        self._index = None
        self._meta: list[dict] = []
        self._ready = False
        self._load()

    def _load(self):
        import faiss
        index_path = self.index_dir / f"{self.language}.index"
        meta_path = self.index_dir / f"{self.language}_meta.json"
        if not index_path.exists() or not meta_path.exists():
            print(f"[RAG] Index missing for '{self.language}' — will fall back to context stuffing")
            return
        self._index = faiss.read_index(str(index_path))
        self._meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self._ready = True
        print(f"[RAG] '{self.language}' index loaded: {len(self._meta)} chunks")

    @property
    def is_ready(self) -> bool:
        return self._ready

    def retrieve(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """
        Returns top-k chunks sorted by cosine similarity.
        Each chunk: {text, source, score}
        Returns [] if index not ready.
        """
        if not self._ready:
            return []

        model = _get_model()
        embedding = model.encode([query], normalize_embeddings=True).astype("float32")
        scores, indices = self._index.search(embedding, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            chunk = self._meta[idx]
            results.append({
                "text": chunk["text"],
                "source": chunk["source"],
                "score": float(score),
            })
        return results

    def format_context(self, chunks: list[dict]) -> str:
        """Format retrieved chunks for insertion into system prompt."""
        if not chunks:
            return "(No relevant knowledge base content found for this query.)"
        parts = []
        for c in chunks:
            parts.append(f"[Source: {c['source']} | Similarity: {c['score']:.2f}]\n{c['text']}")
        return "\n\n---\n\n".join(parts)
