"""
Custom theme layer for the Streamlit frontend.
Injects CSS scoped to Streamlit's own data-testid hooks so it survives
minor version upgrades better than targeting auto-generated class names.

Ink & Wash redesign — palette, layout and mascot match the approved
prototype (frontend/design-prototype/ink-wash-redesign.html). Two shells:
  inject_theme("customer")  light sidebar, gradient chat canvas (app.py)
  inject_theme("staff")     dark rail + white panel (the 4 back-office pages)
"""

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).parent / "assets"

# The 8 Ink & Wash swatches, plus two derived text tones (deeper than
# Carbon Ink) so body copy keeps ≥ 4.5:1 contrast on white.
PALETTE = {
    "rice": "#F2FAFA", "dilute": "#CBE4F0", "first": "#A5D0E9", "half": "#81BCDF",
    "full": "#5EA2D3", "dark": "#4185BC", "conc": "#286AA5", "carbon": "#195392",
    "ink": "#0F2C4A", "muted": "#4F6B85",
}

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap');

:root {
  --rice: #F2FAFA; --dilute: #CBE4F0; --first: #A5D0E9; --half: #81BCDF;
  --full: #5EA2D3; --dark: #4185BC; --conc: #286AA5; --carbon: #195392;
  --ink: #0F2C4A; --muted: #4F6B85; --line: #DCEAF2; --white: #FFFFFF;
  --rail: #0F2C4A;
  /* Meaning colours (Dashboard 2026-11): blue stays the structure; these four
     are used only where a colour says something — attention / urgent / done / AI-knowledge. */
  --amber: #D98A0B; --coral: #E8604C; --green: #1F8F69; --violet: #6B58C9; --teal: #2BA39B;
  --shadow-card: 0 1px 2px rgba(15,44,74,.05), 0 14px 36px rgba(40,106,165,.12);
  --font-ui: 'Plus Jakarta Sans', 'Noto Sans TC', -apple-system, 'PingFang TC', 'Microsoft JhengHei', sans-serif;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
[data-testid="stMarkdownContainer"], button, input, textarea {
  font-family: var(--font-ui);
}
[data-testid="stAppViewContainer"] { color: var(--ink); }

/* Streamlit's icon glyphs are font ligatures (e.g. "smart_toy" renders as
   a robot icon) — a blanket font-family override turns them back into
   literal text, so keep the icon font untouched here. */
[data-testid="stIconMaterial"] {
  font-family: "Material Symbols Rounded" !important;
}

[data-testid="stHeader"] { background: transparent; }

/* The menu Streamlit builds from file names can't be translated; i18n.render_nav draws ours. */
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] { margin: 1px 0; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
  border-radius: 12px; padding: 7px 14px; font-weight: 600;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { font-size: 14.5px; }
/* language switch under the menu */
[data-testid="stSidebar"] [data-testid="stSegmentedControl"] { margin: 6px 0 4px; }

h1, h2, h3, h4 {
  font-family: var(--font-ui) !important;
  font-style: normal;
  font-weight: 800 !important;
  color: var(--ink);
  letter-spacing: -.01em;
}

/* ── Sidebar nav: the entry script is listed by its filename ("app");
   swap in the product name without renaming the file everyone runs. */
[data-testid="stSidebarNav"] li:first-child a span {
  visibility: hidden;
  position: relative;
  overflow: visible;
}
[data-testid="stSidebarNav"] li:first-child a span::after {
  content: "💬 AI 客服";
  visibility: visible;
  position: absolute;
  left: 0;
  top: 0;
  white-space: nowrap;
}

/* ── Buttons ─────────────────────────────────────────────── */
/* Keyed off the button's own `kind` attribute rather than a wrapper
   data-testid — Streamlit gives st.form_submit_button's primary variant
   kind="primaryFormSubmit" (not "primary"), so a testid-scoped selector
   silently misses it and leaves it in Streamlit's default red. */
button[kind] {
  border-radius: 999px;
  border: 1px solid var(--line);
  font-weight: 700;
  color: var(--ink);
  background: var(--white);
}
button[kind]:hover { border-color: var(--full); color: var(--carbon); }
button[kind="primary"],
button[kind="primaryFormSubmit"] {
  background: var(--conc);
  border: none;
  color: var(--white);
}
button[kind="primary"]:hover,
button[kind="primaryFormSubmit"]:hover {
  background: var(--carbon);
  color: var(--white);
}

/* ── Text inputs ─────────────────────────────────────────────
   Streamlit's real border/background lives on the wrapper div, not
   the <input> itself — targeting the <input> alone is invisible. */
[data-testid="stTextInputRootElement"],
[data-testid="stTextAreaRootElement"],
[data-baseweb="select"] > div {
  border-radius: 12px !important;
  border: 1px solid var(--line) !important;
  background: var(--white) !important;
}

/* ── Alerts (disclaimer / banners / success) ─────────────────── */
[data-testid="stAlert"] {
  border-radius: 14px;
  border: 1px solid var(--line);
}
[data-testid="stAlertContentInfo"] { color: var(--carbon); }

/* ── Bordered containers = cards ─────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 22px !important;
  border-color: var(--line) !important;
}
.st-key-card, [class*="st-key-card_"] {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 18px 20px;
}

/* ── Metrics: each KPI as its own soft card ──────────────────── */
[data-testid="stMetric"] {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px 18px;
}
[data-testid="stMetricLabel"] { color: var(--muted); font-weight: 600; }
[data-testid="stMetricValue"] { color: var(--ink); font-weight: 800; font-size: 1.55rem; }

/* ── Expanders ───────────────────────────────────────────────── */
[data-testid="stExpander"] details {
  border: 1px solid var(--line) !important;
  border-radius: 16px !important;
  background: var(--white);
}

/* ── Dataframes inside cards ─────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }

/* ── Chat messages ───────────────────────────────────────────
   stChatMessage is a full-width flex row with no bubble width cap —
   cap content width, then flip the row for any message that isn't the
   customer's own (the AI's mascot avatar and the agent's 🧑‍💼 alike),
   so customer and customer-service replies sit on opposite sides. */
[data-testid="stChatMessage"] { background: transparent; }
[data-testid="stChatMessageContent"] {
  max-width: 78%;
  width: fit-content;
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 18px;
  border-top-right-radius: 6px;
  box-shadow: var(--shadow-card);
  padding: 0.6rem 0.95rem;
  /* Streamlit reserves ~56px here for its own hover toolbar. Once the row
     below is reversed, that reserved space lands between the bubble and
     the avatar instead of at the outer edge — drop it so the avatar sits
     flush against the bubble. */
  margin-right: 0 !important;
}
[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) {
  flex-direction: row-reverse;
}
/* The customer's own message: solid Concentrated bubble, white text */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
  background: var(--conc);
  border: none;
  border-radius: 18px;
  border-top-left-radius: 6px;
  box-shadow: none;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] * {
  color: var(--white) !important;
}
[data-testid="stChatMessageAvatarUser"] {
  background: var(--first) !important;
  border-radius: 50%;
}
/* The assistant avatar is the mascot image, which carries its own round
   background — an opaque fill here would show as a ring behind it. */
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessageAvatarCustom"] {
  background: transparent !important;
  border-radius: 50%;
}
[data-testid="stChatMessage"] img { border-radius: 50%; }

