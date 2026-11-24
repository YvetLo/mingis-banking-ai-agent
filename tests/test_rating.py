"""
Satisfaction rating — Sprint 16.

The /rating endpoint is a pure DB write (no LLM call), so these tests
are cheap and assert exact behavior: the score is stored, reflected in
/stats (avg + distribution), surfaced via /ratings, and out-of-range
scores are rejected. This is also the "低品質評分" raw material the
planned knowledge improvement pipeline will cluster on, so the low-score +
comment path is covered explicitly.
"""


def test_submit_rating_reflected_in_stats(client):
    before = client.get("/stats").json()["rating_count"]

    r = client.post("/rating", json={"session_id": "test-rate-1", "score": 5})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    after = client.get("/stats").json()
    assert after["rating_count"] == before + 1
    assert after["avg_rating"] is not None
    assert after["rating_distribution"].get("5", 0) >= 1


def test_low_score_with_comment_is_retrievable(client, customer_headers):
    # Attributing the rating to a user_id is an identity claim, so this
    # needs that user's token (backend/main.py::_resolve_claimed_user_id).
    # Guest ratings — no user_id — still need no auth; see
    # test_submit_rating_reflected_in_stats above.
    r = client.post("/rating", json={
        "session_id": "test-rate-low", "score": 1,
        "user_id": "user_001", "comment": "問了三次都沒得到我要的資訊",
    }, headers=customer_headers("user_001"))
    assert r.status_code == 200

    low = client.get("/ratings", params={"max_score": 2, "limit": 100}).json()
    mine = [x for x in low if x["session_id"] == "test-rate-low"]
    assert len(mine) == 1
    assert mine[0]["score"] == 1
    assert mine[0]["comment"] == "問了三次都沒得到我要的資訊"
    assert mine[0]["user_id"] == "user_001"


def test_ratings_max_score_filter_excludes_high_scores(client):
    client.post("/rating", json={"session_id": "test-rate-high", "score": 5})

    low = client.get("/ratings", params={"max_score": 2, "limit": 100}).json()
    assert not any(x["session_id"] == "test-rate-high" for x in low)


def test_blank_comment_stored_as_null(client):
    client.post("/rating", json={"session_id": "test-rate-blank", "score": 2, "comment": "   "})
    low = client.get("/ratings", params={"max_score": 2, "limit": 100}).json()
    mine = [x for x in low if x["session_id"] == "test-rate-blank"]
    assert len(mine) == 1
    assert mine[0]["comment"] is None


def test_score_out_of_range_rejected(client):
    for bad in (0, 6, -1):
        r = client.post("/rating", json={"session_id": "test-rate-bad", "score": bad})
        assert r.status_code == 422

    # nothing from the rejected calls should have been written
    low = client.get("/ratings", params={"limit": 200}).json()
    assert not any(x["session_id"] == "test-rate-bad" for x in low)
