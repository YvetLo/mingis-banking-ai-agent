"""
AI Banking Customer Assistant — Agent Console (Streamlit Page)
Real human-agent replies to escalated conversations — see backend main.py's
/handoff/* endpoints and frontend/app.py for the customer-facing side of the
same conversation thread.

Both sides are live: a Streamlit script only re-runs on interaction, so a
customer's reply used to sit in the database until the agent happened to click
something. The thread and the queue counter sit in st.fragment(run_every=...)
blocks, which re-run on a timer WITHOUT re-running the page — so a half-typed
reply in the chat box survives the refresh.

2026-11: the queue puts urgent cases first and shows how long each has been
waiting; "mark resolved" asks first and can be undone; ticket facts are one row of
chips; the page speaks Chinese or English (see i18n.py).
"""

import os
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components

from case_view import status_label, ticket_chips
from i18n import current_lang, render_nav, t, ticket_reason, waiting
from staff_auth import staff_session
from theme import MASCOT_HEAD_PATH, inject_theme

st.set_page_config(
    page_title=f"{t('console.page_title')} — {t('common.suffix')}",
    page_icon="🧑‍💼",
    layout="wide",
)

inject_theme("staff")
render_nav()

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend

# Mingis — same mascot avatar as the customer-facing app, so the AI's own
# pre-handoff messages are recognizable here too.
AVATAR_ASSISTANT = MASCOT_HEAD_PATH
REFRESH_SECS = 5        # thread polling — fast enough to feel like chat
QUEUE_REFRESH_SECS = 15  # new-ticket watcher; new cases aren't as time-critical

head_l, head_r = st.columns([3, 2], vertical_alignment="bottom")
head_l.title(t("console.title"))
head_l.caption(t("console.purpose"))
with head_r:
    auto_refresh = st.toggle(t("console.auto", s=REFRESH_SECS), value=True, help=t("console.auto_help"))


