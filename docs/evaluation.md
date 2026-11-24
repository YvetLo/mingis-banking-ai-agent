**English** · [繁體中文](evaluation.zh-TW.md)

# Evaluation Framework

Sprint 19: build a repeatable, low-cost, deterministic golden set first, so there is a baseline that can show whether "tuning the RAG / prompt / model this time really made things better". The design deliberately avoids LLM-as-Judge at first: the credibility of the score comes from having a reference answer to compare against, not from another model's subjective rating.

Division of labour with `tests/security/`: the security tests are a hard gate (a hole is a failure, no partial credit); this suite is a quality baseline (a single case may fluctuate, but the aggregate metrics must hold their thresholds). The two deliberately do not share cases. The injection strings are maintained in one place only, `tests/security/test_prompt_injection.py`; the "Safety pass rate" metric here simply cites that suite's pass rate instead of building a second copy.

## golden_cases.jsonl

`tests/eval/golden_cases.jsonl`, one JSON case per line, 30 questions:

| Category | Count | Files |
|---|---|---|
| FAQ (is the retrieved source well-founded) | 10 | `zh_faq_*` / `en_faq_*`, covering 8 of the 9 knowledge-base documents |
| Account / lost card (login, tools, workflow) | 8 | `zh_acct_*` / `en_acct_*` / `zh_cardloss_*` / `en_cardloss_*` |
| Handoff (7 of the 9 business rules that `classify_intent` covers) | 8 | `zh_handoff_*` / `en_handoff_*`: 6 positives (one per category) plus 1 negative (the "you got it wrong" edge case; precision is only meaningful with a real negative) |
| Multi-turn (does a pronoun clause carry over from earlier turns) | 4 | `zh_multi_*` / `en_multi_*` |

Fields (depending on the case type; not every field appears on every line):

```json
{"id": "zh_fraud_001", "category": "handoff", "language": "zh",
 "query": "我的信用卡有一筆不是我刷的消費",
 "expected_intent": "handoff", "expected_handoff_category": "fraud_or_security",
 "should_handoff": true}
```

`category` decides which runner picks the case up. `should_handoff` is present on every line (explicitly `false` even for faq / account / card_loss), so handoff precision and recall have all 26 single-turn cases as the denominator, rather than comparing the 8 handoff cases only with each other.

`multi_turn` uses `"turns": [...]` instead of a single `"query"`; the expected values for the last turn go in `expected_intent` / `expected_sources`.

## Three runners

| File | How it tests | Cost |
|---|---|---|
| `test_intent_regression.py` | Calls `classify_intent()` directly (the same function as `tests/test_router_intent.py`), without running the FAQ or Account node | One classification LLM call per case; each case is classified once (cached), and the per-case and aggregate tests share the result |
| `test_retrieval_regression.py` | Calls `RAGRetriever.retrieve()` directly, never touching the LLM | Free and fastest |
| `test_conversation_regression.py` | Runs the whole `/chat` path, sending `turns` in order, passing `history` / `workflow` along like the real frontend | One full generation per turn; the 4 cases are the most expensive |

How to run:
```bash
pytest tests/eval/                               # everything
pytest tests/eval/test_retrieval_regression.py   # retrieval only (fastest, free)
```

## The four v1 metrics (2026-09-01 baseline)

| Metric | Result | How it is computed |
|---|---|---|
| Intent accuracy | **100%** (26/26) | `test_aggregate_intent_accuracy_meets_threshold`, threshold 90% |
| Handoff precision / recall | **100% / 100%** | `test_aggregate_handoff_precision_recall_meet_threshold`, 85% each |
| Retrieval hit rate (Top-5) | **100%** (14/14) | `test_aggregate_retrieval_hit_rate_meets_threshold`, threshold 90% |
| Safety pass rate | **100%** (27/27, cited from `tests/security/`) | Pass rate of `pytest tests/security/ -q` |

All four are above their thresholds, so this baseline can be used to check whether future prompt / RAG / model changes really made things better or worse. Below a threshold, CI should go red, rather than someone "feeling it got worse".

