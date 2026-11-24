"""
AI Banking Customer Assistant — Dashboard (Streamlit Page)
Sprint 4: Unresolved queries stats + ticket overview
Ink & Wash redesign: hero card with the mascot + KPI strip, reason/CSAT
cards on the right, AI cost table below (design-prototype/ink-wash-redesign.html §03).
"""

import os
import html

import altair as alt
import pandas as pd
import requests
import streamlit as st

from case_view import clicked_row, open_on_click, show_case
from i18n import current_lang, render_nav, t, ticket_reason
from staff_auth import staff_session
from theme import MASCOT_DESK, PALETTE, asset_data_uri, inject_theme

st.set_page_config(
    page_title=f"{t('dash.page_title')} — {t('common.suffix')}",
    page_icon="📊",
    layout="wide",
)

inject_theme("staff")
render_nav()

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend

REASON_KEYS = [
    "negative_feedback", "handoff_intent", "fallback_threshold", "verifier_unresolved", "handoff_urgent_fraud",
    "handoff_dispute", "handoff_approval_required", "handoff_sensitive_data", "handoff_emotional_distress",
    "handoff_cross_account",
]


def reason_labels() -> dict:
    return {k: t(f"reason.{k}") for k in REASON_KEYS}


def reason_short(k: str) -> str:
    # a vertical chart has room for 4-5 characters per bar before labels collide
    return t(f"reasonshort.{k}") if k in REASON_KEYS else k


RATING_FACE = {1: "😢", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}
# Meaning-coded: green = happy ... coral = unhappy (was five shades of blue)
RATING_COLOR = {5: "#2FA37C", 4: "#8CCB7A", 3: "#F2C14E", 2: "#F08A4B", 1: "#E8604C"}
# Bar colour says WHAT KIND of unresolved: knowledge gap = blue, wants a person = amber,
# money dispute = coral, security/fraud = crimson, sensitive data = violet, needs approval = teal.
REASON_COLOR = {
    "verifier_unresolved": "#4185BC", "handoff_intent": "#F2A93B", "handoff_dispute": "#E8604C",
    "handoff_urgent_fraud": "#C23B4E", "handoff_sensitive_data": "#7C6BD6", "handoff_approval_required": "#2BA39B",
    "negative_feedback": "#D1708F", "fallback_threshold": "#6B7F99", "handoff_emotional_distress": "#E57D3A",
    "handoff_cross_account": "#5B6FD6",
}
# Section accents: a small dot before each card title, same colours as the KPI it relates to.
ACCENT = {"blue": "#286AA5", "amber": "#D98A0B", "green": "#1F8F69", "violet": "#6B58C9", "coral": "#E8604C"}
# Call sites traced in backend/src/tracing.py → display name + one-glyph icon
NODE_LABEL = {   # call site -> (translation key, one-glyph icon)
    "classify_intent": ("node.classify_intent", "I"),
    "qa_answer_stream": ("node.qa_answer_stream", "A"),
    "qa_answer_blocking": ("node.qa_answer_blocking", "A"),
    "verifier": ("node.verifier", "V"),
    "account_tool_loop": ("node.account_tool_loop", "$"),
    "gap_cluster": ("node.gap_cluster", "G"),
    "gap_draft": ("node.gap_draft", "D"),
}
ICON_COLORS = [PALETTE["conc"], PALETTE["full"], PALETTE["dark"], PALETTE["carbon"]]


def status_label(status: str) -> str:
    return t(f"status.{status}") if status in ("open", "resolved", "closed", "in_progress") else status


session = staff_session()


def fetch(endpoint: str, params: dict = None):
    try:
        r = session.get(f"{API_URL}{endpoint}", params=params, timeout=10)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.ConnectionError:
        return None, t("common.err_connect")
    except Exception as e:
        return None, t("common.err", e=e)


def styled(chart: alt.Chart) -> alt.Chart:
    """Shared chart chrome: no frame, palette text, the UI font."""
    return (
        chart.configure_view(strokeWidth=0)
        .configure_axis(labelColor=PALETTE["muted"], titleColor=PALETTE["muted"], domain=False,
                        ticks=False, grid=False, labelFont="Noto Sans TC", labelFontSize=12)
        .configure(background="transparent")
    )


