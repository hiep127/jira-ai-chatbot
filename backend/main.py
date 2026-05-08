from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

from backend.agent.graph import build_graph
from backend.agent.llm_factory import build_llm

logger = logging.getLogger(__name__)


class CompactRequest(BaseModel):
    thread_id: str


class CompactResponse(BaseModel):
    status: str
    message: str


class ChatRequest(BaseModel):
    prompt: str
    thread_id: str = "default"
    prefixes: list[str] = []
    mode: str = "TEAM"
    parent_link: str = ""
    custom_jql: str = ""


class ChatResponse(BaseModel):
    response: str
    thread_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle — sys.executable is the .exe, not Python,
        # so the stdio MCP subprocess cannot be started. Boot without tools.
        app.state.graph = build_graph([])
        yield
    else:
        async with MultiServerMCPClient(
            {
                "jira": {
                    "command": sys.executable,
                    "args": ["tools/mock_jira_mcp.py"],
                    "transport": "stdio",
                }
            }
        ) as mcp_client:
            tools = mcp_client.get_tools()
            app.state.graph = build_graph(tools)
            yield


app = FastAPI(lifespan=lifespan)


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok", "message": "pong"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    try:
        result = await request.app.state.graph.ainvoke(
            {
                "messages":             [HumanMessage(content=body.prompt)],
                "prefixes":             body.prefixes,
                "mode":                 body.mode,
                "tickets":              [],
                "summaries":            [],
                "ticket_summaries":     [],
                "parent_link":          body.parent_link,
                "custom_jql":           body.custom_jql,
            },
            config={"configurable": {"thread_id": body.thread_id}},
        )
        response_text = result["messages"][-1].content
        return ChatResponse(response=response_text, thread_id=body.thread_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compact", response_model=CompactResponse)
async def compact(body: CompactRequest, request: Request) -> CompactResponse:
    config = {"configurable": {"thread_id": body.thread_id}}

    # ── Step 1: Read current thread state ──────────────────────────────────
    try:
        state = await request.app.state.graph.aget_state(config)
    except Exception as e:
        logger.error("[/compact] aget_state failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read thread state: {e}. Restart the application or check server logs at backend/main.py.",
        )

    old_messages = state.values.get("messages", [])

    # ── Guardrail ───────────────────────────────────────────────────────────
    if len(old_messages) < 4:
        return CompactResponse(status="skipped", message="Not enough messages to compress.")

    # ── Step 2: LLM summarization call ─────────────────────────────────────
    try:
        llm = build_llm()
        summary_prompt = (
            "Summarise the following conversation in 3-5 sentences. "
            "Preserve key facts, decisions, and open questions.\n\n"
            + "\n".join(f"{m.__class__.__name__}: {m.content}" for m in old_messages)
        )
        summary_response = await llm.ainvoke([HumanMessage(content=summary_prompt)])
        summary_text = summary_response.content
    except Exception as e:
        logger.error("[/compact] LLM summarization failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Summarization failed: {e}. Verify your AI provider credentials are configured correctly in Settings.",
        )

    # ── Step 3: State mutation — prune old messages, insert summary ─────────
    remove_ops = [RemoveMessage(id=m.id) for m in old_messages]
    new_summary_msg = SystemMessage(content=f"[Compacted history] {summary_text}")

    try:
        await request.app.state.graph.aupdate_state(
            config,
            {"messages": remove_ops + [new_summary_msg]},
        )
    except Exception as e:
        logger.error("[/compact] aupdate_state failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write compacted state: {e}. This may indicate a corrupted checkpoint. Try starting a new conversation.",
        )

    return CompactResponse(status="success", message="Context compacted.")
