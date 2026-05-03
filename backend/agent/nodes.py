from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Send

from backend.agent.llm_factory import build_llm

MAX_TOOL_ROUNDS = 5

# ---------------------------------------------------------------------------
# System prompts (sourced from agents/backlog-summary.agent.md)
# ---------------------------------------------------------------------------

_ORCHESTRATOR_FETCH_PROMPT = """\
You are the Global Backlog Orchestrator.
Your only task right now is to call get_tickets_by_batch with the prefixes and \
mode you have been given. Call the tool immediately — do not write any prose first.\
"""

_ORCHESTRATOR_COMPILE_PROMPT = """\
You are the Global Backlog Orchestrator.
You have received per-ticket Technical Pulse summaries from the Daily Summarizer.
Build the High-Density markdown table:

| Ticket (Link) | Instance | Status | Pulse (from latest comment) | Blocker |
| :--- | :--- | :--- | :--- | :--- |

URL rules:
- LGE tickets (DVDNAIVI, AUDIODV, REAVN, DNSD): https://jira.lge.com/issue/browse/{KEY}
- SPAWS tickets: https://spaws.jp.nissan.biz/jira/browse/{KEY}

Pulse icons: 🔍 under analysis  🟢 resolved/done  🚨 critical blocker  ⏳ waiting

Use ONLY data supplied by the sub-agent — never fabricate.
After building the table call save_summary_to_linux with \
ticket_key="GLOBAL" and filename="backlog_sync.md".\
"""

_SUMMARIZER_PROMPT = """\
You are the Daily Summarizer sub-agent. Your job is to deeply understand a Jira \
ticket and produce a concise, insightful summary — not just extract raw text.

Steps:
1. Call fetch_ticket_metadata for the given ticket (comment_limit=15).
2. Read the ticket description, status, and all comments carefully.
3. Using your reasoning, synthesize:
   - A 1-sentence Pulse: what is the team actually working on or discussing RIGHT NOW?
     Capture the technical essence, not just a restatement of the title.
     If there are no comments write exactly: No recent activity.
   - A Blocker: any explicit impediment mentioned (one word/phrase), or — if none.
4. Reply with ONE line in this exact pipe-delimited format (no markdown):
   TICKET_KEY | INSTANCE | STATUS | PULSE | BLOCKER

Good Pulse examples:
  "Team is investigating a NullPointerException in AudioService.init() on build 4.2.1."
  "Waiting for hardware team to confirm audio focus regression reproduces on latest firmware."
Bad Pulse (do not do this):
  "Reproduced on build 4.2.1. Looks like a null-pointer in AudioService.init()." — this
  is just a raw copy of a comment, not a synthesis.

Do NOT copy-paste comment text verbatim. Reason about what is happening and summarise it.\
"""


# ---------------------------------------------------------------------------
# Fallback: simple single-agent nodes (used when no tools are available)
# ---------------------------------------------------------------------------

def make_llm_node(tools: list):
    """Single-agent node — used as fallback when MCP tools are unavailable."""
    def node(state: dict) -> dict:
        llm = build_llm()
        bound = llm.bind_tools(tools) if tools else llm
        response = bound.invoke(state["messages"])
        return {"messages": [response]}
    return node


def route_after_llm(state: dict) -> str:
    last = state["messages"][-1]
    tool_rounds = sum(
        1 for m in state["messages"]
        if hasattr(m, "tool_calls") and m.tool_calls
    )
    if tool_rounds >= MAX_TOOL_ROUNDS:
        return END
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


# ---------------------------------------------------------------------------
# Orchestrator nodes
# ---------------------------------------------------------------------------

def make_orchestrator_fetch_node(fetch_tool):
    """Instructs the LLM to call get_tickets_by_batch with the filter config."""
    def node(state: dict) -> dict:
        prefixes    = state.get("prefixes",    ["SPAWS", "LGE"])
        mode        = state.get("mode",        "TEAM")
        parent_link = state.get("parent_link", "")
        filters     = state.get("filters",     {})

        context = f"Fetch all tickets for prefixes={prefixes}, mode='{mode}'."
        if parent_link:
            context += f" parent_link='{parent_link}'."
        if filters:
            context += f" filters={filters}."
        context += " Call get_tickets_by_batch now."

        llm = build_llm().bind_tools([fetch_tool])
        messages = [
            SystemMessage(content=_ORCHESTRATOR_FETCH_PROMPT),
            HumanMessage(content=context),
        ]
        response = llm.invoke(messages)
        return {"messages": [response]}
    return node