/* ── Chat input: white pill with a round Concentrated send button ── */
[data-testid="stChatInput"] {
  border-radius: 999px;
  border: 1px solid var(--white);
  background: var(--white);
  box-shadow: 0 10px 30px rgba(40,106,165,.18);
  padding-left: 8px;
}
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] textarea {
  background: transparent !important;
  border: none !important;
}
[data-testid="stChatInputSubmitButton"] {
  background: var(--conc) !important;
  border-radius: 50% !important;
  color: var(--white) !important;
}
[data-testid="stChatInputSubmitButton"] svg { fill: var(--white) !important; color: var(--white) !important; }
</style>
"""

# ── Customer shell: light sidebar, gradient canvas, centred hero ────────────
CUSTOMER_CSS = """
<style>
[data-testid="stAppViewContainer"] {
  background: linear-gradient(180deg, #FFFFFF 0%, var(--rice) 36%, var(--dilute) 70%, var(--first) 86%, var(--first) 100%);
  background-attachment: fixed;
}
/* The docked chat input floats over the scrolling page. Its bar is solid
   var(--first) — the canvas's solid bottom band — so content scrolls fully
   *under* it instead of showing through behind the input and disclaimer.
   The soft fade sits just above the bar (::before), outside its box. */
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"] { background: transparent; }
[data-testid="stBottom"] > div { background: var(--first) !important; }
[data-testid="stBottom"] > div::before {
  content: ""; position: absolute; left: 0; right: 0; top: -28px; height: 28px;
  background: linear-gradient(180deg, rgba(165,208,233,0), var(--first));
  pointer-events: none;
}

[data-testid="stSidebar"] {
  background: var(--white);
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] [data-testid="stBaseButton-segmented_controlActive"] {
  background: var(--dilute); color: var(--carbon); border: 1px solid var(--first); font-weight: 700;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { color: var(--ink); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: var(--dilute); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] { background: var(--dilute); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p { color: var(--carbon); font-weight: 700; }
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: var(--dilute);
  border-radius: 10px;
}
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--carbon); font-weight: 700; }
/* Sidebar sections wrapped in st.container(border=True) become pale cards */
[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--rice);
  border: 1px solid var(--line) !important;
  border-radius: 16px !important;
}
[data-testid="stSidebar"] h3 { font-size: 15px !important; color: var(--carbon); }

