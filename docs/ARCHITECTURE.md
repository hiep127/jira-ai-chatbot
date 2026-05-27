# Jira App Architecture & Engineering Standards

All proposed feature plans MUST strictly adhere to these 5 core rules. If a plan violates any of these, it is critically flawed and must be rejected.

## 1. Strict Layered Architecture (Separation of Concerns)
- **Frontend (`app/ui/`):** Purely Flet UI components. NO direct database or API calls here. UI components only trigger state changes or API requests.
- **Backend (`app/api/`):** FastAPI routes. Must use standard Pydantic models for validation.
- **Orchestration (`agents/`):** LangGraph nodes and state definitions. 
- **Tools (`tools/`):** MCP servers and standalone Python scripts for specific tasks.

## 2. Context Budgeting (The Context Lifeline)
- **Rule:** LLM context windows are expensive and limited. Jira API responses are massive.
- **Requirement:** NO raw Jira JSON payloads may be passed directly to the frontend or the LLM. 
- **Solution:** All plans interacting with Jira MUST specify a parsing/truncation step to extract ONLY the requested keys (e.g., `issue_key`, `summary`, `status`) before returning data.

## 3. Actionable Observability
- **Rule:** No silent failures. No generic "An error occurred."
- **Requirement:** All network calls (especially Jira/FastAPI) must be wrapped in explicit `try/except` blocks.
- **Solution:** Errors must be caught and logged with actionable remediation steps (e.g., "Error 401: Token expired. Check JIRA_PAT in .env").

## 4. Mathematical Precision & State Safety
- **Rule:** Vague plans result in hallucinated code.
- **Requirement:** Plans must list exact file paths to be modified.
- **Requirement:** If modifying LangGraph state, the plan must explicitly state how the `AgentState` TypedDict is updated to prevent infinite routing loops.

## 5. Security & Credentials
- **Rule:** No hardcoded tokens, passwords, or URLs.
- **Requirement:** All credentials must be loaded via `os.getenv()` or an MCP-provided secure context.

---

## Project Structure

```
AI Chatbot/
├── CLAUDE.md                ← Claude Code guidance and workflow rules
├── CODING_STANDARDS.md      ← App code standards (backend + frontend only)
├── DESIGN.md                ← UI/UX design system
├── STATUS.md                ← Authoritative record of what is built and pending
├── requirements.txt         ← Python dependency manifest
├── run_harness.py           ← Dev harness for end-to-end test runs (gitignored)
│
├── docs/
│   ├── ARCHITECTURE.md      ← Engineering laws + project structure (this file)
│   ├── feature_plan.md      ← Current implementation plan (regenerated each session, gitignored)
│   ├── req.md               ← Incoming feature requirements (gitignored)
│   ├── flet_implementation_rules.md  ← Flet 0.84 API reference
│   └── superpowers/
│
├── scripts/
│   ├── build_release.py     ← Preferred build script (PyInstaller + gh.exe download)
│   ├── build.bat            ← Legacy build helper
│   └── build_installer.iss  ← Inno Setup installer script
│
├── frontend/
│   ├── main.py              ← Flet app entry point; starts backend in-process, owns all UI state
│   ├── __init__.py
│   └── views/
│       ├── chat.py          ← (reserved) — chat view decomposition target
│       ├── config.py        ← Provider configuration dialog
│       ├── jira_settings.py ← Jira filter import dialog and error-dialog helper
│       └── __init__.py
│
├── backend/
│   ├── main.py              ← FastAPI app; /chat, /compact, /health, /api/filters/parse-jql routes
│   ├── __init__.py
│   ├── agent/
│   │   ├── graph.py         ← LangGraph graph definition and compilation (MemorySaver checkpointer)
│   │   ├── llm_factory.py   ← Builds the LLM client from provider credentials at runtime
│   │   ├── nodes.py         ← LangGraph node functions (llm_call, orchestrator_fetch, route_after_llm)
│   │   ├── state.py         ← AgentState TypedDict (extends MessagesState)
│   │   └── __init__.py
│   └── utils/
│       ├── jql_parser.py    ← Parses raw JQL strings into structured filter dicts (Context Budgeting)
│       └── __init__.py
│
├── config/
│   ├── providers.py         ← Credential read/write via keyring (Windows Credential Manager)
│   └── __init__.py
│
├── tools/
│   ├── jira_tool.py         ← MCP tool: fetches Jira issues and returns only parsed fields
│   ├── mock_jira_mcp.py     ← Stub MCP server for local dev/testing without live Jira
│   └── __init__.py
│
└── tests/
    ├── test_ping.py         ← Health-check integration test
    └── test_providers.py    ← Credential store unit tests
```

### Data Flow Summary

**Flet → FastAPI:** `frontend/main.py` communicates with the backend exclusively over `localhost:8000` HTTP using `httpx`. It never imports backend modules for data access (exception: the in-process uvicorn launch at startup to avoid fork-bombing a packaged `.exe`).

**FastAPI → LangGraph → MCP:** `/chat` passes the user prompt and filter state into the compiled LangGraph graph. The graph's nodes invoke Jira tool calls via MCP (`tools/jira_tool.py`). `jql_parser.py` and the tool layer ensure only extracted fields (`issue_key`, `summary`, `status`, `assignee`) reach the LLM — never raw Jira JSON payloads.
