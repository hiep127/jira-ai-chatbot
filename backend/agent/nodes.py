from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.types import Command, Send

from backend.agent.llm_factory import call_copilot
from backend.agent.state import TicketState

MAX_TOOL_ROUNDS = 5

logger = logging.getLogger(__name__)


def _extract_text(result: Any) -> str:
    """Extract plain text from an MCP tool ainvoke result.

    langchain-mcp-adapters 0.2+ returns a list of content-block dicts
    (e.g. [{'type': 'text', 'text': '...', 'id': '...'}]), not a plain string.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                return item["text"]
    return str(result)

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
You receive ONE ticket key and its full metadata JSON. Your steps:
1. From the JSON extract: KEY, STATUS, ASSIGNEE, SUMMARY, latest 5 comments.
2. Determine INSTANCE: "LGE" if prefix in {DVDNAIVI, AUDIODV, REAVN, DNSD}, else "SPAWS".
3. Synthesise a 1-sentence PULSE: what is the team actually doing RIGHT NOW?
   Reason from the comments — do NOT copy-paste verbatim. If no comments: "No recent activity."
4. Identify BLOCKER: one word/phrase for any explicit impediment, or "—" if none.
5. Output EXACTLY ONE pipe-delimited line — no prose, no markdown, no extra lines:
   TICKET_KEY | INSTANCE | STATUS | PULSE | BLOCKER\
"""


# ---------------------------------------------------------------------------
# Fallback: simple single-agent nodes (used when no tools are available)
# ---------------------------------------------------------------------------

def make_llm_node(tools: list[Any]) -> Callable[[dict], dict]:
    """Single-agent node — used as fallback when MCP tools are unavailable."""
    async def node(state: dict) -> dict:
        history = "\n".join(
            f"{m.__class__.__name__}: {m.content}"
            for m in state["messages"]
            if hasattr(m, "content") and m.content
        )
        result = await call_copilot(prompt=history, model_id=state.get("model_id", ""))
        return {"messages": [AIMessage(content=result)]}
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
# v4 Map-Reduce orchestrator nodes
# ---------------------------------------------------------------------------

_LGE_PREFIXES = {"DVDNAIVI", "AUDIODV", "REAVN", "DNSD"}
_CLOSED_STATUSES = {"Closed", "Integrated", "Merged_VLM", "Done"}


def make_discovery_and_dispatch_node(batch_tool: Any) -> Callable[[dict], Command]:
    """Python-only node: fetch ticket keys via batch tool, filter, fan-out via Send."""
    async def node(state: dict) -> Command:
        prefixes = state.get("prefixes", ["SPAWS", "LGE"])
        mode = state.get("mode", "TEAM")
        custom_jql = state.get("custom_jql", "")

        try:
            result = await batch_tool.ainvoke(
                {"args": {"prefixes": prefixes, "mode": mode, "custom_jql": custom_jql}}
            )
            raw = _extract_text(result)
        except Exception as e:
            return Command(
                update={"messages": [AIMessage(content=(
                    f"ERROR: Batch fetch failed — {e}. "
                    "Verify JIRA credentials in jira_server.env."
                ))]},
                goto="aggregate_summary_node",
            )

        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            tickets: list[dict] = []
            for prefix_tickets in data.get("data", {}).values():
                if isinstance(prefix_tickets, list):
                    tickets.extend(prefix_tickets)
        except (json.JSONDecodeError, AttributeError) as e:
            return Command(
                update={"messages": [AIMessage(content=(
                    f"ERROR: Failed to parse batch response — {e}. "
                    "Check get_tickets_by_batch tool output format."
                ))]},
                goto="aggregate_summary_node",
            )

        valid_keys = [
            t["key"] for t in tickets
            if not t.get("key", "").startswith("CCC-")
            and not t.get("summary", "").startswith("CCC-")
        ]

        if not valid_keys:
            return Command(
                update={"messages": [AIMessage(content="No actionable tickets found after filtering.")]},
                goto="aggregate_summary_node",
            )

        return Command(goto=[Send("ticket_summarizer_node", {"ticket_id": k}) for k in valid_keys])

    return node


def make_ticket_summarizer_node(fetch_tool: Any) -> Callable[[TicketState], dict]:
    """Fetch ticket metadata, budget context locally, then summarise with a plain LLM call."""
    async def node(state: TicketState) -> dict:
        ticket_id: str = state["ticket_id"]

        try:
            tool_result = await fetch_tool.ainvoke(
                {"args": {"ticket_key": ticket_id, "comment_limit": 5}}
            )
            raw = _extract_text(tool_result)
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if parsed.get("status") != "SUCCESS":
                raise Exception(f"Jira tool returned non-SUCCESS status: {parsed.get('status')}")
            data = parsed["data"]
            slim = {
                "title":       data.get("summary", "N/A"),
                "description": (data.get("description") or "No description.")[:2000],
                "comments":    [c["body"] for c in data.get("comments", [])[:5]],
            }
            summary = await call_copilot(
                prompt=f"Ticket key: {ticket_id}\n\nMetadata JSON:\n{json.dumps(slim, indent=2)}",
                model_id=state.get("model_id", ""),
                system_prompt=_SUMMARIZER_DAILY_PROMPT,
            )
            return {"ticket_summaries": [summary]}

        except Exception as e:
            fallback = (
                f"{ticket_id} | ERROR | ERROR | "
                f"Summarizer failed — {e}. Check provider credentials in Settings. | —"
            )
            return {"ticket_summaries": [fallback]}

    return node


def make_aggregate_and_report_node(save_tool: Any) -> Callable[[dict], dict]:
    """Python-only node: parse accumulated summaries, build Markdown table, save, return."""
    async def node(state: dict) -> dict:
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
            await save_tool.ainvoke(
                {"args": {"ticket_key": "GLOBAL", "filename": "backlog_sync.md", "content": table}}
            )
        except Exception as e:
            logger.warning(
                "[aggregate] save failed — %s. "
                "Check Linux workspace path and permissions.", e
            )

        return {"messages": [AIMessage(content=table)]}

    return node
