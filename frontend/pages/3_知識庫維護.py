"""
AI Banking Customer Assistant — Knowledge Base (Streamlit Page)
Add / edit / archive supplementary knowledge (kb_entries), rebuild the FAISS index and
hot-swap it live (no server restart), and a retrieval test tool to confirm a new entry
is now found. See backend main.py's /kb/* endpoints and rag/build_index.py's reindex_all().

2026-11: a status bar says how many changes the live index does not contain yet (the
easiest thing to forget was "rebuild the index"); the entry list is a searchable table
that opens an edit dialog; archiving moved out of the edit row into its own,
quieter section; the page speaks Chinese or English (see i18n.py).
"""

import os

import requests
import streamlit as st

from case_view import clicked_row, open_on_click   # the same "click a row, open a dialog" helpers
from i18n import render_nav, t
from staff_auth import staff_session
from theme import inject_theme

st.set_page_config(page_title=f"{t('kb.page_title')} — {t('common.suffix')}", page_icon="📚", layout="wide")

inject_theme("staff")
render_nav()

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend
HIGH_CONFIDENCE_THRESHOLD = 0.60  # mirrors nodes.py — above this the FAQ Node skips the verifier

session = staff_session()


def lang_name(code: str) -> str:
    return t("common.zh") if code == "zh" else t("common.en")


def lang_option(code: str) -> str:
    # always in the language's own name: a flag is a country, not a language
    return "中文" if code == "zh" else "English"


st.title(t("kb.title"))
st.caption(t("kb.purpose"))


def api_get(endpoint, params=None):
    try:
        r = session.get(f"{API_URL}{endpoint}", params=params, timeout=15)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, t("common.err_connect")
    except Exception as e:
        return None, t("common.err", e=e)


# A change made in a dialog ends in st.rerun(), which would swallow a message shown
# right then — so the message is parked here and shown on the next run.
flash = st.session_state.pop("kb_flash", None)
if flash:
    st.toast(flash, icon="✅")

# ── Index status: how many changes the live index doesn't have yet ───────────
status, status_err = api_get("/kb/status")
pending = (status or {}).get("pending_changes", 0)

bar_msg, bar_btn = st.columns([4, 1], vertical_alignment="center")
if status_err:
    bar_msg.error(status_err)
elif pending:
    bar_msg.warning(t("kb.pending", n=pending))
else:
    stamp = (status.get("indexed_at") or "—")[:16].replace("T", " ")
    bar_msg.success(t("kb.fresh", t=stamp))
if bar_btn.button(t("kb.apply") if pending else t("kb.rebuild"), type="primary" if pending else "secondary",
                  use_container_width=True):
    with st.spinner(t("kb.spinner_reindex")):
        try:
            resp = session.post(f"{API_URL}/kb/reindex", timeout=120)
            resp.raise_for_status()
            counts = resp.json().get("chunk_counts", {})
            st.session_state["kb_flash"] = t("kb.reindexed", zh=counts.get("zh", 0), en=counts.get("en", 0))
            st.rerun()
        except Exception as e:
            st.error(t("kb.reindex_failed", e=e))

st.divider()

# ── Add new knowledge ─────────────────────────────────────────────────────────
st.subheader(t("kb.add_title"))
st.caption(t("kb.add_note"))

with st.form("add_kb_entry", clear_on_submit=True):
    c1, c2 = st.columns([1, 3])
    language = c1.selectbox(t("kb.f_language"), ["zh", "en"], format_func=lang_option)
    title = c2.text_input(t("kb.f_title"), placeholder=t("kb.f_title_ph"))
    content = st.text_area(t("kb.f_content"), height=140, placeholder=t("kb.f_content_ph"))
    tags = st.text_input(t("kb.f_tags"), placeholder=t("kb.f_tags_ph"))
    submitted = st.form_submit_button(t("kb.add"), type="primary")

    if submitted:
        if not title.strip() or not content.strip():
            st.warning(t("kb.need_both"))
        else:
            try:
                resp = session.post(
                    f"{API_URL}/kb/entries",
                    json={"language": language, "title": title, "content": content, "tags": tags},
                    timeout=15,
                )
                resp.raise_for_status()
                st.session_state["kb_last_added"] = {"title": title, "language": language}
                st.session_state["kb_flash"] = t("kb.added", title=title)
                st.rerun()
            except Exception as e:
                st.error(t("kb.add_failed", e=e))


def use_for_test(title: str, language: str) -> None:
    """on_click callback: fill the test tool below (callbacks run before the widgets exist)."""
    st.session_state["test_query"] = title
    st.session_state["test_lang"] = language
    st.session_state["run_test"] = True


last_added = st.session_state.get("kb_last_added")
if last_added:
    if pending:
        st.caption(t("kb.test_added_wait"))
    else:
        st.button(t("kb.test_added", title=last_added["title"]), on_click=use_for_test,
                  args=(last_added["title"], last_added["language"]))

st.divider()

# ── Existing entries: searchable table → edit dialog ─────────────────────────
st.subheader(t("kb.list_title"))


