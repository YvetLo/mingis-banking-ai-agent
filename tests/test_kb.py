"""
Knowledge Base maintenance — Sprint 17.

The kb_entries CRUD endpoints are pure DB writes, so they're asserted
exactly. assemble_docs() (markdown + active kb_entries, the input to the
FAISS rebuild) is tested directly without embedding — that keeps the
suite fast and, importantly, avoids clobbering the real data/faiss_index
that the rest of the suite's retrieval tests depend on. The actual
reindex + hot-swap is verified live (it re-embeds and rewrites the index
files), not in pytest.
"""

from pathlib import Path

import pytest

from backend.src.rag.build_index import assemble_docs

KB_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"


@pytest.fixture(autouse=True)
def _staff_auth(client, staff_headers):
    """Sprint 19 gated every /kb/* route behind staff auth (see
    tests/security/test_authorization.py) — apply it for every test in
    this file rather than threading headers through each call."""
    client.headers.update(staff_headers)
    yield
    client.headers.pop("Authorization", None)


def test_create_list_edit_archive_restore(client):
    r = client.post("/kb/entries", json={
        "language": "zh", "title": "測試條目A", "content": "內容A", "tags": "a,b",
    })
    assert r.status_code == 200
    eid = r.json()["id"]

    active = client.get("/kb/entries", params={"language": "zh", "status": "active"}).json()
    assert any(x["id"] == eid and x["title"] == "測試條目A" for x in active)

    r = client.put(f"/kb/entries/{eid}", json={"title": "測試條目A2", "content": "內容A2", "tags": "c"})
    assert r.status_code == 200
    entry = next(x for x in client.get("/kb/entries", params={"status": "active"}).json() if x["id"] == eid)
    assert entry["title"] == "測試條目A2"
    assert entry["updated_at"] is not None

    # archive drops it from active and moves it to archived (rollback path)
    client.post(f"/kb/entries/{eid}/archive")
    assert not any(x["id"] == eid for x in client.get("/kb/entries", params={"status": "active"}).json())
    assert any(x["id"] == eid for x in client.get("/kb/entries", params={"status": "archived"}).json())

    client.post(f"/kb/entries/{eid}/restore")
    assert any(x["id"] == eid for x in client.get("/kb/entries", params={"status": "active"}).json())


def test_kb_entry_validation(client):
    assert client.post("/kb/entries", json={"language": "fr", "title": "x", "content": "y"}).status_code == 422
    assert client.post("/kb/entries", json={"language": "zh", "title": "  ", "content": "y"}).status_code == 422
    assert client.post("/kb/entries", json={"language": "zh", "title": "x", "content": "  "}).status_code == 422


def test_kb_edit_or_archive_unknown_404s(client):
    assert client.put("/kb/entries/999999", json={"title": "a", "content": "b"}).status_code == 404
    assert client.post("/kb/entries/999999/archive").status_code == 404
    assert client.post("/kb/entries/999999/restore").status_code == 404


def test_kb_entries_language_isolation(client):
    zh_id = client.post("/kb/entries", json={"language": "zh", "title": "中文條目ISO", "content": "x"}).json()["id"]
    en_list = client.get("/kb/entries", params={"language": "en", "status": "active"}).json()
    assert not any(x["id"] == zh_id for x in en_list)


def test_assemble_docs_combines_markdown_and_active_entries(client):
    # curated markdown is always present…
    docs = assemble_docs("zh", KB_DIR)
    assert any(d["source"] == "credit_card_fees.md" for d in docs)

    # …and an active entry joins it, embedding title + content together
    title = "獨特測試標題_KBXYZ"
    eid = client.post("/kb/entries", json={
        "language": "zh", "title": title, "content": "這是一段測試答案內容",
    }).json()["id"]

    docs = assemble_docs("zh", KB_DIR)
    entry_doc = next((d for d in docs if d["source"] == title), None)
    assert entry_doc is not None
    assert title in entry_doc["text"]
    assert "測試答案" in entry_doc["text"]
    assert entry_doc["kb_entry_id"] == eid

    # archiving removes it from the next rebuild's input
    client.post(f"/kb/entries/{eid}/archive")
    assert not any(d["source"] == title for d in assemble_docs("zh", KB_DIR))
