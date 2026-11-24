"""
Back-office language support (中文 / English) — 2026-11

These tests exist so a missed translation fails here instead of showing up on a screen:
  * every string has both languages, with the same {placeholders};
  * no English text still contains Chinese;
  * every key the pages use exists, and every reason code the backend can write has labels;
  * a ticket's stored (Chinese) reason is rendered in English, with the customer's own
    words left exactly as typed;
  * the menu only points at pages that exist.
"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
sys.path.insert(0, str(FRONTEND))

from i18n import NAV, REASON_EN, SIGNAL_KIND_EN, signal_summary, ticket_reason, waiting   # noqa: E402
from strings import STRINGS                                   # noqa: E402

from backend.src.agent.handoff import CATEGORY_LABEL          # noqa: E402

CJK = re.compile(r"[一-鿿]")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def test_every_string_has_both_languages():
    for key, entry in STRINGS.items():
        assert set(entry) == {"zh", "en"}, key
        assert entry["zh"].strip() and entry["en"].strip(), key


def test_placeholders_match_between_languages():
    for key, entry in STRINGS.items():
        assert set(PLACEHOLDER.findall(entry["zh"])) == set(PLACEHOLDER.findall(entry["en"])), key


def test_english_text_has_no_chinese_left_in_it():
    left = {k: e["en"] for k, e in STRINGS.items() if CJK.search(e["en"])}
    assert not left, left


def test_every_key_the_pages_use_exists():
    used = set()
    for path in list(FRONTEND.glob("*.py")) + list((FRONTEND / "pages").glob("*.py")):
        used |= set(re.findall(r'\bt\("([a-z_]+\.[a-z_0-9]+)"', path.read_text(encoding="utf-8")))
    assert used, "found no t(...) calls — is the pattern still right?"
    assert not (used - set(STRINGS)), sorted(used - set(STRINGS))


def test_every_reason_code_the_backend_can_write_has_labels():
    codes = set(CATEGORY_LABEL) | {"negative_feedback", "fallback_threshold", "verifier_unresolved"}
    for code in codes:
        assert f"reason.{code}" in STRINGS, code
        assert f"reasonshort.{code}" in STRINGS, code


def test_every_ticket_status_has_a_label():
    for status in ("open", "resolved", "closed", "in_progress"):
        assert f"status.{status}" in STRINGS


def test_every_backend_category_label_has_an_english_version():
    """A new category added to handoff.CATEGORY_LABEL must be added to i18n.REASON_EN too."""
    for label in CATEGORY_LABEL.values():
        assert label in REASON_EN, label
        out = ticket_reason(f"轉真人客服：{label}", "en")
        assert not CJK.search(out), out


def test_ticket_reason_chinese_is_unchanged():
    d = "轉真人客服：帳務爭議/退款｜帳單問題｜上週五多收了"
    assert ticket_reason(d, "zh") == d
    assert ticket_reason(d, "zh", strip_prefix=True) == "帳務爭議/退款｜帳單問題｜上週五多收了"


def test_ticket_reason_english_translates_labels_but_not_what_the_customer_typed():
    d = "轉真人客服：帳務爭議/退款｜帳單問題｜11/03 在 XX 百貨的那筆不對"
    out = ticket_reason(d, "en")
    assert out == "Handoff: Billing dispute / refund | Bill issue | 11/03 在 XX 百貨的那筆不對"


def test_ticket_reason_translates_the_guest_form_labels():
    d = "轉真人客服：使用者主動要求真人客服｜信用卡客戶｜我想問帳單分期"
    assert ticket_reason(d, "en", strip_prefix=True) == "Customer asked for an agent | Credit card customer | 我想問帳單分期"


def test_ticket_reason_handles_empty_and_unprefixed_text():
    assert ticket_reason(None, "en") == ""
    assert ticket_reason("something else", "en") == "something else"


def test_waiting_time_in_both_languages():
    now = datetime(2026, 11, 20, 12, 0)
    created = (now - timedelta(days=3, hours=4, minutes=5)).isoformat()
    assert waiting(created, now, "zh") == "3 天 4 小時"
    assert waiting(created, now, "en") == "3d 4h"
    assert waiting((now - timedelta(minutes=7)).isoformat(), now, "en") == "7m"
    assert waiting((now - timedelta(hours=2, minutes=9)).isoformat(), now, "zh") == "2 小時 9 分"
    assert waiting((now + timedelta(minutes=5)).isoformat(), now, "en") == "0m"      # clock skew: never negative


def test_menu_points_at_real_pages_with_labels():
    for path, key in NAV:
        assert (FRONTEND / path).exists(), path
        assert key in STRINGS


def test_signal_summary_is_translated_and_covers_every_signal_kind():
    assert signal_summary("未解決查詢×2；真人客服對話×1", "en") == "unresolved queries ×2; agent conversations ×1"
    assert signal_summary("未解決查詢×2；真人客服對話×1", "zh") == "未解決查詢×2；真人客服對話×1"
    assert signal_summary(None, "en") == "—"
    # every "kind" gather_signals can emit must be known, or it would show up in Chinese
    import re
    source = (Path(__file__).resolve().parent.parent / "backend/src/agent/gap_pipeline.py").read_text(encoding="utf-8")
    kinds = set(re.findall(r'"kind": "([^"]+)"', source))
    assert kinds and kinds <= set(SIGNAL_KIND_EN), kinds - set(SIGNAL_KIND_EN)
