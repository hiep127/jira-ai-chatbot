# Python, FastAPI, and Flet Execution Standards

All Python code written for this application MUST adhere to the following rules. The QA Reviewer will fail any code that violates these standards.

## 1. Type Hinting
- Every function, method, and endpoint MUST have complete Python type hinting.
- Use `list[str]`, `dict[str, Any]`, etc., natively (Python 3.10+).

## 2. FastAPI Backend Rules
- All route handlers must be `async def`.
- Every incoming payload and outgoing response MUST be validated using a Pydantic `BaseModel`. No raw dictionary returns from API endpoints.
- Any Jira API failures must be caught and raised as explicit `HTTPException` errors with clear detail messages.

## 3. Flet Frontend Rules
- Do NOT write massive inline UI trees. Break complex Flet UI sections into separate helper functions (e.g., `def build_sidebar() -> ft.Container:`).
- UI state must not be mixed with backend API logic. Use asynchronous HTTP calls (`httpx` or `aiohttp`) from the Flet client to the FastAPI backend.

## 4. No Placeholder Code
- Do not leave `pass`, `TODO`, or `FIXME` blocks in the code. If a function is defined in the plan, it must be fully implemented.

## 5. GitHub Copilot API
- Use `get_local_github_token()` directly as `Authorization: Bearer <token>` when calling `api.githubcopilot.com`. Do NOT call `https://api.github.com/copilot_internal/v2/token` to exchange it for a session token. That endpoint is an undocumented internal API restricted to the official VS Code Copilot OAuth app; tokens from the `gh` CLI return 404. The public `api.githubcopilot.com` endpoints (`/models`, `/chat/completions`) accept the OAuth token directly without any exchange step.

## 6. MCP / `langchain-mcp-adapters` API
- As of version 0.1.0, `MultiServerMCPClient` is **not** a context manager. Never call `__aenter__` / `__aexit__` on it — they raise `NotImplementedError`. Always use the stateless pattern and always `await get_tools()`:
  ```python
  # CORRECT
  client = MultiServerMCPClient({...})
  tools = await client.get_tools()

  # WRONG — raises NotImplementedError
  async with MultiServerMCPClient({...}) as client:
      tools = await client.get_tools()

  # WRONG — missing await, returns a coroutine not a list
  tools = client.get_tools()
  ```
- Each tool invocation opens its own short-lived subprocess session automatically; there is no persistent connection to manage or close.
