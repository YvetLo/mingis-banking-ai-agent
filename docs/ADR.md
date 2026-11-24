**English** · [繁體中文](ADR.zh-TW.md)

# Architecture Decision Record (ADR)
# AI Banking Customer Assistant

The reason, trade-offs and production path for each important technical decision.

*Some decisions refer to planning-era file names (for example `rag_chain.py`, `docs/agent_design.md`); the current structure is in [architecture.md](architecture.md).*

---

## ADR-001: Streamlit for the frontend, not Next.js

**Date**: 2026-07-06
**Status**: Adopted

**Background**:
The project needs a demo-able chat interface. The candidates were Next.js (React) and Streamlit (Python).

**Decision**: Streamlit

**Reasons**:
- Written in Python, consistent with the backend AI stack; no new framework to learn
- Fast to build (a chat interface in under a day), leaving more time for the AI logic
- A very gentle learning curve for a developer with intermediate Python
- Streamlit `session_state` can hold the conversation memory directly, with no extra state-management library

**Trade-offs**:
- Limited UI customisation (no pixel-level design)
- No true multi-user concurrency (each session is isolated and cannot talk to other sessions)
- Not the standard enterprise frontend stack

**Production path**:
Switch to Next.js 14 (App Router). The backend API does not change; only the way the frontend calls it does.
The chat interface can be built quickly with the Vercel AI SDK, and WebSocket supports live streamed replies.

---

## ADR-002: Function routing for the agent, not LangGraph

**Date**: 2026-07-06
**Status**: Adopted (Sprints 1-5), upgraded in Sprint 6

**Background**:
The AI agent must route by intent to different handling modes (FAQ / Account / Workflow / Handoff).
The candidates were LangGraph (a graph-based state machine) and plain if/else function routing.

**Decision**: function routing for Sprints 1-5, refactor to LangGraph in Sprint 6

**Reasons**:
- Function routing lets the business logic of each mode work first; only after the behaviour is confirmed correct is it refactored
- LangGraph has a steep learning curve; using it from day one would make debugging much harder
- Get the logic right first, then the architecture: this is the right order for enterprise iterative development
- After Sprints 1-5 the behaviour of every node is fully understood, so the refactor can be done with confidence

**Trade-offs**:
- Function routing reads well but scales badly: adding an intent means changing the core logic
- No clear state-management boundary; workflow state has to be managed by hand

**Production path**:
Sprint 6 already upgraded to LangGraph: node boundaries are clear and state is traceable.
Adding features later (such as apply_product or dispute_transaction) only requires adding a node, without affecting existing logic.

---

## ADR-003: SQLite for the database, not PostgreSQL

**Date**: 2026-07-06
**Status**: Adopted

**Background**:
The system needs to store tickets and unresolved-question records. The candidates were SQLite (file-based) and PostgreSQL (server-based).

**Decision**: SQLite

**Reasons**:
- No separate database service to start, which lowers local-development complexity
- Python ships the `sqlite3` module, so there is nothing extra to install
- The data volume is small (demo scale), and SQLite performance is entirely sufficient
- The schema is largely compatible with PostgreSQL, so switching only means changing the connection string

**Trade-offs**:
- No concurrent multi-user writes (fine for a single-user demo, not for production)
- No built-in connection pooling or backup
- No JSON-type queries (PostgreSQL supports them)

**Switching command** (SQLite → PostgreSQL):
```python
# SQLite (now)
DATABASE_URL = "sqlite:///./data.db"

# PostgreSQL (production)
DATABASE_URL = "postgresql://user:password@localhost/banking_ai"
```
Only this line changes; the SQLAlchemy ORM layer would not need to change. *(Planning-era note: the code currently uses `sqlite3` directly, so a real migration would also touch `database.py`.)*

---

## ADR-004: FAISS for the vector store, not ChromaDB

**Date**: 2026-07-06
**Status**: Adopted

**Background**:
FAQ lookup needs vector search. The candidates were FAISS (Facebook AI) and ChromaDB.

**Decision**: FAISS

**Reasons**:
- FAISS runs entirely locally, with no extra service to start
- Fast search, suitable for a demo-scale knowledge base (< 1000 chunks)
- Well known in the AI community and the industry, with plenty of material and examples
- Easy to install in Python (`pip install faiss-cpu`)

**Trade-offs**:
- FAISS does not support live index updates (it must be rebuilt), so a knowledge-base update needs a rebuild script
- No built-in metadata filtering (ChromaDB has it)
- No distributed deployment

**Production path**:
When the knowledge base grows, consider ChromaDB (supports live updates) or Pinecone (cloud-hosted).
The interface is abstracted, so switching only means changing the vector-store initialisation in `rag_chain.py` *(a planning-era file name; today it is `backend/src/rag/retriever.py`)*.

---

## ADR-005: Context stuffing in Sprint 1, not RAG

**Date**: 2026-07-06
**Status**: Done (Sprint 1), upgraded to RAG in Sprint 5

**Background**:
For the first version of FAQ lookup, a way was needed to give Claude the knowledge-base information.

**Decision**: In Sprint 1, put the whole FAQ into the system prompt (context stuffing)

**Reasons**:
- The fastest way to verify that the conversation logic is right, without building a vector database
- While the knowledge base is small (< 5 documents) the token count is acceptable
- First confirm that "the conversation design is right", then that "the retrieval method is right"

