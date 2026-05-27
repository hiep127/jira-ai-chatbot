from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from backend.agent.nodes import (
    make_aggregate_and_report_node,
    make_discovery_and_dispatch_node,
    make_llm_node,
    make_ticket_summarizer_node,
    route_after_llm,
)
from backend.agent.state import AgentState


def build_graph(tools: list[Any]) -> Any:
    """Build and compile the agent graph.

    Full orchestrator flow (when all three MCP tools are present):
        START
          → discovery_and_dispatch   (Python: batch fetch + CCC filter → Send fan-out)
          → ticket_summarizer_node × N (LLM + fetch_tool, parallel)
          → aggregate_summary_node   (Python: filter + build Markdown table + save)
          → END

    Fallback (missing critical tools): simple single-LLM loop.
    """
    tools_by_name = {t.name: t for t in tools}
    batch_tool = tools_by_name.get("get_tickets_by_batch")
    metadata_tool = tools_by_name.get("fetch_ticket_metadata")
    save_tool = tools_by_name.get("save_summary_to_linux")

    if not batch_tool or not metadata_tool or not save_tool:
        graph = StateGraph(AgentState)
        graph.add_node("llm", make_llm_node(tools))
        if tools:
            graph.add_node("tools", ToolNode(tools))
            graph.add_conditional_edges("llm", route_after_llm, {"tools": "tools", END: END})
            graph.add_edge("tools", "llm")
        else:
            graph.add_edge("llm", END)
        graph.add_edge(START, "llm")
        return graph.compile(checkpointer=MemorySaver())

    graph = StateGraph(AgentState)

    graph.add_node("discovery_and_dispatch",
                   make_discovery_and_dispatch_node(batch_tool))
    graph.add_node("ticket_summarizer_node",
                   make_ticket_summarizer_node(metadata_tool))
    graph.add_node("aggregate_summary_node",
                   make_aggregate_and_report_node(save_tool))

    graph.add_edge(START, "discovery_and_dispatch")

    graph.add_edge("ticket_summarizer_node", "aggregate_summary_node")
    graph.add_edge("aggregate_summary_node", END)

    return graph.compile(checkpointer=MemorySaver())
