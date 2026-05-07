# Feature Plan: UI Polish & Architecture Documentation

**Source Context:** Flet Frontend UI (`frontend/main.py`) & Workspace Documentation
**Architecture Laws:** Actionable Observability, Deterministic State Management
**Objective:** Relocate the Compact button, add a validation guardrail to the Summary feature, and generate a comprehensive architecture document.

Operating strictly in **Plan Mode**, please outline the modifications to achieve the following 3 requirements. Do not write the full code until I approve the plan.

## 1. Move "Compact" Button to the Input Row
**Issue:** The Compact button is currently in the header, but functionally it belongs near the chat input where the user manages their conversation.
**Implementation in `frontend/main.py`:**
* **Remove from Header:** Locate the top navigation `ft.Row` that contains `title_text`, `summary_btn`, `compact_btn`, and `settings_btn`. Remove `compact_btn` from this array.
* **Add to Input Row:** Locate the bottom `ft.Row` that contains the `input_field` and `send_btn`. Inject `compact_btn` into this row so that it sits immediately to the left of the `send_btn`. 

## 2. Guardrail for "Generate Daily Summary"
**Issue:** If a user clicks the Summary button without configuring any Jira filters, the app still triggers a useless backend call.
**Implementation in `frontend/main.py`:**
* **Locate Handler:** Find the `async def on_daily_summary(e: ft.ControlEvent):` function.
* **Add Validation:** At the very beginning of the function, check if the app's state has any valid filters. (e.g., `if not app_state.get("filters"):`)
* **Halt & Warn:** If the filter dictionary is empty, completely abort the execution. Do *not* call `process_chat_message`. Instead, call our standard error handler:
  `show_error_dialog(page, "Cannot generate summary: No Jira filters configured.\n\nRemediation: Please open Settings (the gear icon) and import a JQL string or add a filter before requesting a summary.")`

## 3. Generate Project Structure Documentation
**Issue:** The project has grown significantly, and we need a snapshot of the architecture for future maintenance.
**Implementation:**
* **Scan Workspace:** Claude, use your file system tools to scan the current directory structure (specifically `frontend/`, `backend/`, `tools/`, and `config/`).
* **Create File:** Generate a new file named `ARCHITECTURE.md` at the root of the project.
* **Content Requirements:**
  1. A text-based tree diagram of the project structure.
  2. A brief 1-2 sentence description of what each major file is responsible for (e.g., `frontend/main.py`, `backend/agent/graph.py`, `tools/mock_jira_mcp.py`).
  3. A short summary of the data flow (how Flet talks to FastAPI, and how LangGraph talks to the MCP servers).

---
**Claude:** Please acknowledge these instructions. Show me exactly which lines you plan to change in `frontend/main.py` for Steps 1 & 2, and confirm you will scan the workspace to generate `ARCHITECTURE.md` for Step 3.