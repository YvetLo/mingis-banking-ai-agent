"""
LangGraph Nodes — Sprint 6 (Router/CardLoss/Handoff/FAQ/Logger), Sprint 7 (Account),
Sprint 9 (Router → real LLM intent classification), Sprint 12 (FAQ grounding verifier),
Sprint 13 (FAQ Node answer generation deferred for streaming),
Sprint 14 (business-defined handoff trigger rules)

Sprint 6 moved Sprint 1-5's if/else `chat()` branches into a graph
without changing external behavior. Sprint 7 gave the Account Node a
real implementation: instead of stuffing the user's full account data
into the FAQ Node's system prompt, it now runs its own Claude call with
tools (get_account_balance / get_credit_card_bill / get_transactions)
and only fetches what the question actually needs. See docs/ADR.md
ADR-008 and docs/design_journal.md Sprint 7 entry for the reasoning.

Sprint 9 replaced the Router's keyword matching with a real LLM
classifier (see .intent.classify_intent) — the two exceptions,
in-progress workflow continuation and the frontend's force_handoff
flag, stay deterministic pre-checks because they're about server-side
state, not about understanding what the user just said.

Sprint 12 added a grounding verifier to the FAQ Node (see .verifier) —
a diagnostic case study found that RAG similarity scores alone can't
tell "chunks that answer the question" from "chunks that merely score
above a threshold," so ambiguous retrievals now get an independent
check before a draft answer is even generated, escalating to Handoff
rather than risking an ungrounded reply.

Sprint 13 stopped the FAQ Node's normal (non-escalation) path from
calling Claude for the final answer itself — it returns
`pending_stream` (system prompt + messages) instead, so main.py's
`/chat` (blocking) and `/chat/stream` (token-by-token) endpoints can
each finish that one call their own way without duplicating the
routing/retrieval/verification logic above it.

Sprint 14 expanded the Router's handoff classification from a single
generic case ("user explicitly asked for a human") to a set of named
business rules (fraud/security, disputes, approval-required requests,
sensitive data changes, emotional distress, cross-account complexity)
— see .intent.INTENT_CLASSIFIER_TOOL's handoff_category enum and
HANDOFF_CATEGORY_REASON below. Each maps to its own trigger_reason so
the Dashboard can tell these apart, not lump them into one bucket.

Sprint 15 made escalation actually reach a human: both Handoff Node
and the FAQ Node's verifier-escalation branch now call
.handoff.escalate_to_human() to open a real ticket and seed a
persisted conversation thread, instead of only logging the event.

Sprint 15 follow-up (manual testing, 2026-08-01): sensitive_data_change
gets its own message instead of the generic apologetic HANDOFF_MSG (see
SENSITIVE_DATA_HANDOFF_MSG), and every handoff path appends a soft,
non-blocking login reminder for guest users (see LOGIN_REMINDER /
_with_login_reminder) — a hard login gate was considered and rejected
because it would strand someone reporting a compromised/locked account.

Sprint 19 added a pre-handoff intake for GUESTS who simply ask for a
human with no context ("我要找真人客服") — handoff_intake_node collects
customer type + a one-line problem description before opening the
ticket, so the agent picks up a queue item that says who and what
instead of an empty thread. Deliberately scoped to that one case: a
logged-in customer is already identified, and every other handoff
category (fraud, dispute, sensitive data, ...) already carries the
problem in the triggering message — asking those customers to fill in a
form first would delay exactly the cases that matter most.
"""

import json
import os
import re
from typing import Any

from ..card_loss_workflow import handle_step as card_loss_step, is_step_input
from ..database import log_unresolved
from ..mock_api.mock_data import get_user_by_id
from ..nlp import is_negative_feedback, detect_language
from ..prompts import HANDOFF_MSG, build_account_system_prompt, build_system_prompt
from .handoff import escalate_to_human
from .intent import classify_intent
from .state import AgentState
from .suggestions import account_followups, suggest_followups
from .tools import ACCOUNT_TOOLS, execute_tool
from .verifier import verify_chunks_sufficient
from ..tracing import traced_create

MAX_TOOL_ITERATIONS = 3

# Below this top-1 retrieval score, a chunk's similarity alone isn't a
# reliable signal — the diagnostic case study measured real "genuinely
# answerable" scores as low as 0.482 and real "genuine gap" scores as
# high as 0.500 (overlapping), so only clearly-confident retrievals
# (>= this) skip the verifier call; everything else pays the extra
# latency to get an actual grounding judgment instead of a guess.
HIGH_CONFIDENCE_THRESHOLD = 0.60

# Every FAQ answer is grounding-checked, not only the low-scoring ones (2026-11, ADR-020).
# Measured on 12 real knowledge gaps + 62 answerable questions: checking only below the
# 0.60 line above stopped 5 of the 12 gaps; the other 7 scored 0.60-0.76 (a long refund
# question scored 0.66) and were answered from loosely related text, with the model
# filling in reasons the knowledge base never gave. Gap and answerable scores overlap,
# so no score line separates them — only the verifier's judgment did (12 of 12).
# Cost: one extra small model call (~2-4s) per FAQ answer, and a few more handoffs.
# VERIFY_ALWAYS=0 restores the old "only below the line" behaviour.
VERIFY_ALWAYS = os.getenv("VERIFY_ALWAYS", "1").strip().lower() not in ("0", "false", "no", "off")