def edit_dialog(entry: dict, archived_view: bool):
    @st.dialog(t("kb.entry_title"), width="large")
    def _dialog():
        eid = entry["id"]
        st.caption(t("kb.entry_meta", id=eid, created=entry["created_at"][:19].replace("T", " ")))
        if entry.get("source") == "pipeline":
            st.caption(t("kb.entry_from_pipeline"))
            st.page_link("pages/4_知識優化.py", label=t("kb.to_gap"))
        if archived_view:
            st.markdown(f"**{entry['title']}**")
            st.write(entry["content"])
            if entry.get("tags"):
                st.caption(f"🏷️ {entry['tags']}")
            if st.button(t("kb.restore"), key=f"restore_{eid}", type="primary"):
                try:
                    session.post(f"{API_URL}/kb/entries/{eid}/restore", timeout=15).raise_for_status()
                    st.session_state["kb_flash"] = t("kb.restored", title=entry["title"])
                    st.rerun()
                except Exception as ex:
                    st.error(t("common.op_failed", e=ex))
            return

        with st.form(f"edit_{eid}"):
            new_title = st.text_input(t("kb.f_title"), value=entry["title"])
            new_content = st.text_area(t("kb.f_content"), value=entry["content"], height=160)
            new_tags = st.text_input(t("kb.f_tags"), value=entry.get("tags") or "")
            save = st.form_submit_button(t("kb.save"), type="primary")
        if save:
            try:
                session.put(
                    f"{API_URL}/kb/entries/{eid}",
                    json={"title": new_title, "content": new_content, "tags": new_tags}, timeout=15,
                ).raise_for_status()
                st.session_state["kb_flash"] = t("kb.saved", title=new_title)
                st.rerun()
            except Exception as ex:
                st.error(t("kb.save_failed", e=ex))

        # Archiving is rarer and less welcome than saving: its own quiet section, not a twin button.
        st.divider()
        st.caption(t("kb.archive_note"))
        if st.button(t("kb.archive"), key=f"archive_{eid}"):
            try:
                session.post(f"{API_URL}/kb/entries/{eid}/archive", timeout=15).raise_for_status()
                st.session_state["kb_flash"] = t("kb.archived", title=entry["title"])
                st.rerun()
            except Exception as ex:
                st.error(t("kb.archive_failed", e=ex))
    _dialog()


f1, f2, f3, f4 = st.columns([3, 1.2, 1.4, 1.4], vertical_alignment="bottom")
query = f1.text_input(t("kb.search"), key="kb_search")
lang_filter = f2.selectbox(t("kb.filter_lang"), ["all", "zh", "en"],
                           format_func=lambda x: t("kb.filter_all") if x == "all" else lang_option(x))
source_filter = f3.selectbox(t("kb.filter_source"), ["all", "manual", "pipeline"],
                             format_func=lambda x: {"all": t("kb.filter_all"), "manual": t("kb.source_manual"),
                                                    "pipeline": t("kb.source_pipeline")}[x])
show_archived = f4.toggle(t("kb.show_archived"), value=False)

entries, err = api_get("/kb/entries", {"status": "archived" if show_archived else "active", "limit": 200})
if err:
    st.error(err)
elif not entries:
    st.info(t("kb.list_empty_archived") if show_archived else t("kb.list_empty"))
else:
    needle = query.strip().lower()
    shown = [
        e for e in entries
        if (lang_filter == "all" or e["language"] == lang_filter)
        and (source_filter == "all" or (e.get("source") or "manual") == source_filter)
        and (not needle or needle in e["title"].lower() or needle in e["content"].lower())
    ]
    if not shown:
        st.info(t("kb.list_no_match"))
    else:
        ev = st.dataframe(
            [
                {
                    "ID": e["id"],
                    t("kb.col_title"): ("🤖 " if e.get("source") == "pipeline" else "") + e["title"],
                    t("kb.col_language"): lang_option(e["language"]),
                    t("kb.col_source"): t("kb.source_pipeline") if e.get("source") == "pipeline" else t("kb.source_manual"),
                    t("kb.col_updated"): (e.get("updated_at") or e["created_at"])[:16].replace("T", " "),
                }
                for e in shown
            ],
            key="tbl_kb", on_select="rerun", selection_mode="single-cell", hide_index=True, width="stretch",
            height=min(420, 38 + 35 * len(shown)),
        )
        st.caption(t("kb.hint"))
        hit = clicked_row(ev, len(shown))
        picked = shown[hit[0]] if hit else None
        open_on_click("kb", (picked["id"], hit[1]) if picked else None, lambda: edit_dialog(picked, show_archived))

st.divider()

# ── Retrieval test tool ───────────────────────────────────────────────────────
st.subheader(t("kb.test_title"))
st.caption(t("kb.test_note", thr=f"{HIGH_CONFIDENCE_THRESHOLD:.2f}"))
with st.expander(t("kb.test_scope_title")):
    st.write(t("kb.test_scope_body"))

tc1, tc2 = st.columns([3, 1])
test_q = tc1.text_input(t("kb.test_q"), key="test_query", placeholder=t("kb.test_q_ph"))
test_lang = tc2.selectbox(t("kb.test_lang"), ["zh", "en"], format_func=lang_option, key="test_lang")

run = st.button(t("kb.test_run")) or st.session_state.pop("run_test", False)
if run:
    if not test_q.strip():
        st.warning(t("kb.test_empty_q"))
    else:
        result, rerr = api_get("/kb/retrieve", {"q": test_q, "language": test_lang, "top_k": 3})
        if rerr:
            st.error(rerr)
        elif not result.get("ready"):
            st.warning(t("kb.test_not_ready"))
        elif not result.get("chunks"):
            st.info(t("kb.test_nothing"))
        else:
            top = result["chunks"][0]["score"]
            if top < HIGH_CONFIDENCE_THRESHOLD:
                st.warning(t("kb.test_low", top=f"{top:.3f}", thr=f"{HIGH_CONFIDENCE_THRESHOLD:.2f}"))
            for i, ch in enumerate(result["chunks"], 1):
                score = ch["score"]
                ok = score >= HIGH_CONFIDENCE_THRESHOLD
                st.markdown(t("kb.test_result", mark="🟢" if ok else "🟡", i=i, score=f"{score:.3f}",
                              verdict=t("kb.verdict_ok") if ok else t("kb.verdict_low"), source=ch["source"]))
                st.caption(ch["text"][:300] + ("…" if len(ch["text"]) > 300 else ""))