def fetch(endpoint: str, params: dict = None):
    try:
        r = staff_session().get(f"{API_URL}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, t("common.err_connect")
    except Exception as e:
        return None, t("common.err", e=e)


@st.fragment(run_every=REFRESH_SECS if auto_refresh else None)
def render_thread(ticket_id: str):
    """The live half of the page. Re-runs on its own timer, so a new
    customer message shows up without the agent touching anything —
    and without re-running the script around it."""
    thread_data, thread_err = fetch(f"/handoff/{ticket_id}/messages")
    if thread_err:
        st.error(thread_err)
        return

    ticket = thread_data["ticket"]
    messages = thread_data["messages"]

    st.markdown(ticket_chips(ticket), unsafe_allow_html=True)

    for m in messages:
        if m["role"] == "agent":
            with st.chat_message("assistant", avatar="🧑‍💼"):
                st.caption(t("console.me"))
                st.markdown(m["content"])
        elif m["role"] == "user":
            with st.chat_message("user"):
                st.markdown(m["content"])
        else:
            with st.chat_message("assistant", avatar=AVATAR_ASSISTANT):
                st.caption(t("case.mingis_before"))
                st.markdown(m["content"])

    stamp = datetime.now().strftime("%H:%M:%S")
    st.caption(
        t("console.updated", t=stamp, s=REFRESH_SECS) if auto_refresh else t("console.updated_off", t=stamp)
    )
    if not auto_refresh and st.button(t("console.refresh_now"), key="manual_refresh_thread"):
        st.rerun(scope="fragment")


@st.fragment(run_every=QUEUE_REFRESH_SECS if auto_refresh else None)
def watch_queue(known_count: int):
    """Notices cases that arrived after this page was drawn. Only offers
    a reload instead of doing it — reloading unprompted would yank the
    selected case out from under the agent mid-reply."""
    latest, queue_err = fetch("/handoff/tickets", {"status": "open", "limit": 50})
    if queue_err or latest is None or len(latest) == known_count:
        return
    st.info(t("console.queue_changed", n=len(latest)))
    if st.button(t("console.reload"), key="reload_queue"):
        st.rerun(scope="app")


def confirm_resolve(ticket_id: str):
    """Resolving takes the case out of the queue, so ask first (it can still be reopened)."""
    @st.dialog(t("console.confirm_title"))
    def _dialog():
        st.markdown(t("console.confirm_body", id=ticket_id))
        yes, no = st.columns(2)
        if yes.button(t("console.confirm_yes"), type="primary", use_container_width=True):
            try:
                staff_session().post(f"{API_URL}/handoff/{ticket_id}/resolve", timeout=10).raise_for_status()
                st.session_state["just_resolved"] = ticket_id
                st.rerun()
            except Exception as e:
                st.error(t("common.op_failed", e=e))
        if no.button(t("console.confirm_no"), use_container_width=True):
            st.rerun()
    _dialog()


def sort_key(ticket: dict, oldest_first: bool):
    urgent = 0 if ticket.get("priority") == "high" else 1     # urgent always on top
    created = datetime.fromisoformat(ticket["created_at"]).timestamp()
    return (urgent, created if oldest_first else -created)


# ── undo for the last "resolved" ─────────────────────────────────────────────
undo_id = st.session_state.get("just_resolved")
if undo_id:
    u1, u2 = st.columns([4, 1], vertical_alignment="center")
    u1.success(t("console.resolved_ok", id=undo_id))
    if u2.button(t("console.undo"), key="undo_resolve", use_container_width=True):
        try:
            staff_session().post(f"{API_URL}/handoff/{undo_id}/reopen", timeout=10).raise_for_status()
            st.session_state.pop("just_resolved", None)
            st.rerun()
        except Exception as e:
            st.error(t("common.op_failed", e=e))
    st.session_state.pop("just_resolved", None)     # offered once, on the run right after resolving

all_tickets, err = fetch("/handoff/tickets", {"status": "open", "limit": 50})

if err:
    st.error(err)
elif not all_tickets:
    st.success(t("console.empty"))
    watch_queue(0)
else:
    # Stacked layout: the conversation gets the full page width on top, the
    # queue sits underneath. The queue still has to be drawn FIRST (the
    # selected row decides which thread to show), so both areas are reserved
    # up front and filled out of order.
    thread_area = st.container()
    queue_area = st.container()

    lang = current_lang()
    with queue_area:
        st.markdown(f'<div class="card-title">{t("console.queue", n=len(all_tickets))}</div>', unsafe_allow_html=True)
        watch_queue(len(all_tickets))

        # Filter by reason, sort by urgency / waiting time.
        reason_of = {tk["id"]: ticket_reason(tk.get("description"), lang, strip_prefix=True).split("｜")[0].split(" | ")[0]
                     for tk in all_tickets}
        f1, f2 = st.columns(2)
        reasons = sorted(set(reason_of.values()))
        picked_reason = f1.selectbox(t("console.filter"), [t("console.filter_all")] + reasons)
        sort_choice = f2.selectbox(t("console.sort"), [t("console.sort_urgent"), t("console.sort_oldest")])
        tickets = [tk for tk in all_tickets
                   if picked_reason == t("console.filter_all") or reason_of[tk["id"]] == picked_reason]
        tickets.sort(key=lambda tk: sort_key(tk, oldest_first=(sort_choice == t("console.sort_oldest"))))

        if not tickets:
            st.info(t("console.filter_none"))
            thread_area.info(t("console.filter_none"))
            st.stop()
        ids = [tk["id"] for tk in tickets]

        # Which case is open: a fresh click wins; otherwise a case sent here
        # from the Dashboard ("Handle in Agent Console"); otherwise whatever was
        # open last time; otherwise the first. st.dataframe can't preselect a
        # row, so a "▶" in front of the case number marks the open one.
        cells = st.session_state.get("queue", {}).get("selection", {}).get("cells", [])
        hit = cells[0] if cells and cells[0][0] < len(ids) else None
        clicked = (ids[hit[0]], hit[1]) if hit else None      # (case id, column): every new click counts
        focus_id = st.session_state.pop("focus_ticket", None)
        scroll_to_thread = False
        if clicked and clicked != st.session_state.get("_last_clicked_ticket"):
            st.session_state["_last_clicked_ticket"] = clicked
            selected_ticket_id = clicked[0]
            scroll_to_thread = True
        elif focus_id in ids:
            selected_ticket_id = focus_id
            scroll_to_thread = True
        elif st.session_state.get("selected_ticket") in ids:
            selected_ticket_id = st.session_state["selected_ticket"]
        else:
            selected_ticket_id = ids[0]
        st.session_state["selected_ticket"] = selected_ticket_id

        rows = [
            {
                t("console.col_ticket"): ("▶ " if tk["id"] == selected_ticket_id else "")
                                         + ("🚨 " if tk.get("priority") == "high" else "") + tk["id"],
                t("console.col_reason"): ticket_reason(tk.get("description"), lang, strip_prefix=True),
                t("console.col_waiting"): waiting(tk["created_at"], lang=lang),
                t("console.col_created"): tk["created_at"][:16].replace("T", " "),
            }
            for tk in tickets
        ]
        st.dataframe(
            rows, key="queue", on_select="rerun", selection_mode="single-cell",
            hide_index=True, width="stretch", height=320,
            column_config={
                t("console.col_ticket"): st.column_config.TextColumn(width="medium"),
                t("console.col_reason"): st.column_config.TextColumn(width="large"),
                t("console.col_waiting"): st.column_config.TextColumn(width="small"),
                t("console.col_created"): st.column_config.TextColumn(width="small"),
            },
        )
        st.caption(t("console.hint"))

    # The conversation is above the queue, so a click down here changes
    # something that is scrolled out of view — bring it back into view.
    if scroll_to_thread:
        components.html(
            "<script>"
            "const d = window.parent.document;"
            "const m = d.querySelector('[data-testid=\"stMain\"]') || d.querySelector('section.main') "
            "  || d.querySelector('[data-testid=\"stAppViewContainer\"]');"
            "if (m) m.scrollTo({top: 0, behavior: 'smooth'});"
            "</script>",
            height=0,
        )

    with thread_area:
        with st.container(border=True):
            st.markdown(f'<div class="card-title">{t("console.thread", id=selected_ticket_id)}</div>', unsafe_allow_html=True)
            render_thread(selected_ticket_id)

            # Kept OUTSIDE the auto-refreshing fragment on purpose, so a
            # half-typed reply survives the timer. Inside a container it
            # renders inline, right under the conversation it answers.
            # Every ticket listed is status="open" by the query above.
            reply = st.chat_input(t("console.reply_input"))
            b1, b2 = st.columns([1, 3], vertical_alignment="center")
            if b1.button(t("console.resolve"), type="primary", use_container_width=True):
                confirm_resolve(selected_ticket_id)
            b2.page_link("pages/4_知識優化.py", label=t("console.improve"))

    if reply:
        try:
            staff_session().post(
                f"{API_URL}/handoff/{selected_ticket_id}/messages",
                json={"role": "agent", "content": reply},
                timeout=10,
            )
        except Exception as e:
            st.error(t("console.send_failed", e=e))
        st.rerun()