NOT_LOGGED_IN_ACCOUNT = {
    "zh": "要查詢帳務資訊，需要先登入喔！請點選側邊欄登入。",
    "en": "Please log in first to check your account information.",
}

TOOL_LOOP_FALLBACK = {
    "zh": "抱歉，這個查詢比較複雜，請稍後再試，或撥打客服專線 0800-XXX-XXX。",
    "en": "Sorry, this request is taking a bit long. Please try again or call 0800-XXX-XXX.",
}

# Distinct from HANDOFF_MSG (backend/src/prompts.py): that one is a reply
# to the USER asking for/complaining their way to a human, so an
# apologetic tone fits. This one fires when the AI itself decides it
# can't help — the user just asked a plain question, so "很抱歉我沒能
# 解決" reads as if they'd been arguing with the bot, which they weren't.
VERIFIER_ESCALATION_MSG = {
    "zh": "此問題我為您轉接真人客服回覆，轉接中，請稍候。",
    "en": "Let me transfer you to a human agent for this one — please hold on.",
}

# Sprint 14 — maps classify_intent()'s handoff_category to a distinct
# trigger_reason, so the Dashboard can tell "user explicitly asked for
# a human" apart from "system detected a dispute/fraud/approval-needed
# case" — these represent different signals for whoever triages the
# queue, not just a generic "handoff happened" bucket.
HANDOFF_CATEGORY_REASON = {
    "explicit_request": "handoff_intent",
    "fraud_or_security": "handoff_urgent_fraud",
    "dispute_or_refund": "handoff_dispute",
    "approval_required": "handoff_approval_required",
    "sensitive_data_change": "handoff_sensitive_data",
    "emotional_distress": "handoff_emotional_distress",
    "cross_account_complexity": "handoff_cross_account",
}

# Fraud/security is the one category the business rules call out for
# immediate + urgent handling — a distinct, more reassuring message
# rather than the generic apologetic HANDOFF_MSG (see prompts.py),
# which reads as if the bot failed to help, not as "we caught this and
# are prioritizing it."
URGENT_FRAUD_HANDOFF_MSG = {
    "zh": (
        "已將您的問題標記為緊急案件，立即為您轉接真人客服處理。\n\n"
        "📞 **緊急服務專線：0800-XXX-XXX**（24 小時真人客服接聽）\n\n"
        "若您的卡片可能遭盜用，建議您也可以直接告訴我「我要掛失」，我可以立即協助您停用卡片。"
    ),
    "en": (
        "This has been marked as an urgent case and you're being connected to a live agent immediately.\n\n"
        "📞 **Emergency line: 0800-XXX-XXX** (24/7 live agents)\n\n"
        "If your card may have been used without authorization, you can also tell me \"block my card\" "
        "and I can deactivate it right away."
    ),
}

# sensitive_data_change previously fell through to the generic HANDOFF_MSG
# ("很抱歉我沒能完全解決您的問題"), which reads like an apology for failing
# to answer — but requiring a human here isn't a failure, it's policy
# (identity-sensitive changes always need a person). Reported in manual
# testing 2026-08-01; scope was deliberately kept to just this category
# rather than rewording every policy-driven handoff (see design_journal.md
# Sprint 15 follow-up).
SENSITIVE_DATA_HANDOFF_MSG = {
    "zh": "請稍候，我為您轉接真人客服協助處理。",
    "en": "Please hold on — I'm transferring you to a human agent for assistance.",
}

# Appended to any handoff reply when the customer isn't logged in — soft
# nudge only, never blocks the transfer (a hard login gate would strand
# someone whose account is already locked/compromised, e.g. a fraud
# report). If they do log in while the handoff conversation is still
# open, frontend/app.py links the ticket to their user_id after the fact
# via /handoff/{id}/link-user, so this reminder's payoff (agent doesn't
# have to re-verify identity) still lands even without a hard gate.
LOGIN_REMINDER = {
    "zh": "💡 建議您可以先登入帳號，讓客服人員能更快確認您的身份，不需要重新驗證。",
    "en": "💡 Logging in first helps our agent verify your identity faster — no need to re-verify from scratch.",
}


def _with_login_reminder(msg: str, language: str, authenticated: bool) -> str:
    if authenticated:
        return msg
    return f"{msg}\n\n{LOGIN_REMINDER[language]}"

# Recognizes "please undo/restore my already-blocked card" — distinct from
# card_loss_workflow.py's _is_cancel(), which only cancels an IN-PROGRESS
# verification (steps 1-3). There is no unblock_card() capability by design
# (a completed block is meant to be a one-way action, same as a real bank);
# this just stops the Router/Node from misreading "please cancel/restore"
# as "start a brand new loss report" (see docs/design_journal.md Sprint 10).
RESTORE_KW = ["取消掛失", "解除掛失", "撤銷掛失", "恢復使用", "找到卡", "找到了",
              "cancel the block", "unblock", "restore my card", "reactivate my card"]