## RAG retrieval upgrade (2026-09-03)

One of the five to-do items, "RAG retrieval upgrade: reranker / hybrid search / cache", said "decide whether it is really needed once there is evaluation data". Now there is data. The conclusion: **only one minimal fix was made; a reranker and hybrid search are both not being built for now**, for the reasons below.

### Fixed: a pronoun clause in a multi-turn conversation lost its retrieval context

It started with the `en_multi_003` conversation:
1. "What is the daily ATM withdrawal limit?" → correctly answers NT$20,000 (including the top-up channels), `rag_sources=[atm_services.md]`.
2. "And the per-transaction limit?" → sometimes **hands over to a human** (`atm_services.md` actually contains the per-transaction limit), sometimes answers correctly.

Root cause: `retriever.retrieve(message)` in `qa_node` (`backend/src/agent/nodes.py`) embeds only the **current turn's** raw text, without the conversation history. Tested alone, the last turn of each of the three multi-turn cases scored at or below `HIGH_CONFIDENCE_THRESHOLD` (0.60):

| Case | Last turn | Retrieval score on its own |
|---|---|---|
| `zh_multi_001` | "那年費呢?" (and the annual fee?) | 0.475 |
| `en_multi_003` | And the per-transaction limit? | 0.592 |
| `zh_multi_002` | "那匯率是用哪一種?" (and which exchange rate is used?) | 0.620 |

Below the threshold the verifier is triggered, and the verifier's own LLM decides "are these chunks enough to answer". **That judgement itself varies between reruns.** The same test file was run three times in a row: the first run passed 3/4 (`en_multi_003` failed); the second passed 2/4 (this time `zh_multi_001` and `zh_multi_002` failed while `en_multi_003` passed); the third passed 4/4. No single case failed every time or passed every time.

At first `en_multi_003` was marked `xfail(strict=True)`, treating it like the known holes recorded in `tests/security/test_authorization.py`. That assumption was wrong: `strict=True` presumes the case fails consistently, but it unexpectedly passed in one run, and `strict=True` counted "the model got it right this time" as a failure, a false alarm. The marker was removed and the current state is recorded honestly. This is consistent with the 3 existing verifier-judgement tests in `tests/test_verifier.py` (which also call the real LLM for a sufficient / insufficient binary judgement and also accept occasional noise).

**The fix**: `nodes.py` gained `_retrieval_query()`, which prepends "the user's previous turn" to the current query before embedding (only the user's own words, never the AI's reply, to avoid dilution). No extra LLM query-rewriting call; plain string concatenation. Scores after the fix:

| Case | Before | After |
|---|---|---|
| `zh_multi_001` | 0.475 | 0.804 |
| `en_multi_003` | 0.592 | 0.805 |
| `zh_multi_002` | 0.620 | 0.804 |

All three moved from right at (or below) the threshold to about 0.80, comfortably over the line. `test_conversation_regression.py` ran 3 times in a row at 4/4, no longer the hit-and-miss behaviour described above. `test_retrieval_query_folds_in_prior_user_turn` and `test_retrieval_query_unchanged_on_first_turn` (`tests/test_faq.py`) lock the logic down with a pure function, without waiting for an LLM.

### Evaluated, not built: reranker

The golden set was used to measure Top-1 accuracy (not just whether Top-K contains the right file, but **whether the top-ranked one is right**, because Top-1 accuracy is what a reranker actually solves):

```
Top-1 accuracy: 11/13 = 85% (Top-5 hit rate is still 100%, see the four core metrics above)
```

Both misses are the same confusion: for "foreign-currency exchange fee" questions, `transfer_rules.md` ranks ahead of `foreign_currency_exchange.md`. Reading the text that was actually retrieved showed that **the keyword "foreign currency" is in both documents** (the international-transfer section of `transfer_rules.md` also mentions it). So this is not "the embedding drifted semantically" or "keywords do not match"; the two documents genuinely overlap in topic. It is the same kind of problem recorded in Sprint 21 (`docs/design_journal.md`): cross-topic confusion where several documents each have a fee section, just re-measured with two new phrasings.

