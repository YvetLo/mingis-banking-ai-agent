"""
AI Banking Customer Assistant — Frontend (Streamlit)
Sprint 2: FAQ + Account Query with Login
Sprint 13: streams the FAQ Node's answer via /chat/stream
Sprint 15: once handed off, locks into a real human-agent conversation
(see frontend/pages/2_客服人員介面.py for the agent's side)
"""

import os
import codecs
import json
import uuid
from datetime import datetime

import requests
import streamlit as st

from i18n import current_lang, render_nav
from theme import MASCOT_FULL, MASCOT_HEAD, MASCOT_HEAD_PATH, asset_data_uri, inject_theme

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Future Bank AI 客服",
    page_icon="🏦",
    layout="centered",
    initial_sidebar_state="expanded",
)

inject_theme("customer")

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend

# Mingis — the AI assistant's avatar (frontend/assets/mascot_head.png, rendered
# from design-prototype/mascot-3d.html)
AVATAR_ASSISTANT = MASCOT_HEAD_PATH

# How often the handed-off conversation polls for the agent's reply
# (Sprint 19). Matches the agent console's own refresh, so neither side
# is meaningfully ahead of the other.
HANDOFF_REFRESH_SECS = 5

DISCLAIMER = {
    "zh": "本助理提供之資訊僅供參考，不構成財務建議。實際利率、費用以官網公告為準。",
    "en": "Information provided is for reference only and does not constitute financial advice.",
}

WELCOME = {
    "zh": "信用卡費用、帳戶服務、轉帳規則都可以問；登入後還能查詢帳單和消費明細。",
    "en": "Ask about card fees, account services or transfer rules — log in to also check your bill and transactions.",
}

HERO_BADGE = {"zh": "🏦 Future銀行 AI 客服・Mingis", "en": "🏦 Future Bank AI Assistant · Mingis"}
HERO_TITLE = {
    "zh": "嗨，我是 Mingis<br>今天想問什麼呢？",
    "en": "Hi, I'm Mingis<br>How can I help today?",
}
# Once logged in, greet the customer by name, like the reference screen.
HERO_TITLE_NAMED = {
    "zh": "{name}，您好<br>今天想問什麼呢？",
    "en": "Hi {name},<br>how can I help today?",
}

TEST_ACCOUNTS = [
    ("demo_user1", "demo1234", "陳小明（一般上班族，2 張信用卡）"),
    ("demo_user2", "demo5678", "王大明（商務人士，無限卡）"),
    ("demo_user3", "demo9999", "陳春花（銀髮族，定存帳戶）"),
]

# Score → face (Sprint 16). 笑臉 for happy, 哭臉 for unhappy — the icon
# represents the score, so any 1-5 input maps to one of these.
RATING_SCALE = {1: "😢", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}
RATING_LABEL = {
    "zh": {1: "很不滿意", 2: "不太滿意", 3: "普通", 4: "滿意", 5: "很滿意"},
    "en": {1: "Very unhappy", 2: "Unhappy", 3: "Okay", 4: "Happy", 5: "Very happy"},
}

