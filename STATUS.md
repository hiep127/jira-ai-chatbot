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
  ├── discovery_and_dispatch → calls get_tickets_by_batch (MCP), fans out via Send
  ├── [Send fan-out]         → one ticket_summarizer_node per ticket (parallel)
  │     └── ticket_summarizer_node
  │           ├── fetches ticket via fetch_ticket_metadata (MCP)
  │           ├── context budgeting: strips raw JSON → slim {title, description[:2000], comments[:5][body]}
  │           └── LLM synthesizes Pulse row → appended to state.ticket_summaries
  ├── aggregate_summary_node → compiles High-Density markdown table; calls save_summary_to_linux
  └── END
```

Fallback: if the live `jira-harness` MCP server is unreachable, the backend fails fast with a clear error. The mock server (`tools/mock_jira_mcp.py`) has been permanently removed.

## What's Complete

### Backend
| File | Status | Notes |
|---|---|---|
| `backend/main.py` | ✅ | FastAPI app, `/ping`, `/health`, `/chat`, `/compact`; `GET /auth/github/status`, `POST /auth/github/spawn-terminal`; `GET /models` (fetches Copilot model list, `ModelInfo` schema, caches in `app.state.models_cache`, busts on `?refresh=true`); `model_id` field on `ChatRequest` and `CompactRequest`; 401 guard in `/chat` requires valid GitHub CLI token; mock MCP fallback removed — live `jira-harness` server only, fail-fast on connection error; `POST /reload-profiles` endpoint hot-reloads MCP subprocess with updated credentials without app restart; `_build_mcp_env()` reads `get_profiles()` + keyring → builds `JIRA_PROFILES_JSON` env var; `asyncio.Lock` prevents concurrent reload races |
| `backend/agent/state.py` | ✅ | `AgentState` with `ticket_summaries: Annotated[list[str], operator.add]` reducer; `TicketState` with `ticket_id` field for map-reduce fan-out |
| `backend/agent/nodes.py` | ✅ | `make_discovery_and_dispatch_node` fans out via `Send("ticket_summarizer_node", {"ticket_id": k})`; `make_ticket_summarizer_node` applies context budgeting (strips raw Jira JSON → slim `{title, description[:2000], comments[:5][body]}`) before LLM call; `make_aggregate_and_report_node` compiles and saves |
| `backend/agent/graph.py` | ✅ | Flat map-reduce graph: nodes `ticket_summarizer_node` + `aggregate_summary_node`; conditional edges target list updated; all `summarizer_daily` / `aggregate_and_report` references replaced |
| `backend/agent/llm_factory.py` | ✅ | `build_llm(model_id="")` / `build_summarizer_llm(model_id="")` — Copilot-only; `ChatOpenAI` via GitHub Copilot endpoint; falls back to `_DEFAULT_MODEL` (`gpt-4o`) / `_DEFAULT_SUMMARIZER_MODEL` (`gpt-4o-mini`) when `model_id` is empty |
| `backend/utils/github_auth.py` | ✅ | `get_local_github_token()` (calls `gh auth token`, `CREATE_NO_WINDOW` flag suppresses console flash); `check_auth(force=False)` (module-level cache `_auth_cache`); `spawn_windows_auth_terminal()` (opens cmd.exe); `_gh_exe()` checks frozen `tools/gh.exe`, then project-root `tools/gh.exe` (dev mode), then PATH |
| `config/providers.py` | ✅ | Per-profile PAT helpers: `get_jira_pat_for_profile(name)`, `set_jira_pat_for_profile(name, pat)`, `delete_jira_pat_for_profile(name)` stored in Windows Credential Manager under `jira_pat_{name.lower()}`; legacy `get_jira_pat`/`set_jira_pat` preserved for backward compatibility |
| `config/settings.py` | ✅ | `get_profiles() -> list[dict]` and `save_profiles(profiles)` for persisting Jira profiles (non-sensitive fields only: `name`, `host`, `custom_jql`) to `settings.json`; `"profiles"` added to `_PERSIST_KEYS` |
| `tools/jira_tool.py` | ✅ | Dynamic `JIRA_CONFIGS` built from `JIRA_PROFILES_JSON` env var injected by backend at subprocess start (no hardcoded credentials); updated `get_jira_client(profile_name, ticket_key)` routing; `get_tickets_by_batch` prefixes now refer to profile names (defaults to all configured profiles); `clone_ticket_from_spaws_to_lge` uses named profile lookup |

### Frontend
| File | Status | Notes |
|---|---|---|
| `frontend/main.py` | ✅ | Flet desktop app; starts backend in-process (thread); 10 s health-check timeout; auth guard container (`refresh_auth_state()`); `app_state` carries `model_id`/`model_name`/`model_tier`; `model_id` forwarded in `/chat` and `/compact` payloads; model chip button opens `open_model_picker`; GitHub Copilot 401 → `page.show_dialog(SnackBar)`; `FilterChip` active-profile selector row (between Jira Parent Link and send controls); `_toggle_profile()` mutates `app_state["active_profiles"]` set; active profiles persisted to `settings.json` and restored on launch; `prefixes` in `/chat` payload set from active profiles; chip row rebuilt on `on_settings_saved` callback |
| `frontend/components/__init__.py` | ✅ | Empty package marker for `frontend/components/` |
| `frontend/components/model_picker.py` | ✅ | `open_model_picker(page, app_state, on_model_selected)` — `AlertDialog` (360 px); search field + Refresh + Gear header; `ft.ListView` of `ListTile` rows with checkmark on active model; collapsible "Other Models" section; `ft.ProgressRing` while fetching; 401 → closes picker and opens `open_config_dialog`; writes `model_id`/`model_name`/`model_tier` into `app_state` |
| `frontend/views/config.py` | ✅ | Copilot auth dialog (`open_config_dialog`); proactive `_check_copilot_status()` via `page.run_task`; `on_save`/`on_close` async; `page.show_dialog()` / `page.pop_dialog()` (Flet 0.84 API); `on_closed` callback |
| `frontend/views/dialogs.py` | ✅ | `show_error_dialog` — `page.show_dialog()` / `page.pop_dialog()` (Flet 0.84 API) |
| `frontend/views/jira_settings.py` | ✅ | Two-panel profile CRUD dialog (860×480 px); left panel: scrollable `ft.ListView` of `ft.ListTile` per profile + `+ Add Profile` button; right panel: Name, Host URL, PAT (masked), Custom JQL fields with `Save Profile` / `Delete Profile` actions; `Save & Close` persists profiles then fires `POST /reload-profiles`; `on_auth_change` callback; Flet 0.84 API (`page.show_dialog()` / `page.pop_dialog()`, `ft.Icons.*`, `ft.Colors.*`, `ft.Padding()`, `ft.Border()`) |

**UI features:**
- Chat message bubbles (user / assistant)
- Jira Parent Link input field
- Multi-profile chip row: `FilterChip` toggles per Jira profile; selection persisted across restarts; chips rebuilt after settings dialog closes
- Settings gear icon → opens Jira profile CRUD dialog (two-panel, add/edit/delete profiles)
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

### MCP Tools (live)
| Tool | Server | Used by |
|---|---|---|
| `get_tickets_by_batch` | `jira-harness` (live) | `orchestrator_fetch` |
| `fetch_ticket_metadata` | `jira-harness` (live) | `summarizer_llm` |
| `save_summary_to_linux` | `jira-harness` (live) | `orchestrator_compile` |

`tools/mock_jira_mcp.py` has been permanently deleted. The backend now strictly depends on the live `jira-harness` server; if it fails to connect on startup, the backend logs a clear error and fails fast (no silent mock fallback).

## What's Pending

| # | Task | Notes |
|---|---|---|
| 1 | End-to-end test | Run backend, trigger backlog-summary agent against live `jira-harness`, verify markdown table output and file save |
| 2 | Rebuild `.exe` | Run `python build_release.py` once live MCP integration is confirmed working |
| 3 | Markdown rendering in UI | Optional: render the High-Density table as formatted markdown in the Flet chat bubble instead of raw text |

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

## Jira Profile Routing

Profiles replace the old hardcoded prefix-to-instance map. Each profile stores `name`, `host`, and `custom_jql` in `settings.json`; PATs are in Windows Credential Manager. The backend injects all profiles as `JIRA_PROFILES_JSON` into the MCP subprocess at startup (and on `/reload-profiles`).

`get_tickets_by_batch` accepts `prefixes` = list of profile names (e.g. `["SPAWS", "LGE"]`). If no prefixes are passed, all configured profiles are scanned. `fetch_ticket_metadata` falls back to the first configured profile when no matching profile name is found for a ticket key.