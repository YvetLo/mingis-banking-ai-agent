"""
AI Banking Customer Assistant — Knowledge Improvement Pipeline (Streamlit Page)
Cluster the bot's failure signals into topics, review the AI-generated FAQ drafts
(approve / edit / skip), and see the before→after retrieval score once a draft is
approved into the knowledge base. See backend main.py's /gap/* endpoints and
agent/gap_pipeline.py.

2026-11: the analysis result is shown as a funnel (signals → topics → drafts →
approved) with the topics that were left out and why; the "before / now" confidence
is drawn against the 0.60 line instead of being three bare numbers; the page speaks
Chinese or English (see i18n.py).
"""

import os

import requests
import streamlit as st

from i18n import render_nav, signal_summary, t
from staff_auth import staff_session
from theme import inject_theme

st.set_page_config(page_title=f"{t('gap.page_title')} — {t('common.suffix')}", page_icon="🧩", layout="wide")

inject_theme("staff")
render_nav()

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend
THRESHOLD = 0.60


def lang_option(code: str) -> str:
    return "中文" if code == "zh" else "English"     # a language's own name, not a flag


session = staff_session()

st.title(t("gap.title"))
st.caption(f"{t('gap.subtitle')}　|　{t('gap.purpose')}")


def api_get(endpoint, params=None):
    try:
        r = session.get(f"{API_URL}{endpoint}", params=params, timeout=20)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, t("common.err_connect")
    except Exception as e:
        return None, t("common.err", e=e)


def score_badge(score):
    if score is None:
        return "—"
    mark = "🟢" if score >= THRESHOLD else "🟡"
    return f"{mark} {score:.3f}"


def score_verdict(score):
    """Plain-language reading of a retrieval score for non-technical staff."""
    if score is None:
        return ""
    return t("kb.verdict_ok") if score >= THRESHOLD else t("kb.verdict_low")


def confidence_bars(pre, live) -> str:
    """'Before' and 'now' confidence as two bars with the 0.60 line drawn through them:
    green = at or above the line (Mingis answers), amber = below it (hands off to an agent)."""
    def row(label, value):
        if value is None:
            return ""
        colour = "#2FA37C" if value >= THRESHOLD else "#F2A93B"
        return (
            f'<div class="ba-row"><span class="lab">{label}</span><div class="ba-track">'
            f'<i class="ba-fill" style="width:{max(0, min(value, 1)) * 100:.0f}%;background:{colour}"></i>'
            f'<i class="ba-thr" style="left:{THRESHOLD * 100:.0f}%"></i></div>'
            f'<span class="val">{value:.2f}</span></div>'
        )
    return (
        f'<div class="ba">{row(t("gap.bar_before"), pre)}{row(t("gap.bar_now"), live)}'
        f'<div class="ba-note">▏{t("gap.bar_threshold", thr=f"{THRESHOLD:.2f}")}</div></div>'
    )


approved, aerr = api_get("/gap/drafts", {"status": "approved"})
pending, perr = api_get("/gap/drafts", {"status": "pending"})

st.divider()

# ── Analyze + funnel ──────────────────────────────────────────────────────────
c1, c2 = st.columns([1, 2.4])
with c1:
    if st.button(t("gap.analyze"), type="primary", use_container_width=True):
        with st.spinner(t("gap.spinner")):
            try:
                resp = session.post(f"{API_URL}/gap/analyze", timeout=180)
                resp.raise_for_status()
                st.session_state["gap_analyze_result"] = resp.json()
                st.rerun()
            except Exception as e:
                st.error(t("gap.analyze_failed", e=e))
with c2:
    st.caption(t("gap.scope_note"))

res = st.session_state.get("gap_analyze_result")
if res:
    def step(n, label, tone):
        return f'<div class="fstep" style="--k:{tone}"><div class="n">{n}</div><div class="l">{label}</div></div>'
    st.markdown(
        '<div class="funnel">'
        + step(res.get("gap_signals", 0), t("gap.funnel_signals"), "var(--conc)")
        + '<div class="farrow">→</div>' + step(res.get("topics_total", 0), t("gap.funnel_topics"), "var(--violet)")
        + '<div class="farrow">→</div>' + step(res.get("new_drafts", 0), t("gap.funnel_drafts"), "var(--amber)")
        + '<div class="farrow">→</div>' + step(len(approved or []), t("gap.funnel_approved"), "var(--green)")
        + "</div>",
        unsafe_allow_html=True,
    )
    excluded = res.get("excluded_topics") or []
    if excluded:
        with st.expander(t("gap.excluded", n=len(excluded))):
            st.caption(t("gap.excluded_note"))
            for label in excluded:
                st.markdown(f"- {label}")
else:
    st.caption(t("gap.funnel_hint"))