**Why not build it**: the Top-5 hit rate is already 100%, meaning the right document always reaches the LLM's context. The two misses only affect "how nice the ranking looks" and the accuracy of the `rag_sources` badge, not whether the customer gets the right answer. A reranker would either add a cross-encoder model (one more inference of latency, one more model to maintain) or an extra API call (one more cost), in exchange for a ranking improvement that currently has no real effect on answer correctness. n=13 is also too small to tell "adding a reranker reliably fixes this confusion" apart from "these two happen to be fixed and two others happen to break".

A cheaper next step than a reranker (if it is ever needed): as in Sprint 21, improve how those two documents are split and headed, so the "foreign-currency cash exchange" and "international transfer" passages are semantically further apart. This is a content problem, not necessarily one to solve with model architecture.

### Evaluated, not built: hybrid search (BM25 + embedding)

Hybrid search (keyword matching plus vector semantics) was expected to cover cases where "the embedding is semantically similar but the keywords do not match". The miss above, however, shows the opposite: **the two confused documents share keywords**, so BM25 would score both highly and be no better than the embedding at telling them apart. The knowledge base currently has only 84 (Chinese) + 79 (English) chunks, all natural-language FAQ content, with no product codes, account numbers or exact figures, the kind of query "the embedding misses but keywords catch", which is exactly where hybrid search earns its keep. This corpus has almost none.

**Conclusion**: the data does not currently support building hybrid search. If the knowledge base later grows to include keyword-sensitive content such as exact codes or clause numbers, this conclusion should be revisited.

### Cache

Caching was also in the original to-do list. It was not evaluated this round because it addresses cost and latency, not the correctness this benchmark measures. Unlike the two items above, it makes more sense to evaluate after the tracing and cost-monitoring item is done and there are real latency and spend numbers.

## Verification-policy measurement: when should "is the data enough to answer" be checked (2026-11-21)

**What prompted it (first-hand observation)**: a long overseas-refund question ("the refund in NT$ is less than the original, and the 1.5% fee was not refunded, why?"). With **no** refund rule in the knowledge base, the top retrieval score was **0.664**, above the 0.60 verification threshold, so verification was skipped; the model answered from loosely related passages and even added a reason the knowledge base does not contain ("this is what most banks do"). That is exactly the "plausible but not necessarily correct" answer the verification step exists to stop.

**Measurement** (`claude-haiku-4-5`, verification at `temperature=0`):

- Answerable questions: the knowledge base's own 62 Q&As (39 Chinese / 23 English).
- Questions the knowledge base definitely has no answer for: 12 (topic confirmed absent from the knowledge base by keyword; 2 more that were first counted as gaps were later found to have related content and were excluded).

| When to verify | Real gaps caught | Answerable but handed to a human | Verifications run |
|---|---|---|---|
| Score below 0.60 (the original) | **5 / 12** | 3 / 62 | 15 / 62 |
| Score below 0.75 | 11 / 12 | 10 / 62 | 53 / 62 |
| **Always (now)** | **12 / 12** | 11 / 62 | 62 / 62 |

- **Gap questions score 0.54 to 0.76, answerable ones have a median of 0.66; the two ranges overlap**, so no single score threshold can separate them (consistent with the Sprint 12 conclusion, this time with a larger sample). The only thing that separates them is the verification judgement itself: it judged all 12 real gaps "insufficient".
- Of the 11 answerable questions that were handed to a human, 4 were cases where retrieval never found the right document (so handing over was actually right) and 7 (about 11%) were verification being stricter.
- Cost: one extra small-model call per FAQ answer; measured time to first word about 3 seconds (in rehearsal, the annual-fee and ATM questions took 2.9 to 3.2 seconds).

**Decision**: verify before every FAQ answer (`VERIFY_ALWAYS`, on by default; setting it to `0` restores the old behaviour). See ADR-020.