def _is_restore_request(text: str) -> bool:
    return any(kw in text.lower() for kw in RESTORE_KW)

CANNOT_RESTORE_MSG = {
    "zh": "已完成的掛失無法透過線上客服復原，需要由真人客服協助確認身分後恢復使用或補發新卡。請撥打 0800-XXX-XXX，我們的客服人員會立即協助您！",
    "en": "A completed card block can't be reversed through chat. Please call 0800-XXX-XXX — our team will verify your identity and help restore or reissue your card.",
}

# ── Router Node ──────────────────────────────────────────────────────────────

def make_router_node(client, model: str):
    def router_node(state: AgentState) -> dict:
        message = state["user_message"]
        language = detect_language(message)

        # An in-progress workflow continues when this message answers the
        # step it's on (mirrors Sprint 3's `if wf.step > 0` guard) — that
        # check is deterministic, no classifier call. workflow_data["type"]
        # tells the two multi-turn flows apart; the card-loss flow predates
        # it and carries no type key.
        step = state.get("workflow_step", 0)
        if step > 0:
            data = state.get("workflow_data", {})
            if data.get("type") == INTAKE_WORKFLOW:
                return {"language": language, "intent": "handoff_intake"}
            if data.get("type") == BILL_CLARIFY_WORKFLOW:
                return {"language": language, "intent": "bill_clarify"}
            if is_step_input(message, {"step": step, "data": data}):
                return {"language": language, "intent": "card_loss"}
            # A side question mid card-loss ("我這個月帳單多少" at step 2):
            # answer it as a normal turn but leave workflow_step/data as
            # they are, so main.py can append the pointer back to the step.
            intent, handoff_category = classify_intent(client, model, message)
            if intent in ("faq", "account"):
                return {"language": language, "intent": intent, "paused_workflow": True}
            if intent == "handoff":
                # A human takes over from here; the half-done flow ends.
                reason = HANDOFF_CATEGORY_REASON.get(handoff_category or "", "handoff_intent")
                return {"language": language, "intent": "handoff", "handoff_reason": reason,
                        "workflow_step": 0, "workflow_data": {}}
            return {"language": language, "intent": "card_loss"}

        # Frontend sets this once fallback_count crosses the threshold;
        # also deterministic, independent of what this message says.
        if state.get("force_handoff"):
            return {"language": language, "intent": "handoff", "handoff_reason": "fallback_threshold"}

        # A bare greeting / thanks / goodbye ("你好！", "Hi", "謝謝") is not a
        # question about the bank. Left to the pipeline below it was read as an
        # FAQ, retrieved nothing relevant (score ~0.24) and the verifier then
        # escalated it to a human agent. Deterministic, no LLM call, and only
        # for messages that are *nothing but* the greeting — "你好，年費多少？"
        # still goes through as a normal question.
        smalltalk = _match_smalltalk(message)
        if smalltalk:
            kind, lang = smalltalk
            return {"language": lang, "intent": "smalltalk", "smalltalk_kind": kind}

        # "我的帳單金額有問題" with nothing else: ask WHICH item first, then
        # hand over. Deterministic and checked BEFORE the LLM classifier,
        # because the classifier is not stable on this sentence (it flips
        # between `account` and a dispute handoff run to run) — and either
        # way the agent would otherwise pick up a case that says nothing.
        if _is_vague_bill_complaint(message):
            return {"language": language, "intent": "bill_clarify",
                    "handoff_reason": "handoff_dispute"}

        intent, handoff_category = classify_intent(client, model, message)
        if intent == "handoff":
            reason = HANDOFF_CATEGORY_REASON.get(handoff_category or "", "handoff_intent")
            # A guest who just asks for a human hasn't told us who they are
            # OR what they want — collect both first (Sprint 19). Every
            # other category already states the problem in this very
            # message, and a logged-in customer is already identified, so
            # they go straight through.
            if (reason == "handoff_intent"
                    and not state.get("user_authenticated", False)):
                return {"language": language, "intent": "handoff_intake",
                        "handoff_reason": reason}
            return {"language": language, "intent": "handoff", "handoff_reason": reason}
        return {"language": language, "intent": intent}

    return router_node


# ── CardLoss Node ────────────────────────────────────────────────────────────

