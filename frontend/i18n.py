"""
Platform-wide UI language (中文 / English) for the back-office pages and the
shared navigation.

One setting, one place:
  * the language lives in st.session_state["ui_lang"] (so every page of the same
    browser session shares it) and is mirrored into the URL (?lang=en) so a
    refresh keeps it;
  * `lang_switcher()` is the single control, drawn at the top of every sidebar;
  * `t(key)` looks a string up in strings.STRINGS and falls back to Chinese if an
    English version is missing — a gap must never show up as a blank or a KeyError.

Deliberately NOT translated: customer conversations, agents' own replies, and
knowledge-base entries (they are data, and the KB already keeps zh and en apart).
The one exception is a ticket's "reason", which the backend stores as Chinese
text; `ticket_reason()` renders it in the chosen language (see below).

The customer chat page (app.py) has its own text table and, by default, follows
the language the customer is writing in; it uses `lang_switcher(effective=...)`
only so that a manual choice wins over that automatic one.
"""

from datetime import datetime, timedelta

import streamlit as st

from strings import STRINGS

LANGS = {"zh": "中文", "en": "English"}
DEFAULT_LANG = "en"   # English by default; the sidebar switch (or ?lang=zh) selects 中文


# ── language state ───────────────────────────────────────────────────────────
def _init() -> None:
    if "ui_lang" in st.session_state:
        return
    wanted = st.query_params.get("lang")
    if wanted in LANGS:
        st.session_state.ui_lang = wanted
        st.session_state.ui_lang_manual = True
    else:
        st.session_state.ui_lang = DEFAULT_LANG


def current_lang() -> str:
    _init()
    return st.session_state.ui_lang


def _on_switch() -> None:
    chosen = st.session_state.get("_lang_widget")
    if chosen in LANGS:   # the segmented control can be un-picked (None): ignore
        st.session_state.ui_lang = chosen
        st.session_state.ui_lang_manual = True
        st.query_params["lang"] = chosen


def lang_switcher(effective: str | None = None) -> str:
    """The one language control. `effective` is the language the page is really
    showing when that is not simply ui_lang (the customer page, which follows the
    conversation until the user picks one). Returns the language in force."""
    _init()
    shown = effective or st.session_state.ui_lang
    st.session_state["_lang_widget"] = shown          # keep the control in step with what is shown
    with st.sidebar:
        st.segmented_control(
            "language", options=list(LANGS), format_func=LANGS.get, key="_lang_widget",
            on_change=_on_switch, label_visibility="collapsed", selection_mode="single",
        )
    return shown


# ── strings ──────────────────────────────────────────────────────────────────
def t(key: str, **kw) -> str:
    entry = STRINGS[key]
    text = entry.get(current_lang()) or entry["zh"]
    return text.format(**kw) if kw else text


# ── navigation (replaces Streamlit's file-name based menu, which cannot be translated) ──
NAV = [
    ("app.py", "nav.chat"),
    ("pages/1_Dashboard.py", "nav.dashboard"),
    ("pages/2_客服人員介面.py", "nav.console"),
    ("pages/3_知識庫維護.py", "nav.kb"),
    ("pages/4_知識優化.py", "nav.gap"),
]


def render_nav(staff: bool = True, effective: str | None = None) -> None:
    """Sidebar navigation + language switch, to be called first on every page.
    `effective`: see lang_switcher (only the customer chat page passes it)."""
    with st.sidebar:
        if staff:
            st.markdown(f'<div class="rail-brand">🏦 {t("brand.console")}</div>', unsafe_allow_html=True)
        for path, key in NAV:
            st.page_link(path, label=t(key))
    lang_switcher(effective)


# ── localised ticket reason ──────────────────────────────────────────────────
# Tickets store their reason as Chinese text (handoff.py: "轉真人客服：<label>｜<extra>…").
# The labels below are the ones the backend writes; tests/test_i18n.py fails if the
# backend gains a new label that is not listed here.
REASON_EN = {
    "使用者主動要求真人客服": "Customer asked for an agent",
    "使用者主動要求真人": "Customer asked for an agent",           # older tickets, before the wording change
    "緊急：疑似盜刷/詐騙": "Urgent: suspected fraud",
    "帳務爭議/退款": "Billing dispute / refund",
    "需人工核准（減免/貸款/額度）": "Needs approval (waiver / loan / limit)",
    "敏感資料變更": "Sensitive data change",
    "情緒激動": "Customer upset",
    "跨帳戶/跨產品": "Cross-account / product",
    "連續未解決": "Unresolved repeatedly",
    "AI 判定知識庫不足": "AI found the knowledge base insufficient",
    # what a guest picks in the pre-transfer form, and the bill-issue marker
    "銀行帳戶客戶": "Bank account customer",
    "信用卡客戶": "Credit card customer",
    "非本行客戶": "Not yet a customer",
    "未指明": "Not specified",
    "帳單問題": "Bill issue",
}
_PREFIX = "轉真人客服："


def ticket_reason(description: str | None, lang: str | None = None, strip_prefix: bool = False) -> str:
    """Render a stored ticket description in `lang`. Fixed labels are translated;
    anything the customer typed (intake / bill detail) is shown exactly as written."""
    lang = lang or current_lang()
    desc = description or ""
    if desc.startswith(_PREFIX):
        body = desc[len(_PREFIX):]
        head = _PREFIX if not strip_prefix else ""
    else:
        body, head = desc, ""
    if lang == "zh":
        return head + body if head else body
    parts = [REASON_EN.get(p, p) for p in body.split("｜")]
    prefix_en = "Handoff: " if head else ""
    return prefix_en + " | ".join(parts)


# The knowledge-improvement pipeline stores how a draft's evidence breaks down as Chinese text
# ("未解決查詢×2；真人客服對話×1", see gap_pipeline._signal_summary / gather_signals).
SIGNAL_KIND_EN = {"未解決查詢": "unresolved queries", "低分回饋": "low-score feedback", "真人客服對話": "agent conversations"}


def signal_summary(text: str | None, lang: str | None = None) -> str:
    lang = lang or current_lang()
    if not text or lang == "zh":
        return text or "—"
    parts = []
    for part in text.split("；"):
        kind, _, n = part.partition("×")
        parts.append(f"{SIGNAL_KIND_EN.get(kind, kind)} ×{n}" if n else SIGNAL_KIND_EN.get(kind, part))
    return "; ".join(parts)


# ── waiting time ─────────────────────────────────────────────────────────────
def waiting(created_iso: str, now: datetime | None = None, lang: str | None = None) -> str:
    """How long a case has been open: "3 天 4 小時" / "3d 4h"."""
    lang = lang or current_lang()
    delta = (now or datetime.now()) - datetime.fromisoformat(created_iso)
    if delta < timedelta(0):
        delta = timedelta(0)
    days, rem = divmod(int(delta.total_seconds()), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if lang == "zh":
        if days:
            return f"{days} 天 {hours} 小時"
        if hours:
            return f"{hours} 小時 {minutes} 分"
        return f"{minutes} 分鐘"
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