# Every customer-facing string, keyed by the language the backend detected
# (st.session_state.language). Terminology is fixed on purpose: 真人客服 /
# "human agent" is the channel the customer is transferred to, 客服專員 /
# "agent" is the person replying in it — same split the backend's own
# replies use (nodes.py). Error copy never names internals (uvicorn,
# exception text): the customer can't act on those, and they read as alarm.
UI_TEXT = {
    "title": {"zh": "🏦 Future銀行 AI 客服", "en": "🏦 Future Bank AI Assistant"},
    "err_connection": {
        "zh": "⚠️ 系統暫時無法連線，請稍後再試一次。",
        "en": "⚠️ We can't connect right now. Please try again in a moment.",
    },
    "err_reply": {
        "zh": "⚠️ 抱歉，這次沒能取得回覆，請再傳送一次您的問題。",
        "en": "⚠️ Sorry, we couldn't get a reply. Please send your question again.",
    },
    "err_thread": {
        "zh": "⚠️ 暫時無法載入對話，系統會自動重試。",
        "en": "⚠️ Couldn't load the conversation. We'll retry automatically.",
    },
    "err_send": {
        "zh": "⚠️ 訊息沒有送出，請再傳送一次。",
        "en": "⚠️ Your message wasn't sent. Please send it again.",
    },
    "err_rating": {
        "zh": "⚠️ 評分沒有送出，請再按一次「送出評分」。",
        "en": "⚠️ Your rating wasn't sent. Please tap “Submit rating” again.",
    },
    "login_failed": {
        "zh": "帳號或密碼不正確，請再試一次，或使用下方的「測試帳號」。",
        "en": "Incorrect username or password. Try again, or use a test account below.",
    },
    "login_missing": {"zh": "請輸入帳號和密碼", "en": "Please enter your username and password"},
    "logged_in": {"zh": "✅ 已登入：{name}", "en": "✅ Logged in: {name}"},
    "test_accounts": {"zh": "📋 測試帳號", "en": "📋 Test accounts"},
    "new_chat": {"zh": "開始新對話", "en": "Start new chat"},
    "can_ask": {"zh": "**💡 可以問：**", "en": "**💡 Try asking:**"},
    "stuck_hint": {
        "zh": "💬 一直找不到答案嗎？直接輸入「我要找真人客服」，我們會幫您轉接。",
        "en": "💬 Not finding what you need? Type “I want a human agent” and we'll transfer you.",
    },
    "dev_info": {"zh": "🛠 開發者資訊（Demo）", "en": "🛠 Developer info (demo)"},
    "workflow_banner": {
        "zh": "🔒 信用卡掛失進行中：{step}　　輸入「取消」可隨時結束",
        "en": "🔒 Card block in progress: {step}　　Type “cancel” to stop anytime",
    },
    "handoff_banner": {
        "zh": "🤝 已為您轉接真人客服。客服專員的回覆會直接顯示在下方，不用重新整理頁面；您也可以先描述您的狀況。",
        "en": "🤝 You've been transferred to a human agent. Their reply will appear below automatically — no need to refresh. Feel free to describe your situation in the meantime.",
    },
    "mingis_wait": {
        "zh": "客服專員馬上就來。我已把您的問題整理好交給他，您可以先補充說明。",
        "en": "An agent will be right with you. I've passed your question along — feel free to add details meanwhile.",
    },
    "mingis_live": {
        "zh": "客服專員已接手，我在一旁協助記錄。需要我時隨時叫我！",
        "en": "An agent has taken over and I'm assisting from the side. Call me anytime you need me!",
    },
    "mingis_done": {
        "zh": "問題已處理完成。還有其他問題，隨時找我！",
        "en": "All done on this one. If you have other questions, I'm right here!",
    },
    "chip_wait": {"zh": "等待客服專員接手", "en": "Waiting for an agent"},
    "chip_live": {"zh": "客服專員服務中", "en": "Agent on the case"},
    "chip_done": {"zh": "已結案", "en": "Resolved"},
    "handoff_resolved": {
        "zh": "✅ 客服專員已將這次的問題標記為已解決，謝謝您的耐心等候！",
        "en": "✅ Your agent has marked this case as resolved. Thank you for your patience!",
    },
    "rate_service": {"zh": "⭐ 為這次服務評分", "en": "⭐ Rate this service"},
    "agent_label": {"zh": "客服專員", "en": "Agent"},
    "handoff_status": {
        "zh": "🕘 最後更新 {time}　|　每 {secs} 秒自動接收客服專員的回覆",
        "en": "🕘 Last updated {time}　|　Checking for agent replies every {secs}s",
    },
    "handoff_input": {"zh": "輸入訊息給客服專員…", "en": "Message your agent…"},
    "chat_input": {"zh": "輸入您的問題（中文或英文皆可）", "en": "Ask your question (English or Chinese)"},
    "followups": {"zh": "💡 您可能還想問：", "en": "💡 You might also ask:"},
    "thinking": {"zh": "Mingis 正在幫您查詢…", "en": "Mingis is looking into it…"},
    "sources": {"zh": "📚 參考來源：{sources}", "en": "📚 Sources: {sources}"},
    "end_and_rate": {"zh": "⭐ 結束對話並評分", "en": "⭐ End chat and rate"},
    "rating_thanks": {
        "zh": "🙏 謝謝您的評分！您的回饋會幫助我們改善服務。",
        "en": "🙏 Thanks for your rating! Your feedback helps us improve.",
    },
    "rating_title": {"zh": "### 請為這次的服務評分", "en": "### How was your experience?"},
    "rating_caption": {"zh": "您的評分會幫助我們改善服務 🙌", "en": "Your rating helps us improve 🙌"},
    "rating_picked": {"zh": "您的評分：{face} {score} 分（{label}）", "en": "Your rating: {face} {score} ({label})"},
    "rating_comment": {"zh": "方便告訴我們哪裡可以再改進嗎？（選填）", "en": "What could we do better? (optional)"},
    "rating_placeholder": {"zh": "例如：問了幾次都沒得到我要的資訊…", "en": "e.g. I asked several times but didn't get what I needed…"},
    "rating_submit": {"zh": "送出評分", "en": "Submit rating"},
    "back_to_chat": {"zh": "← 返回對話", "en": "← Back to chat"},
    "logged_in_as": {"zh": "🔓 登入身分：{name}", "en": "🔓 Logged in as: {name}"},
}