def card_loss_node(state: AgentState) -> dict:
    language = state["language"]
    message = state["user_message"]
    user_id = state.get("user_id")
    step = state.get("workflow_step", 0)
    data = state.get("workflow_data", {})

    if step > 0:
        if not user_id:
            msg = ("請先登入才能繼續掛失流程。" if language == "zh"
                   else "Please log in to continue.")
            return {"response": msg, "workflow_step": 0, "workflow_data": {}}
        response_text, updated = card_loss_step(message, {"step": step, "data": data}, user_id, language)
        return {"response": response_text, "workflow_step": updated["step"], "workflow_data": updated["data"]}

    # step == 0 → this turn is the trigger that opens the workflow
    if not user_id:
        msg = ("要辦理掛失，需要先登入才能驗證身分。請點側邊欄登入！"
               if language == "zh" else "Please log in first to report a lost card.")
        return {"response": msg}

    # "取消掛失"/"找到卡了" etc. are about an ALREADY-completed block, not a
    # new report — without this check the message below would blindly
    # restart verification instead of answering what was actually asked.
    if _is_restore_request(message):
        user = get_user_by_id(user_id)
        has_blocked_card = user and any(c["status"] != "active" for c in user.get("cards", []))
        if has_blocked_card:
            return {"response": CANNOT_RESTORE_MSG[language]}

    msg = ("好的，馬上協助您辦理掛失！\n\n為了保護帳戶安全，需要先確認身分。\n**請問您的身分證後四碼是？**"
           if language == "zh"
           else "I'll help you block the card right away!\n\nTo protect your account, I need to verify your identity.\n**What are the last 4 digits of your national ID?**")
    return {"response": msg, "workflow_step": 1, "workflow_data": {}}


# ── Handoff Intake Node (Sprint 19) ──────────────────────────────────────────
# A guest typing "我要找真人客服" gives the agent nothing to work with: no
# identity, no problem. One question collects both, so the ticket that
# lands in the console already says who this is and what they need —
# which is the same payoff the login reminder aims for, for customers who
# don't want to (or can't) log in.

INTAKE_WORKFLOW = "handoff_intake"   # workflow_data["type"] marker — see router

# Ordered: "非本行" is checked before the card/account keywords so
# "我不是本行客戶，想問信用卡" lands on 3 rather than 2.
CUSTOMER_TYPE_LABEL = {
    "zh": {"1": "銀行帳戶客戶", "2": "信用卡客戶", "3": "非本行客戶", None: "未指明"},
    "en": {"1": "Bank account customer", "2": "Credit card customer",
           "3": "Not yet a customer", None: "Not specified"},
}
CUSTOMER_TYPE_KEYWORDS = [
    ("3", ["非本行", "不是本行", "還不是", "不是你們", "沒有帳戶", "沒開戶", "還沒開戶",
           "not a customer", "not yet a customer", "don't have an account",
           "do not have an account", "prospective"]),
    ("1", ["銀行帳戶", "存款", "帳戶客戶", "活存", "定存", "薪轉",
           "bank account", "savings", "deposit account"]),
    ("2", ["信用卡", "卡友", "卡片客戶", "credit card", "cardholder"]),
]

INTAKE_PROMPT = {
    "zh": (
        "好的，我幫您轉接真人客服。為了幫您接到對的窗口、也避免客服重複詢問，先跟您確認兩件事：\n\n"
        "**1️⃣ 請問您是？**\n\n"
        "1. 銀行帳戶客戶\n"
        "2. 信用卡客戶\n"
        "3. 非本行客戶\n\n"
        "**2️⃣ 請簡單描述您要詢問的問題**\n\n"
        "請一併回覆，例如：「2，我想問信用卡帳單分期」。（輸入「取消」可結束）"
    ),
    "en": (
        "Sure — I'll connect you with a human agent. Two quick things first, so we can route you "
        "to the right desk and the agent doesn't have to ask again:\n\n"
        "**1️⃣ Which describes you?**\n\n"
        "1. Bank account customer\n"
        "2. Credit card customer\n"
        "3. Not yet a customer\n\n"
        "**2️⃣ Briefly, what would you like help with?**\n\n"
        "Reply with both, e.g. \"2, I'd like to ask about installment plans.\" (Type \"cancel\" to stop.)"
    ),
}

INTAKE_REASK = {
    "zh": (
        "不好意思，我沒有讀懂。**請直接回覆 1、2 或 3**（1. 銀行帳戶客戶　2. 信用卡客戶　3. 非本行客戶），"
        "並用一句話說明您要詢問的問題，例如：「1，我的轉帳一直失敗」。"
    ),
    "en": (
        "Sorry, I didn't catch that. **Please reply with 1, 2, or 3** (1. Bank account customer, "
        "2. Credit card customer, 3. Not yet a customer) plus one line on what you need help with — "
        "e.g. \"1, my transfers keep failing.\""
    ),
}

# The customer type came through but the problem didn't — asking the
# whole question again would look like the bot ignored what they just
# typed, so this only asks for the missing half.
INTAKE_REASK_DESCRIPTION = {
    "zh": "了解，您是{type_label}。**請再用一句話描述您要詢問的問題**，客服才知道從哪裡幫您處理。",
    "en": "Got it — {type_label}. **Could you describe in one line what you need help with?** "
          "That's what the agent needs to pick this up.",
}

INTAKE_CANCELLED = {
    "zh": "好的，已取消轉接。若還有其他問題，我很樂意繼續為您服務 🙂",
    "en": "No problem — transfer cancelled. I'm happy to keep helping here 🙂",
}

