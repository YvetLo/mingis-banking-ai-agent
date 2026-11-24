"""
Grounding verifier — Sprint 12.

Sprint 6-9's FAQ Node only ever asked "did any retrieved chunk clear a
similarity score line" (backend/src/rag/retriever.py's old
SIMILARITY_THRESHOLD). A diagnostic case study (see docs/design_journal.md
Sprint 12 entry) found this asks the wrong question: chunks can individually score above
any reasonable threshold while none of them actually answer the user's
question (the 外幣兌換 case — three chunks scored 0.42/0.38/0.32,
none about foreign currency exchange), AND the score bands for "genuine
gap" and "genuinely answerable" overlap (0.500 vs 0.482 in the measured
data), so no single global threshold can separate them.

This module asks the actual question instead: given the question and
the retrieved chunks (not the threshold score), can these chunks
actually answer it? Same forced-tool-call pattern as intent.py, so the
result is always a clean boolean, never free text to parse.

Only called when qa_node's top-1 retrieval score falls below
HIGH_CONFIDENCE_THRESHOLD — see nodes.py. Clearly-confident retrievals
skip this call entirely to keep it off the latency-critical path for
the majority of FAQ traffic (measured added latency: ~2.2-3.8s per
call, see docs/design_journal.md Sprint 12 entry).
"""

from ..tracing import traced_create

VERIFY_TOOL = {
    "name": "verify_groundedness",
    "description": "Judge whether the retrieved knowledge base chunks actually contain enough information to answer the user's question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sufficient": {
                "type": "boolean",
                "description": (
                    "True only if the chunks directly address what the user asked — not just the same "
                    "general topic. False if the chunks are about a related-but-different subject (e.g. "
                    "domestic transfer fees when the user asked about foreign currency cash exchange), or "
                    "don't contain the specific information needed."
                ),
            },
            "reason": {
                "type": "string",
                "description": "One short sentence explaining the judgment.",
            },
        },
        "required": ["sufficient", "reason"],
    },
}

VERIFIER_SYSTEM_PROMPT = """\
You are a strict grounding checker for a bank customer service knowledge base.
You will be given a user's question and the chunks retrieved for it.
Call verify_groundedness with your judgment — never respond with plain text.
Judge only whether the CHUNKS contain the answer, not whether a plausible-sounding
answer could be improvised. Being topically related is not enough — the chunks
must actually contain the specific information the question asks for.

Exception: for genuinely dynamic data that changes daily and could never be a
fixed number in a document (e.g. "what is the USD exchange rate right now"),
a chunk that provides a live-lookup channel (a URL, an app feature) for that
exact data counts as sufficient — the user doesn't need a literal number in
the text, they need to know where to get it. This does NOT apply to data that
should have a static answer (fees, limits, hours) but is simply missing."""


def verify_chunks_sufficient(client, model: str, question: str, chunks_text: str) -> tuple[bool, str]:
    result = traced_create(
        client, "verifier",
        model=model,
        max_tokens=100,
        temperature=0,   # a grounding verdict must be repeatable: the same question + chunks gave opposite answers at the default temperature
        system=VERIFIER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Question: {question}\n\nRetrieved chunks:\n{chunks_text}"}],
        tools=[VERIFY_TOOL],
        tool_choice={"type": "tool", "name": "verify_groundedness"},
    )
    for block in result.content:
        if block.type == "tool_use":
            return block.input["sufficient"], block.input.get("reason", "")
    return False, "verifier tool call did not return — failing closed"
