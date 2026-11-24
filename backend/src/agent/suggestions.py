"""
Quick-reply suggestions — Sprint 20.

Two jobs:
  1. Starter shortcuts on the welcome screen, so a customer who doesn't
     know what to type has something to click.
  2. Follow-up shortcuts after each answer, extended from the topic the
     customer just asked about.

**A suggestion is only shown if this bot can actually answer it.** That
sounds obvious, but it's the whole design constraint: a shortcut the bot
answers with "很抱歉我沒能解決您的問題" is worse than no shortcut at all,
because the dead end was the bot's own suggestion.

Two things enforce it:

  - The pool is curated per knowledge-base topic (TOPIC_FOLLOWUPS below),
    not generated. An LLM asked to "suggest related questions" writes
    plausible questions the KB has no content for; the first measurement
    of this feature found 4 of 5 questions lifted verbatim out of the
    KB's own FAQ sections still escalated to a human, so even "it's in
    the knowledge base" is not sufficient evidence on its own.
  - Every candidate is checked against the LIVE index before being shown
    (`_answerable`) and dropped unless it clears the same 0.60 confidence
    the FAQ Node uses to skip its grounding verifier. This is one
    embedding encode per candidate, cached per index build — no LLM call
    on a path where the customer is already waiting for their reply.

The filter is what keeps this honest as the KB changes: add knowledge and
more shortcuts light up; archive knowledge and the shortcuts that relied
on it disappear on the next reindex instead of turning into dead ends.

See docs/ADR.md ADR-015.
"""

MAX_SUGGESTIONS = 3

# Mirrors nodes.HIGH_CONFIDENCE_THRESHOLD (imported the other way round —
# nodes imports this module). Above this the FAQ Node answers directly;
# below it the answer goes through the verifier and may well escalate,
# which is exactly what a shortcut must never do.
HIGH_CONFIDENCE_THRESHOLD = 0.60

# Follow-ups per knowledge-base source file. Written to match how a
# customer would actually phrase the question, then measured against the
# index — anything that didn't retrieve its own topic confidently was
# rewritten or dropped rather than shipped hopefully.
#
# Phrasing note (Sprint 21, found by live verification): a question about
# MY limit — "What is my daily transfer limit?", "How much can I borrow?"
# — classifies as `account`, not `faq`, so a guest clicking it is told to
# log in. The impersonal phrasing asks the same thing and routes to the
# knowledge base. Retrieval score alone doesn't catch this; only running
# the question through the real graph does.
TOPIC_FOLLOWUPS = {
    "zh": {
        "account_services.md": [
            "開戶需要準備什麼證件？",
            "帳戶管理費怎麼算？",
            "活存和定存的利率差多少？",
            "要怎麼線上開戶？",
        ],
        "atm_services.md": [
            "ATM 每天最多可以領多少錢？",
            "ATM 單筆提款上限是多少？",
            "ATM 可以做哪些交易？",
        ],
        "credit_card_benefits.md": [
            "信用卡現金回饋怎麼計算？",
            "白金卡和無限卡有什麼旅遊優惠？",
            "有哪些通路有加碼優惠？",
        ],
        "credit_card_fees.md": [
            "信用卡年費多少？如何免年費？",
            "國外刷卡的手續費怎麼算？",
            "預借現金的手續費和利息是多少？",
            "帳單分期要收多少手續費？",
            "循環利息怎麼算？",
        ],
        "digital_banking.md": [
            "網路銀行有哪些功能？",
            "網路銀行要怎麼開通？",
            "網路銀行怎麼登入？",
        ],
        "foreign_currency_exchange.md": [
            "要怎麼預約換外幣？",
            "臨櫃換外幣要帶什麼證件？",
            "換外幣有金額上限嗎？",
        ],
        "general_services.md": [
            "客服電話幾號？服務時間到幾點？",
            "分行營業時間是幾點到幾點？",
        ],
        "loan_overview.md": [
            "房貸利率大概多少？",
            "房貸申請要準備哪些文件？",
            "申請信貸需要什麼條件？",
            "信貸額度最高可以借多少？",
            "可以提前還款嗎？會不會有違約金？",
        ],
        "transfer_rules.md": [
            "國際匯款要怎麼辦理？",
            "轉帳多久會到帳？",
        ],
    },
    "en": {
        "account_services.md": [
            "What documents do I need to open an account?",
            "What are the savings and time deposit rates?",
            "Is there an account maintenance fee?",
            "How do I open an account online?",
            "Can I break a time deposit early?",
        ],
        "atm_services.md": [
            "What is the daily ATM withdrawal limit?",
            "How much is the interbank ATM fee?",
            "What transactions can I do at an ATM?",
        ],
        "credit_card_benefits.md": [
            "How is credit card cashback calculated?",
            "What travel benefits do platinum cards have?",
            "What can I redeem reward points for?",
        ],
        "credit_card_fees.md": [
            "How much is the credit card annual fee?",
            "How much is the foreign transaction fee?",
            "What are the cash advance fees?",
            "What is the installment plan fee?",
        ],
        "digital_banking.md": [
            "How do I reset my online banking password?",
            "What can I do with online banking?",
            "How do I register for online banking?",
        ],
        "foreign_currency_exchange.md": [
            "How much is the currency exchange fee?",
            "Which currencies can I exchange?",
            "Is there a limit on currency exchange?",
            "What do I need to bring to exchange currency?",
        ],
        "general_services.md": [],
        "loan_overview.md": [
            "What are the mortgage interest rates?",
            "What documents does a mortgage application need?",
            "What are the requirements for a personal loan?",
        ],
        "transfer_rules.md": [
            "How do I make an international wire transfer?",
            "What is the daily transfer limit?",
        ],
    },
}