INTAKE_DONE = {
    "zh": "收到！已將您的身分（{type_label}）與問題描述一併送出，正在為您轉接真人客服，請稍候。",
    "en": "Got it! I've passed on your details ({type_label}) and your question — connecting you to an agent now.",
}

# After MAX_INTAKE_ATTEMPTS the transfer goes through regardless — don't
# read back "您的身分（未指明）" at someone who just wants a person.
INTAKE_DONE_PARTIAL = {
    "zh": "收到！已將您的問題送出，正在為您轉接真人客服，請稍候。",
    "en": "Got it! I've passed your question along — connecting you to an agent now.",
}

INTAKE_CANCEL_KW = ["取消", "不用了", "算了", "cancel", "never mind", "nevermind"]

# Two attempts, then escalate anyway with whatever we have — a customer
# who already asked for a human should never be stuck in a form loop
# with a bot.
MAX_INTAKE_ATTEMPTS = 2
MIN_DESCRIPTION_LEN = 5   # shorter than this ("帳單") isn't a triageable description


def _parse_customer_type(text: str) -> str | None:
    """1/2/3 if the reply picks one — by digit (leading, or standalone
    anywhere) or by describing it in words; None if it's unclear."""
    normalized = text.translate(str.maketrans("１２３", "123"))
    leading = re.match(r"^\s*[（(\[]?\s*([123])\s*[．.、,，）)\]:：-]?", normalized)
    if leading:
        return leading.group(1)

    lowered = normalized.lower()
    for value, keywords in CUSTOMER_TYPE_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return value

    standalone = re.findall(r"(?<!\d)([123])(?!\d)", normalized)
    if len(set(standalone)) == 1:
        return standalone[0]
    return None


def _strip_type_marker(text: str) -> str:
    """The problem description, with a leading '2、' / '(3)' option marker
    removed so the agent's queue doesn't read '2, 我要問年費'."""
    normalized = text.translate(str.maketrans("１２３", "123"))
    return re.sub(r"^\s*[（(\[]?\s*[123]\s*[．.、,，）)\]:：-]?\s*", "", normalized).strip()


def _is_intake_cancel(text: str) -> bool:
    return any(kw in text.lower() for kw in INTAKE_CANCEL_KW)


def handoff_intake_node(state: AgentState) -> dict:
    message = state["user_message"]
    step = state.get("workflow_step", 0)
    data = dict(state.get("workflow_data", {}))
    # A reply of just "2" would language-detect as zh no matter what the
    # customer was speaking, so the flow keeps the language it opened in.
    language = data.get("language") or state["language"]

    if step == 0:
        return {
            "response": INTAKE_PROMPT[language],
            "language": language,
            "workflow_step": 1,
            "workflow_data": {"type": INTAKE_WORKFLOW, "language": language, "attempts": 0},
        }

    if _is_intake_cancel(message):
        return {"response": INTAKE_CANCELLED[language], "language": language,
                "workflow_step": 0, "workflow_data": {}}

    # Both halves accumulate across attempts: answering "2" and then
    # "我的轉帳一直失敗" must not lose the "2" the customer already gave.
    customer_type = _parse_customer_type(message) or data.get("customer_type")
    description = data.get("description") or ""
    replied_description = _strip_type_marker(message)
    if len(replied_description) > len(description):
        description = replied_description
    attempts = data.get("attempts", 0) + 1
    collected = {**data, "type": INTAKE_WORKFLOW, "language": language,
                 "attempts": attempts, "customer_type": customer_type,
                 "description": description}

    type_label = CUSTOMER_TYPE_LABEL[language][customer_type]
    if attempts < MAX_INTAKE_ATTEMPTS and (customer_type is None or len(description) < MIN_DESCRIPTION_LEN):
        reask = (INTAKE_REASK[language] if customer_type is None
                 else INTAKE_REASK_DESCRIPTION[language].format(type_label=type_label))
        return {
            "response": reask,
            "language": language,
            "workflow_step": 1,
            "workflow_data": collected,
        }

    done = (INTAKE_DONE[language].format(type_label=type_label) if customer_type
            else INTAKE_DONE_PARTIAL[language])
    msg = _with_login_reminder(done, language, state.get("user_authenticated", False))
    ticket_id = escalate_to_human(
        session_id=state["session_id"],
        user_id=state.get("user_id"),
        history=state.get("messages", []),
        trigger_message=message,
        response_text=msg,
        category="handoff_intent",
        intake={"type_label": type_label, "description": description or "（未描述）",
                "language": language},
    )
    return {
        "response": msg,
        "language": language,
        "intent": "handoff",          # so the frontend switches to the handoff view
        "handoff_ticket_id": ticket_id,
        "workflow_step": 0,
        "workflow_data": {},
        "log_entries": [{"trigger_reason": "handoff_intent", "intent": "escalation"}],
    }


# ── Small-talk Node ──────────────────────────────────────────────────────────
# Pure greetings / thanks / goodbyes get a friendly canned reply from Mingis:
# no retrieval, no verifier, no ticket, and nothing logged as "unresolved"
# (it isn't a failure, so it must not show up as a knowledge gap either).