**Limits of context stuffing (why Sprint 5 upgraded to RAG)**:
1. As FAQ documents grow, the token count exceeds the limit (Claude Haiku's maximum is 200K tokens)
2. It cannot show the "source document" (showing sources adds credibility)
3. It cannot set a similarity threshold to decide on a fallback
4. Updating the knowledge base means editing the system prompt

**This evolution is itself a design process worth recording**:
> "I first verified the logic in the simplest way, and only introduced RAG after hitting a real limit,
>  rather than over-engineering from the start. That lets me say clearly what RAG solved."

---

## ADR-006: Claude API for the LLM, not OpenAI

**Date**: 2026-07-06
**Status**: Adopted

**Background**:
The candidates for the system's core LLM were the Claude API (Anthropic) and the OpenAI API (GPT).

**Decision**: Claude API (claude-haiku-4-5)

**Reasons**:
- An Anthropic API key was already available, with nothing extra to apply for
- claude-haiku-4-5 is fast and cheap, suitable for frequent demo calls
- A 200K-token context window greatly reduces the limits of context stuffing
- Consistent with the Claude Code development environment, so the stack is unified

**Trade-offs**:
- OpenAI is better known in the industry, and some developers may be more familiar with the GPT API
- LangChain has more integration documentation for OpenAI

**How to switch** (Claude → OpenAI):
```python
# Claude (now)
from anthropic import Anthropic
client = Anthropic()
response = client.messages.create(model="claude-haiku-4-5", ...)

# OpenAI (if a switch is needed)
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model="gpt-4o-mini", ...)
```
The interface logic is the same, so the cost of switching is low.

---

## ADR-007: Separate FAISS indexes per language, not one multilingual index

**Date**: 2026-07-06
**Status**: Adopted

**Background**:
The system must support Chinese and English queries. The candidates were:
(A) a single multilingual embedding model with a single index
(B) detect the language, then route to a separate index for that language

**Decision**: option B (separate indexes plus language routing)

**Reasons**:
- Although a multilingual embedding model (such as paraphrase-multilingual-mpnet-base-v2) supports cross-language search,
  in testing, Chinese questions often retrieved English documents (close in vector space but a different language), causing confusion
- Separate indexes guarantee that a Chinese question always searches Chinese documents and an English question English ones
- Detecting the language and then routing is clear and maintainable
- The two knowledge bases are independent, so updating one does not affect the other

**Trade-offs**:
- Two parallel sets of knowledge-base documents (one Chinese, one English) have to be maintained
- Index build time × 2, disk space × 2

**Production path**:
If the knowledge base grows, consider the Cohere multilingual-v3 embedding,
whose cross-language search is clearly better than sentence-transformers, which would allow going back to a single index.

---

## ADR-008: Tool-calling for the Account node, not context stuffing

**Date**: 2026-07-17
**Status**: Adopted (Sprint 7)

**Background**:
In Sprints 1-6, account queries put the user's savings, credit cards, bills and recent transactions "all" into the system prompt (`format_user_context`), with FAQ and Account sharing one Claude call (see the follow-up to ADR-002 and the Sprint 6 design journal). The candidates were (A) keep context stuffing, (B) give the Account node real tool-calling, letting Claude call `get_account_balance` / `get_credit_card_bill` / `get_transactions` according to the question.

**Decision**: option B; the Account node becomes a tool-calling agent separate from the FAQ node.

**Reasons**:
- Context stuffing sends data unrelated to the question into the prompt (for example, someone who only asks for a balance gets the card limits, bills and transaction details too), which wastes tokens and raises the chance of the model ignoring instructions or hallucinating
- Tool-calling lets Claude decide which API to call from the actual question, closer to a real enterprise agent architecture (calling the core banking system's real API rather than dumping the whole record on the LLM)
- The node boundary becomes real: the Sprint 6 Account "node" was really only a label the Router attached; from Sprint 7 it is a truly independent execution unit

**Security decision (incidental)**:
`user_id` is deliberately not part of the tool schema exposed to Claude; the node layer injects it when it runs the tool (see `backend/src/agent/tools.py`). This differs from the original tool spec in `docs/agent_design.md` §4.2-4.4, which listed `user_id` as a parameter; that spec was written for a general server-side API. Here, letting the model fill in `user_id` would let a prompt injection query someone else's account, so the backend injects it and does not trust an identity parameter produced by the model.

**Trade-offs**:
- A turn may need two or more Claude API calls (first trigger tool_use, then send the tool_result to get the final answer), so latency and cost are higher than with context stuffing
- A tool-calling loop has to be maintained (`MAX_TOOL_ITERATIONS` caps it to prevent runaway loops), more complex than a single call
- The Router used keywords to separate `account` from `faq`, which could still misjudge; on a misjudgement the FAQ node's context stuffing still carried the user's account data as a safety net (see the Sprint 6 journal), so it would not completely fail to answer, only without the precision of tool-calling

**Production path**:
Functions like `get_account_balance` currently read in-memory mock data; production would replace them with calls to the core banking API (with timeouts, retries and audit logs). The Router's keyword classification should also be upgraded to real LLM intent classification, to lower the misjudgement rate.

---

## ADR-009: LLM intent classification for the Router, not keyword matching

**Date**: 2026-07-20
**Status**: Adopted (Sprint 9)

**Background**:
`docs/agent_design.md` §3.1 defined the Router as "intent classification (LLM)" from Phase 5 (before Sprint 1), but in Sprints 1-8 keyword matching (`is_card_loss` / `is_handoff_trigger` / `is_account_query`) simulated it: get the business logic and node boundaries working first, and leave the classifier itself for last (ADR-002 and ADR-008 both foretold this step). The candidates were (A) keep tuning the keyword list, (B) really call Claude to classify.

**Decision**: option B; the Router now uses `classify_intent()` in `backend/src/agent/intent.py`.

**Reasons**:
- The failure mode of keyword matching is structural, not a matter of the list being too short: "credit card annual fee" contains none of the `ACCOUNT_KW` words and correctly lands in FAQ, but the list cannot handle "when does this card's annual fee fall due", which semantically needs personal account data yet may wrongly trigger the FAQ keyword logic. Keyword matching can only check whether certain words appear, and cannot understand meaning
- Forcing Claude to call the `classify_intent` tool with `tool_choice` guarantees a structured one-of-four result every time (`faq` / `account` / `card_loss` / `handoff`), with no free text to parse and no "the model did not follow the format" exception to handle
- This honours a spec written in Sprint 1; it is not a new feature. It shows that "first make the logic work with a simple approach, confirm the node-boundary design is right, and only then bring in the complexity of LLM classification" was a deliberate engineering judgement, not something left to the end

**Trade-off (latency and cost)**:
- Not every turn pays for an extra API call: when a lost-card flow is in progress (`workflow_step > 0`) and when the frontend forces a handoff (`force_handoff`), the judgement stays deterministic and skips the classifier. These are essentially "system state" rather than "needing to understand what the user said", and handing them to an LLM would only add an unnecessary source of uncertainty
- But for FAQ / Account / the first trigger of a lost-card or handoff, each turn does pay for one extra classifier call (`max_tokens=64`, a very short system prompt), so these conversations go from 1 Claude call to at least 2, with higher latency and cost than pure keyword matching
- The classifier is not 100% accurate. The first version hit a concrete case: "you got it wrong, that is not the answer I wanted" was misclassified as `handoff` because it sounds like a complaint. The fix was to list counter-examples explicitly in the tool description (merely saying "the answer is wrong / unhelpful" is not a request for a human; classify it under the original topic), and to pin the case as a regression test that fails automatically in `tests/test_router_intent.py`

**Production path**:
If the "low confidence → ask the user" behaviour from §3.1 is built later, a different calling style is needed to get a confidence score (for example, checking whether the model hesitates when the forced `tool_choice` is removed, or using logprobs). It was judged to have low marginal value for demonstrating the core agent architecture, so Sprint 9 did not implement it.

---

## ADR-010: A separate grounding verifier in the FAQ node, not just a higher similarity threshold

**Date**: 2026-07-27
**Status**: Adopted (Sprint 12)

**Background**:
A diagnostic case study found that RAG similarity scores cannot reliably tell whether "the retrieved content really answers the question". In the foreign-currency-exchange case, three chunks scored (0.421 / 0.381 / 0.324), all above the original threshold of 0.30, yet none of them was actually about foreign-currency exchange. Measuring the scores of 17 real questions then showed that the highest score of the "known gap" (0.500) was higher than the lowest score of the questions that "really can be answered" (0.482): the score ranges of the two categories overlap directly, so no single global threshold can catch the gaps without hurting real questions. The candidates were (A) accept the limitation and only record it honestly; (B) raise the threshold, accepting a partial improvement that still misses some cases; (C) add a separate role that reads the retrieved content itself (not the score) to judge whether it is enough to answer.

**Decision**: option C. Add `backend/src/agent/verifier.py`, which uses forced `tool_choice` structured output to judge "are the chunks enough to answer the question". It was triggered only when the score fell in the ambiguous zone (< 0.60), and on "not enough" it handed over to a human early, skipping draft generation.

**Reasons**:
- The score overlap is fundamental (a small corpus with highly shared wording). Tuning the threshold treats the symptom, and option B would make people believe the problem was solved, which is more dangerous than honestly recording the limitation
- Only by reading the content, rather than just the score, can the system answer "is this answer grounded" rather than "did something cross the score line". A score mechanism is architecturally unable to do that
- Triggering only in the ambiguous zone meant most clear traffic paid no latency. By ordering "verify first, then decide whether to generate a draft", the can't-answer case becomes faster than the normal path (it saves the most expensive step, draft generation)

**Trade-offs**:
- Traffic in the ambiguous zone pays the latency of one extra LLM call, measured at about 2.2 to 3.8 seconds
- The scope was only the FAQ node (`intent="faq"`); the Account node's tool-calling data lookups are unaffected. This was a deliberate narrowing, since the two have structurally different failure modes and there was no need to widen it at once
- The old `rag_low_similarity` mechanism was fully replaced rather than kept alongside, to avoid logging two records with the same meaning for one failure

**Production path**:
Bank FAQs are naturally highly repetitive, so production should add a cache to the verifier (skip the call on a cache hit for the same question plus chunk combination), and consider giving "the AI itself judged it cannot answer" (`verifier_unresolved`) and "the user asked for a human" (`handoff_intent`) different priorities in the agent queue.

---

## ADR-011: Handoff as a ticket plus a conversation thread, not just extending the existing ticket record

**Date**: 2026-07-27
**Status**: Adopted (Sprint 15)

**Background**:
Since Sprint 4 the `tickets` table had been insert-only (see the reflections in the Sprint 8/11/14 design journals): it only recorded "a handoff to a human happened once", and the `status` column existed but was never updated. This time the goal was "a human agent can actually reply to the customer". The minimal approach was to keep using the `tickets` table and add a `resolution_note` column for the agent to fill in; but the user's requirement was explicitly a "chat box": the customer must be able to add messages and the agent to reply several times, an ordered multi-turn conversation rather than a one-off outcome. The candidates were (A) add a column to `tickets` itself to hold the last reply; (B) create a separate `handoff_messages` table for the full thread, with `tickets` keeping only case-level metadata (status, priority).

**Decision**: option B. Add the `handoff_messages` table (`ticket_id`, `session_id`, `role`, `content`, `created_at`); leave the `tickets` table as it was, adding only `update_ticket_status()` so `status` becomes mutable for the first time. Add a shared helper `escalate_to_human()` (`backend/src/agent/handoff.py`) which, when it creates the case, writes "the conversation history before the handoff + the triggering message + the AI's handoff reply" into the thread in one go, shared by the Handoff node (the user asked for a person) and the FAQ node's grounding-verifier branch (Sprint 12, the AI judged the knowledge base insufficient).

**Reasons**:
- "Case state" (whether a case is open or resolved) and "conversation content" (what each side said back and forth) have different change frequencies and access patterns: the former changes once or twice per case, the latter gains a row every turn. Mixing them in one table either needs constant UPDATEs of one big text column (easy to overwrite under concurrency, and hard to keep a full history) or can only store the last message (not what a "conversation" needs: when the customer follows up with a second sentence, the first would be gone)
- If the two handoff triggers (user-requested vs verifier-judged) each had their own logic for creating a case and writing messages, adding a third trigger later (for example the "fraud-case priority queue" planned in Sprint 14 but not yet built) would mean changing two places instead of one. A shared helper keeps it to one implementation
- No new LLM call was added, and the existing classification and retrieval logic of Router / FAQ / Account was not touched. `escalate_to_human()` is pure database work, run after an existing node returns its result

**Trade-offs**:
- One more table and four new endpoints, more complex than adding a column; but the complexity matches a real requirement (multi-turn conversation) and is not over-engineering
- `handoff_messages` has no read/unread marker, so both agent and customer re-read the whole thread instead of "only the new messages". That is no performance problem at demo scale; at volume it needs pagination or a cursor
- The agent page had no login or case assignment, so anyone who opens the page can handle any case. This was deliberately out of scope (see the Sprint 15 reflection in `docs/design_journal.md`), a demo-stage trade-off

**Production path**:
Production `handoff_messages` should consider read state, agent login and case assignment (to stop two people handling the same case and overwriting each other's replies), and the "urgent-case priority queue" left over from the Sprint 14 ADR. At the time, the `priority` column was used only for display and `/handoff/tickets` did not yet sort by priority. *(Later, in Sprint 22, the agent console was changed to put urgent cases first.)*

---

## ADR-012: New knowledge stored in a DB table, with a hot rebuild and in-place hot swap of the retriever, not editing markdown and restarting

**Date**: 2026-08-02
**Status**: Adopted (Sprint 17)

**Background**:
The knowledge base was originally markdown under `data/knowledge_base`; at start-up `build_index.py` built it into a FAISS index and `main.py` loaded the retriever once at startup. To let the maintenance UI add knowledge "that takes effect immediately", there were two separate questions: (1) where the new knowledge is stored; (2) how the index is updated afterwards. For (1) the candidates were "edit the markdown files directly" vs "a separate DB table, indexed together with the markdown". For (2) they were "rerun build_index and restart the server" vs "hot-rebuild and swap the index inside the running process".

**Decision**:
(1) New content goes in the `kb_entries` table (with language / title / content / tags / status / source / timestamps) and the markdown stays untouched; when indexing, `assemble_docs()` merges the markdown chunks with the active `kb_entries`.
(2) After `POST /kb/reindex` recomputes the index files, it replaces the values of the `retrievers` dict in place (`retrievers[lang] = RAGRetriever(...)`), with no restart and no graph rebuild.

**Reasons**:
- **A table rather than editing files**: each supplementary entry needs governance fields (source manual/pipeline, status, timestamps) that markdown cannot hold. Archive as a soft delete gives a way back (especially once AI-generated drafts are published, where it must be possible to roll back one found to be bad). Editing files from the UI is fragile and easy to damage existing content.
- **What makes the in-place hot swap work**: the closure of `make_qa_node` captures the `retrievers` dict object, and `qa_node` calls `retrievers.get(language)` on every run. So replacing a value in the dict means a running graph gets the new retriever on its next call, with no extra reload mechanism. This is the simplest solution after reading the existing closure semantics, not a newly added framework.
- **No conflict with `--reload`**: uvicorn's reload only watches `.py` files, so writing `.index` / `.json` does not trigger a restart, and the hot swap is stable within one process.
- **Reindex reuses the embedding-model singleton**: when `reindex_all()` is not given a model it takes the already loaded singleton from `retriever._get_model()`, so a live call only pays the recomputation cost and does not load another copy of the model.

**Trade-offs**:
- **Full rebuild, not incremental**: every reindex recomputes the whole index. At demo scale (a few dozen chunks) that is a few seconds; only a large knowledge base needs incremental updates or caching. Simple and correct was chosen deliberately (incremental updates need meta to be kept aligned with archive and edit, which is error-prone).
- **Concurrency**: during the rebuild the old retriever keeps serving, and a single assignment that swaps a value is atomic in CPython, so in-flight requests using the old object are unaffected. There is no read-write lock; that is acceptable for a demo, while high-concurrency production needs a more rigorous double-buffered switch.
- **Test boundary**: a real reindex overwrites the one global real index and runs the embedding model, so it is not put in pytest (it would pollute other tests that depend on the index). The pure function `assemble_docs` is tested instead, and reindex is verified live.

**Production path**:
For a large knowledge base, move to incremental indexing or add an embedding cache; change the hot swap to double buffering (build into a shadow index, then switch atomically once ready) to avoid any latency jitter during the rebuild; `kb_entries` could gain a version-history table (archive/restore currently gives basic rollback, but no per-version diff).

---

## ADR-013: Knowledge improvement uses LLM topic clustering plus a `kb_actionable` guardrail, and measures the effect as retrieval confidence before/after

> **Naming note**: this feature is now called the "Knowledge Improvement Pipeline" (formerly the "knowledge-gap pipeline"). The internal identifiers (`gap_pipeline.py`, the `/gap/*` endpoints, the `kb_gap_drafts` table, the `gap_*` functions) keep the old name so existing databases and APIs are not touched; "gap" in the text means the concept of content the knowledge base really lacks, not the feature's name.

**Date**: 2026-08-02
**Status**: Adopted (Sprint 18)

**Background**:
Accumulated failure signals (unresolved queries, negative feedback or low scores, handoff conversations) should automatically become FAQ drafts that can be published. Three separate decisions: (1) how to group the signals into topics; (2) how to avoid turning signals that "should be handled by a human" into a self-service FAQ; (3) how to quantify "effect".

**Decision**:
(1) **LLM topic clustering** (one forced `tool_choice` call returning topics + member_ids + representative_query), rather than embedding k-means / HDBSCAN.
(2) For each topic the clustering call attaches a **`kb_actionable`** boolean: true only for informational questions that "adding one knowledge-base article can resolve by self-service"; topics needing human discretion (fee waivers, data or security changes, fraud, disputes, complaints, approvals) are false and no draft is generated.
(3) Effect = **the representative question's retrieval confidence before/after** (the score before publishing vs after the rebuild, with threshold 0.60), supplemented by "how many similar questions occurred after publishing".

**Reasons**:
- **LLM clustering vs embedding grouping**: at this scale (a dozen or so signals), embedding grouping needs a choice of k, the groups are unlabeled and must be named afterwards, and small data is unstable. LLM grouping comes with a topic name and a representative question, is explainable, is stable on small data, and matches the project's existing forced-tool-call technique. Only thousands of signals would need embedding grouping or a coarse pre-filter, which is a production-scale problem.
- **The `kb_actionable` guardrail**: the user's request literally asked to "cluster the handoff conversations", but doing so literally would turn an operation like "change my contact phone number", which policy requires a human to handle, into a public self-service FAQ, breaking the Sprint 14 principle of "hand to a human what should go to a human". Be wide on sources and strict on publishing: let the LLM tell "knowledge gap vs correct handoff" at clustering time. Measured: 14 signals → 7 topics, only 3 actionable.
- **Retrieval confidence rather than a "resolution rate"**: a "resolution rate" needs defining, needs time to accumulate, and is easy to fake; "the representative question's retrieval went from 0.53 to 0.70 and was not stumped again after publishing" can be verified independently at every step and proven on the spot. Using "first filter out signals the current index already answers well" as the gap criterion anchors the effect to the same yardstick (the 0.60 threshold) and makes published topics disappear from the next analysis without a separate de-duplication table.

**Trade-offs**:
- The clustering prompt has a size cap (`MAX_SIGNALS=80`); thousands of signals would need a coarse pre-filter or embedding grouping.
- Approving rebuilds the index one by one (reusing the hot swap of ADR-012), so approving in a batch rebuilds several times; production should collapse that to one.
- The policy topics with `kb_actionable=false` are currently only excluded, with no feedback into strengthening Router rules or staffing analysis (an extension).
- "Similar recurrence" uses a fixed embedding-similarity threshold (0.62) that must be calibrated to the corpus; topics that were "skipped" are excluded with an embedding-similarity threshold (0.82), also a heuristic.
- Test boundary: analyze (LLM non-determinism) and approve (overwrites the real index) are not in pytest; only the deterministic review plumbing is tested, and the heavy parts are verified live (the same trade-off as ADR-012).

**Production path**:
Use embedding grouping or a coarse pre-filter for large volumes; merge batch approvals into one rebuild; route the `kb_actionable=false` policy topics into Router-rule strengthening and staffing analysis; calibrate the "recurrence" and skip-dedup thresholds to the real corpus; add a de-duplication / conflict check against the existing knowledge base before a draft is published (human review is the safeguard today).

---

## ADR-014: Live updates of the agent conversation via fragment polling; guest intake before handoff

**Date**: 2026-08-13
**Status**: Adopted (Sprint 19)

**Background**:
A user test reported "after the customer replies, the agent console never updates". A Streamlit script only reruns on interaction, so the Sprint 15 two-way human-agent conversation did not update at all in the most common state of "both sides have the page open, waiting for the other". Separately, a ticket opened when a guest simply said "I want a human agent" carried only one line, "the user asked for a human agent", leaving the agent who took it with no context.

**Decision**:
(1) Both the customer-side and agent-side threads are wrapped in **`st.fragment(run_every=5)`** for automatic polling; the agent's case queue has its own watcher at `run_every=15` that **only signals a new case and never switches automatically**. The turn that triggers the handoff adds one `st.rerun()` so the screen switches into the human conversation immediately.
(2) Add a **Handoff Intake node**: when `explicit_request` **and not logged in**, first ask "1 bank-account customer / 2 credit-card customer / 3 not a customer of this bank" plus a one-line description of the question, and only call `escalate_to_human()` once collected; ask at most two rounds, then hand over anyway. The customer category and description are written into the ticket description and a structured block of the thread.
(3) The Dashboard bar chart became horizontal and uses **Altair** rather than `st.bar_chart(horizontal=True)`.

**Reasons**:
- **Fragment vs a full-page auto-rerun**: a full-page rerun would wipe the reply the agent is typing and reset a case half selected: "clearing the input box every 5 seconds" is worse than not updating automatically. A fragment reruns only that block. The cost is that `st.chat_input` must stay outside the fragment (inside it loses its pinned-to-bottom placement), and buttons inside a fragment must use `st.rerun(scope="app")`.
- **Intake only for explicit_request and not logged in**: for the other handoff categories (fraud, dispute, sensitive data change…) the triggering message already describes the problem, so asking again is repetition and would delay the urgent cases Sprint 14 designed as "hand over immediately"; a logged-in customer's identity is already on the ticket. This continues the same principle as Sprint 15's refusal of a hard login gate: **the value of the information collected must outweigh the delay it causes**.
- **A two-round cap**: a customer who has already asked for a human must not be trapped by a bot in a form loop; if nothing is collected, record "not specified" and hand over anyway.
- **Altair vs the built-in horizontal option**: `st.bar_chart(horizontal=True)` does rotate 90 degrees, but the y-axis labels are truncated ("🔍AI 判定知識…"), the axis title is still the rotated Chinese text, and at a fixed height Vega **silently drops** labels to avoid overlap (only 2 of 4 categories were shown). Only Altair allows setting `labelLimit`, removing the axis title, letting the chart height grow with the row count through `alt.Step`, and pinning integer ticks (otherwise a single data point prints "0 1 1").

**Trade-offs**:
- 5-second polling produces a considerable request volume with many users (every open tab makes one `GET /handoff/{id}/messages` every 5 seconds); production should switch to WebSocket/SSE push.
- On the agent side every fragment update redraws the whole thread, so a long conversation makes the browser scroll position jump.
- Intake parses 1/2/3 plus keywords by rules; with more options or freer customer answers it becomes unreliable (the fallback is "not specified" and a handover anyway, so it never gets stuck). A lightweight LLM extraction would be more robust.
- The guest path goes from one turn to two, so `tests/test_handoff.py` has to drive it through `guest_escalate()`; the extra `/chat` call does not call the classifier (`workflow_step > 0` takes the deterministic branch), so there is no extra LLM cost.
- The customer category is currently only context; it is not yet used for any real grouping or routing.

**Production path**:
Replace polling with WebSocket/SSE; render the thread incrementally to avoid redrawing the whole thing; switch the intake parsing to LLM extraction with more options; connect the customer category to real triage routing (different categories to different teams) and SLA statistics.

---

## ADR-015: Suggested questions only offer "verified answerable" questions, extended from the retrieved topic

**Date**: 2026-08-22
**Status**: Adopted (Sprint 20)

**Background**:
The chat box should offer suggested questions and, based on what the customer just asked, extend into the next questions they might ask. There is one core risk: **if a suggestion cannot be answered when clicked, that dead end is created by the chatbot itself**. The customer is not asking at random; they clicked a button we gave them.

**Decision**:
(1) The candidate questions are **hand-curated** (`TOPIC_FOLLOWUPS`, grouped by knowledge-base source file), not generated live by an LLM.
(2) Before each candidate is shown, one retrieval is run against the **current index**; if the score does not reach the FAQ node's 0.60 confidence threshold, it is not shown (`_answerable`, cached, cleared when the index is rebuilt).
(3) Follow-up questions come from **the sources the answer actually retrieved** (`rag_sources`), in relevance order; when the topic has no usable question (for example it hit only a `kb_entry` added in the maintenance UI), fall back to the popular starter questions.
(4) Account-type suggestions (`ACCOUNT_SUGGESTIONS`) get no retrieval check, since they go through the Account node and do not touch the knowledge base, but they were also tested for real beforehand.

**Reasons**:
- **Why not let an LLM generate them**: an LLM writes questions that look reasonable but have no content in the knowledge base. And testing showed that even "questions copied straight from the knowledge base's `## FAQ` section" are not safe enough: of 5 questions, 4 ended in a handoff (two were correctly classified by the Router as dispute/refund, two retrieved the wrong file). **"Written in the knowledge base" does not mean "the chatbot can answer it"**; the only reliable criterion is to actually run it.
- **Why the 0.60 retrieval threshold as the filter**: it is exactly the line the FAQ node uses to decide "answer directly" or "ask the verifier to review (possibly handing over)". A suggestion must be guaranteed to take the former. That reuses the existing definition of confidence instead of inventing another.
- **Why a runtime filter rather than a hard-coded list**: the knowledge base changes. Add knowledge and more suggestions light up automatically; archive knowledge and the suggestions that depend on it disappear automatically after the next rebuild instead of becoming dead ends. This guardrail lets the list be maintained together with the knowledge base, with nobody having to remember to come back and edit it.
- **Cost**: one embedding encode per candidate, cached per index version and warmed at start-up and after a rebuild. **There is no extra LLM call on the response path**: while the customer waits for the reply there must be no additional model round trip.
- **Near-duplicate filtering uses Jaccard rather than one-sided overlap**: Chinese questions share many function words (我/的/是/多少), so a one-sided ratio would wrongly judge "how much is left in my account balance?" a duplicate of "how much is my bill this month" and hide it.

**Trade-offs**:
- The question bank is hand-maintained content and must be revisited after large knowledge-base changes (the test `test_every_curated_faq_suggestion_clears_the_threshold` points out which one has gone stale).
- The English bank is sparser (the foreign-currency / general-services / transfer topics currently have no question that clears the threshold), so those topics fall back to the popular questions. The root cause is that the Chinese and English chunking leaves some topics with low scores overall, an existing retrieval-quality problem.
- Follow-ups come from "the sources actually retrieved", so they occasionally drift along the retrieval to a neighbouring topic (in testing, the top source for "cash advance" was `atm_services.md`, so the follow-up became an ATM question). Related but not exactly on topic, which is still better than "on topic but unanswerable".
- The filter only guarantees "will be answered confidently", not "the answer is good"; that remains the job of the existing grounding verifier and the knowledge-base content.

**Production path**:
Manage the question bank from the knowledge-base maintenance UI (fill in "related questions" when adding knowledge) and run an answerability check automatically in the publishing flow; feed click-through back into the ranking (often-clicked ones first); a topic where no candidate clears the threshold is sent straight into the Sprint 18 pipeline as a knowledge-gap signal.

---

## ADR-016: Heading-aware and CJK-aware chunking for the knowledge base, TOP_K 3 → 5

**Date**: 2026-08-23
**Status**: Adopted (Sprint 21)

**Background**:
The original chunking took 400 "words" with `text.split()`. Chinese has no spaces, so **a whole Chinese markdown file counted as 1 word and became 1 chunk**. One vector per document answers "roughly what is this document about", not "which passage can answer this question". Measured consequences: the top source for "cross-bank transfer fee" was `foreign_currency_exchange.md` (not `transfer_rules.md`), "time-deposit interest rate" hit `loan_overview.md` (the loan rate, not the deposit rate), and "I cannot receive the OTP" went straight to a human. This was also the root cause of several questions being scrapped while curating the Sprint 20 suggestion bank.

**Decision**:
(1) Chunking now **uses markdown headings as the main boundary**: each `##` / `###` section becomes its own chunk, and only if it is too long does it fall back to size-based windows (split on whole lines, never cutting a table row).
(2) Each chunk gets its **heading path** prepended (`Transfers and remittance > Domestic transfer > How to transfer and fees`) and embedded with it.
(3) Length is counted in **units** = CJK characters + Latin words, replacing `text.split()`.
(4) `TOP_K` 3 → 5.

**Reasons**:
- **The heading is the best boundary**: in these documents a `##` / `###` section happens to be exactly one topic ("cross-bank ATM fee", "annual fee"), more accurate than any character-count cut.
- **The heading path must be embedded together with the body**: a passage about the "annual fee" whose body never repeats the words "credit card" would lose to a whole document that mentions "credit card" repeatedly, without the breadcrumb. This item alone contributed a great deal: after removing the repeated `# heading` line from the body and keeping it only in the breadcrumb, Chinese top-1 rose again from 79% to 85%.
- **Splitting `###` too**: this was **decided after measuring**, not by intuition. Splitting only `##` gave English top-1 89%; splitting `###` as well gave 96% (100% in the final version). The cost was Chinese recall@3 dropping by about 3 percentage points.
- **Raising TOP_K to 5 recovers the recall**: chunks are about 6 times smaller, so the content of 3 chunks is far less than that of the earlier 3 whole documents. Measured Chinese recall@3 is 92% and recall@5 97%; and the text volume of 5 passages is still far smaller than that of the earlier 3 whole documents.

**Measured results** (39 Chinese / 28 English questions, each annotated with the file it should hit):

| | Chinese before | Chinese after | English before | English after |
|---|---|---|---|---|
| Correct file ranked first | 54% | **85%** | 71% | **100%** |
| Correct file in the top three | 74% | **92%** | 82% | **100%** |
| Top score ≥ 0.60 | 64% | **87%** | 43% | **89%** |

Number of chunks: Chinese 10 → 84, English 14 → 79.

**Trade-offs**:
- More chunks → slightly longer index build time and memory (unnoticeable at this scale).
- Small chunks can **amplify the confidence score of a wrong hit**: in an experiment, a badly cut version made "what is a designated-account transfer?" hit the wrong file with a high 0.772. A higher score does not mean more accurate, which is why the decision looks at top-1 and recall rather than the average score.
- The meaning of the 0.60 threshold effectively got stricter (the same question now scores higher more easily), so more questions in the Sprint 20 suggestion bank pass; the bank was expanded and each question re-tested for real.
- 3 Chinese questions still hit the wrong file, all cross-topic confusion where several documents each have a "fee / limit" section; the correct passage is still within the top 5.
- The chunking logic depends on the markdown heading structure. If the knowledge base later uses long text with no headings, it falls back to size-based windows (covered by tests).

**Production path**:
Semantic chunking or late chunking; tune TOP_K per language; put this retrieval benchmark into CI so it regresses automatically when the knowledge base changes; use reranking to handle the cross-topic confusion where several documents have a fee section.

---

*Last updated: 2026-08-23*
*Each time a sprint meets a new important decision, add an ADR entry to this document.*

---

## ADR-017: Vague bill complaints are clarified first, then handed to a human, with the decision placed before the LLM classifier

**Date**: 2026-11-18
**Status**: Adopted (Sprint 22)

**Background**:
In testing, a customer typing "something is wrong with the amount on my bill" was handed straight to a human; the case did not say which charge or what the problem was, so the agent had to start asking from scratch. The business requirement: first ask the customer which charge is wrong, and hand over after they answer. The implementation question was "where to decide that this is a vague bill complaint".

**Options**:
- A: change the intent classifier's prompt so it returns a new `clarify` category for such messages.
- B: use a keyword rule **before** the Router calls the classifier (bill + problem wording, with no specific clue).
- C: let the handoff node decide whether to ask first.

**Decision**: B.

**Reasons**:
- **The classifier is unstable on this sentence.** The same "我的帳單金額有問題" ("something is wrong with my bill amount") run 6 times was classified `account` (the account lookup) 5 times and `handoff / dispute_or_refund` once; the variants "帳單金額有問題" and "我的信用卡帳單金額有問題" were classified as handoff. If the clarifying question were written in the handoff node (C), the `account` cases would never trigger it; relying on a prompt change (A) would still give a probabilistic result, the same sentence being asked about today and not tomorrow.
- **This is a business rule, not semantic understanding.** "What counts as vague" can be listed explicitly: no amount, and none of the specific words such as "never swiped" or "charged twice". A rule is testable and predictable, and it is how the Router already works (a lost-card flow in progress and `force_handoff` are both decided deterministically before the classifier).
- **Zero LLM cost**, and the clarifying turn does not wait for the classifier.

**Trade-offs**:
- A keyword rule misses wording that was not listed (for example a message without "bill" plus a problem word does not trigger it); when it misses, it falls back to the old behaviour (the classifier decides), which is no worse than before.
- The rule is **deliberately conservative**: if the message contains any specific clue, or is longer than 30 characters, it does not ask. Fraud-type messages ("there is a charge on my bill I never made") always take the original path, so urgent cases do not queue behind a question.
- On `force_handoff` (the same problem repeatedly unresolved) the question is skipped, so a customer who is already stuck does not face one more gate.
- The customer is asked at most two rounds, after which the case is handed over whatever they reply (consistent with guest intake, ADR-014).

**Tests**: `tests/test_bill_clarify.py`: positive and negative examples of the detection rule, the question, opening a ticket after the reply with the explanation carried into the ticket, cancel, a too-short reply asked again and then handed over, and `force_handoff` skipping. No LLM is called.

---

## ADR-018: Plain greetings are answered directly by a deterministic Router rule, not sent into the FAQ flow

**Date**: 2026-11-18
**Status**: Adopted (Sprint 22)

**Background**:
Testing found that a customer typing "Hello!" was immediately handed to a human. The records (`unresolved_queries`) showed the intent was classified `faq`, the top retrieval score was only 0.238, below the 0.60 threshold, and the verifier judged the data insufficient and handed over (October's "Hi" did the same, at 0.210). The "do not answer when unsure" design was not wrong; the mistake was that a greeting is not a question that needs a lookup, yet it entered the lookup flow.

**Decision**: In the Router, before the LLM classifier, use a rule to decide that "the whole sentence is just a greeting / thanks / goodbye" and reply with a fixed message (`smalltalk_node`).

**Reasons**:
- The same principle as ADR-017: this kind of judgement can be listed explicitly and tested, needs no LLM, and costs no money and no latency.
- Safer than "tuning the verifier or lowering the threshold": the threshold is the confidence baseline of the whole system (ADR-010), and changing it for greetings would affect real FAQ judgements too.
- More stable than "adding a smalltalk intent for the classifier": the classifier is inherently unstable on short sentences (the 6-run measurement in ADR-017).

**Trade-offs**:
- It only recognises explicitly listed phrasings; greetings not on the list (for example "heyyyyy") still take the original path, and the list can be extended from real conversation records.
- The rule requires "the whole sentence is only a greeting"; if a question is attached ("hello, how much is the annual fee?") it always takes the original path, so it never swallows a real question; the tests cover sentences that must not be intercepted such as "Hello Mingis, my card was stolen".
- In ordering, `force_handoff` and in-progress workflows come first, so a customer who is stuck is not sent back by a "hello".
- The reply is fixed text and does not vary with context; the price is predictability.

**Tests**: `tests/test_smalltalk.py`.

---

## ADR-019: Bilingual staff UI through a central string table and a hand-drawn navigation bar; ticket reasons translated at display time, with no database change

**Date**: 2026-11-20
**Status**: Adopted (Sprint 22)

**Background**: The whole platform (customer UI and four staff pages) should switch between Chinese and English. About 270 lines of code contained Chinese strings, with three awkward points: (1) Streamlit's page menu is generated from file names and cannot be translated; (2) the customer home page already had logic to "switch automatically by the language the customer types"; (3) a ticket's "reason" is stored in the database as Chinese text.

**Decision**:
- Put the text in one side-by-side Chinese/English string table (`frontend/strings.py`), used with `t("area.name")`, falling back to Chinese when English is missing.
- Hide Streamlit's built-in menu and draw the navigation bar with `st.page_link`, so the labels can be translated; the language switch sits under the navigation bar.
- The language lives in `session_state` and is also written to the URL as `?lang=`, so a refresh does not lose it.
- Customer home page: a manual switch wins; without one it follows the conversation language (Mingis's reply language still follows what the customer types).
- Ticket reasons stay in Chinese in the database; the fixed labels are translated through a lookup table **at display time**; what the customer typed is shown as written.

*(Later change, 2026-11-25: the default UI language is now English, with `?lang=zh` or the sidebar switch selecting Chinese. The mechanism above is unchanged.)*

**Reasons**:
- A central string table plus automated tests is easier to maintain than `if lang == "en"` scattered across pages, and it turns a "missed translation" into a test failure.
- Replacing the navigation bar is the only way to make the menu follow the language; the cost is losing Streamlit's own "current page" marker, which was restored with custom styling.
- No database change: storing the reasons as codes would mean migrating old data and touching the backend, a risk larger than this change's value.

**Trade-offs**:
- The ticket-reason lookup table is maintained by hand (`i18n.REASON_EN`). If the backend adds a reason label and forgets the English, the screen shows Chinese; `tests/test_i18n.py` compares `handoff.CATEGORY_LABEL` with the table and fails if one is missing.
- Part of the customer home page's text is still in `app.py`'s own string table rather than `strings.py`, because it already had a complete bilingual set; it was not moved this time, only its language decision rule changed.
- What is not translated is the data itself: customer conversations, agent replies, and knowledge-base entries.

---

## ADR-020: Verify that the data is sufficient before every FAQ answer, not only when the retrieval score is low

**Date**: 2026-11-21
**Status**: Adopted (Sprint 22)

**Background**: ADR-010 introduced the grounding verifier but called it only when the top retrieval score was below 0.60 (high-confidence retrievals skipped it to save latency). Testing found that a long overseas-refund question still scored 0.664 when the knowledge base had no answer; with verification skipped, the model answered from similar passages and added a reason the knowledge base does not contain. The measurement (see "Verification-policy measurement" in `docs/evaluation.md`) showed that the score ranges of gap questions and answerable questions overlap (gaps 0.54-0.76, answerable median 0.66), so no score threshold separates them; the existing rule caught only 5 of 12 real gaps.

**Options**:
- A: keep "verify only below 0.60".
- B: raise the threshold (0.75, 0.80…).
- C: verify before every FAQ answer.
- D: fold the verification into answer generation (one call; the model reports "insufficient data" itself).

**Decision**: C, keeping the environment variable `VERIFY_ALWAYS=0` as a way back; at the same time add to the answer rules "do not add reasons the knowledge base does not state, and do not attribute a fee or decision to a third party the knowledge base does not mention". Verification moves to `temperature=0`.

**Reasons**:
- B was equal to C in measurement: at a threshold of 0.80, 60 of the 62 answerable questions still needed verification, saving nothing, so the simple C was chosen directly.
- The verification itself is accurate (it judged all 12 real gaps "insufficient data"); the problem is only "when to run it".
- In a banking context, the cost of "not handing over when it should have" is higher than "handing over a few more".

**Trade-offs**:
- Latency: the time to first word of each FAQ answer rises by about 2-4 seconds (about 3 seconds in rehearsal); one more small-model call, at a very small cost.
- A higher handoff share: about 11 of the 62 answerable questions (18%) are handed over, 4 of which were correctly handed over because retrieval did not find the document, and about 7 (11%) are verification being stricter.
- D was not chosen: folding the judgement into the streamed answer would mean switching to a handoff in the middle of streaming and moving ticket creation out of the node, a large and risky change; and the independent verification has measurement evidence while self-reporting does not. Left as a future optimisation.
- **The suggested questions must be gated at the same time**: with stricter verification, a suggestion that cannot pass verification becomes a dead end. 7 of 77 did not pass (retrieval ranked the wrong passage first), were removed, and `tests/test_shortcuts_verified.py` prevents a regression.
- An unfixed underlying problem: those 7 show a **retrieval** weakness (cross-topic confusion). Verification only turns it from "silently answering wrongly" into "handing to a human"; it did not make retrieval better.

**Tests**: `tests/test_verify_always.py` (no model call: a high score is verified too, and with the switch off the behaviour returns to the old one), `tests/test_verifier.py` (the overseas-refund gap and the case after the rule was added), `tests/test_shortcuts_verified.py`.