STEP_LABELS = {
    "zh": {1: "步驟 1/3 身分驗證", 2: "步驟 2/3 選擇卡片", 3: "步驟 3/3 確認掛失"},
    "en": {1: "Step 1/3 Verify identity", 2: "Step 2/3 Choose card", 3: "Step 3/3 Confirm"},
}

EXAMPLE_QUESTIONS = {
    ("zh", True): ["我本月帳單多少？", "我的帳戶餘額是多少？", "幫我看最近的消費明細", "我要掛失信用卡"],
    ("zh", False): ["信用卡年費多少？", "ATM 每天可以提多少？", "轉帳手續費怎麼算？"],
    ("en", True): ["What's my current bill?", "What's my account balance?", "Show my recent transactions", "I want to block my card"],
    ("en", False): ["What's the annual fee?", "What's the daily ATM limit?", "What is the cashback rate?"],
}


def _lang() -> str:
    current_lang()   # makes sure ?lang= / the switcher state is read before we look at it
    # A language picked with the switcher wins; otherwise follow the language the
    # customer is writing in (set from each reply's X-Language header).
    lang = st.session_state.ui_lang if st.session_state.get("ui_lang_manual") else st.session_state.get("language", "zh")
    return lang if lang in ("zh", "en") else "zh"


def t(key: str, **kwargs) -> str:
    """Customer-facing copy in the current language (see UI_TEXT)."""
    text = UI_TEXT[key][_lang()]
    return text.format(**kwargs) if kwargs else text


def _md_safe(text: str) -> str:
    """Escapes '$' for display only. Bank replies say things like
    "NT$12,450" — Streamlit's markdown renderer treats a pair of bare $
    as a LaTeX span, which swallows the amount and any ** bold markers
    between them. Callers must apply this at the st.markdown/write_stream
    boundary, never to text going back into session_state or the backend,
    or the escaping compounds on every rerun."""
    return text.replace("$", "\\$")


# ── Session State Init ─────────────────────────────────────────────────────────
def _restore_from_backend(session_id: str) -> bool:
    """Sprint 19 — a browser refresh drops Streamlit's own st.session_state
    entirely (there's no server affinity keeping it alive), so without
    this a refresh mid-conversation used to lose the login, the whole
    chat, and any in-progress workflow (e.g. mid card-loss). The backend
    persists state after every /chat turn (see backend/main.py's
    _persist_session); this restores it when the URL already carries the
    ?sid= from before the refresh (see init_session() below for where sid
    itself is kept alive). Returns True only on an actual restore, so the
    caller knows whether it still needs to assign a session_id itself."""
    try:
        resp = requests.get(f"{API_URL}/session/{session_id}", timeout=10)
    except requests.exceptions.ConnectionError:
        return False
    if resp.status_code != 200:
        return False
    data = resp.json()
    st.session_state.session_id = session_id
    st.session_state.messages = data["messages"]
    st.session_state.language = data["language"]
    st.session_state.workflow = data["workflow"]
    st.session_state.handoff_active = data["handoff_active"]
    st.session_state.handoff_ticket_id = data["handoff_ticket_id"]
    if data["user_id"]:
        st.session_state.user_id = data["user_id"]
        st.session_state.user_name = data["user_name"]
        st.session_state.token = data["token"]
        st.session_state.is_authenticated = True
    return True


def init_session():
    defaults = {
        "messages": [],
        "language": "zh",
        "welcomed": False,
        "user_id": None,
        "user_name": None,
        "token": None,          # JWT from /mock-api/auth/login — sent as Authorization: Bearer
        "is_authenticated": False,
        "workflow": {"step": 0, "data": {}},
        "fallback_count": 0,
        "rag_sources": [],
        "handoff_active": False,
        "handoff_ticket_id": None,
        "suggestions": [],               # quick-reply shortcuts under the last answer
        "pending_suggestion": None,      # set by a shortcut click, consumed as input
        "rating_prompt_active": False,   # showing the end-of-chat rating UI
        "pending_score": None,           # score picked, not yet submitted
        "rating_submitted": False,       # rating done for this conversation
    }
    # session_id is handled separately below (restored or freshly minted),
    # so its presence — not the loop above — is what "already initialized
    # this browser session" means here.
    first_run = "session_id" not in st.session_state
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if first_run:
        sid = st.query_params.get("sid")
        if not (sid and _restore_from_backend(sid)):
            st.session_state.session_id = sid or str(uuid.uuid4())
            st.query_params["sid"] = st.session_state.session_id