SMALLTALK_PHRASES = {
    "greeting": {
        "zh": ["你好", "妳好", "您好", "哈囉", "哈嘍", "嗨", "嗨嗨", "安安", "早安", "午安", "晚安", "你好嗎", "您好嗎"],
        "en": ["hi", "hello", "hey", "hiya", "yo", "hi there", "hello there", "hey there",
               "good morning", "good afternoon", "good evening"],
    },
    "thanks": {
        "zh": ["謝謝", "謝謝你", "謝謝您", "謝啦", "感謝", "感謝你", "感謝您", "多謝", "謝謝囉", "感恩"],
        "en": ["thanks", "thank you", "thank you so much", "thanks a lot", "thx", "ty", "many thanks"],
    },
    "bye": {
        "zh": ["掰掰", "拜拜", "再見", "掰"],
        "en": ["bye", "goodbye", "bye bye", "see you", "see ya"],
    },
}

SMALLTALK_REPLY = {
    "greeting": {
        "zh": "嗨，我是 Mingis 😊 信用卡費用、帳戶服務、轉帳規則都可以問我；登入後還能查詢帳單和消費明細。今天想問什麼呢？",
        "en": "Hi, I'm Mingis 😊 Ask me about card fees, account services or transfer rules — log in and I can also check your bill and transactions. What can I help with today?",
    },
    "thanks": {
        "zh": "不客氣！還有其他問題，隨時找我 😊",
        "en": "You're welcome! Ask me anytime if there's anything else 😊",
    },
    "bye": {
        "zh": "謝謝您，再見！有需要隨時回來找我 👋",
        "en": "Thanks for stopping by — bye! Come back anytime 👋",
    },
}

def _squash(text: str) -> str:
    """lowercase, drop spaces/punctuation/emoji (CJK letters are \\w, so they survive)"""
    return re.sub(r"[\W_]+", "", text.lower())


# squashed phrase -> (kind, language), built once
_SMALLTALK_INDEX = {
    _squash(phrase): (kind, lang)
    for kind, by_lang in SMALLTALK_PHRASES.items()
    for lang, phrases in by_lang.items()
    for phrase in phrases
}


def _match_smalltalk(text: str):
    """(kind, language) if the message is nothing but a greeting / thanks /
    goodbye, else None. Punctuation, emoji and spaces are ignored, and the
    assistant's own name may follow ("Hi Mingis")."""
    core = re.sub(r"mingis$", "", _squash(text))
    return _SMALLTALK_INDEX.get(core) if core else None


def smalltalk_node(state: AgentState) -> dict:
    kind = state.get("smalltalk_kind", "greeting")
    language = state["language"]
    return {"response": SMALLTALK_REPLY[kind][language], "language": language}


# ── Bill-problem Clarify Node ────────────────────────────────────────────────
# "我的帳單金額有問題" tells the agent nothing: which charge? what's wrong
# with it? Sending that straight to the queue means the agent's first
# message is the question the bot could have asked. So the bot asks it
# once, and the customer's answer rides along in the ticket.
#
# Only for a *vague* complaint. As soon as the customer names something
# specific (a charge, an amount, "重複扣款", "沒刷過"…) the normal routing
# takes over — fraud in particular must never wait behind a question.

BILL_CLARIFY_WORKFLOW = "bill_clarify"   # workflow_data["type"] marker — see router

BILL_KW = ["帳單", "账单", "bill", "statement"]
BILL_PROBLEM_KW = ["有問題", "有问题", "不對", "不对", "不正確", "不正确", "錯誤", "错误", "怪怪", "奇怪",
                   "異常", "异常", "不符", "有誤", "有误", "出錯", "疑問", "疑问", "多收", "算錯",
                   "wrong", "incorrect", "issue", "problem", "error", "mistake", "doesn't look right",
                   "does not look right"]
# Anything in this list means the customer already pointed at something
# concrete, or it's a different category (fraud / dispute / refund) that
# has its own handling — either way, don't hold them up with a question.
BILL_SPECIFIC_KW = ["沒刷", "没刷", "盜刷", "盗刷", "被盜", "重複", "重复", "退款", "扣款", "多扣", "分期",
                    "年費", "年费", "利息", "手續費", "手续费", "那一筆", "這一筆", "這筆", "那筆", "一筆", "第一筆",
                    "unauthorized", "fraud", "duplicate", "refund", "charged twice", "double", "installment",
                    "annual fee", "interest", "transaction"]
BILL_VAGUE_MAX_LEN = 30   # a longer message very likely already explains itself


def _is_vague_bill_complaint(text: str) -> bool:
    lowered = text.lower()
    if len(text.strip()) > BILL_VAGUE_MAX_LEN or re.search(r"\d", text):
        return False   # digits = an amount/date/line item was named
    if not any(kw in lowered for kw in BILL_KW):
        return False
    if not any(kw in lowered for kw in BILL_PROBLEM_KW):
        return False
    return not any(kw in lowered for kw in BILL_SPECIFIC_KW)