# Welcome-screen starters. Deliberately spread across topics (card / ATM /
# digital / deposit / FX) rather than three variations of one thing — this
# is the customer's first impression of what the assistant covers.
FAQ_STARTERS = {
    "zh": [
        "信用卡年費多少？如何免年費？",
        "ATM 每天最多可以領多少錢？",
        "網路銀行有哪些功能？",
        "信用卡現金回饋怎麼計算？",
        "開戶需要準備什麼證件？",
    ],
    "en": [
        "How much is the credit card annual fee?",
        "What is the daily ATM withdrawal limit?",
        "What can I do with online banking?",
        "How is credit card cashback calculated?",
        "What documents do I need to open an account?",
        "How do I reset my online banking password?",
    ],
}

# These route to the Account Node, which answers from the customer's own
# data rather than the knowledge base — so they're exempt from the
# retrieval check below (there's nothing to retrieve) and are only ever
# offered to someone already logged in.
ACCOUNT_SUGGESTIONS = {
    "zh": [
        "我這個月的帳單金額是多少？",
        "我的帳戶餘額還有多少？",
        "幫我看最近的消費明細",
    ],
    "en": [
        "How much is my bill this month?",
        "What's my account balance?",
        "Show me my recent transactions",
    ],
}

# 2026-11 trim (ADR-020): FAQ answers are now grounding-checked every time, so a shortcut must also
# pass the verifier or it becomes a dead end. Seven curated follow-ups did not — and for a good reason:
# retrieval put the wrong article first (e.g. "國內轉帳的手續費怎麼算？" returned the INTERNATIONAL wire
# fee), so they would have been answered from the wrong text. They were removed here; the retrieval
# weakness behind them is logged in docs/evaluation.md. tests/test_shortcuts_verified.py keeps every
# remaining shortcut honest.

# Offered AFTER an account answer: the other account questions, minus
# whatever was just asked — being told your balance and then offered
# "what's my balance?" is the one thing this feature must not do.
#
# Measured, then trimmed: "我的信用卡額度還剩多少？" was dropped because the
# Account Node has no credit-limit tool (it answers with the bill and an
# apology), and "繳款截止日是什麼時候？" because on its own it classifies as
# FAQ, not account, and escalates. Both read as perfectly sensible
# follow-ups — which is exactly why the list is measured rather than
# written from intuition.
ACCOUNT_FOLLOWUPS = ACCOUNT_SUGGESTIONS

# (language, question) -> top-1 retrieval score. The index only changes on
# reindex, and _rebuild_and_swap_index() clears this, so a candidate is
# encoded at most once per index build.
_score_cache: dict[tuple[str, str], float] = {}