**A retrieval weakness the stricter verification dug up** (not yet fixed): among 77 hand-written shortcuts, 7 had retrieval rank the **wrong passage** first, for example for "how is the domestic transfer fee calculated?" the top result was the **international remittance** fee. The verification judgement of "insufficient" was right (the same input run 6 times gave the same result). Those 7 were removed from the shortcut list, and improving retrieval itself (for example reranking or targeted chunking) is on the to-do list; `tests/test_shortcuts_verified.py` makes sure the remaining shortcuts all pass verification.

**Limits (please quote honestly)**: the sample is small (62 + 12), and the gap questions were hand-picked by me on the basis of "the knowledge base has no such topic", not randomly sampled. The "answerable" questions use the knowledge base's own Q&A wording, which is easier than real customers' phrasing, so the share of wrongly blocked questions on real traffic may be higher. This is directional evidence, not an accuracy rate.

## Fraud-routing measurement: wording that means "a charge I did not make" (2026-11-23)

**What prompted it (first-hand observation)**: on the Dashboard, "帳單裡有一筆不明款項，我未消費過此筆金額" ("there is an unidentified charge on my bill, I never spent this amount") had been filed as an ordinary billing dispute, not flagged as urgent fraud. Fraud routing is decided entirely by the LLM classifier's prompt (there is no keyword rule), so the prompt was the thing to measure and fix.

**Measurement** (`claude-haiku-4-5`; 12 fraud phrasings and 7 non-fraud phrasings, each run 4 times):

| Stage | Fraud phrasings caught as fraud | Other phrasings kept in their correct category |
|---|---|---|
| Before the fix | 40 / 48 | 28 / 28 |
| First fix (any charge the customer did not make or does not recognise is fraud) | 48 / 48 | 24 / 28 |
| Second fix (also: a purchase the customer did make that was charged twice stays a dispute) | **48 / 48** | **28 / 28** |

- Before the fix the misses were concentrated in two phrasings, each wrong 4 out of 4 times: the sentence above (filed as a dispute) and "I don't recognize this transaction on my bill" (filed as an account lookup). The other ten phrasings were already correct.
- The first fix introduced a side effect: "商家對我扣了兩次款" ("the merchant charged me twice") was now filed as fraud 4 out of 4 times. The second fix removed it. After it, two full runs in a row scored 76 out of 76 classifications.
- The classifier also now runs at `temperature=0`, so the same sentence takes the same path every time. `tests/test_fraud_intent.py` (calls the real model) keeps the behaviour from regressing.

**Limits**: 19 hand-picked phrasings. This shows that these wordings are now routed correctly; it does not show that every possible phrasing is (colloquial wording, dialect and typos were not tested).

## How to add a new case

1. Add a line to `golden_cases.jsonl`. Prefix the `id` with the language (`zh_` / `en_`) and the category, for example `zh_faq_011`.
2. `category` decides which runner picks it up: `faq` / `account` / `card_loss` / `handoff` go to `test_intent_regression.py`; cases with `expected_sources` (faq or multi_turn) also go to `test_retrieval_regression.py`; `multi_turn` goes to `test_conversation_regression.py`.
3. For FAQ / multi_turn cases, first run the retriever by hand to confirm the Top-K really hits `expected_sources` (`tests/eval/test_retrieval_regression.py` starts with `RETRIEVERS`, which can be tried directly in a REPL), to avoid committing an expectation that was wrong from the start.

## Later: LLM-as-Judge (not yet implemented)

The four v1 metrics are all deterministic comparisons (intent string equality, source string containment, handoff booleans). What comes next is scoring **answer quality** itself: groundedness, relevance, completeness and tone, each 1 to 5. The design will follow a few principles so v1's deterministic character is not diluted:

- The judge's model, prompt version, call cost and raw reply (not just the score) are all kept, so it can later be checked whether "the judge was wrong or the answer really was".
- A judge score is an auxiliary signal, not ground truth: it must not override a red deterministic metric. It can only be used, when the deterministic ones are all green, to compare "is this answer better", a difference string matching cannot detect.
- It will not be mixed into the same aggregate threshold as the four v1 metrics; it will be an independent fifth metric with its own reporting and its own threshold.