def route_after_orchestrator_fetch(state: dict) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "orchestrator_tools"
    return END


def parse_tickets_node(state: dict) -> dict:
    """Extract the flat ticket list from the get_tickets_by_batch ToolMessage."""
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage):
            raw = msg.content
            if isinstance(raw, list):
                raw = " ".join(
                    block.get("text", "") for block in raw if isinstance(block, dict)
                )
            try:
                data = json.loads(raw)
                tickets: list[dict] = []
                for prefix_tickets in data.get("data", {}).values():
                    tickets.extend(prefix_tickets)
                return {"tickets": tickets}
            except (json.JSONDecodeError, AttributeError):
                pass
    return {"tickets": []}


def dispatch_to_summarizer(state: dict):
    """Fan-out: send one message per ticket to the summarizer sub-graph."""
    tickets = state.get("tickets", [])
    if not tickets:
        return END
    return [
        Send("summarizer", {"messages": [], "ticket": t, "summaries": []})
        for t in tickets
    ]


def make_orchestrator_compile_node(save_tool):
    """Compiles all per-ticket summaries into the final table and saves it."""
    def node(state: dict) -> dict:
        summaries = state.get("summaries", [])
        summaries_text = "\n".join(f"[{i + 1}] {s}" for i, s in enumerate(summaries))
        llm = build_llm().bind_tools([save_tool])
        messages = [
            SystemMessage(content=_ORCHESTRATOR_COMPILE_PROMPT),
            HumanMessage(content=(
                "Here are the per-ticket summaries from the Daily Summarizer:\n\n"
                f"{summaries_text}\n\n"
                "Build the High-Density table, then save it."
            )),
        ]
        response = llm.invoke(messages)
        return {"messages": [response]}
    return node


def route_after_compile(state: dict) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "save_tools"
    return END


# ---------------------------------------------------------------------------
# Summarizer sub-graph nodes
# ---------------------------------------------------------------------------

def make_summarizer_node(fetch_tool):
    """Summarizer LLM — fetches metadata then synthesizes a Pulse summary."""
    def node(state: dict) -> dict:
        ticket = state.get("ticket", {})
        ticket_key = ticket.get("key", "UNKNOWN")
        messages = list(state.get("messages", []))

        if not messages:
            messages = [
                SystemMessage(content=_SUMMARIZER_PROMPT),
                HumanMessage(content=(
                    f"Ticket key: {ticket_key}\n"
                    f"Title: {ticket.get('summary', 'N/A')}\n"
                    "Call fetch_ticket_metadata now."
                )),
            ]

        llm = build_llm().bind_tools([fetch_tool])
        response = llm.invoke(messages)
        return {"messages": [response]}
    return node


def route_after_summarizer(state: dict) -> str:
    last = state["messages"][-1]
    tool_rounds = sum(
        1 for m in state["messages"]
        if hasattr(m, "tool_calls") and m.tool_calls
    )
    if tool_rounds >= MAX_TOOL_ROUNDS:
        return "extract_summary"
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "summarizer_tools"
    return "extract_summary"


def extract_summary_node(state: dict) -> dict:
    """Pull the synthesized summary line and write it to state.summaries."""
    for msg in reversed(state["messages"]):
        if (
            hasattr(msg, "content")
            and msg.content
            and not (hasattr(msg, "tool_calls") and msg.tool_calls)
            and not isinstance(msg, (SystemMessage, ToolMessage))
        ):
            return {"summaries": [str(msg.content)]}
    ticket_key = state.get("ticket", {}).get("key", "UNKNOWN")
    return {"summaries": [f"{ticket_key} | UNKNOWN | UNKNOWN | No summary generated. | —"]}
