"""
Staff-tool support endpoints — 2026-11

  POST /handoff/{id}/reopen   undo for "mark resolved"
  GET  /kb/status             how many knowledge changes the live index lacks
Neither calls an LLM. (/kb/reindex itself is not exercised here: it rewrites the
real index — see test_kb.py.)
"""

from tests.test_case_record import make_ticket


def test_reopen_brings_a_resolved_case_back(client, staff_headers):
    tid = make_ticket(client, "test-reopen")
    assert client.post(f"/handoff/{tid}/resolve", headers=staff_headers).status_code == 200
    assert client.get(f"/handoff/{tid}/messages").json()["ticket"]["status"] == "resolved"
    assert client.post(f"/handoff/{tid}/reopen", headers=staff_headers).status_code == 200
    assert client.get(f"/handoff/{tid}/messages").json()["ticket"]["status"] == "open"


def test_reopen_is_staff_only_and_404s_for_unknown_ticket(client, staff_headers, customer_headers):
    tid = make_ticket(client, "test-reopen-auth")
    assert client.post(f"/handoff/{tid}/reopen").status_code == 401
    assert client.post(f"/handoff/{tid}/reopen", headers=customer_headers("demo_user1")).status_code == 403
    assert client.post("/handoff/T-nope/reopen", headers=staff_headers).status_code == 404


def test_kb_status_counts_changes_not_yet_in_the_index(client, staff_headers):
    before = client.get("/kb/status", headers=staff_headers).json()["pending_changes"]
    client.post("/kb/entries", headers=staff_headers,
                json={"language": "zh", "title": "測試用條目", "content": "測試內容", "tags": ""})
    after = client.get("/kb/status", headers=staff_headers).json()["pending_changes"]
    assert after == before + 1


def test_kb_status_is_staff_only(client, customer_headers):
    assert client.get("/kb/status").status_code == 401
    assert client.get("/kb/status", headers=customer_headers("demo_user1")).status_code == 403
