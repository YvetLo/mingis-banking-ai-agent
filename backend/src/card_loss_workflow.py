"""
Credit card loss workflow — 4-step state machine.
Handles identity verification, card selection, confirmation, and execution.
"""

import re
from typing import Any

from .database import create_ticket
from .mock_api.mock_data import block_card, get_user_by_id, verify_identity

# ── Helpers ───────────────────────────────────────────────────────────────────

# Digit lookarounds, not \b: Python's \b treats CJK characters as word
# characters, so "後四碼是5678" or "第2張" never matched with \b.
def _4digits(text: str) -> str | None:
    m = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    return m.group(1) if m else None

def _is_cancel(text: str) -> bool:
    return any(w in text.lower() for w in ["取消", "算了", "不要了", "cancel", "stop", "quit"])

# Punctuation/quotes a user may wrap the phrase in; stripped before matching.
_EDGE_CHARS = "，。！？、,.!?\"'“”‘’「」『』()（） \t　"

# Blocking a card is irreversible here — there is no unblock_card() by
# design (see agent/nodes.py's CANNOT_RESTORE_MSG), so this gate is
# deliberately strict in two ways.
#
# 1. It matches the WHOLE message, not a substring. The previous version
#    returned True for any text containing "好"/"是"/"對"/"確認", so
#    "好像不是這張" (hesitating) and "我不確認" (refusing) both blocked
#    the very card the user was questioning.
# 2. It requires the full phrase rather than a bare "好"/"ok", so the
#    confirming turn can't be an incidental agreement carried over from
#    the previous message. docs/architecture.md §6 specifies this.
#
# The step-2 and step-3 prompts quote these phrases verbatim — keep them
# in sync if this set changes.
_CONFIRM_PHRASES = {
    "確認掛失", "確定掛失",
    "confirm block", "confirm blocking", "confirm the block",
}


def _is_confirm(text: str) -> bool:
    return text.strip().strip(_EDGE_CHARS).strip().lower() in _CONFIRM_PHRASES

def _match_card(text: str, cards: list[dict]) -> dict | None:
    text_lower = text.lower()
    # By number
    m = re.search(r"(?<!\d)([1-9])(?!\d)", text_lower)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(cards):
            return cards[idx]
    # By last4
    m = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    if m:
        for c in cards:
            if c["last4"] == m.group(1):
                return c
    # By type keyword
    kw_map = [("白金", "白金"), ("platinum", "Platinum"), ("無限", "無限"),
              ("infinite", "Infinite"), ("金卡", "金"), ("gold", "Gold"),
              ("一般", "一般"), ("standard", "Standard")]
    for kw, card_kw in kw_map:
        if kw in text_lower:
            for c in cards:
                if card_kw.lower() in c["type"].lower():
                    return c
    return None

def _fmt_cards(cards: list[dict], language: str) -> str:
    if language == "zh":
        return "\n".join(f"{i+1}. {c['type']}（末碼 {c['last4']}）" for i, c in enumerate(cards))
    return "\n".join(f"{i+1}. {c['type']} (last 4: {c['last4']})" for i, c in enumerate(cards))

# ── Side questions mid-flow ───────────────────────────────────────────────────
#
# A customer at step 2 who asks "我這個月帳單多少" used to get "沒找到符合的
# 卡片" back — the question was misread as a card choice and ignored. The
# Router now asks is_step_input() first: only a message the current step
# can actually consume stays in the workflow; anything else is classified
# and answered as a normal turn, with the workflow state left untouched
# and resume_prompt() appended so the customer finds their way back.

# Words that, on their own, add nothing beyond "cancel" — "取消掛失" or
# "算了吧" is still a pure cancel; "算了先查帳單" carries a new question.
_CANCEL_FILLER = ["取消", "算了", "不要了", "掛失", "流程", "了", "吧", "啦", "我",
                  "cancel", "stop", "quit", "please", "the", "block", "process", "it"]


