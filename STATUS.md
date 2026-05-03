# Project Status

## Overview

Autonomous AI agent Windows desktop app. A user pastes a Jira parent link and the agent fetches all child tickets, runs a parallel summarizer per ticket, then compiles a High-Density markdown table with Technical Pulse and blocker status.

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop UI | Flet (Python) |
| Backend API | FastAPI + Uvicorn |
| Agent loop | LangGraph (orchestrator + summarizer sub-graph) |
| LLM access | LangChain (OpenAI / Anthropic / Azure via keyring) |
| Tool routing | MCP via `langchain-mcp-adapters` |
| Jira integration | Jira REST API (MCP tools: `get_tickets_by_batch`, `fetch_ticket_metadata`, `save_summary_to_linux`) |
| Credential storage | `keyring` (Windows Credential Manager) |
| Distribution | PyInstaller `.exe` via `build.bat` |

## Architecture

```
User (Flet UI)
  │  HTTP POST /chat
  ▼
FastAPI backend (port 8000)
  │
  ▼
LangGraph Orchestrator
  ├── orchestrator_fetch   → calls get_tickets_by_batch (MCP)
  ├── orchestrator_tools   → executes batch fetch
  ├── parse_tickets        → extracts flat ticket list → state.tickets
  ├── [Send fan-out]       → one summarizer sub-graph per ticket (parallel)
  │     └── Summarizer Sub-graph
  │           ├── summarizer_llm    → calls fetch_ticket_metadata (MCP), synthesizes Pulse
  │           ├── summarizer_tools
  │           └── extract_summary   → appends "KEY | INSTANCE | STATUS | PULSE | BLOCKER" to state.summaries
  ├── orchestrator_compile → builds High-Density markdown table
  ├── save_tools           → calls save_summary_to_linux(ticket_key="GLOBAL", filename="backlog_sync.md")
  └── END
```

Fallback: if any of the three MCP tools are missing (bundled `.exe` or MCP server down), the graph falls back to a simple single-LLM loop so the app stays usable.

## What's Complete

### Backend
| File | Status | Notes |
|---|---|---|
| `backend/main.py` | ✅ | FastAPI app, `/ping`, `/health`, `/chat`; `ChatRequest` includes `prefixes`, `mode`, `parent_link`, `filters` |
| `backend/agent/state.py` | ✅ | `AgentState` and `SummarizerState` with `operator.add` reducer on `summaries` |
| `backend/agent/nodes.py` | ✅ | All orchestrator + summarizer nodes; LLM synthesizes Pulse (not raw copy-paste) |
| `backend/agent/graph.py` | ✅ | Full orchestrator + `_build_summarizer_subgraph`; fallback to single-LLM if tools missing |
| `backend/agent/llm_factory.py` | ✅ | `build_llm()` — reads provider config from keyring |
| `config/providers.py` | ✅ | Credential read/write via `keyring` (Windows Credential Manager) |

### Frontend
| File | Status | Notes |
|---|---|---|
| `frontend/main.py` | ✅ | Flet desktop app; starts backend in-process (thread); 120 s timeout |
| `frontend/views/config.py` | ✅ | Provider configuration dialog (API key, model, base URL) |

**UI features:**
- Chat message bubbles (user / assistant)
- Jira Parent Link input field
- Dynamic Filter Builder: add/remove rows, supports Project / Assignee / Status filters
- Settings gear icon → opens config dialog

### Build Pipeline
| File | Status | Notes |
|---|---|---|
| `build.bat` | ✅ | Kills running `Jira AI.exe`, locates `flet.exe`, runs PyInstaller |
| `Jira AI.spec` | ✅ | `collect_all()` for LangChain/LangGraph; `console=False`; hidden imports for uvicorn and keyring |
| `dist/Jira AI.exe` | ✅ | Last known-good build |

**Known runtime fixes already applied:**
| Error | Fix |
|---|---|
| `Unable to configure formatter 'default'` | `log_config=None` in `uvicorn.Config` |
| Backend failed to start (white screen) | `sys.frozen` check in lifespan — skips MCP subprocess in bundle |
| X button not closing | Removed `prevent_close=True` and `on_window_event` |
| `flet.controls.alignment` attribute error | Removed `alignment=` from `_make_bubble`; margin handles positioning |

### MCP Tools (mock)
| Tool | File | Used by |
|---|---|---|
| `get_tickets_by_batch` | `tools/mock_jira_mcp.py` | `orchestrator_fetch` |
| `fetch_ticket_metadata` | `tools/mock_jira_mcp.py` | `summarizer_llm` |
| `save_summary_to_linux` | `tools/mock_jira_mcp.py` | `orchestrator_compile` |

## What's Pending

| # | Task | Notes |
|---|---|---|
| 1 | Wire up real `jira-harness` MCP server | Replace `mock_jira_mcp.py` reference in `backend/main.py` lifespan with real server command |
| 2 | End-to-end test | Run backend, trigger backlog-summary agent, verify markdown table output and file save |
| 3 | Rebuild `.exe` | Run `build.bat` once real MCP integration is confirmed working |
| 4 | Markdown rendering in UI | Optional: render the High-Density table as formatted markdown in the Flet chat bubble instead of raw text |

## How to Run (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Start backend
uvicorn backend.main:app --reload --port 8000

# Start frontend (separate terminal)
python frontend/main.py

# Run tests
pytest
```

## Pulse Icons

| Icon | Meaning |
|---|---|
| 🔍 | Under analysis |
| 🟢 | Resolved / done |
| 🚨 | Critical blocker |
| ⏳ | Waiting |

## Jira URL Rules

| Project prefix | URL pattern |
|---|---|
| DVDNAIVI, AUDIODV, REAVN, DNSD | `https://jira.lge.com/issue/browse/{KEY}` |
| SPAWS | `https://spaws.jp.nissan.biz/jira/browse/{KEY}` |