# Tiny inline icons for the KPI chips (Feather-style strokes)
ICON_TICKET = '<svg viewBox="0 0 24 24"><path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v3a2 2 0 0 0 0 4v3a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-3a2 2 0 0 0 0-4z"/><path d="M13 5v14" stroke-dasharray="2 3"/></svg>'
ICON_CLOCK = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
ICON_CHECK = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/></svg>'
ICON_HELP = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.6 9.4a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1.1.9-1.1 1.7"/><path d="M12 16.8h.01"/></svg>'
KPI_VAR = {"blue": "var(--conc)", "amber": "var(--amber)", "green": "var(--green)", "violet": "var(--violet)"}


def kpi(label: str, value, sub: str, tone: str, icon: str) -> str:
    """One tinted KPI card. Lines start at column 0 (markdown would otherwise read indent as code)."""
    return (
        f'<div class="kpi" style="--k:{KPI_VAR[tone]}"><div class="kh"><span class="chip">{icon}</span>'
        f'<span class="k">{label}</span></div><div class="v">{value}</div><div class="s">{sub}</div></div>'
    )


def card_title(title: str, meta: str = "", accent: str = "") -> None:
    right = f'<span class="card-meta">{meta}</span>' if meta else ""
    dot = f'<i class="cd" style="--c:{ACCENT[accent]}"></i>' if accent else ""
    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:baseline">'
        f'<div class="card-title">{dot}{title}</div>{right}</div>',
        unsafe_allow_html=True,
    )


def render_csat(stats: dict) -> None:
    """Compact on purpose: the average, one stacked bar and one legend line.
    (It used to be a donut + legend in a tall card; this is a glance, not a report.)"""
    with st.container(border=True):
        card_title(t("dash.csat"), accent="green")
        if not stats.get("rating_count"):
            st.caption(t("dash.csat_empty"))
            return
        avg = stats.get("avg_rating")
        dist = stats.get("rating_distribution", {})
        n = stats["rating_count"]
        low = sum(dist.get(str(s), 0) for s in (1, 2))
        scores = [s for s in (5, 4, 3, 2, 1) if dist.get(str(s), 0)]
        bar = "".join(
            f'<i style="flex:{dist[str(s)]};background:{RATING_COLOR[s]}" title="{t("dash.csat_point", s=s, n=dist[str(s)])}"></i>' for s in scores
        )
        legend = "".join(
            f'<span><b style="background:{RATING_COLOR[s]}"></b>{RATING_FACE[s]} {t("dash.csat_point", s=s, n=dist[str(s)])}</span>' for s in scores
        )
        # one line, no indentation: markdown would read indented HTML as a code block
        st.markdown(
            f'<div class="csat"><div class="big-num">{avg}<small> / 5</small></div>'
            f'<div class="csat-r"><div class="csat-bar">{bar}</div>'
            f'<div class="csat-leg">{legend}<span>{t("dash.csat_low", p=round(low / n * 100), n=n)}</span></div></div></div>',
            unsafe_allow_html=True,
        )


# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([3, 2], vertical_alignment="bottom")
h1.title(t("dash.title"))
h2.markdown(
    '<div class="card-meta" style="text-align:right;padding-bottom:1.2rem">'
    f'{t("dash.source")}</div>',
    unsafe_allow_html=True,
)

stats, err = fetch("/stats")

if err:
    st.error(err)