BILL_CLARIFY_PROMPT = {
    "zh": "請詳細說明帳單內容哪一筆有問題？讓客服人員能立即了解您的問題及需求。（輸入「取消」可結束）",
    "en": "Could you tell us in detail which item on your bill looks wrong? "
          "That way our agent can understand your issue and what you need right away. "
          "(Type \"cancel\" to stop.)",
}

BILL_CLARIFY_REASK = {
    "zh": "不好意思，我還需要多一點資訊。**請說明是帳單上的哪一筆（例如日期、商家或金額）有問題？**",
    "en": "Sorry, I need a bit more to go on. **Which item on the bill (date, merchant or amount) looks wrong?**",
}

BILL_CLARIFY_DONE = {
    "zh": "收到，已將您的說明一併送出，正在為您轉接真人客服，請稍候。",
    "en": "Got it — I've passed your description along and I'm connecting you to a human agent now.",
}

BILL_CLARIFY_CANCELLED = INTAKE_CANCELLED
MIN_BILL_DETAIL_LEN = 3
MAX_BILL_CLARIFY_ATTEMPTS = 2   # same rule as intake: never trap someone who wants a person in a form loop


def bill_clarify_node(state: AgentState) -> dict:
    message = state["user_message"]
    step = state.get("workflow_step", 0)
    data = dict(state.get("workflow_data", {}))
    language = data.get("language") or state["language"]

    if step == 0:
        return {
            "response": BILL_CLARIFY_PROMPT[language],
            "language": language,
            "workflow_step": 1,
            "workflow_data": {"type": BILL_CLARIFY_WORKFLOW, "language": language, "attempts": 0},
        }

    if _is_intake_cancel(message):
        return {"response": BILL_CLARIFY_CANCELLED[language], "language": language,
                "workflow_step": 0, "workflow_data": {}}

    attempts = data.get("attempts", 0) + 1
    detail = message.strip()
    if attempts < MAX_BILL_CLARIFY_ATTEMPTS and len(detail) < MIN_BILL_DETAIL_LEN:
        return {
            "response": BILL_CLARIFY_REASK[language],
            "language": language,
            "workflow_step": 1,
            "workflow_data": {**data, "attempts": attempts},
        }

    msg = _with_login_reminder(BILL_CLARIFY_DONE[language], language, state.get("user_authenticated", False))
    ticket_id = escalate_to_human(
        session_id=state["session_id"],
        user_id=state.get("user_id"),
        history=state.get("messages", []),
        trigger_message=message,
        response_text=msg,
        category="handoff_dispute",
        bill_detail={"detail": detail, "language": language},
    )
    return {
        "response": msg,
        "language": language,
        "intent": "handoff",          # so the frontend switches to the handoff view
        "handoff_ticket_id": ticket_id,
        "workflow_step": 0,
        "workflow_data": {},
        "log_entries": [{"trigger_reason": "handoff_dispute", "intent": "escalation"}],
    }


# ── Handoff Node ─────────────────────────────────────────────────────────────

def handoff_node(state: AgentState) -> dict:
    language = state["language"]
    reason = state.get("handoff_reason", "handoff_intent")
    if reason == "handoff_urgent_fraud":
        msg = URGENT_FRAUD_HANDOFF_MSG[language]
    elif reason == "handoff_sensitive_data":
        msg = SENSITIVE_DATA_HANDOFF_MSG[language]
    else:
        msg = HANDOFF_MSG[language]
    msg = _with_login_reminder(msg, language, state.get("user_authenticated", False))

    ticket_id = escalate_to_human(
        session_id=state["session_id"],
        user_id=state.get("user_id"),
        history=state.get("messages", []),
        trigger_message=state["user_message"],
        response_text=msg,
        category=reason,
    )

    return {
        "response": msg,
        "handoff_ticket_id": ticket_id,
        "log_entries": [{"trigger_reason": reason, "intent": "escalation"}],
    }


# ── FAQ Node ─────────────────────────────────────────────────────────────────

def _retrieval_query(messages: list[dict], message: str) -> str:
    """Retrieval used to embed only the current turn, so a pronoun-only
    follow-up ("那年費呢?") with no topic word of its own retrieved
    ambiguously — see docs/evaluation.md's "已知落差" for the measured
    gap (0.475-0.620 vs. HIGH_CONFIDENCE_THRESHOLD's 0.60) and how
    prepending the prior user turn closes it (~0.80 on the same cases).
    Only the USER's own last turn is folded in, not the assistant's
    reply — that's the topic the customer actually cares about, and
    stays short enough not to dilute the current turn's own keywords."""
    prior_user_turns = [m["content"] for m in messages if m.get("role") == "user"]
    if not prior_user_turns:
        return message
    return f"{prior_user_turns[-1]} {message}"


