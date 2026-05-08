from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END
from langgraph.types import Send

from backend.agent.llm_factory import build_llm, build_summarizer_llm
from backend.agent.state import TicketState

MAX_TOOL_ROUNDS = 5

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

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

_SUMMARIZER_DAILY_PROMPT = """\
You are the Summarizer Agent (Audio Framework Specialist).
You receive ONE ticket key. Your steps:
1. Call fetch_ticket_metadata for the given ticket (comment_limit=5).
2. From the JSON response extract: KEY, STATUS, ASSIGNEE, SUMMARY, latest 5 comments.
3. Determine INSTANCE: "LGE" if prefix in {DVDNAIVI, AUDIODV, REAVN, DNSD}, else "SPAWS".
4. Synthesise a 1-sentence PULSE: what is the team actually doing RIGHT NOW?
   Reason from the comments — do NOT copy-paste verbatim. If no comments: "No recent activity."
5. Identify BLOCKER: one word/phrase for any explicit impediment, or "—" if none.
6. Output EXACTLY ONE pipe-delimited line — no prose, no markdown, no extra lines:
   TICKET_KEY | INSTANCE | STATUS | PULSE | BLOCKER\
"""


# ---------------------------------------------------------------------------
# Fallback: simple single-agent nodes (used when no tools are available)
# ---------------------------------------------------------------------------

def make_llm_node(tools: list[Any]) -> Callable[[dict], dict]:
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
# Summarizer sub-graph nodes (kept; used by legacy fallback path)
# ---------------------------------------------------------------------------

def make_summarizer_node(fetch_tool: Any) -> Callable[[dict], dict]:
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


# ---------------------------------------------------------------------------
# v4 Map-Reduce orchestrator nodes
# ---------------------------------------------------------------------------

_LGE_PREFIXES = {"DVDNAIVI", "AUDIODV", "REAVN", "DNSD"}
_CLOSED_STATUSES = {"Closed", "Integrated", "Merged_VLM", "Done"}


def make_discovery_and_dispatch_node(batch_tool: Any) -> Callable[[dict], Any]:
    """Python-only node: fetch ticket keys via batch tool, filter, fan-out via Send."""
    def node(state: dict) -> Any:
        prefixes = state.get("prefixes", ["SPAWS", "LGE"])
        mode = state.get("mode", "TEAM")
        custom_jql = state.get("custom_jql", "")

        try:
            raw = batch_tool.invoke({"prefixes": prefixes, "mode": mode, "custom_jql": custom_jql})
        except Exception as e:
            return {
                "messages": [AIMessage(content=(
                    f"ERROR: Batch fetch failed — {e}. "
                    "Verify JIRA credentials in jira_server.env."
                ))]
            }

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            tickets: list[dict] = []
            for prefix_tickets in data.get("data", {}).values():
                if isinstance(prefix_tickets, list):
                    tickets.extend(prefix_tickets)
        except (json.JSONDecodeError, AttributeError) as e:
            return {
                "messages": [AIMessage(content=(
                    f"ERROR: Failed to parse batch response — {e}. "
                    "Check get_tickets_by_batch tool output format."
                ))]
            }

        valid_keys = [
            t["key"] for t in tickets
            if not t.get("key", "").startswith("CCC-")
            and not t.get("summary", "").startswith("CCC-")
        ]

        if not valid_keys:
            return {
                "messages": [AIMessage(content="No actionable tickets found after filtering.")]
            }

        return [Send("summarizer_daily", {"ticket_key": k}) for k in valid_keys]

    return node


def make_summarizer_daily_node(fetch_tool: Any) -> Callable[[TicketState], dict]:
    """LLM + tool loop node: fetch one ticket's metadata, synthesise to a pipe-delimited line."""
    def node(state: TicketState) -> dict:
        ticket_key: str = state["ticket_key"]

        try:
            messages: list = [
                SystemMessage(content=_SUMMARIZER_DAILY_PROMPT),
                HumanMessage(content=f"Ticket key: {ticket_key}"),
            ]
            llm = build_summarizer_llm().bind_tools([fetch_tool])

            for _ in range(3):
                response = llm.invoke(messages)
                if not (hasattr(response, "tool_calls") and response.tool_calls):
                    break
                messages.append(response)
                for tool_call in response.tool_calls:
                    logger.debug("[summarizer_daily] tool_call args: %s", tool_call["args"])
                    result = fetch_tool.invoke(tool_call["args"])
                    messages.append(
                        ToolMessage(content=str(result), tool_call_id=tool_call["id"])
                    )

            return {"ticket_summaries": [str(response.content)]}

        except Exception as e:
            fallback = (
                f"{ticket_key} | ERROR | ERROR | "
                f"Summarizer failed — {e}. Check provider credentials in Settings. | —"
            )
            return {"ticket_summaries": [fallback]}

    return node


def make_aggregate_and_report_node(save_tool: Any) -> Callable[[dict], dict]:
    """Python-only node: parse accumulated summaries, build Markdown table, save, return."""
    def node(state: dict) -> dict:
        lge_base = os.getenv("JIRA_LGE_BASE_URL", "")
        spaws_base = os.getenv("JIRA_SPAWS_BASE_URL", "")

        if not lge_base or not spaws_base:
            logger.warning(
                "[aggregate] JIRA_LGE_BASE_URL or JIRA_SPAWS_BASE_URL not set. "
                "Add them to tools/jira_server.env to generate clickable ticket links."
            )

        rows: list[tuple[str, str, str, str, str]] = []
        for line in state.get("ticket_summaries", []):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 5:
                continue
            key, instance, status, pulse, blocker = parts[0], parts[1], parts[2], parts[3], parts[4]
            if key.startswith("CCC-") or status in _CLOSED_STATUSES:
                continue
            rows.append((key, instance, status, pulse, blocker))

        if rows:
            header = (
                "| Ticket (Link) | Instance | Status | Pulse | Blocker |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
            )
            body_lines: list[str] = []
            for key, instance, status, pulse, blocker in rows:
                prefix = key.split("-")[0]
                base = lge_base if prefix in _LGE_PREFIXES else spaws_base
                url = f"{base}{key}" if base else key
                body_lines.append(f"| [{key}]({url}) | {instance} | {status} | {pulse} | {blocker} |")
            table = header + "\n".join(body_lines)
        else:
            table = "No active tickets after filtering."

        try:
            save_tool.invoke({
                "ticket_key": "GLOBAL",
                "filename": "backlog_sync.md",
                "content": table,
            })
        except Exception as e:
            logger.warning(
                "[aggregate] save failed — %s. "
                "Check Linux workspace path and permissions.", e
            )

        return {"messages": [AIMessage(content=table)]}

    return node