init_session()


def reset_conversation():
    """Fresh conversation — same fields the sidebar and post-rating
    "新對話" button both clear. Keeps auth state untouched. Also rotates
    the URL's ?sid= (Sprint 19) — otherwise a refresh right after
    starting a new conversation would restore the old, just-abandoned one
    instead of the blank slate the customer asked for."""
    st.session_state.messages = []
    st.session_state.session_id = str(uuid.uuid4())
    st.query_params["sid"] = st.session_state.session_id
    st.session_state.welcomed = False
    st.session_state.workflow = {"step": 0, "data": {}}
    st.session_state.fallback_count = 0
    st.session_state.handoff_active = False
    st.session_state.handoff_ticket_id = None
    st.session_state.rating_prompt_active = False
    st.session_state.pending_score = None
    st.session_state.rating_submitted = False
    st.session_state.handoff_resolved_seen = False
    st.session_state.suggestions = []
    st.session_state.pending_suggestion = None


def use_suggestion(question: str):
    """Shortcut click → next run treats it exactly like typed input.
    An on_click callback (rather than checking the button's return value)
    because these buttons render near the BOTTOM of the script, after the
    input-handling block — the callback runs before the next script run,
    so the question is processed on that run instead of needing an extra
    st.rerun() round trip."""
    st.session_state.pending_suggestion = question


def _display_name(full: str, language: str) -> str:
    """Mock-API names come as "陳小明 / Chen Xiao-Ming" — greet in the page's language."""
    parts = [p.strip() for p in (full or "").split("/")]
    return parts[-1] if language == "en" and len(parts) > 1 else parts[0]


