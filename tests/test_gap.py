"""
Knowledge improvement pipeline — Sprint 18.

Drafts are normally produced by POST /gap/analyze (two LLM calls) and
approved via POST /gap/drafts/{id}/approve (which reindexes). Both are
verified live, not in pytest — analyze is nondeterministic and approve
rewrites the real FAISS index the rest of the suite depends on. What's
asserted here is the deterministic review plumbing: a draft (inserted
directly, standing in for one analyze would have produced) can be
listed, edited, skipped, and that unknown ids 404. This is the workflow
the 知識優化流程 page drives.
"""

import pytest

from backend.src.database import create_gap_draft


@pytest.fixture(autouse=True)
def _staff_auth(client, staff_headers):
    """Sprint 19 gated every /gap/* route behind staff auth (see
    tests/security/test_authorization.py) — apply it for every test in
    this file rather than threading headers through each call."""
    client.headers.update(staff_headers)
    yield
    client.headers.pop("Authorization", None)


def _make_draft(**kw):
    defaults = dict(
        language="zh", topic="測試主題", question="測試問題？", answer="測試答案",
        representative_query="測試問題？", signal_summary="未解決查詢×2",
        signal_count=2, pre_score=0.42, tags="a,b",
    )
    defaults.update(kw)
    return create_gap_draft(**defaults)["id"]


def test_gap_draft_listed_and_editable(client):
    did = _make_draft()
    pending = client.get("/gap/drafts", params={"status": "pending"}).json()
    assert any(x["id"] == did for x in pending)

    r = client.put(f"/gap/drafts/{did}", json={"question": "新問題？", "answer": "新答案", "tags": "c"})
    assert r.status_code == 200
    got = next(x for x in client.get("/gap/drafts", params={"status": "pending"}).json() if x["id"] == did)
    assert got["question"] == "新問題？"
    assert got["answer"] == "新答案"
    assert got["updated_at"] is not None


def test_gap_draft_skip_moves_out_of_pending(client):
    did = _make_draft(topic="要略過的主題")
    client.post(f"/gap/drafts/{did}/skip")
    assert not any(x["id"] == did for x in client.get("/gap/drafts", params={"status": "pending"}).json())
    assert any(x["id"] == did for x in client.get("/gap/drafts", params={"status": "skipped"}).json())


def test_gap_draft_edit_validation(client):
    did = _make_draft()
    assert client.put(f"/gap/drafts/{did}", json={"question": "  ", "answer": "x"}).status_code == 422
    assert client.put(f"/gap/drafts/{did}", json={"question": "x", "answer": "  "}).status_code == 422


def test_gap_unknown_draft_404s(client):
    assert client.put("/gap/drafts/999999", json={"question": "a", "answer": "b"}).status_code == 404
    assert client.post("/gap/drafts/999999/skip").status_code == 404
    assert client.post("/gap/drafts/999999/approve").status_code == 404
    assert client.get("/gap/drafts/999999/effectiveness").status_code == 404


# ── approving twice must not write the knowledge twice (2026-11) ─────────────────────────────
def test_claiming_a_draft_succeeds_exactly_once():
    from backend.src.database import claim_gap_draft
    draft_id = _make_draft(topic="只能認領一次", question="只能認領一次？")
    assert claim_gap_draft(draft_id) is True
    assert claim_gap_draft(draft_id) is False


def test_two_simultaneous_approvals_write_one_knowledge_entry(client, monkeypatch):
    """The real incident: 核准入庫 clicked twice created two identical entries 3.6s apart,
    because the draft was only marked approved after the (slow) reindex. The reindex is
    stubbed with a delay so the window is wide, and so the real index is never rewritten."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    import backend.main as main
    from backend.src.agent import gap_pipeline

    monkeypatch.setattr(main, "_rebuild_and_swap_index", lambda: time.sleep(0.4) or {"zh": 0, "en": 0})
    monkeypatch.setattr(gap_pipeline, "_top_score", lambda *a, **k: 0.7)
    title = "同時核准測試-" + str(time.time_ns())
    draft_id = _make_draft(topic=title, question=title, answer="答案")

    def approve(_):
        return client.post(f"/gap/drafts/{draft_id}/approve").status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        codes = sorted(ex.map(approve, range(2)))
    assert codes == [200, 409]

    entries = [e for e in client.get("/kb/entries", params={"limit": 500}).json() if e["title"] == title]
    assert len(entries) == 1, entries
    assert client.get(f"/gap/drafts/{draft_id}/effectiveness").json()["pre_score"] is not None


# ── a mis-clicked 略過 must be undoable (2026-11) ────────────────────────────────────────────
def test_restore_brings_a_skipped_draft_back_to_pending(client):
    draft_id = _make_draft(topic="還原測試", question="還原測試？")
    assert client.post(f"/gap/drafts/{draft_id}/skip").status_code == 200
    assert client.post(f"/gap/drafts/{draft_id}/restore").status_code == 200
    pending = client.get("/gap/drafts", params={"status": "pending"}).json()
    assert draft_id in [d["id"] for d in pending]


def test_restore_refuses_drafts_that_are_not_skipped(client):
    draft_id = _make_draft(topic="還原測試2", question="還原測試2？")
    assert client.post(f"/gap/drafts/{draft_id}/restore").status_code == 409      # still pending
    assert client.post("/gap/drafts/99999/restore").status_code == 404
