from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

from backend.agent.graph import build_graph


class ChatRequest(BaseModel):
    prompt: str
    thread_id: str = "default"
    prefixes: list[str] = ["SPAWS", "LGE"]
    mode: str = "TEAM"
    parent_link: str = ""
    filters: dict[str, list[str]] = {}


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
def ping():
    return {"status": "ok", "message": "pong"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    try:
        result = await request.app.state.graph.ainvoke(
            {
                "messages":    [HumanMessage(content=body.prompt)],
                "prefixes":    body.prefixes,
                "mode":        body.mode,
                "tickets":     [],
                "summaries":   [],
                "parent_link": body.parent_link,
                "filters":     body.filters,
            },
            config={"configurable": {"thread_id": body.thread_id}},
        )
        response_text = result["messages"][-1].content
        return ChatResponse(response=response_text, thread_id=body.thread_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
