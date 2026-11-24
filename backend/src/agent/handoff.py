"""
Escalation-to-human bookkeeping — Sprint 15.

Every path that hands a conversation off to a human (handoff_node's
business rules from Sprint 14, and qa_node's verifier-triggered
escalation) needs the SAME two side effects: create a ticket an agent
can pick up, and seed a persisted conversation thread with everything
the agent needs to have context — the prior turns plus the message
that triggered escalation plus what the bot told the customer. Shared
here so neither call site duplicates it.
"""

from ..database import add_handoff_message, create_ticket

CATEGORY_LABEL = {
    "handoff_intent": "使用者主動要求真人客服",
    "handoff_urgent_fraud": "緊急：疑似盜刷/詐騙",
    "handoff_dispute": "帳務爭議/退款",
    "handoff_approval_required": "需人工核准（減免/貸款/額度）",
    "handoff_sensitive_data": "敏感資料變更",
    "handoff_emotional_distress": "情緒激動",
    "handoff_cross_account": "跨帳戶/跨產品",
    "fallback_threshold": "連續未解決",
    "verifier_unresolved": "AI 判定知識庫不足",
}


BILL_DETAIL_SUMMARY = {
    "zh": "📋 **帳單問題說明**\n- 客戶描述：{detail}",
    "en": "📋 **Bill issue details**\n- Customer's description: {detail}",
}

INTAKE_SUMMARY = {
    "zh": "📋 **轉接前資料收集**\n- 客戶類別：{type_label}\n- 問題描述：{description}",
    "en": "📋 **Pre-transfer intake**\n- Customer type: {type_label}\n- Issue: {description}",
}


def escalate_to_human(
    session_id: str,
    user_id: str | None,
    history: list[dict],
    trigger_message: str,
    response_text: str,
    category: str,
    intake: dict | None = None,
    bill_detail: dict | None = None,
) -> str:
    """`intake` (Sprint 19) carries what the pre-handoff intake collected
    from a guest — {type_label, description, language}. It goes into the
    ticket description so the console's queue line is triageable at a
    glance, and into the thread as a structured block so the agent reads
    it without scrolling through the AI turns above it."""
    priority = "high" if category == "handoff_urgent_fraud" else "normal"
    description = f"轉真人客服：{CATEGORY_LABEL.get(category, category)}"
    if intake:
        description += f"｜{intake['type_label']}｜{intake['description'][:40]}"
    if bill_detail:
        # `bill_detail` = {detail, language}: what the customer said when
        # asked WHICH item on the bill is wrong, so the queue line and the
        # thread both say so without the agent scrolling back.
        description += f"｜帳單問題｜{bill_detail['detail'][:40]}"
    ticket = create_ticket(
        type="handoff",
        user_id=user_id,
        description=description,
        priority=priority,
    )
    ticket_id = ticket["ticket_id"]

    for msg in history:
        add_handoff_message(ticket_id, session_id, msg["role"], msg["content"])
    add_handoff_message(ticket_id, session_id, "user", trigger_message)
    if bill_detail:
        add_handoff_message(
            ticket_id, session_id, "assistant",
            BILL_DETAIL_SUMMARY[bill_detail.get("language", "zh")].format(detail=bill_detail["detail"]),
        )
    if intake:
        add_handoff_message(
            ticket_id, session_id, "assistant",
            INTAKE_SUMMARY[intake.get("language", "zh")].format(
                type_label=intake["type_label"], description=intake["description"],
            ),
        )
    add_handoff_message(ticket_id, session_id, "assistant", response_text)

    return ticket_id
