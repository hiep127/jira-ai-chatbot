# Project Progress

## Build Pipeline

### `build.bat` — ✅ Complete
- Kills any running `Jira AI.exe` instance before building
- Locates `flet.exe` via `sysconfig.get_path('scripts', 'nt_user')` fallback
- Runs `python -m PyInstaller "Jira AI.spec" --noconfirm --distpath dist` (bypasses flet pack argparse limitations)

### `Jira AI.spec` — ✅ Complete
- Uses `collect_all()` for: `langchain_core`, `langchain_openai`, `langchain_anthropic`, `langgraph`, `langchain_mcp_adapters`
- Hidden imports: uvicorn lifecycle modules, fastapi, starlette, keyring.backends.Windows, httpx
- `console=False` (no terminal window)

### Known runtime fixes applied
| Error | Fix applied |
|---|---|
| `Unable to configure formatter 'default'` | `log_config=None` in uvicorn.Config |
| Backend failed to start (white screen) | `sys.frozen` check in lifespan — skips MCP subprocess in bundle |
| X button not closing | Removed `prevent_close=True` and `on_window_event` |
| `module 'flet.controls.alignment' has no attribute 'center_right'` | Removed `alignment=` from `_make_bubble`; margin handles positioning |

---

## Multi-Agent Workflow

### Architecture
```
User message (with prefixes + mode filters)
  ↓
FastAPI /chat
  ↓
LangGraph Orchestrator (AgentState)
  ├── orchestrator_fetch  → calls get_tickets_by_batch
  ├── orchestrator_tools  → executes tool call
  ├── parse_tickets       → extracts flat ticket list → state.tickets
  ├── [Send fan-out] summarizer × N  ← one per ticket, parallel
  │     └── Summarizer Sub-graph (SummarizerState)
  │           ├── summarizer_llm  → calls fetch_ticket_metadata, synthesizes Pulse
  │           ├── summarizer_tools
  │           └── extract_summary → appends to state.summaries
  ├── orchestrator_compile → builds High-Density markdown table
  ├── save_tools           → calls save_summary_to_linux(ticket_key="GLOBAL", filename="backlog_sync.md")
  └── END
```

### Files

| File | Status | Notes |
|---|---|---|
| `backend/agent/state.py` | ✅ Complete | `AgentState`, `SummarizerState` with `operator.add` reducer on `summaries` |
| `backend/agent/nodes.py` | ✅ Complete | All orchestrator + summarizer nodes; LLM synthesizes Pulse (not raw copy-paste) |
| `backend/agent/graph.py` | ✅ Complete | Full orchestrator + `_build_summarizer_subgraph`; falls back to single-LLM if tools missing |
| `backend/agent/llm_factory.py` | ✅ Existing | `build_llm()` — reads provider config from keyring |
| `backend/main.py` | ✅ Updated | `ChatRequest` now includes `prefixes` + `mode`; graph seeded with `tickets=[]`, `summaries=[]` |
| `frontend/main.py` | ✅ Updated | Filter bar: SPAWS/LGE checkboxes + TEAM/PERSONAL dropdown; timeout raised to 120s |

### MCP Tools expected (from `jira-harness` server)
| Tool name | Used by |
|---|---|
| `get_tickets_by_batch` | `orchestrator_fetch` — discovery step |
| `fetch_ticket_metadata` | `summarizer_llm` — per-ticket metadata + comments |
| `save_summary_to_linux` | `orchestrator_compile` — saves final report |

### Fallback behaviour
If any of the three tools above are missing (e.g. bundled `.exe`, or MCP server down), `build_graph` falls back to a simple single-LLM loop so the app remains usable.

### URL rules (encoded in `_ORCHESTRATOR_COMPILE_PROMPT`)
- LGE tickets (DVDNAIVI, AUDIODV, REAVN, DNSD): `https://jira.lge.com/issue/browse/{KEY}`
- SPAWS tickets: `https://spaws.jp.nissan.biz/jira/browse/{KEY}`

### Pulse icons
| Icon | Meaning |
|---|---|
| 🔍 | Under analysis |
| 🟢 | Resolved / done |
| 🚨 | Critical blocker |
| ⏳ | Waiting |

---

## Pending / Next Steps

- [ ] Wire up real `jira-harness` MCP server in `backend/main.py` lifespan (currently using `tools/mock_jira_mcp.py`)
- [ ] End-to-end test: run backend, trigger backlog-summary agent, verify markdown table output
- [ ] Rebuild `.exe` with `build.bat` once MCP integration is confirmed working
- [ ] Optional: render markdown table in the Flet chat bubble (currently displayed as raw text)