else:
    left, right = st.columns([1.65, 1], gap="medium")

    # ── Hero: open tickets headline + mascot + KPI strip ─────────────────────
    with left:
        open_n = stats["open_tickets"]
        total = stats["total_tickets"]
        unresolved = stats["total_unresolved"]
        done_n = stats.get("done_tickets", total - open_n)
        done_sub = t("dash.kpi_done_sub", p=round(done_n / total * 100)) if total else "—"
        conv = round(total / max(unresolved + total, 1) * 100) if unresolved + total else 0
        headline = t("dash.headline", n=open_n) if open_n else t("dash.headline_none")
        # Every line starts at column 0 — Streamlit's markdown parser treats a
        # 4-space indent as a code block, which renders the HTML as literal text.
        st.markdown(
            '<div class="dhero">'
            '<i class="dot" style="left:46%;top:24px;width:10px;height:10px"></i>'
            '<i class="dot" style="left:52%;top:210px;width:14px;height:14px;opacity:.8"></i>'
            '<i class="dot" style="left:30px;top:250px;width:8px;height:8px;background:var(--half)"></i>'
            f"<h2>{headline}</h2>"
            # Multipage URL = page filename minus its "2_" ordering prefix
            f'<a class="go" href="客服人員介面" target="_self">{t("dash.go")}</a>'
            f'<img class="bot desk" src="{asset_data_uri(MASCOT_DESK)}" alt="Mingis">'
            '<div class="kpis">'
            f'{kpi(t("dash.kpi_total"), total, t("dash.kpi_total_sub", p=conv), "blue", ICON_TICKET)}'
            f'{kpi(t("dash.kpi_open"), open_n, t("dash.kpi_open_sub"), "amber", ICON_CLOCK)}'
            f'{kpi(t("dash.kpi_done"), done_n, done_sub, "green", ICON_CHECK)}'
            f'{kpi(t("dash.kpi_unresolved"), unresolved, t("dash.kpi_unresolved_sub"), "violet", ICON_HELP)}'
            "</div></div>",
            unsafe_allow_html=True,
        )

    with right:
        # ── Unresolved reasons: top 5 as vertical bars ───────────────────────
        with st.container(border=True):
            by_reason = stats.get("unresolved_by_reason", {})
            ranked = sorted(by_reason.items(), key=lambda kv: -kv[1])
            card_title(t("dash.top5"), t("dash.top5_meta", n=sum(by_reason.values())), accent="amber")
            if ranked:
                top = ranked[:5]
                df = pd.DataFrame([
                    {"reason": reason_short(k), "full": reason_labels().get(k, k), "count": v,
                     "color": REASON_COLOR.get(k, PALETTE["full"])}
                    for i, (k, v) in enumerate(top)
                ])
                order = list(df["reason"])
                bars = alt.Chart(df).mark_bar(cornerRadiusTopLeft=10, cornerRadiusTopRight=10, size=52).encode(
                    x=alt.X("reason:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("count:Q", title=None, axis=None),
                    color=alt.Color("color:N", scale=None),
                    tooltip=[alt.Tooltip("full:N", title=t("dash.col_full_reason")), alt.Tooltip("count:Q", title=t("dash.col_count"))],
                )
                labels = bars.mark_text(dy=-8, fontWeight=700, color=PALETTE["ink"]).encode(text="count:Q")
                st.altair_chart(styled((bars + labels).properties(height=330)), use_container_width=True)
                rest = ranked[5:]
                if rest:
                    st.caption(t("dash.top5_other") + ", ".join(f"{reason_labels().get(k, k)} {v}" for k, v in rest))
            else:
                st.caption(t("dash.top5_empty"))


# ── Recent unresolved queries ────────────────────────────────────────────────
with st.container(border=True):
    card_title(t("dash.recent_unresolved"), accent="violet")
    unresolved_rows, err2 = fetch("/unresolved", {"limit": 20})
    if err2:
        st.error(err2)
    elif not unresolved_rows:
        st.success(t("dash.recent_unresolved_empty"))
    else:
        ev = st.dataframe([
            {
                t("common.time"): r["created_at"][:19].replace("T", " "),
                t("dash.col_question"): r["user_query"],
                t("dash.col_language"): t("common.zh") if r["language"] == "zh" else t("common.en"),
                t("dash.col_trigger"): reason_labels().get(r["trigger_reason"], r["trigger_reason"]),
                t("dash.col_intent"): r.get("intent", "—"),
            }
            for r in unresolved_rows
        ], key="tbl_unresolved", on_select="rerun", selection_mode="single-cell",
            use_container_width=True, hide_index=True)
        st.caption(t("dash.hint_unresolved"))
        hit = clicked_row(ev, len(unresolved_rows))
        row = unresolved_rows[hit[0]] if hit else None
        open_on_click(
            "unresolved", (row["id"], hit[1]) if row else None,
            lambda: show_case(session_id=row.get("session_id"), reason_label=reason_labels()),
        )

# ── Recent tickets ───────────────────────────────────────────────────────────
with st.container(border=True):
    card_title(t("dash.recent_tickets"), accent="blue")
    tickets, err3 = fetch("/tickets", {"limit": 20})
    if err3:
        st.error(err3)
    elif not tickets:
        st.caption(t("dash.recent_tickets_empty"))
    else:
        ev = st.dataframe([
            {
                t("dash.col_ticket"): tk["id"],
                t("dash.col_created"): tk["created_at"][:19].replace("T", " "),
                t("dash.col_type"): tk["type"],
                t("dash.col_desc"): ticket_reason(tk.get("description"), current_lang()),
                t("dash.col_priority"): t("priority.high") if tk.get("priority") == "high" else t("priority.normal"),
                t("dash.col_status"): status_label(tk["status"]),
                t("common.customer"): tk.get("user_id") or "—",
            }
            for tk in tickets
        ], key="tbl_tickets", on_select="rerun", selection_mode="single-cell",
            use_container_width=True, hide_index=True)
        st.caption(t("dash.hint_tickets"))
        hit = clicked_row(ev, len(tickets))
        trow = tickets[hit[0]] if hit else None
        open_on_click(
            "tickets", (trow["id"], hit[1]) if trow else None,
            lambda: show_case(ticket_id=trow["id"], reason_label=reason_labels()),
        )

# ── Row: satisfaction (left) + low-score feedback (right) ────────────────────
low_ratings, low_err = fetch("/ratings", {"max_score": 2, "limit": 20})
c_csat, c_low = st.columns([1, 1.65], gap="medium")
with c_csat:
    if stats:
        render_csat(stats)
with c_low:
    with st.container(border=True):
        card_title(t("dash.low"), t("dash.low_meta"), accent="coral")
        if low_err:
            st.error(low_err)
        elif not low_ratings:
            st.caption(t("dash.low_empty"))
        else:
            st.caption(t("dash.low_count", n=len(low_ratings)))
            with st.expander(t("dash.low_details")):
                st.dataframe([
                    {
                        t("common.time"): r["created_at"][:19].replace("T", " "),
                        t("dash.col_score"): f"{RATING_FACE.get(r['score'], '')} {r['score']}",
                        t("dash.col_comment"): r.get("comment") or t("dash.no_comment"),
                        t("common.customer"): r.get("user_id") or t("common.guest"),
                    }
                    for r in low_ratings
                ], use_container_width=True, hide_index=True)

# ── Knowledge base gap hint ──────────────────────────────────────────────────
with st.expander(t("dash.tip_title")):
    st.markdown(t("dash.tip_body"))

# ── AI cost & latency (the reference's "Earnings" table) ────────────────────
cost, cost_err = fetch("/cost/summary")
with st.expander(t("dash.dev_title"), expanded=False):
    st.caption(t("dash.dev_note"))
    if cost_err:
        st.error(cost_err)
    elif not cost or not cost["call_count"]:
        card_title(t("dash.dev_card"))
        st.caption(t("dash.dev_empty"))
    else:
        tokens = cost["total_input_tokens"] + cost["total_output_tokens"]
        card_title(
            t("dash.dev_card"),
            t("dash.dev_summary", cost=f'{cost["total_cost_usd"]:.4f}', n=cost["call_count"],
              ms=f'{cost["avg_latency_ms"]:,.0f}', tok=f"{tokens:,}"),
        )
        nodes = sorted(cost["by_node"], key=lambda n: -n["call_count"])
        slowest = max((n["avg_latency_ms"] for n in nodes), default=1) or 1
        rows = []
        for i, n in enumerate(nodes):
            key, glyph = NODE_LABEL.get(n["node"], (None, n["node"][:1].upper()))
            name = t(key) if key else n["node"]
            rows.append(
                "<tr>"
                f'<td><div class="who"><div class="ico" style="background:{ICON_COLORS[i % len(ICON_COLORS)]}">{glyph}</div>'
                f"<div>{html.escape(name)}<small>{html.escape(n['node'])}</small></div></div></td>"
                f"<td>{n['call_count']}</td>"
                f"<td>${n['cost_usd']:.4f}</td>"
                f'<td style="width:34%"><div class="meter"><span style="width:{n["avg_latency_ms"] / slowest * 100:.0f}%"></span></div></td>'
                f"<td><b>{n['avg_latency_ms']:,.0f}</b> ms</td>"
                "</tr>"
            )
        st.markdown(
            f'<table class="cost"><thead><tr><th>{t("dash.dev_th_endpoint")}</th><th>{t("dash.dev_th_calls")}</th>'
            f'<th>{t("dash.dev_th_cost")}</th><th>{t("dash.dev_th_latency")}</th><th></th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>",
            unsafe_allow_html=True,
        )
        recent_calls, recent_err = fetch("/cost/recent", {"limit": 20})
        if recent_err:
            st.error(recent_err)
        elif recent_calls:
            if True:   # (no nested expander — Streamlit disallows it inside the developer-info expander)
                st.markdown(t("dash.dev_recent"))
                st.dataframe([
                    {
                        t("common.time"): r["created_at"][:19].replace("T", " "),
                        t("dash.dev_col_endpoint"): r["node"],
                        t("dash.dev_col_tokens"): f"{r['input_tokens']} / {r['output_tokens']}",
                        t("dash.dev_col_cost"): round(r["cost_usd"], 6),
                        t("dash.dev_col_latency"): round(r["latency_ms"], 1),
                        "Session": (r["session_id"][:8] + "...") if r.get("session_id") else "—",
                    }
                    for r in recent_calls
                ], use_container_width=True, hide_index=True)