def make_qa_node(client, retrievers: dict, kb: dict, model: str, max_tokens: int):
    def qa_node(state: AgentState) -> dict:
        language = state["language"]
        message = state["user_message"]
        user_id = state.get("user_id")

        log_entries: list[dict] = []
        neg_fb = is_negative_feedback(message)
        if neg_fb:
            log_entries.append({"trigger_reason": "negative_feedback", "intent": "feedback"})

        retriever = retrievers.get(language)
        rag_sources: list[str] = []
        needs_verification = False
        top_score = None
        if retriever and retriever.is_ready:
            rag_chunks = retriever.retrieve(_retrieval_query(state.get("messages", []), message))
            rag_sources = list(dict.fromkeys(c["source"] for c in rag_chunks))
            top_score = rag_chunks[0]["score"] if rag_chunks else 0.0
            needs_verification = VERIFY_ALWAYS or top_score < HIGH_CONFIDENCE_THRESHOLD
            rag_context = retriever.format_context(rag_chunks)
        else:
            rag_context = kb[language]

        # Every retrieval is checked unless VERIFY_ALWAYS is off (then only the
        # ambiguous ones are) — see VERIFY_ALWAYS above. Applies regardless of login
        # status: account context only helps account-shaped questions,
        # and this Node only ever handles intent="faq" (account-shaped
        # questions are routed to Account Node instead), so a logged-in
        # user gets no extra protection from a general-knowledge gap.
        if needs_verification:
            sufficient, reason = verify_chunks_sufficient(client, model, message, rag_context)
            if not sufficient:
                log_entries.append({
                    "trigger_reason": "verifier_unresolved",
                    "intent": "faq",
                    "similarity_score": top_score,
                })
                msg = _with_login_reminder(
                    VERIFIER_ESCALATION_MSG[language], language, state.get("user_authenticated", False),
                )
                ticket_id = escalate_to_human(
                    session_id=state["session_id"],
                    user_id=user_id,
                    history=state.get("messages", []),
                    trigger_message=message,
                    response_text=msg,
                    category="verifier_unresolved",
                )
                return {
                    "response": msg,
                    "intent": "handoff",  # so the frontend's handoff banner shows too
                    "handoff_ticket_id": ticket_id,
                    "is_negative_feedback": neg_fb,
                    "rag_sources": rag_sources,
                    "log_entries": log_entries,
                }

        system_prompt = build_system_prompt(language, user_id, rag_context=rag_context)
        messages: list[dict[str, Any]] = list(state.get("messages", []))
        messages.append({"role": "user", "content": message})

        # Defer the actual generation call — see AgentState.pending_stream.
        # /chat finishes this blocking (identical behavior/latency to
        # before); /chat/stream finishes it with client.messages.stream()
        # so the user sees tokens as they're generated instead of waiting
        # for the whole answer (see docs/design_journal.md Sprint 13).
        #
        # Follow-up shortcuts extend from the sources this answer actually
        # retrieved, so they stay on the customer's current topic. Computed
        # here (before generation) so they can ride along in /chat/stream's
        # headers, which are sent before the first token.
        return {
            "pending_stream": {"system": system_prompt, "messages": messages, "max_tokens": max_tokens},
            "is_negative_feedback": neg_fb,
            "rag_sources": rag_sources,
            "suggestions": suggest_followups(retriever, language, rag_sources, message),
            "log_entries": log_entries,
        }

    return qa_node


# ── Account Node ─────────────────────────────────────────────────────────────

def make_account_node(client, retrievers: dict, model: str, max_tokens: int):
    def account_node(state: AgentState) -> dict:
        language = state["language"]
        user_id = state.get("user_id")

        if not user_id:
            return {"response": NOT_LOGGED_IN_ACCOUNT[language]}

        system_prompt = build_account_system_prompt(language)
        messages: list[dict[str, Any]] = list(state.get("messages", []))
        messages.append({"role": "user", "content": state["user_message"]})

        for _ in range(MAX_TOOL_ITERATIONS):
            result = traced_create(
                client, "account_tool_loop",
                model=model, max_tokens=max_tokens, system=system_prompt,
                messages=messages, tools=ACCOUNT_TOOLS,
            )
            if result.stop_reason != "tool_use":
                text = "".join(b.text for b in result.content if b.type == "text")
                # No retrieved sources to extend from here (this Node answers
                # from the user's own account data), so the follow-ups are the
                # natural next questions after a balance/bill answer.
                return {"response": text,
                        "suggestions": account_followups(
                            retrievers.get(language), language, state["user_message"])}

            messages.append({"role": "assistant", "content": result.content})
            tool_results = []
            for block in result.content:
                if block.type == "tool_use":
                    output = execute_tool(block.name, block.input, user_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, ensure_ascii=False),
                    })
            messages.append({"role": "user", "content": tool_results})

        return {
            "response": TOOL_LOOP_FALLBACK[language],
            "log_entries": [{"trigger_reason": "tool_loop_exceeded", "intent": "account"}],
        }

    return account_node


# ── Logger Node ──────────────────────────────────────────────────────────────

def logger_node(state: AgentState) -> dict:
    for entry in state.get("log_entries", []):
        log_unresolved(
            session_id=state["session_id"],
            user_query=state["user_message"],
            language=state["language"],
            intent=entry.get("intent", "unknown"),
            trigger_reason=entry["trigger_reason"],
            similarity_score=entry.get("similarity_score"),
        )
    return {}
