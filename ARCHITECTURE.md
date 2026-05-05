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
