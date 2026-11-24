"""
LangGraph wiring — Sprint 6 (graph structure), Sprint 7 (real Account Node),
Sprint 9 (Router uses LLM intent classification)

    START
      │
      ▼
   router ──intent=card_loss──► card_loss ──────────────────► END
      │
      ├──intent=handoff────────► handoff ──► logger ─────────► END
      │
      ├──intent=handoff_intake─► handoff_intake ──escalated?──► logger ─► END
      │                              └──still collecting──────────────► END
      │
      ├──intent=smalltalk──────► smalltalk ───────────────────► END
      │
      ├──intent=bill_clarify───► bill_clarify ──escalated?──► logger ─► END
      │                              └──asking which item──────────────► END
      │
      ├──intent=faq────────────► qa ──has log_entries?──► logger ─► END
      │                             └──no────────────────────────► END
      │
      └──intent=account────────► account ──has log_entries?──► logger ─► END
                                     └──no────────────────────────────► END

Matches docs/agent_design.md §5. FAQ and Account are now independent
nodes (see nodes.py module docstring for the Sprint 6 -> 7 evolution).
"""

from langgraph.graph import END, StateGraph

from . import nodes as N
from .state import AgentState


def build_graph(client, retrievers: dict, kb: dict, model: str, max_tokens: int):
    router_node = N.make_router_node(client, model)
    qa_node = N.make_qa_node(client, retrievers, kb, model, max_tokens)
    account_node = N.make_account_node(client, retrievers, model, max_tokens)

    graph = StateGraph(AgentState)
    graph.add_node("router", router_node)
    graph.add_node("card_loss", N.card_loss_node)
    graph.add_node("handoff", N.handoff_node)
    graph.add_node("handoff_intake", N.handoff_intake_node)
    graph.add_node("bill_clarify", N.bill_clarify_node)
    graph.add_node("smalltalk", N.smalltalk_node)
    graph.add_node("qa", qa_node)
    graph.add_node("account", account_node)
    graph.add_node("logger", N.logger_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        lambda s: s["intent"],
        {"card_loss": "card_loss", "handoff": "handoff", "handoff_intake": "handoff_intake",
         "bill_clarify": "bill_clarify", "smalltalk": "smalltalk",
         "faq": "qa", "account": "account"},
    )
    graph.add_edge("card_loss", END)
    graph.add_edge("smalltalk", END)
    graph.add_edge("handoff", "logger")
    # Only the turn that actually escalates carries log_entries — the
    # question/re-ask turns are still an ongoing conversation, not an
    # unresolved query to log.
    graph.add_conditional_edges(
        "handoff_intake",
        lambda s: "logger" if s.get("log_entries") else END,
        {"logger": "logger", END: END},
    )
    graph.add_conditional_edges(
        "bill_clarify",
        lambda s: "logger" if s.get("log_entries") else END,
        {"logger": "logger", END: END},
    )
    graph.add_conditional_edges(
        "qa",
        lambda s: "logger" if s.get("log_entries") else END,
        {"logger": "logger", END: END},
    )
    graph.add_conditional_edges(
        "account",
        lambda s: "logger" if s.get("log_entries") else END,
        {"logger": "logger", END: END},
    )
    graph.add_edge("logger", END)

    return graph.compile()
