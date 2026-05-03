from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from backend.agent.nodes import (
    dispatch_to_summarizer,
    extract_summary_node,
    make_llm_node,
    make_orchestrator_compile_node,
    make_orchestrator_fetch_node,
    make_summarizer_node,
    parse_tickets_node,
    route_after_compile,
    route_after_llm,
    route_after_orchestrator_fetch,
    route_after_summarizer,
)
from backend.agent.state import AgentState, SummarizerState


def _build_summarizer_subgraph(fetch_tool):
    """Per-ticket summarizer: fetch metadata → synthesize Pulse → extract."""
    sg = StateGraph(SummarizerState)

    sg.add_node("summarizer_llm", make_summarizer_node(fetch_tool))
    sg.add_node("summarizer_tools", ToolNode([fetch_tool]))
    sg.add_node("extract_summary", extract_summary_node)

    sg.add_edge(START, "summarizer_llm")
    sg.add_conditional_edges(
        "summarizer_llm",
        route_after_summarizer,
        {"summarizer_tools": "summarizer_tools", "extract_summary": "extract_summary"},
    )
    sg.add_edge("summarizer_tools", "summarizer_llm")
    sg.add_edge("extract_summary", END)

    return sg.compile()


def build_graph(tools: list):
    """Build and compile the agent graph.

    Full orchestrator flow (when all three MCP tools are present):
        START
          → orchestrator_fetch  (calls get_tickets_by_batch)
          → orchestrator_tools  (executes the batch fetch)
          → parse_tickets       (extracts flat ticket list → state.tickets)
          → [Send fan-out] summarizer × N  (one per ticket, parallel)
          → orchestrator_compile (builds High-Density table, calls save_summary_to_linux)
          → save_tools          (executes the save call)
          → END

    Fallback (no tools or missing critical tools): simple single-LLM loop.
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

    summarizer_subgraph = _build_summarizer_subgraph(metadata_tool)

    graph = StateGraph(AgentState)

    graph.add_node("orchestrator_fetch", make_orchestrator_fetch_node(batch_tool))
    graph.add_node("orchestrator_tools", ToolNode([batch_tool]))
    graph.add_node("parse_tickets", parse_tickets_node)
    graph.add_node("summarizer", summarizer_subgraph)
    graph.add_node("orchestrator_compile", make_orchestrator_compile_node(save_tool))
    graph.add_node("save_tools", ToolNode([save_tool]))

    graph.add_edge(START, "orchestrator_fetch")
    graph.add_conditional_edges(
        "orchestrator_fetch",
        route_after_orchestrator_fetch,
        {"orchestrator_tools": "orchestrator_tools", END: END},
    )
    graph.add_edge("orchestrator_tools", "parse_tickets")
    graph.add_conditional_edges(
        "parse_tickets",
        dispatch_to_summarizer,
        ["summarizer"],
    )
    graph.add_edge("summarizer", "orchestrator_compile")
    graph.add_conditional_edges(
        "orchestrator_compile",
        route_after_compile,
        {"save_tools": "save_tools", END: END},
    )
    graph.add_edge("save_tools", END)

    return graph.compile(checkpointer=MemorySaver())
