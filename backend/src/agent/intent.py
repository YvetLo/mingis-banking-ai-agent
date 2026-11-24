"""
Router Node intent classification — Sprint 9, Sprint 14 (handoff trigger rules)

Sprint 1-8 routed on keyword matching (backend/src/nlp.py). This
replaces that with the real LLM classifier docs/agent_design.md §3.1
specified from the start ("Intent Classification（LLM 分類）") —
keyword matching was always a placeholder for this.

`tool_choice` forces Claude to call `classify_intent`, so the result is
always one of the four valid categories — no free-text parsing, no
"model didn't follow instructions" failure mode to handle.

Sprint 14 added `handoff_category` — business rules for WHY a message
should escalate (fraud/security, disputes, approval-required requests,
sensitive data changes, emotional distress, cross-account complexity),
on top of the original "user explicitly asked for a human" case. Two
related triggers are deliberately NOT here: a lost/stolen card stays
`card_loss` (existing workflow, not a handoff), and "same question
unresolved 2-3 times" is the frontend-tracked `fallback_count` /
`force_handoff` mechanism (router_node checks it before ever calling
this classifier) — see docs/design_journal.md Sprint 14 entry.
"""

from ..tracing import traced_create

INTENT_CLASSIFIER_TOOL = {
    "name": "classify_intent",
    "description": "Classify a bank customer service message into exactly one intent category, plus a handoff reason when applicable.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["faq", "account", "card_loss", "handoff"],
                "description": (
                    "faq: general informational questions about bank products, services, rates, or rules "
                    "that can be answered from a knowledge base WITHOUT needing the user's own account data "
                    "or any human approval (e.g. what a fee/rate IS, how loan terms work, digital banking "
                    "features, branch hours). "
                    "account: questions about the user's OWN account — balance, bill, transactions. If the user says a "
                    "charge is NOT theirs or they do not recognize it, it is NOT account — use handoff. "
                    "card_loss: user wants to report a lost/stolen card so it can be blocked. "
                    "handoff: see handoff_category below for the specific rules — do NOT use handoff just "
                    "because the user sounds mildly annoyed or says a previous answer was wrong/unhelpful "
                    "(e.g. '你搞錯了，這不是我要的答案', 'that's not right', 'not helpful'); those are "
                    "frustrated follow-ups on the SAME topic — classify by the underlying topic (faq or "
                    "account), not as handoff."
                ),
            },
            "handoff_category": {
                "type": "string",
                "enum": [
                    "explicit_request",
                    "fraud_or_security",
                    "dispute_or_refund",
                    "approval_required",
                    "sensitive_data_change",
                    "emotional_distress",
                    "cross_account_complexity",
                ],
                "description": (
                    "REQUIRED when intent is 'handoff', omit otherwise. Pick the ONE rule that applies:\n"
                    "explicit_request — user directly asks for a human/live agent, or explicitly wants to "
                    "file a formal complaint (e.g. '我要真人', '我要投訴', 'speak to an agent').\n"
                    "fraud_or_security — unauthorized transactions, card fraud, scams, or suspicious login "
                    "activity (e.g. '我的卡有一筆我沒刷過的交易', 'someone logged into my account'). ANY charge the "
                    "user says they did not make, did not spend, or do not recognize counts as fraud_or_security "
                    "even when worded softly or as a billing question (e.g. '帳單裡有一筆不明款項，我未消費過此筆金額', "
                    "'我完全不認識這筆消費', 'I don't recognize this transaction on my bill') — do NOT classify those "
                    "as dispute_or_refund or account. The reverse also holds: a purchase the user DID make that was "
                    "charged twice, charged the wrong amount, or never refunded (e.g. '商家對我扣了兩次款') is "
                    "dispute_or_refund, NOT fraud. This is "
                    "NOT the same as reporting your own card lost/stolen (that's card_loss) — this is about "
                    "a transaction or access the user did NOT authorize.\n"
                    "dispute_or_refund — account/billing disputes: a refund that never arrived, a duplicate "
                    "charge, a wrong amount charged (e.g. '這筆退款一直沒收到', '我被重複扣款了'). Distinct from "
                    "'account' intent, which is just looking up your own current balance/bill/transactions, "
                    "not disputing one. Also distinct from 'faq': asking WHY a refund amount differs from the "
                    "original charge (exchange-rate difference on an overseas purchase) or whether a fee is "
                    "refundable is an explanation question — classify it as faq (e.g. '海外網站退貨後退款的台幣"
                    "比原本少，手續費也沒退，為什麼？'). Only use dispute_or_refund when the user says the refund "
                    "is missing, duplicated or wrong and wants it corrected or investigated.\n"
                    "approval_required — requests that need human discretion or authority to approve: fee "
                    "waiver requests, exception requests, loan applications, credit limit increase requests, "
                    "or applying for special terms (e.g. '可以幫我減免年費嗎', '我要申請貸款', '我要調高額度'). "
                    "Distinct from 'faq' intent, which is just asking what a fee/rate/loan term IS, not "
                    "requesting an exception or approval for it.\n"
                    "sensitive_data_change — user wants to change highly sensitive account data or security "
                    "settings (e.g. change registered phone number, change password, disable/change 2FA).\n"
                    "emotional_distress — the user is clearly angry, using abusive/hostile language, or "
                    "expresses extreme urgency/distress — NOT the same as merely saying an answer was wrong "
                    "or unhelpful (that stays faq/account). This is for genuine hostility or crisis language "
                    "(e.g. cursing, 'this is ridiculous, fix it NOW', threats), not ordinary dissatisfaction.\n"
                    "cross_account_complexity — the question spans multiple accounts, multiple people, "
                    "multiple products, or clearly needs more than one department (e.g. asking about a joint "
                    "issue across a credit card AND a loan at once, or acting on someone else's account)."
                ),
            },
        },
        "required": ["intent"],
    },
}

CLASSIFIER_SYSTEM_PROMPT = """\
You are an intent classifier for a bank customer service chatbot.
Read the user's message and call classify_intent with exactly one category.
Always call the tool — never respond with plain text.
You see only this one message, no prior conversation — if it's a short
reaction with no clear topic of its own (e.g. "that's wrong", "not
helpful"), classify it as faq rather than guessing account, card_loss,
or handoff.
When intent is "handoff", you MUST also set handoff_category to the one
rule that applies — see its enum description for the exact distinctions
(especially: informational questions stay faq/account even on topics
like fees or loans; only actual approval/exception/dispute requests on
those same topics become handoff)."""


def classify_intent(client, model: str, message: str) -> tuple[str, str | None]:
    result = traced_create(
        client, "classify_intent",
        model=model,
        max_tokens=100,
        temperature=0,   # routing must be repeatable: the same sentence was flipping between categories
        system=CLASSIFIER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
        tools=[INTENT_CLASSIFIER_TOOL],
        tool_choice={"type": "tool", "name": "classify_intent"},
    )
    for block in result.content:
        if block.type == "tool_use":
            return block.input["intent"], block.input.get("handoff_category")
    return "faq", None  # unreachable while tool_choice forces the call; safe default if it ever isn't