/* Small centred page label replaces the old big title */
.topbar {
  text-align: center;
  font-weight: 700;
  font-size: 15px;
  color: var(--ink);
  margin: -8px 0 6px;
}

/* ── Mingis stays on screen during a human-agent conversation ──
   Sticky strip at the top of the thread: avatar + status chip + one
   line of what Mingis is doing. Sticky (not a corner float) so it never
   covers the chat input or a long message, and never scrolls away. */
/* Streamlit wraps each markdown in its own element container, so `position:
   sticky` on the bar alone has no tall parent to stick within — stick the
   wrapper instead (its parent is the whole thread). */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] .mingis-bar) {
  position: sticky; top: 8px; z-index: 20;
}
.mingis-bar {
  display: flex; align-items: center; gap: 14px;
  background: linear-gradient(135deg, var(--dilute) 0%, var(--rice) 100%);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: var(--shadow-card);
  padding: 10px 18px 10px 12px;
  margin: 0 0 16px;
}
.mingis-bar img { width: 62px; height: 62px; flex: none; }
.mingis-bar .nm { font-weight: 800; color: var(--ink); font-size: 16px; }
.mingis-bar .chip {
  display: inline-block; margin-left: 8px; vertical-align: 2px;
  font-size: 12px; font-weight: 700; color: var(--white);
  padding: 2px 10px; border-radius: 999px; background: var(--conc);
}
.mingis-bar .chip.wait { background: #D9902B; }
.mingis-bar .chip.live { background: #2E9E6B; }
.mingis-bar .chip.done { background: var(--muted); }
.mingis-bar .msg { font-size: 13.5px; line-height: 1.55; color: var(--muted); margin-top: 2px; }

/* ── Hero (empty conversation) — the reference's right-hand screen ── */
.hero {
  text-align: center;
  padding: 4px 8px 6px;
}
.hero-bot {
  height: 290px;
  filter: drop-shadow(0 18px 24px rgba(40,106,165,.22));
}
.hero-badge {
  display: inline-block;
  background: var(--conc);
  color: var(--white);
  font-size: 13px;
  font-weight: 700;
  padding: 7px 18px;
  border-radius: 999px;
  margin-top: 10px;
}
.hero-title {
  font-size: 34px;
  line-height: 1.25;
  font-weight: 800;
  color: var(--ink);
  margin: 14px 0 6px;
}
.hero-sub {
  color: var(--muted);
  font-size: 14.5px;
  line-height: 1.7;
  max-width: 520px;
  margin: 0 auto 14px;
}

/* Starter / follow-up shortcuts as soft pills (keys: starter_N, followup_N) */
/* Buttons size to their label, so their element container is only as wide
   as the button — centre the container itself in the column. */
[class*="st-key-starter_"] { align-self: center; }
[class*="st-key-starter_"] button,
[class*="st-key-followup_"] button {
  background: rgba(255,255,255,.78);
  border: 1px solid var(--white);
  box-shadow: 0 4px 14px rgba(40,106,165,.10);
  font-weight: 500;
  color: var(--ink);
}
[class*="st-key-followup_"] button {
  border: 1px solid var(--first);
  color: var(--carbon);
  font-weight: 600;
}
</style>
"""

# ── Staff shell: dark rail, white rounded panel on a soft canvas ────────────
STAFF_CSS = """
<style>
[data-testid="stAppViewContainer"] {
  background: linear-gradient(135deg, #E3F0F7 0%, var(--rice) 45%, #DDEDF6 100%);
}
[data-testid="stMainBlockContainer"] {
  background: rgba(255,255,255,.92);
  border-radius: 28px;
  box-shadow: var(--shadow-card);
  margin-top: 28px;
  margin-bottom: 28px;
  padding: 2.2rem 2.4rem 2.6rem !important;
  max-width: 1280px;
}
[data-testid="stBottom"], [data-testid="stBottom"] > div,
[data-testid="stBottomBlockContainer"] { background: transparent; }

[data-testid="stSidebar"] {
  background: var(--rail);
  border-right: none;
}
[data-testid="stSidebar"] * { color: #C9DCEB; }
[data-testid="stSidebarNav"]::before {
  content: "🏦  Future銀行後台";
  display: block;
  color: var(--white);
  font-weight: 800;
  font-size: 16px;
  padding: 4px 18px 16px;
}
.rail-brand { color: var(--white); font-weight: 800; font-size: 16px; padding: 4px 6px 12px; }
[data-testid="stSidebar"] [data-testid="stBaseButton-segmented_control"] {
  background: transparent; color: #B9CFE1; border: 1px solid rgba(185,207,225,.35);
}
[data-testid="stSidebar"] [data-testid="stBaseButton-segmented_controlActive"] {
  background: rgba(94,162,211,.38); color: var(--white); border: 1px solid rgba(94,162,211,.6); font-weight: 700;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { color: #B9CFE1; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background: rgba(94,162,211,.14); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] { background: rgba(94,162,211,.24); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p { color: var(--white); font-weight: 700; }
[data-testid="stSidebarNav"] a { border-radius: 12px; }
[data-testid="stSidebarNav"] a span { color: #B9CFE1 !important; font-weight: 600; }
[data-testid="stSidebarNav"] a:hover { background: rgba(94,162,211,.14); }
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: rgba(94,162,211,.24);
  box-shadow: inset 3px 0 0 var(--full);
}
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--white) !important; }
[data-testid="stSidebarCollapseButton"] svg, [data-testid="stSidebarHeader"] svg { color: #C9DCEB; }

h1 { font-size: 2.1rem !important; }

/* ── Dashboard hero card ─────────────────────────────────────── */
.dhero {
  position: relative;
  border-radius: 24px;
  background: linear-gradient(135deg, var(--dilute) 0%, var(--rice) 55%, #E7F2F9 100%);
  padding: 32px 30px 16px;
  min-height: 400px;
  display: flex;
  flex-direction: column;
  margin-top: 48px;
}
.dhero::before {
  content: "";
  position: absolute;
  right: 50px; top: 30px;
  width: 230px; height: 230px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(129,188,223,.55), rgba(129,188,223,0) 70%);
}
.dhero h2 {
  position: relative;
  font-size: 40px !important;
  line-height: 1.15;
  margin: 0 0 18px;
  max-width: 55%;
  padding: 0;
}
.dhero .go {
  position: relative;
  align-self: flex-start;
  background: var(--carbon);
  color: var(--white) !important;
  text-decoration: none;
  font-weight: 700;
  font-size: 14px;
  padding: 10px 20px;
  border-radius: 999px;
}
.dhero .go:hover { background: var(--ink); }
.dhero .bot {
  position: absolute;
  right: 26px; top: -64px;
  height: 340px;
  filter: drop-shadow(0 20px 26px rgba(25,83,146,.25));
  pointer-events: none;
}
/* Mingis at the desk (Dashboard): wider than the standing figure, so it sits
   lower and tucks under the translucent KPI band instead of floating. */
.dhero .bot.desk {
  right: 8px; top: -104px;   /* clear of the 4 KPI cards: the desk ends above the band */
  height: 340px;
}
.dhero .dot { position: absolute; border-radius: 50%; background: var(--white); }
.kpis {
  position: relative;
  margin-top: auto;
  margin-left: -14px; margin-right: -14px;
  background: rgba(255,255,255,.84);
  backdrop-filter: blur(10px);
  border: 1px solid var(--white);
  border-radius: 20px;
  padding: 16px 24px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.kpis { padding: 12px; }
/* One tint per KPI (--k): the card is a pale wash of it, the icon chip a deeper one. */
.kpi { background: color-mix(in srgb, var(--k) 11%, #fff); border-radius: 14px; padding: 12px 14px; min-width: 0; }
.kpi .kh { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.kpi .chip {
  flex: none; width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center;
  background: color-mix(in srgb, var(--k) 20%, #fff); color: var(--k);
}
.kpi .chip svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.kpi .k { font-size: 13px; color: var(--muted); font-weight: 700; }
.kpi .v { font-size: 38px; font-weight: 800; letter-spacing: -.02em; line-height: 1.15; color: var(--ink); }
.kpi .s { font-size: 12px; color: var(--muted); }

/* Ticket facts as one row of chips (status / urgency / customer / waiting) instead of three big number cards */
.tchips { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 12px; }
.tchip {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 999px;
  font-size: 13px; font-weight: 600; color: var(--ink);
  background: color-mix(in srgb, var(--c, var(--conc)) 12%, #fff);
  border: 1px solid color-mix(in srgb, var(--c, var(--conc)) 28%, #fff);
}
.tchip.open { --c: var(--amber); } .tchip.done { --c: var(--green); } .tchip.urgent { --c: var(--coral); }

/* Knowledge Improvement funnel: signals -> topics -> drafts -> approved */
.funnel { display: flex; align-items: stretch; gap: 8px; flex-wrap: wrap; margin: 4px 0 8px; }
.fstep { flex: 1; min-width: 120px; border-radius: 14px; padding: 10px 14px; background: color-mix(in srgb, var(--k) 11%, #fff); }
.fstep .n { font-size: 30px; font-weight: 800; line-height: 1.15; color: var(--ink); }
.fstep .l { font-size: 12.5px; font-weight: 600; color: var(--muted); }
.farrow { align-self: center; color: var(--muted); font-weight: 700; }

/* Confidence before / now, drawn against the 0.60 line */
.ba { margin: 4px 0 10px; }
.ba-row { display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: 13px; color: var(--muted); }
.ba-row .lab { width: 64px; flex: none; font-weight: 600; }
.ba-track { position: relative; flex: 1; height: 12px; border-radius: 999px; background: var(--line); }
.ba-fill { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 999px; }
.ba-thr { position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--ink); opacity: .55; }
.ba-row .val { width: 48px; flex: none; text-align: right; font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums; }
.ba-note { font-size: 12px; color: var(--muted); margin-left: 74px; }

.card-title { font-size: 16px; font-weight: 800; color: var(--ink); margin: 0 0 6px; }
.card-title .cd { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; vertical-align: 1px; background: var(--c, var(--conc)); }
.card-meta { font-size: 13px; color: var(--muted); }
.big-num { font-size: 46px; font-weight: 800; line-height: 1; color: var(--ink); }
.big-num small { font-size: 18px; color: var(--muted); font-weight: 700; }
/* Customer satisfaction, compact: big average + one stacked bar + one legend line */
.csat { display: flex; align-items: center; gap: 18px; padding: 4px 0 10px; }
.csat .big-num { font-size: 38px; flex: none; }
.csat-r { flex: 1; min-width: 0; }
.csat-bar { display: flex; gap: 2px; height: 10px; border-radius: 999px; overflow: hidden; background: var(--line); }
.csat-bar i { display: block; min-width: 4px; }
.csat-leg { display: flex; flex-wrap: wrap; gap: 2px 14px; margin-top: 8px; font-size: 12.5px; color: var(--muted); }
.csat-leg b { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 5px; }
.legend { font-size: 13px; color: var(--muted); margin-top: 8px; line-height: 1.8; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }

/* AI cost table (reference's "Earnings" table) */
table.cost { width: 100%; border-collapse: collapse; font-size: 14px; border: none; }
/* Streamlit's markdown tables add cell borders and a header fill — reset them */
table.cost th, table.cost td { border-left: none !important; border-right: none !important; border-top: none !important; background: transparent !important; }
table.cost thead tr, table.cost tbody tr { background: transparent !important; border: none; }
table.cost th { text-align: left; font-size: 12px; color: var(--muted); font-weight: 600; padding: 8px 6px; border-bottom: 1px solid var(--line); }
table.cost td { padding: 12px 6px; border-bottom: 1px solid var(--line); vertical-align: middle; color: var(--ink); }
table.cost tr:last-child td { border-bottom: none; }
.who { display: flex; align-items: center; gap: 12px; font-weight: 600; }
.who small { display: block; color: var(--muted); font-size: 12px; font-weight: 500; }
.ico { width: 42px; height: 42px; border-radius: 13px; display: grid; place-items: center; color: var(--white); font-weight: 800; flex: none; }
.meter { height: 22px; border-radius: 6px; background: #EEF5F9; position: relative; overflow: hidden; }
.meter span { position: absolute; top: 0; bottom: 0; left: 0; border-radius: 6px; background: repeating-linear-gradient(90deg, var(--first) 0 3px, var(--dilute) 3px 9px); }

@media (max-width: 900px) {
  .dhero h2 { font-size: 30px !important; max-width: 62%; }
  .dhero .bot { height: 240px; top: -30px; right: 6px; }
  .dhero .bot.desk { height: 250px; top: -70px; right: 0; }
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .kpi .v { font-size: 30px; }
}
</style>
"""


def inject_theme(variant: str = "staff") -> None:
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    st.markdown(CUSTOMER_CSS if variant == "customer" else STAFF_CSS, unsafe_allow_html=True)


@lru_cache(maxsize=None)
def asset_data_uri(name: str) -> str:
    """Inline an asset for use inside st.markdown HTML (Streamlit can't
    serve frontend/assets/ by URL without enabling static serving)."""
    path = ASSETS / name
    mime = {"webp": "image/webp", "png": "image/png", "svg": "image/svg+xml"}[path.suffix[1:]]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


MASCOT_FULL = "mascot_full.webp"
MASCOT_DESK = "mascot_desk.webp"
MASCOT_HEAD = "mascot_head.png"   # same file as MASCOT_HEAD_PATH, by name for asset_data_uri
MASCOT_HEAD_PATH = str(ASSETS / "mascot_head.png")
