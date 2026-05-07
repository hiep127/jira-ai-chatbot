# Feature Plan: UI Polish & Architecture Documentation

**Status:** Implemented
**Source:** `req.md` — three parts
**Laws observed:** ARCHITECTURE.md (Strict Layered Architecture, Context Budgeting, Actionable Observability, Mathematical Precision, Security), CLAUDE.md (Plan Mode, MCP-first, no global state, keyring)

---

## Files to Create or Modify

| # | Action | Path |
|---|--------|------|
| 1 | Modify | `frontend/main.py` |
| 2 | Modify | `ARCHITECTURE.md` *(append new section — do NOT replace existing engineering laws)* |
| 3 | Modify | `frontend/views/jira_settings.py` *(UX polish: label shortening, field reordering, validation expansion, SnackBar → `show_error_dialog` — see Part 4)* |

No new packages required. No backend changes required.

---

## Critical Conflict: `ARCHITECTURE.md` Already Exists

`ARCHITECTURE.md` at the project root currently contains the **5 Engineering Laws** that the jira-planner skill reads as its constraint document. Overwriting it would destroy those rules.

**Resolution:** Append a new `## Project Structure` section to the existing file rather than replacing it. All existing law content is preserved verbatim.

---

## Part 1 — Move "Compact" Button to Input Row

**File:** `frontend/main.py`

### Change 1a — Remove `compact_btn` from the header `ft.Row`

**Location:** Line 255

Current:
```
ft.Row([title_text, summary_btn, compact_btn, settings_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
```

New:
```
ft.Row([title_text, summary_btn, settings_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
```

### Change 1b — Inject `compact_btn` into the input `ft.Row`

**Location:** Line 257

Current:
```
ft.Row([input_field, send_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
```

New:
```
ft.Row([input_field, compact_btn, send_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
```

**Result:** `compact_btn` sits immediately left of `send_btn` in the bottom input bar. The button widget itself (defined at lines 226–230) is unchanged.

---

## Part 2 — Guardrail for "Generate Daily Summary"

**File:** `frontend/main.py`

**Location:** `on_daily_summary` function, lines 170–173

Current function body:
```
async def on_daily_summary(e: ft.ControlEvent) -> None:
    await process_chat_message(
        "Please generate a detailed daily summary based on my currently active Jira filters."
    )
```

New function body (guard inserted at the very top, before any network call):
```
async def on_daily_summary(e: ft.ControlEvent) -> None:
    if not app_state.get("filters"):
        show_error_dialog(
            page,
            "Cannot generate summary: No Jira filters configured.\n\n"
            "Remediation: Please open Settings (the gear icon) and import a JQL "
            "string or add a filter before requesting a summary."
        )
        return
    await process_chat_message(
        "Please generate a detailed daily summary based on my currently active Jira filters."
    )
```

**Law compliance (Actionable Observability):** The error dialog provides a specific remediation step. No backend call is made when the guard fires — zero API cost.

**Context Budgeting:** N/A — no Jira API call is made when the guard halts execution. Downstream, the existing `process_chat_message` path already passes only selected filter keys to `/chat`, not raw Jira payloads.

---

## Part 3 — Append Project Structure to `ARCHITECTURE.md`

**File:** `ARCHITECTURE.md`

A new section will be appended after the existing 5-rule law block. The codebase scan (performed above) identified the following files:

```
AI Chatbot/
├── ARCHITECTURE.md          ← Engineering laws + project structure (this file)
├── CLAUDE.md                ← Claude Code guidance and workflow rules
├── feature_plan.md          ← Current implementation plan (regenerated each session)
├── req.md                   ← Incoming feature requirements
├── requirements.txt         ← Python dependency manifest
├── run_harness.py           ← Dev harness for end-to-end test runs
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

---

## Part 4 — Jira Settings UX Polish *(retroactively documented — committed in 809cd0a)*

**File:** `frontend/views/jira_settings.py`

### Change 4a — Label shortening
Field labels renamed for visual brevity and to surface the required-field asterisk:
- `"Filter Profile Name"` → `"Profile Name *"`
- `"Jira Personal Access Token"` → `"Jira PAT *"`
- `"Jira Parent Link (required)"` → `"Jira Parent Link *"`

### Change 4b — Field reordering in `_build_dialog_content`
Credential fields (Profile Name, PAT, Parent Link) moved to the **top** of the dialog, before the JQL import card. Previously they appeared below the card, making required fields harder to locate.

### Change 4c — `on_save` validation expanded
Guard widened from checking only `parent_link_field` to checking all three required fields (profile name, PAT, parent link). Missing any one of these produces an actionable error dialog.

### Change 4d — SnackBar → `show_error_dialog`
Replaced inline `page.open(ft.SnackBar(...))` with the shared `show_error_dialog(page, ...)` helper, consistent with the rest of the UI. The dialog provides a specific remediation string (Law: Actionable Observability).

---

## What This Plan Does NOT Change

- `backend/main.py` — no route changes
- `backend/agent/` — no graph, node, or state changes
- `backend/utils/` — no changes
- `config/providers.py` — no changes
- `tools/` — no changes
- `requirements.txt` — no new packages
- `tests/` — no test changes

**All parts implemented and committed.**