def _is_pure_cancel(text: str) -> bool:
    if not _is_cancel(text):
        return False
    rest = text.lower()
    for w in _CANCEL_FILLER:
        rest = rest.replace(w, "")
    return len(rest.strip(_EDGE_CHARS).replace(" ", "")) <= 2


def is_step_input(message: str, workflow: dict[str, Any]) -> bool:
    """True if the current step can consume this message (an answer to
    the question it just asked, or a plain cancel). False means it's a
    side question for the Router to classify — the workflow is kept."""
    if _is_pure_cancel(message):
        return True
    step = workflow.get("step", 0)
    if step == 1:
        return _4digits(message) is not None
    if step == 2:
        return _match_card(message, workflow.get("data", {}).get("cards", [])) is not None
    if step == 3:
        return _is_confirm(message)
    return True


def resume_prompt(workflow: dict[str, Any], language: str) -> str:
    """The pointer back to the paused step, appended after a side answer.
    Blocking a lost card is urgent, so it's on every such reply."""
    step = workflow.get("step", 0)
    data = workflow.get("data", {})
    zh = language == "zh"
    head = "🔒 **掛失還沒完成**" if zh else "🔒 **Your card isn't blocked yet**"
    if step == 1:
        body = ("請輸入身分證後四碼繼續，或輸入「取消」結束掛失。" if zh
                else "Enter the last 4 digits of your national ID to continue, or type \"cancel\" to stop.")
    elif step == 2:
        cards = _fmt_cards(data.get("cards", []), language)
        body = (f"請選擇要掛失的卡片：\n{cards}\n\n或輸入「取消」結束掛失。" if zh
                else f"Choose the card to block:\n{cards}\n\nor type \"cancel\" to stop.")
    elif step == 3:
        c = data.get("selected_card", {})
        body = (f"要掛失 {c.get('type', '')}（末碼 {c.get('last4', '')}）嗎？請輸入「**確認掛失**」執行，或「**取消**」結束。" if zh
                else f"Block {c.get('type', '')} (last 4: {c.get('last4', '')})? Type **\"confirm block\"** to proceed or **\"cancel\"** to stop.")
    else:
        return ""
    return f"\n\n---\n{head}\n\n{body}"

# ── Workflow Entry Point ───────────────────────────────────────────────────────