def clear_cache() -> None:
    """Called after a reindex — scores computed against the old index must
    not decide what's answerable against the new one."""
    _score_cache.clear()


def _answerable(retriever, language: str, question: str) -> bool:
    """Would the FAQ Node answer this confidently, or fall through to the
    verifier (and possibly a handoff)? Only the former may be offered."""
    if retriever is None or not getattr(retriever, "is_ready", False):
        return False
    key = (language, question)
    if key not in _score_cache:
        chunks = retriever.retrieve(question, top_k=1)
        _score_cache[key] = chunks[0]["score"] if chunks else 0.0
    return _score_cache[key] >= HIGH_CONFIDENCE_THRESHOLD


def _first_answerable(retriever, language: str, candidates, limit: int, exclude=()) -> list[str]:
    picked: list[str] = []
    for question in candidates:
        if question in picked or question in exclude:
            continue
        if _answerable(retriever, language, question):
            picked.append(question)
            if len(picked) >= limit:
                break
    return picked


def _too_similar(candidate: str, asked: str, threshold: float = 0.6) -> bool:
    """Drops a suggestion that's basically what the customer just asked —
    offering it back as "you might also ask" reads like the bot wasn't
    listening. Character/word overlap rather than embeddings: it's a
    cosmetic check, not a retrieval decision, and doesn't deserve a
    second encode on the response path.

    Jaccard (over the union), not overlap-over-candidate: Chinese
    questions share so many function characters (我/的/是/多少) that a
    one-sided ratio called "我的帳戶餘額還有多少？" a duplicate of "我這個月帳單
    多少" and hid a perfectly good follow-up.
    """
    import re
    def tokens(text: str) -> set[str]:
        lowered = text.lower()
        return ({w for w in re.findall(r"[a-z0-9]+", lowered) if len(w) > 2}
                | set(re.findall(r"[一-鿿]", lowered)))
    a, b = tokens(candidate), tokens(asked)
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= threshold


def suggest_followups(
    retriever,
    language: str,
    sources: list[str],
    user_message: str,
    limit: int = MAX_SUGGESTIONS,
) -> list[str]:
    """Follow-ups for a FAQ answer, extended from the sources that were
    actually retrieved for it — i.e. whatever topic the customer is in.

    Sources that aren't knowledge-base filenames are kb_entries added
    through the maintenance UI (their source is the entry title); those
    have no curated follow-ups, so a conversation grounded only in those
    falls back to the popular starters — a working shortcut on another
    topic beats an empty row or a broken one.
    """
    by_source = TOPIC_FOLLOWUPS.get(language, {})
    candidates = [
        q
        for source in sources                       # retrieval order = relevance order
        for q in by_source.get(source, [])
        if not _too_similar(q, user_message)
    ]
    picked = _first_answerable(retriever, language, candidates, limit)

    if not picked:
        fallback = [q for q in FAQ_STARTERS.get(language, []) if not _too_similar(q, user_message)]
        picked = _first_answerable(retriever, language, fallback, limit)
    return picked


def starters(retriever, language: str, authenticated: bool, limit: int = MAX_SUGGESTIONS) -> list[str]:
    """Welcome-screen shortcuts. A logged-in customer leads with their own
    account — that's what they logged in for — and fills the rest with
    popular FAQ topics."""
    account = ACCOUNT_SUGGESTIONS.get(language, [])[:2] if authenticated else []
    faq = _first_answerable(retriever, language, FAQ_STARTERS.get(language, []), limit - len(account))
    return (account + faq)[:limit]


def account_followups(
    retriever,
    language: str,
    user_message: str = "",
    limit: int = MAX_SUGGESTIONS,
) -> list[str]:
    """After an Account Node answer — the natural next questions once
    you've just been told a balance or a bill. The account questions need
    no retrieval check (they never touch the knowledge base), but there
    are only three of them, so the row is topped up with verified FAQ
    topics rather than left short."""
    pool = ACCOUNT_FOLLOWUPS.get(language, ACCOUNT_FOLLOWUPS["zh"])
    picked = [q for q in pool if not _too_similar(q, user_message)][:limit]
    if len(picked) < limit:
        picked += _first_answerable(
            retriever, language, FAQ_STARTERS.get(language, []), limit - len(picked), exclude=picked,
        )
    return picked
