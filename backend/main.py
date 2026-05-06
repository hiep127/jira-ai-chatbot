from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from pydantic import BaseModel

from backend.agent.graph import build_graph
from backend.utils.jql_parser import parse_jql as _parse_jql


class ChatRequest(BaseModel):
    prompt: str
    thread_id: str = "default"
    prefixes: list[str] = []
    mode: str = "TEAM"
    parent_link: str = ""
    filters: dict[str, list[str]] = {}
    selected_filter_keys: list[str] = []


class ChatResponse(BaseModel):
    response: str
    thread_id: str


class JQLParseRequest(BaseModel):
    jql: str


class FilterRow(BaseModel):
    field: str
    operator: str
    value: list[str]


class JQLParseResponse(BaseModel):
    rows: list[FilterRow]


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
                "messages":             [HumanMessage(content=body.prompt)],
                "prefixes":             body.prefixes,
                "mode":                 body.mode,
                "tickets":              [],
                "summaries":            [],
                "parent_link":          body.parent_link,
                "filters":              body.filters,
                "selected_filter_keys": body.selected_filter_keys,
            },
            config={"configurable": {"thread_id": body.thread_id}},
        )
        response_text = result["messages"][-1].content
        return ChatResponse(response=response_text, thread_id=body.thread_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filters/parse-jql", response_model=JQLParseResponse)
async def parse_jql_endpoint(payload: JQLParseRequest) -> JQLParseResponse:
    try:
        rows = _parse_jql(payload.jql.strip())
        return JQLParseResponse(rows=[FilterRow(**r) for r in rows])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
