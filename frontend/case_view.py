"""
Case dialog — shared by the Dashboard's "recent unresolved queries" and "recent tickets".

Click a row, get the whole case in a dialog: who/what/why, the full conversation
(customer, Mingis before the transfer, the agent), what else was logged against the
same chat session (unresolved reasons, CSAT), and — if the case is still open — a reply
box, a confirmed "resolve", and a jump to the agent console with that case selected.
A resolved case can be reopened here (resolving used to be a one-way click).

Two ways in, one record shape (backend main.py `_case_record`):
  by ticket   → /tickets/{id}/record        (a row of recent tickets)
  by session  → /cases/by-session/{sid}     (a row of unresolved queries; the
                session may never have been handed to a human, in which case
                there is a conversation to read but no ticket to answer)
"""

import os

import streamlit as st

from i18n import current_lang, t, ticket_reason, waiting
from staff_auth import staff_session
from theme import MASCOT_HEAD_PATH

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend

RATING_FACE = {1: "😢", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}


def status_label(status: str) -> str:
    return t(f"status.{status}") if status in ("open", "resolved", "closed", "in_progress") else status


def ticket_chips(ticket: dict) -> str:
    """One row of chips: status, urgency, customer, how long it has been open."""
    state = "open" if ticket["status"] == "open" else "done"
    chips = [f'<span class="tchip {state}">{status_label(ticket["status"])}</span>']
    if ticket.get("priority") == "high":
        chips.append(f'<span class="tchip urgent">{t("priority.high")}</span>')
    chips.append(f'<span class="tchip">👤 {t("case.chip_customer", x=ticket.get("user_id") or t("common.guest"))}</span>')
    if ticket["status"] == "open":
        chips.append(f'<span class="tchip">⏱ {t("case.chip_waiting", x=waiting(ticket["created_at"]))}</span>')
    return '<div class="tchips">' + "".join(chips) + "</div>"


def _get(endpoint: str):
    try:
        r = staff_session().get(f"{API_URL}{endpoint}", timeout=10)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, t("case.load_failed", e=e)


def _post(endpoint: str, json=None) -> str | None:
    try:
        staff_session().post(f"{API_URL}{endpoint}", json=json, timeout=10).raise_for_status()
        return None
    except Exception as e:
        return t("common.op_failed", e=e)


def _conversation(messages: list[dict]) -> None:
    for m in messages:
        role = m["role"]
        if role == "agent":
            with st.chat_message("assistant", avatar="🧑‍💼"):
                st.caption(t("case.agent"))
                st.markdown(m["content"])
        elif role == "user":
            with st.chat_message("user"):
                st.markdown(m["content"])
        else:
            with st.chat_message("assistant", avatar=MASCOT_HEAD_PATH):
                st.caption(t("case.mingis_before"))
                st.markdown(m["content"])


def _related(record: dict, reason_label: dict) -> None:
    unresolved, ratings = record.get("unresolved") or [], record.get("ratings") or []
    if not unresolved and not ratings:
        st.caption(t("case.related_none"))
        return
    if unresolved:
        st.markdown(t("case.unresolved_log"))
        st.dataframe([
            {
                t("common.time"): u["created_at"][:19].replace("T", " "),
                t("case.col_question"): u["user_query"],
                t("case.col_reason"): reason_label.get(u["trigger_reason"], u["trigger_reason"]),
                t("case.col_score"): round(u["similarity_score"], 3) if u.get("similarity_score") is not None else "—",
            }
            for u in unresolved
        ], hide_index=True, use_container_width=True)
    if ratings:
        st.markdown(t("case.ratings"))
        st.dataframe([
            {
                t("common.time"): r["created_at"][:19].replace("T", " "),
                t("case.col_rating"): f"{RATING_FACE.get(r['score'], '')} {r['score']}",
                t("case.col_comment"): r.get("comment") or t("dash.no_comment"),
            }
            for r in ratings
        ], hide_index=True, use_container_width=True)