def handle_step(
    message: str,
    workflow: dict[str, Any],
    user_id: str,
    language: str,
) -> tuple[str, dict[str, Any]]:
    """
    Process one workflow step.
    Returns: (response_text, updated_workflow_state)
    """
    step = workflow.get("step", 0)
    data = workflow.get("data", {})

    # Cancel at any step
    if _is_cancel(message):
        msg = ("好的，已取消掛失流程。有需要隨時告訴我！" if language == "zh"
               else "Card loss process cancelled. Let me know if you need help!")
        return msg, {"step": 0, "data": {}}

    # ── Step 1: Waiting for id_last4 ──────────────────────────────────────────
    if step == 1:
        id_last4 = _4digits(message)
        if not id_last4:
            msg = ("麻煩輸入身分證後四碼（4 位數字）喔！"
                   if language == "zh" else "Please enter the last 4 digits of your national ID.")
            return msg, workflow

        attempts = data.get("verify_attempts", 0) + 1
        if not verify_identity(user_id, id_last4):
            if attempts >= 3:
                msg = ("驗證失敗次數過多，請致電 0800-XXX-XXX 由真人客服協助掛失。"
                       if language == "zh" else "Too many failed attempts. Please call 0800-XXX-XXX.")
                return msg, {"step": 0, "data": {}}
            remaining = 3 - attempts
            msg = (f"後四碼不符，再試一次（剩 {remaining} 次機會）。"
                   if language == "zh" else f"Verification failed. Try again ({remaining} attempts left).")
            return msg, {"step": 1, "data": {"verify_attempts": attempts}}

        user = get_user_by_id(user_id)
        active = [c for c in (user["cards"] if user else []) if c["status"] == "active"]
        if not active:
            msg = ("您目前沒有有效的信用卡，無法辦理掛失。如有問題請電 0800-XXX-XXX。"
                   if language == "zh" else "No active cards found. Please call 0800-XXX-XXX.")
            return msg, {"step": 0, "data": {}}

        card_list = _fmt_cards(active, language)
        msg = (f"驗證成功！您有以下信用卡，請問哪張遺失了？\n\n{card_list}\n\n輸入編號或卡片名稱都可以。"
               if language == "zh"
               else f"Identity verified! Which card was lost?\n\n{card_list}\n\nEnter a number or card name.")
        return msg, {"step": 2, "data": {"cards": active}}

    # ── Step 2: Waiting for card selection ────────────────────────────────────
    if step == 2:
        cards = data.get("cards", [])
        selected = _match_card(message, cards)
        if not selected:
            card_list = _fmt_cards(cards, language)
            msg = (f"沒找到符合的卡片，請用編號或末四碼選擇：\n{card_list}"
                   if language == "zh"
                   else f"Couldn't identify the card. Please use the number or last 4 digits:\n{card_list}")
            return msg, workflow

        msg = (f"確認要掛失這張卡嗎？\n\n"
               f"🔒 **{selected['type']}（末碼 {selected['last4']}）**\n\n"
               f"⚠️ 掛失後立即停用，無法繼續消費。\n\n"
               f"請輸入「**確認掛失**」繼續，或「**取消**」結束。"
               if language == "zh"
               else f"Confirm blocking this card?\n\n"
               f"🔒 **{selected['type']} (last 4: {selected['last4']})**\n\n"
               f"⚠️ The card will be disabled immediately.\n\n"
               f"Type **\"confirm block\"** to proceed or **\"cancel\"** to exit.")
        return msg, {"step": 3, "data": {**data, "selected_card": selected}}

    # ── Step 3: Waiting for confirmation ─────────────────────────────────────
    if step == 3:
        if not _is_confirm(message):
            msg = ("請輸入「確認掛失」執行掛失，或「取消」結束。"
                   if language == "zh" else "Type \"confirm block\" to block the card or \"cancel\" to exit.")
            return msg, workflow

        card = data["selected_card"]
        block_result = block_card(user_id, card["card_id"])
        if not block_result.get("success"):
            msg = ("系統無法處理，請撥 0800-XXX-XXX 緊急掛失。"
                   if language == "zh" else "System error. Please call 0800-XXX-XXX immediately.")
            return msg, {"step": 0, "data": {}}

        ticket = create_ticket(
            type="card_loss",
            user_id=user_id,
            card_id=card["card_id"],
            description=f"信用卡掛失：{card['type']}（末碼 {card['last4']}）",
            priority="high",
        )
        blocked_at = block_result["blocked_at"][:19].replace("T", " ")

        msg = (f"✅ 掛失完成！\n\n"
               f"**卡片**：{card['type']}（末碼 {card['last4']}）\n"
               f"**掛失時間**：{blocked_at}\n"
               f"**服務單號**：`{ticket['ticket_id']}`\n\n"
               f"客服將於 1 個工作日內聯繫您辦理補發，如需加急請撥 0800-XXX-XXX。\n\n"
               f"還有其他需要幫忙的嗎？"
               if language == "zh"
               else f"✅ Card successfully blocked!\n\n"
               f"**Card**: {card['type']} (last 4: {card['last4']})\n"
               f"**Blocked at**: {blocked_at}\n"
               f"**Ticket ID**: `{ticket['ticket_id']}`\n\n"
               f"Our team will contact you within 1 business day for card replacement.\n\n"
               f"Is there anything else I can help you with?")
        return msg, {"step": 0, "data": {}}

    return "發生錯誤，請重新嘗試。", {"step": 0, "data": {}}