def render_hero(language: str) -> None:
    """Empty-conversation hero — full-body mascot, badge, big greeting
    (matches design-prototype/ink-wash-redesign.html, section 02)."""
    # Every line starts at column 0 — Streamlit's markdown parser treats a
    # 4-space indent as a code block, which renders the HTML as literal text.
    if st.session_state.is_authenticated and st.session_state.user_name:
        title = HERO_TITLE_NAMED[language].format(name=_display_name(st.session_state.user_name, language))
    else:
        title = HERO_TITLE[language]
    html = (
        '<div class="hero">'
        + f'<img class="hero-bot" src="{asset_data_uri(MASCOT_FULL)}" alt="Mingis">'
        + f'<div><span class="hero-badge">{HERO_BADGE[language]}</span></div>'
        + f'<div class="hero-title">{title}</div>'
        + f'<p class="hero-sub">{WELCOME[language]}</p>'
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_suggestions(questions: list[str], caption: str | None, key_prefix: str, stacked: bool = False):
    """Clickable questions. Rendered as buttons rather than a selectbox/pills
    so a single tap sends the question — the whole point is to save the
    customer from typing. `stacked` lays them out as the hero's centred
    vertical pills; otherwise they share one row under an answer."""
    if not questions:
        return
    if caption:
        st.caption(caption)
    if stacked:
        for i, question in enumerate(questions):
            st.button(question, key=f"{key_prefix}_{i}", on_click=use_suggestion, args=(question,))
        return
    cols = st.columns(len(questions))
    for i, (col, question) in enumerate(zip(cols, questions)):
        col.button(
            question,
            key=f"{key_prefix}_{i}",
            use_container_width=True,
            on_click=use_suggestion,
            args=(question,),
        )


def render_rating_flow(inline: bool = False):
    """Session-level CSAT (Sprint 16). Reached two ways: the "結束對話並評分"
    button of a normal chat (a full rating screen), or — since 2026-11 — drawn
    inline under the conversation the moment an agent marks the case resolved
    (`inline=True`; no button to find, and the agent's last message stays in
    view). Score maps to a face; scores <= 2 also ask an optional reason
    (feeds the knowledge improvement pipeline)."""
    labels = RATING_LABEL[_lang()]
    if inline:
        st.divider()
    if st.session_state.rating_submitted:
        st.success(t("rating_thanks"))
        if st.button(t("new_chat"), type="primary", use_container_width=True):
            reset_conversation()
            st.rerun()
        return

    st.markdown(t("rating_title"))
    st.caption(t("rating_caption"))

    cols = st.columns(5)
    for i, score in enumerate([1, 2, 3, 4, 5]):
        if cols[i].button(RATING_SCALE[score], key=f"rate_btn_{score}", use_container_width=True):
            st.session_state.pending_score = score
            st.rerun()
        cols[i].caption(f"{score}｜{labels[score]}")

    score = st.session_state.pending_score
    if score:
        st.info(t("rating_picked", face=RATING_SCALE[score], score=score, label=labels[score]))
        comment = ""
        if score <= 2:
            comment = st.text_area(
                t("rating_comment"),
                key="rating_comment",
                placeholder=t("rating_placeholder"),
            )
        if st.button(t("rating_submit"), type="primary"):
            # /rating verifies a body user_id against the bearer token, so a
            # logged-in customer's rating must carry it — and a non-2xx has
            # to surface, or a rejected rating would still show "thanks".
            headers = (
                {"Authorization": f"Bearer {st.session_state.token}"}
                if st.session_state.token else {}
            )
            try:
                requests.post(
                    f"{API_URL}/rating",
                    json={
                        "session_id": st.session_state.session_id,
                        "score": score,
                        "user_id": st.session_state.user_id,
                        "comment": comment,
                    },
                    headers=headers,
                    timeout=10,
                ).raise_for_status()
                st.session_state.rating_submitted = True
                st.rerun()
            except requests.exceptions.RequestException:
                st.error(t("err_rating"))

    if not inline and st.button(t("back_to_chat"), use_container_width=True):
        st.session_state.rating_prompt_active = False
        st.session_state.pending_score = None
        st.rerun()

# ── Sidebar — Login ────────────────────────────────────────────────────────────
# Each st.container(border=True) below renders as a rounded "rail-card" —
# see theme.py's [data-testid="stVerticalBlockBorderWrapper"] rule —
# matching the grouped-card rail from the approved prototype instead of
# a flat, divider-separated list.
render_nav(staff=False, effective=_lang())

with st.sidebar:

    with st.container(border=True):
        if not st.session_state.is_authenticated:
            st.subheader("🔐 登入 / Log in")
            username = st.text_input("帳號 / Username", key="login_username")
            password = st.text_input("密碼 / Password", type="password", key="login_password")

            if st.button("登入 / Login", use_container_width=True, type="primary"):
                if username and password:
                    try:
                        resp = requests.post(
                            f"{API_URL}/mock-api/auth/login",
                            json={"username": username, "password": password},
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            # Logging in while a handoff is already open (e.g. a
                            # guest who escalated, then logs in per the reminder
                            # in the bot's reply) should NOT reset the customer
                            # back to a blank AI conversation — it should keep
                            # the same handoff thread and just attach their
                            # identity to it, so the agent doesn't have to
                            # re-verify who they're talking to.
                            mid_handoff = st.session_state.handoff_active and st.session_state.handoff_ticket_id
                            st.session_state.user_id = data["user_id"]
                            st.session_state.user_name = data["name"]
                            st.session_state.token = data["token"]
                            st.session_state.is_authenticated = True
                            if mid_handoff:
                                try:
                                    requests.post(
                                        f"{API_URL}/handoff/{st.session_state.handoff_ticket_id}/link-user",
                                        json={"user_id": data["user_id"]},
                                        headers={"Authorization": f"Bearer {data['token']}"},
                                        timeout=10,
                                    )
                                except Exception:
                                    pass
                            else:
                                st.session_state.messages = []
                                st.session_state.welcomed = False
                                st.session_state.handoff_active = False
                                st.session_state.handoff_ticket_id = None
                                st.session_state.rating_prompt_active = False
                                st.session_state.pending_score = None
                                st.session_state.rating_submitted = False
                            st.rerun()
                        else:
                            st.error(t("login_failed"))
                    except requests.exceptions.ConnectionError:
                        st.error(t("err_connection"))
                else:
                    st.warning(t("login_missing"))

            with st.expander(t("test_accounts")):
                for uname, pwd, desc in TEST_ACCOUNTS:
                    st.caption(f"**{uname}** / {pwd}")
                    st.caption(f"  → {desc}")

        else:
            st.success(t("logged_in", name=st.session_state.user_name))

            if st.button("登出 / Logout", use_container_width=True):
                st.session_state.is_authenticated = False
                st.session_state.user_id = None
                st.session_state.user_name = None
                st.session_state.token = None
                reset_conversation()
                st.rerun()

    with st.container(border=True):
        st.markdown(t("can_ask"))
        for q in EXAMPLE_QUESTIONS[(_lang(), bool(st.session_state.is_authenticated))]:
            st.caption(f"• {q}")

    if st.button(f"💬 {t('new_chat')}", use_container_width=True):
        reset_conversation()
        st.rerun()

    # Build/debug details for demos — collapsed so customers (and screen
    # recordings) don't read them as part of the product. fallback_count is
    # the auto-handoff trigger; MAX_HISTORY_TURNS (backend) caps how many
    # turns the model sees as context, not how long a chat may run.
    with st.expander(t("dev_info")):
        st.caption("Sprint 16 — LangGraph + Verifier + Streaming + Handoff + CSAT")
        st.caption(f"Session: `{st.session_state.session_id[:8]}...`")
        st.caption(f"Language: {st.session_state.language}")
        st.caption(f"Turns: {len(st.session_state.messages) // 2}（context window: last 10）")
        st.caption(f"Unresolved streak: {st.session_state.fallback_count}/3 → auto handoff")

# ── Main Chat Area ─────────────────────────────────────────────────────────────
lang = _lang()
st.markdown(f'<div class="topbar">{t("title")}</div>', unsafe_allow_html=True)
# The disclaimer sits under the docked chat input, as small print — the
# input lives in Streamlit's own bottom container, so it's attached there.
st.markdown(
    "<style>[data-testid='stBottomBlockContainer']::after {"
    f"content: '{DISCLAIMER[lang]}'; display: block; text-align: center;"
    "font-size: 12px; color: var(--muted); margin-top: 8px; }</style>",
    unsafe_allow_html=True,
)

if st.session_state.is_authenticated:
    st.caption(t("logged_in_as", name=st.session_state.user_name))

# Workflow progress banner
wf_step = st.session_state.workflow.get("step", 0)
# The card-loss flow predates workflow "type" and carries none; the intake and
# bill-clarify flows do — they must not show a "card block in progress" banner.
wf_is_card_loss = not st.session_state.workflow.get("data", {}).get("type")
if wf_step > 0 and wf_is_card_loss:
    st.warning(t("workflow_banner", step=STEP_LABELS[lang].get(wf_step, "")))

# Handoff banner — persists for the rest of the session once triggered
if st.session_state.handoff_active and not st.session_state.handoff_ticket_id:
    st.warning(t("handoff_banner"))
# Two misses in a row (the third auto-escalates — see force_handoff below):
# tell the customer they can ask for a person instead of letting them keep
# rephrasing into the same dead end.
elif st.session_state.fallback_count >= 2:
    st.info(t("stuck_hint"))

if st.session_state.rating_prompt_active:
    # ── Session-end satisfaction rating (Sprint 16) ─────────────────────────
    # Takes precedence over both flows below: once the customer chooses to
    # rate (explicit end, or after a resolved handoff), the conversation is
    # over and the only thing on screen is the rating card.
    render_rating_flow()

elif st.session_state.handoff_active and st.session_state.handoff_ticket_id:
    # ── Handoff conversation view (Sprint 15) ───────────────────────────────
    # Completely replaces the AI flow below — once handed off, the customer
    # talks only to the human queue until the case is resolved, per the
    # scope decided for this feature (no mixed AI/human routing).
    ticket_id = st.session_state.handoff_ticket_id

    @st.fragment(run_every=HANDOFF_REFRESH_SECS)
    def render_handoff_thread(tid: str):
        """Polls the thread on a timer so the agent's reply appears on its
        own — waiting on a chat that only updates when you click is the
        one thing a customer shouldn't have to do. Scoped to a fragment
        so the timer doesn't re-run the whole page (and the message the
        customer is typing survives)."""
        try:
            thread_resp = requests.get(f"{API_URL}/handoff/{tid}/messages", timeout=10)
            thread_resp.raise_for_status()
            thread_data = thread_resp.json()
            ticket = thread_data["ticket"]
            thread_messages = thread_data["messages"]
        except requests.exceptions.RequestException:
            st.error(t("err_thread"))
            return

        if ticket["status"] == "resolved":
            st.success(t("handoff_resolved"))
            if not st.session_state.get("handoff_resolved_seen"):
                # First time we see it resolved: redraw the whole page once so the
                # rating panel (drawn outside this timer-driven fragment) appears now.
                st.session_state.handoff_resolved_seen = True
                st.rerun(scope="app")

        # Mingis stays visible while the human agent is on the case (status
        # follows the ticket, refreshed with the thread).
        agent_replied = any(m["role"] == "agent" for m in thread_messages)
        state = "done" if ticket["status"] == "resolved" else ("live" if agent_replied else "wait")
        st.markdown(
            '<div class="mingis-bar">'
            f'<img src="{asset_data_uri(MASCOT_HEAD)}" alt="Mingis">'
            '<div>'
            f'<span class="nm">Mingis</span><span class="chip {state}">{t("chip_" + state)}</span>'
            f'<div class="msg">{t("mingis_" + state)}</div>'
            '</div></div>',
            unsafe_allow_html=True,
        )

        for m in thread_messages:
            if m["role"] == "agent":
                with st.chat_message("assistant", avatar="🧑‍💼"):
                    st.caption(t("agent_label"))
                    st.markdown(_md_safe(m["content"]))
            else:
                avatar = AVATAR_ASSISTANT if m["role"] == "assistant" else None
                with st.chat_message(m["role"], avatar=avatar):
                    st.markdown(_md_safe(m["content"]))

        st.caption(t("handoff_status", time=datetime.now().strftime("%H:%M:%S"), secs=HANDOFF_REFRESH_SECS))

    render_handoff_thread(ticket_id)

    # Resolved → ask for the 1-5 rating right under the conversation, faces in order.
    if st.session_state.get("handoff_resolved_seen"):
        render_rating_flow(inline=True)

    handoff_input = st.chat_input(t("handoff_input"))
    if handoff_input:
        try:
            requests.post(
                f"{API_URL}/handoff/{ticket_id}/messages",
                json={"role": "user", "content": handoff_input},
                timeout=10,
            ).raise_for_status()
            st.rerun()
        except requests.exceptions.RequestException:
            # No rerun here: it would wipe the error before the customer
            # sees it. The thread fragment keeps polling regardless.
            st.error(t("err_send"))

else:
    # ── Normal AI conversation flow ─────────────────────────────────────────
    # Resolved before the hero-vs-history choice below: st.chat_input always
    # docks to its own fixed bottom region regardless of call order, so
    # reading it early is safe — and it's required here, because a fresh
    # submission (or shortcut click) is about to append a message further
    # down. Without checking that up front, the hero would still render off
    # the pre-submission (empty) state, stacking on top of the very answer
    # that just made the conversation non-empty.
    user_input = st.chat_input(t("chat_input"))
    if st.session_state.pending_suggestion:
        user_input = st.session_state.pending_suggestion
        st.session_state.pending_suggestion = None

    if not st.session_state.messages and not user_input:
        # Empty conversation — the mascot hero replaces the old plain
        # welcome bubble as the page's opening thesis.
        render_hero(lang)
        st.session_state.welcomed = True

        # Starter shortcuts — only here, where the customer has nothing to
        # go on yet. Fetched from the backend so the wording lives with the
        # knowledge base it has to stay answerable against.
        cache_key = f"starters_{lang}_{st.session_state.is_authenticated}"
        if cache_key not in st.session_state:
            try:
                st.session_state[cache_key] = requests.get(
                    f"{API_URL}/suggestions",
                    params={"language": lang, "authenticated": st.session_state.is_authenticated},
                    timeout=15,
                ).json().get("suggestions", [])
            except Exception:
                st.session_state[cache_key] = []  # a down backend already errors on send
        render_suggestions(st.session_state[cache_key], None, "starter", stacked=True)
    else:
        # Chat history
        for msg in st.session_state.messages:
            avatar = AVATAR_ASSISTANT if msg["role"] == "assistant" else None
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(_md_safe(msg["content"]))

    if user_input:
        st.session_state.suggestions = []   # stale shortcuts must not outlive their answer
        with st.chat_message("user"):
            st.markdown(_md_safe(user_input))

        assistant_reply = ""
        with st.chat_message("assistant", avatar=AVATAR_ASSISTANT):
            try:
                fc = st.session_state.fallback_count
                # The spinner only covers time-to-first-token (classify_intent,
                # and the grounding verifier on ambiguous FAQ retrievals — see
                # nodes.py) — requests.post(stream=True) returns as soon as
                # response headers arrive, which for /chat/stream is right
                # when the server starts the actual answer generation.
                headers = (
                    {"Authorization": f"Bearer {st.session_state.token}"}
                    if st.session_state.token else {}
                )
                with st.spinner(t("thinking")):
                    resp = requests.post(
                        f"{API_URL}/chat/stream",
                        json={
                            "message": user_input,
                            "session_id": st.session_state.session_id,
                            "history": st.session_state.messages,
                            "user_id": st.session_state.user_id,
                            "workflow": st.session_state.workflow,
                            "fallback_count": fc,
                            "force_handoff": fc >= 3,
                        },
                        headers=headers,
                        timeout=30,
                        stream=True,
                    )
                    resp.raise_for_status()

                # Streamed chunks are shown escaped (see _md_safe) so bare
                # $ in amounts doesn't get read as LaTeX, but the raw,
                # un-escaped text is what has to end up in session_state —
                # it's replayed through history on every rerun and sent
                # back to the backend as conversation context, and
                # escaping that too would double up each round-trip.
                raw_reply_parts = []

                def token_gen():
                    # Decode incrementally (not decode_unicode=True on
                    # iter_content) so a multi-byte UTF-8 character split
                    # across two network chunks never gets corrupted —
                    # matters a lot here since almost every response is
                    # Traditional Chinese.
                    decoder = codecs.getincrementaldecoder("utf-8")()
                    for raw_chunk in resp.iter_content(chunk_size=256):
                        if raw_chunk:
                            text = decoder.decode(raw_chunk)
                            if text:
                                raw_reply_parts.append(text)
                                yield _md_safe(text)
                    tail = decoder.decode(b"", final=True)
                    if tail:
                        raw_reply_parts.append(tail)
                        yield _md_safe(tail)

                st.write_stream(token_gen())
                assistant_reply = "".join(raw_reply_parts)

                st.session_state.language = resp.headers.get("X-Language", "zh")
                workflow_header = resp.headers.get("X-Workflow")
                st.session_state.workflow = json.loads(workflow_header) if workflow_header else {"step": 0, "data": {}}
                rag_sources_header = resp.headers.get("X-Rag-Sources")
                st.session_state.rag_sources = json.loads(rag_sources_header) if rag_sources_header else []
                suggestions_header = resp.headers.get("X-Suggestions")
                st.session_state.suggestions = json.loads(suggestions_header) if suggestions_header else []
                if resp.headers.get("X-Is-Handoff") == "true":
                    st.session_state.handoff_active = True
                    ticket_id = resp.headers.get("X-Handoff-Ticket-Id")
                    if ticket_id:
                        st.session_state.handoff_ticket_id = ticket_id
                if resp.headers.get("X-Is-Negative-Feedback") == "true":
                    st.session_state.fallback_count += 1
                else:
                    st.session_state.fallback_count = 0

            except requests.exceptions.ConnectionError:
                assistant_reply = t("err_connection")
                st.markdown(assistant_reply)
            except Exception:
                assistant_reply = t("err_reply")
                st.markdown(assistant_reply)

            sources = st.session_state.get("rag_sources", [])
            if sources:
                st.caption(t("sources", sources=", ".join(sources)))

        st.session_state.messages.append({"role": "user", "content": user_input})
        st.session_state.messages.append({"role": "assistant", "content": assistant_reply})

        # The view branch at the top of this script already ran, so a turn
        # that just escalated would otherwise leave the customer looking at
        # the AI input box until they happened to send
        # something else — while the agent console already has their case.
        # Nothing is lost by rerunning: escalate_to_human() has already
        # persisted this exact reply into the ticket thread the handoff
        # view reads from.
        # Same reasoning for a language switch: everything above (title,
        # sidebar, banners) was already drawn in the previous language, so
        # the first English answer would otherwise sit inside a Chinese page.
        if (st.session_state.handoff_active and st.session_state.handoff_ticket_id) \
                or _lang() != lang:
            st.rerun()

    # End-of-conversation rating entry point. Rendered here (end of the normal
    # flow, after any new messages are appended) rather than in the sidebar so
    # it appears in the SAME run as the answer — a user who's satisfied and
    # done won't send another message, so a one-rerun-late button could never
    # show for them.
    # Hidden once this turn escalated to a human (handoff_active set above):
    # the case isn't resolved yet, so rating is premature — it reappears only
    # after the agent resolves it, via the "為這次服務評分" button in the
    # handoff view. Rating the AI for a question it correctly handed off would
    # also be measuring the wrong thing.
    # Follow-up shortcuts for the answer above (Sprint 20). Suppressed
    # during a handoff for the same reason as the rating button: the
    # customer is waiting on a person, not browsing FAQ topics.
    if not st.session_state.handoff_active:
        render_suggestions(
            st.session_state.suggestions, t("followups"), "followup",
        )

    if st.session_state.messages and not st.session_state.handoff_active:
        st.divider()
        if st.button(t("end_and_rate"), use_container_width=True):
            st.session_state.rating_prompt_active = True
            st.session_state.rating_submitted = False
            st.session_state.pending_score = None
            st.rerun()
