from __future__ import annotations

import asyncio
import logging
import re
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

from backend.agent.graph import build_graph
from backend.agent.llm_factory import build_llm

logger = logging.getLogger(__name__)


class ModelInfo(BaseModel):
    id: str
    name: str
    vendor: str
    tier: str
    is_other: bool


class CompactRequest(BaseModel):
    thread_id: str
    model_id: str = ""


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
    model_id: str = ""


class ChatResponse(BaseModel):
    response: str
    thread_id: str


class PingResponse(BaseModel):
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str


class GitHubAuthStatusResponse(BaseModel):
    authenticated: bool


class GitHubSpawnTerminalResponse(BaseModel):
    status: str
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller bundle — sys.executable is the .exe, not Python,
        # so the stdio MCP subprocess cannot be started. Boot without tools.
        app.state.graph = build_graph([])
        app.state.models_cache = None
        yield
    else:
        try:
            async with MultiServerMCPClient(
                {
                    "jira": {
                        "command": sys.executable,
                        "args": ["tools/jira_tool.py"],
                        "transport": "stdio",
                    }
                }
            ) as mcp_client:
                tools = mcp_client.get_tools()
                app.state.graph = build_graph(tools)
                app.state.models_cache = None
                yield
        except Exception as exc:
            logger.critical(
                "[startup] Live jira-harness MCP server failed to connect: %s. "
                "Ensure tools/jira_tool.py is present and its dependencies are installed. "
                "Aborting startup.",
                exc,
            )
            raise


app = FastAPI(lifespan=lifespan)


@app.get("/ping")
async def ping() -> PingResponse:
    return PingResponse(status="ok", message="pong")


@app.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="healthy")


@app.get("/auth/github/status")
async def github_auth_status(force: bool = False) -> GitHubAuthStatusResponse:
    from backend.utils.github_auth import check_auth
    authenticated = await asyncio.to_thread(check_auth, force)
    return GitHubAuthStatusResponse(authenticated=authenticated)


@app.post("/auth/github/spawn-terminal")
async def spawn_github_terminal() -> GitHubSpawnTerminalResponse:
    try:
        from backend.utils.github_auth import spawn_windows_auth_terminal
        spawn_windows_auth_terminal()
        return GitHubSpawnTerminalResponse(status="ok", message="Terminal window opened.")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open terminal: {e}. Ensure cmd.exe is accessible on this system.",
        )


@app.get("/models", response_model=list[ModelInfo])
async def list_models(refresh: bool = False, request: Request = None) -> list[ModelInfo]:
    from backend.utils.github_auth import check_auth, get_local_github_token
    if not await asyncio.to_thread(check_auth):
        raise HTTPException(status_code=401, detail="GitHub CLI not authenticated.")

    if not refresh and request.app.state.models_cache is not None:
        return request.app.state.models_cache

    token = await asyncio.to_thread(get_local_github_token)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.githubcopilot.com/models",
                headers={"Authorization": f"Bearer {token}"},
            )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to reach Copilot API: {e}")

    body = r.json()
    raw_models: list[dict] = body.get("data", body.get("models", []))
    if raw_models:
        logger.info("[models] sample raw entry: %s", raw_models[0])

    _PRIMARY_PREFIXES = ("claude-", "gpt-", "o")

    _DATE_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$")

    def _map(m: dict) -> ModelInfo:
        model_id = m.get("id", "")
        return ModelInfo(
            id=model_id,
            name=m.get("name", model_id),
            vendor=m.get("vendor", ""),
            tier=m.get("billing_class") or m.get("model_picker_description") or "standard",
            is_other=not any(model_id.startswith(p) for p in _PRIMARY_PREFIXES),
        )

    models = [_map(m) for m in raw_models]

    # Deduplicate by name: prefer the entry whose id has no date-version suffix
    seen: dict[str, ModelInfo] = {}
    for m in models:
        existing = seen.get(m.name)
        if existing is None or (_DATE_SUFFIX.search(existing.id) and not _DATE_SUFFIX.search(m.id)):
            seen[m.name] = m
    models = list(seen.values())

    def _sort_key(m: ModelInfo) -> tuple:
        return (0 if m.id == "gpt-4o" else 1, m.name.lower())

    models.sort(key=_sort_key)
    request.app.state.models_cache = models
    return models


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    from backend.utils.github_auth import check_auth
    if not await asyncio.to_thread(check_auth):
        raise HTTPException(
            status_code=401,
            detail="GitHub CLI not authenticated. Run 'gh auth login' to authenticate.",
        )
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
                "model_id":             body.model_id,
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
        llm = build_llm(model_id=body.model_id)
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
