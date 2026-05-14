# Project Status

## Overview

Autonomous AI agent Windows desktop app. A user pastes a Jira parent link and the agent fetches all child tickets, runs a parallel summarizer per ticket, then compiles a High-Density markdown table with Technical Pulse and blocker status.

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop UI | Flet 0.84.0 (Python) |
| Backend API | FastAPI + Uvicorn |
| Agent loop | LangGraph (orchestrator + summarizer sub-graph) |
| LLM access | LangChain (GitHub Copilot endpoint only — `ChatOpenAI` via `api.githubcopilot.com`) |
| Tool routing | MCP via `langchain-mcp-adapters` |
| Jira integration | Jira REST API (MCP tools: `get_tickets_by_batch`, `fetch_ticket_metadata`, `save_summary_to_linux`) |
| Credential storage | `keyring` (Windows Credential Manager) |
| Distribution | PyInstaller `.exe` via `build_release.py` (downloads `gh.exe` automatically) |

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
| `backend/main.py` | ✅ | FastAPI app, `/ping`, `/health`, `/chat`, `/compact`; `GET /auth/github/status`, `POST /auth/github/spawn-terminal`; `GET /models` (fetches Copilot model list, `ModelInfo` schema, caches in `app.state.models_cache`, busts on `?refresh=true`); `model_id` field on `ChatRequest` and `CompactRequest`; 401 guard in `/chat` requires valid GitHub CLI token |
| `backend/agent/state.py` | ✅ | `AgentState` and `SummarizerState` with `operator.add` reducer on `summaries` |
| `backend/agent/nodes.py` | ✅ | All orchestrator + summarizer nodes; LLM synthesizes Pulse (not raw copy-paste) |
| `backend/agent/graph.py` | ✅ | Full orchestrator + `_build_summarizer_subgraph`; fallback to single-LLM if tools missing |
| `backend/agent/llm_factory.py` | ✅ | `build_llm(model_id="")` / `build_summarizer_llm(model_id="")` — Copilot-only; `ChatOpenAI` via GitHub Copilot endpoint; falls back to `_DEFAULT_MODEL` (`gpt-4o`) / `_DEFAULT_SUMMARIZER_MODEL` (`gpt-4o-mini`) when `model_id` is empty |
| `backend/utils/github_auth.py` | ✅ | `get_local_github_token()` (calls `gh auth token`, `CREATE_NO_WINDOW` flag suppresses console flash); `check_auth(force=False)` (module-level cache `_auth_cache`); `spawn_windows_auth_terminal()` (opens cmd.exe); `_gh_exe()` checks frozen `tools/gh.exe`, then project-root `tools/gh.exe` (dev mode), then PATH |
| `config/providers.py` | ✅ | Jira PAT helpers + `save_active_provider` only; all multi-provider functions removed (`KEY_PROVIDERS`, `ALL_PROVIDERS`, `load_key`, `save_key`, `delete_key`, `load_active_provider`) |

### Frontend
| File | Status | Notes |
|---|---|---|
| `frontend/main.py` | ✅ | Flet desktop app; starts backend in-process (thread); 10 s health-check timeout; auth guard container (`refresh_auth_state()`); `app_state` carries `model_id`/`model_name`/`model_tier`; `model_id` forwarded in `/chat` and `/compact` payloads; model chip button opens `open_model_picker`; GitHub Copilot 401 → `page.show_dialog(SnackBar)` |
| `frontend/components/__init__.py` | ✅ | Empty package marker for `frontend/components/` |
| `frontend/components/model_picker.py` | ✅ | `open_model_picker(page, app_state, on_model_selected)` — `AlertDialog` (360 px); search field + Refresh + Gear header; `ft.ListView` of `ListTile` rows with checkmark on active model; collapsible "Other Models" section; `ft.ProgressRing` while fetching; 401 → closes picker and opens `open_config_dialog`; writes `model_id`/`model_name`/`model_tier` into `app_state` |
| `frontend/views/config.py` | ✅ | Copilot auth dialog (`open_config_dialog`); proactive `_check_copilot_status()` via `page.run_task`; `on_save`/`on_close` async; `page.show_dialog()` / `page.pop_dialog()` (Flet 0.84 API); `on_closed` callback |
| `frontend/views/dialogs.py` | ✅ | `show_error_dialog` — `page.show_dialog()` / `page.pop_dialog()` (Flet 0.84 API) |
| `frontend/views/jira_settings.py` | ✅ | Settings dialog; Dynamic Filter Builder (`filter_rows_column`, `_make_filter_row()`, `_add_filter_row()`); `on_auth_change` callback; `page.show_dialog()` / `page.pop_dialog()` (Flet 0.84 API); `ft.Icons.DELETE` (not `ft.icons.DELETE`) |

**UI features:**
- Chat message bubbles (user / assistant)
- Jira Parent Link input field
- Dynamic Filter Builder: add/remove rows, supports Project / Assignee / Status filters
- Settings gear icon → opens Jira settings dialog
- Model chip button (header) → opens model picker; selected model name shown on chip
- Auth guard: if GitHub CLI not authenticated, chat is locked and an overlay prompt is shown
- Compact button → `/compact` with active `model_id`
- Generate Daily Summary button → sends pre-built JQL-aware prompt

### Build Pipeline
| File | Status | Notes |
|---|---|---|
| `build_release.py` | ✅ | Preferred build script: runs PyInstaller, copies `jira_server.env`, downloads `gh.exe` to `tools/gh.exe` then copies into `dist/JiraAgent/tools/`, copies `wiki/`; Flet version pre-flight check |
| `build.bat` | ✅ | Legacy helper: kills running `Jira AI.exe`, locates `flet.exe`, runs PyInstaller only (no gh.exe download) |
| `Jira AI.spec` | ✅ | `collect_all()` for LangChain/LangGraph; `console=False`; hidden imports for uvicorn and keyring; output folder `dist/JiraAgent/` |
| `dist/JiraAgent/Jira AI.exe` | ✅ | Last known-good build; `gh.exe` bundled at `dist/JiraAgent/tools/gh.exe` |

**Known runtime fixes already applied:**
| Error | Fix |
|---|---|
| `Unable to configure formatter 'default'` | `log_config=None` in `uvicorn.Config` |
| Backend failed to start (white screen) | `sys.frozen` check in lifespan — skips MCP subprocess in bundle |
| X button not closing | Removed `prevent_close=True` and `on_window_event` |
| `flet.controls.alignment` attribute error | Removed `alignment=` from `_make_bubble`; margin handles positioning |
| `ft.icons.DELETE` AttributeError | Changed to `ft.Icons.DELETE` (Flet 0.84: capitalized enum class, not lowercase module) |
| Dialogs not opening / double-open crash | Migrated from `page.overlay.append` + `dialog.open=True` to `page.show_dialog()` / `page.pop_dialog()` (Flet 0.84 dialog stack API) |
| `'"gh"' is not recognized` in auth terminal | `_gh_exe()` now checks project-root `tools/gh.exe` in dev mode; `build_release.py` downloads there first |

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
| 3 | Rebuild `.exe` | Run `python build_release.py` once real MCP integration is confirmed working |
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