st.divider()

# ── Pending drafts (review) ───────────────────────────────────────────────────
st.subheader(t("gap.pending_title"))

if perr:
    st.error(perr)
elif not pending:
    st.info(t("gap.pending_empty"))
else:
    for d in pending:
        with st.container(border=True):
            st.markdown(t("gap.draft_head", topic=d["topic"], lang=lang_option(d["language"])))
            st.caption(t(
                "gap.draft_meta", n=d["signal_count"], summary=signal_summary(d.get("signal_summary")),
                badge=score_badge(d.get("pre_score")), verdict=score_verdict(d.get("pre_score")), thr=f"{THRESHOLD:.2f}",
            ))
            with st.form(f"draft_{d['id']}"):
                q = st.text_input(t("gap.f_question"), value=d["question"], key=f"q_{d['id']}")
                a = st.text_area(t("gap.f_answer"), value=d["answer"], height=150, key=f"a_{d['id']}")
                tg = st.text_input(t("gap.f_tags"), value=d.get("tags") or "", key=f"tg_{d['id']}")
                b1, b2, b3 = st.columns(3)
                do_save = b1.form_submit_button(t("gap.save"))
                do_approve = b2.form_submit_button(t("gap.approve"), type="primary")
                do_skip = b3.form_submit_button(t("gap.skip"))

                if do_save or do_approve:
                    # approve always applies the current (possibly edited) text first
                    try:
                        session.put(
                            f"{API_URL}/gap/drafts/{d['id']}",
                            json={"question": q, "answer": a, "tags": tg}, timeout=15,
                        ).raise_for_status()
                    except Exception as e:
                        st.error(t("gap.save_failed", e=e))
                    else:
                        if do_save:
                            st.success(t("gap.saved"))
                            st.rerun()
                if do_approve:
                    with st.spinner(t("gap.publishing")):
                        try:
                            r = session.post(f"{API_URL}/gap/drafts/{d['id']}/approve", timeout=120)
                            if r.status_code == 409:     # a double click: the first one already published it
                                st.info(t("gap.already"))
                                st.rerun()
                            r.raise_for_status()
                            res_ = r.json()
                            st.toast(
                                t("gap.published", pre=f"{res_['pre_score']:.3f}", post=f"{res_['post_score']:.3f}"),
                                icon="🎉",
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(t("gap.publish_failed", e=e))
                if do_skip:
                    try:
                        session.post(f"{API_URL}/gap/drafts/{d['id']}/skip", timeout=15).raise_for_status()
                        st.rerun()
                    except Exception as e:
                        st.error(t("common.op_failed", e=e))

st.divider()

# ── Approved drafts + effectiveness ──────────────────────────────────────────
st.subheader(t("gap.approved_title"))

if aerr:
    st.error(aerr)
elif not approved:
    st.caption(t("gap.approved_empty"))
else:
    for d in approved:
        eff, _ = api_get(f"/gap/drafts/{d['id']}/effectiveness")
        with st.container(border=True):
            st.markdown(t("gap.approved_head", topic=d["topic"], q=d["question"]))
            if eff:
                pre = eff.get("pre_score")
                live = eff.get("live_score")
                jumped = (pre is not None and live is not None and live >= THRESHOLD > pre)
                st.markdown(confidence_bars(pre, live), unsafe_allow_html=True)
                m1, m2, m3 = st.columns(3)
                m1.metric(t("gap.m_before"), score_badge(pre))
                m1.caption(score_verdict(pre))
                m2.metric(t("gap.m_now"), score_badge(live),
                          delta=(round(live - pre, 3) if pre is not None and live is not None else None))
                m2.caption(score_verdict(live))
                rec = eff.get("recurrence_since_live")
                m3.metric(t("gap.m_repeat"), "—" if rec is None else t("gap.m_repeat_val", n=rec),
                          help=t("gap.m_repeat_help"))
                if jumped:
                    st.success(t("gap.jumped"))
            st.page_link("pages/3_知識庫維護.py", label=t("gap.to_kb"))

# ── Skipped (transparency) ────────────────────────────────────────────────────
skipped, _ = api_get("/gap/drafts", {"status": "skipped"})
if skipped:
    with st.expander(t("gap.skipped", n=len(skipped))):
        for d in skipped:
            c1, c2 = st.columns([5, 1])
            c1.caption(f"🧩 {d['topic']} — {d['question']}")
            if c2.button(t("gap.restore"), key=f"restore_{d['id']}", use_container_width=True):
                try:
                    session.post(f"{API_URL}/gap/drafts/{d['id']}/restore", timeout=15).raise_for_status()
                    st.rerun()
                except Exception as e:
                    st.error(t("common.op_failed", e=e))