def _actions(ticket: dict) -> None:
    """Reply / resolve (confirmed) / jump to the console — only while the case is open."""
    tid = ticket["id"]
    with st.form(f"case_reply_{tid}", clear_on_submit=True):
        reply = st.text_area(t("case.reply_label"), placeholder=t("case.reply_placeholder"), height=90)
        sent = st.form_submit_button(t("case.send"), type="primary")
    if sent:
        if not reply.strip():
            st.warning(t("case.reply_empty"))
        elif err := _post(f"/handoff/{tid}/messages", {"role": "agent", "content": reply.strip()}):
            st.error(err)
        else:
            st.rerun(scope="fragment")   # reload this dialog, so the reply shows in the thread

    confirm_key = f"case_confirm_resolve_{tid}"
    if st.session_state.get(confirm_key):
        st.warning(t("case.resolve_confirm"))
        y, n = st.columns(2)
        if y.button(t("case.resolve_yes"), key=f"case_yes_{tid}", type="primary", use_container_width=True):
            st.session_state[confirm_key] = False
            if err := _post(f"/handoff/{tid}/resolve"):
                st.error(err)
            else:
                st.rerun(scope="fragment")
        if n.button(t("case.cancel"), key=f"case_no_{tid}", use_container_width=True):
            st.session_state[confirm_key] = False
            st.rerun(scope="fragment")
    else:
        c1, c2 = st.columns(2)
        if c1.button(t("case.resolve"), key=f"case_resolve_{tid}", use_container_width=True):
            st.session_state[confirm_key] = True
            st.rerun(scope="fragment")
        if c2.button(t("case.goto_console"), key=f"case_goto_{tid}", use_container_width=True):
            st.session_state["focus_ticket"] = tid
            st.switch_page("pages/2_客服人員介面.py")


def show_case(*, ticket_id: str | None = None, session_id: str | None = None, reason_label: dict | None = None):
    """Open with exactly one of ticket_id / session_id."""
    reason_label = reason_label or {}

    # Defined per call: the dialog title is fixed when the decorator runs, and it has to
    # follow the language chosen right now.
    @st.dialog(t("case.title"), width="large")
    def _dialog():
        if ticket_id:
            record, err = _get(f"/tickets/{ticket_id}/record")
        elif session_id:
            record, err = _get(f"/cases/by-session/{session_id}")
        else:
            st.info(t("case.no_session"))
            return
        if err:
            st.error(err)
            return

        ticket = record["ticket"]
        if ticket:
            st.markdown(f"#### {ticket['id']}")
            st.markdown(ticket_chips(ticket), unsafe_allow_html=True)
            st.caption(t(
                "case.meta", created=ticket["created_at"][:19].replace("T", " "),
                reason=ticket_reason(ticket.get("description"), current_lang(), strip_prefix=True) or "—",
            ))
        else:
            st.markdown(f"#### {t('case.no_ticket_title')}")
            st.caption(t("case.no_ticket_note"))

        st.markdown(t("case.conversation"))
        messages = record["messages"] or record["chat_messages"]
        if messages:
            with st.container(height=360, border=True):
                _conversation(messages)
        else:
            st.caption(t("case.no_conversation"))

        with st.expander(t("case.related"), expanded=not ticket):
            _related(record, reason_label)

        if ticket:
            st.divider()
            if ticket["status"] == "open":
                _actions(ticket)
            else:
                st.caption(t("case.closed_note"))
                if st.button(t("case.reopen"), key=f"case_reopen_{ticket['id']}", use_container_width=True):
                    if err := _post(f"/handoff/{ticket['id']}/reopen"):
                        st.error(err)
                    else:
                        st.rerun(scope="fragment")
            st.page_link("pages/4_知識優化.py", label=t("case.improve"))

    _dialog()


def clicked_row(event, n_rows: int) -> tuple[int, str] | None:
    """(row index, column) of the cell the user clicked in a dataframe drawn
    with selection_mode="single-cell", else None.

    Cell mode on purpose: "single-row" only selects via a small checkbox in
    the far-left gutter, and clicking the row's text — what anyone does —
    selects nothing, which reads as "clicking does nothing"."""
    cells = event.selection.cells
    if cells and cells[0][0] < n_rows:
        return cells[0][0], cells[0][1]
    return None


def open_on_click(table_key: str, click_id, opener) -> None:
    """Call `opener()` once per new click. `click_id` identifies the click
    (e.g. (row id, column)) or is None when nothing is selected.

    A selected cell stays selected across reruns, so without this the dialog
    would reopen on every unrelated interaction on the page."""
    seen = f"_case_dialog_seen_{table_key}"
    if click_id is None:
        st.session_state.pop(seen, None)
    elif st.session_state.get(seen) != click_id:
        st.session_state[seen] = click_id
        opener()
