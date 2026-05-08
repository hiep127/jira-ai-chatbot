# Feature Plan: Windows CLI-Based GitHub Authentication

**Source Spec:** `req.md`
**Objective:** Implement a GitHub authentication flow relying on the local GitHub CLI (`gh`). When the `/chat` endpoint detects the provider is `github_copilot` but `gh auth token` returns no token, it returns HTTP 401 with a sentinel detail string. The Flet frontend intercepts that 401 and opens an `ft.AlertDialog` with an "Open Terminal & Log In" button that spawns a visible `cmd.exe` window, and a "Refresh / I'm Done" button that re-checks token status via a dedicated endpoint.

---

## Codebase Scan — Current State

| Component | Relevant Detail |
| :--- | :--- |
| `backend/agent/llm_factory.py` L82–98 | `_get_copilot_token()` — private function that already calls `subprocess.run(["gh", "auth", "token"], ...)` and **raises** `RuntimeError` on any failure. This duplicates logic that should live in the new util. |
| `backend/main.py` L77–98 | `POST /chat` — catches `RuntimeError` and returns HTTP 500. No GitHub-auth pre-check today; auth failure surfaces as a generic 500. |
| `backend/main.py` L101–154 | `POST /compact` — calls `build_llm()` directly (line 123). GitHub auth failure here also surfaces as 500. Out of scope for this plan — compact has its own error handling that would require a separate UI update. |
| `frontend/main.py` L113–123 | `process_chat_message` 401 handler — currently shows a static hint about Jira PAT. No distinction between Jira-401 and GitHub-401. |
| `frontend/main.py` L9 | `show_error_dialog` imported from `jira_settings.py` — reused as-is. |
| `backend/utils/` | Contains only `__init__.py` after `jql_parser.py` deletion. New `github_auth.py` goes here. |

---

## Architecture Compliance Check

| Rule | Status | Notes |
| :--- | :--- | :--- |
| **Rule 1 — Layered Architecture** | ✓ | New util in `backend/utils/`, endpoints in `backend/main.py`, UI in `frontend/main.py`. No cross-layer imports. |
| **Rule 2 — Context Budgeting** | N/A | No Jira JSON payloads involved in this feature. |
| **Rule 3 — Observability** | ✓ | All subprocess calls wrapped in `try/except`. 401 detail string includes actionable remediation step. |
| **Rule 4 — Mathematical Precision** | ✓ | Exact file paths listed. `AgentState` TypedDict unchanged — no routing impact. |
| **Rule 5 — Security** | ✓ | Token read via `gh` CLI subprocess only. No token written to files, logs, or HTTP responses. Endpoint payload omits the token value. |

---

## Files to be Modified or Created

| File | Change Type | Summary |
| :--- | :--- | :--- |
| `backend/utils/github_auth.py` | **CREATE** | `get_local_github_token() -> str \| None` and `spawn_windows_auth_terminal()` |
| `backend/agent/llm_factory.py` | **MODIFY** | Replace `_get_copilot_token()` body to delegate to new util (eliminate duplication) |
| `backend/main.py` | **MODIFY** | Add `GET /auth/github/status` and `POST /auth/github/spawn-terminal`; add GitHub-auth pre-check to `/chat` |
| `frontend/main.py` | **MODIFY** | Add `_open_github_auth_dialog()` local function; update 401 branch in `process_chat_message` |

`backend/agent/graph.py`, `backend/agent/nodes.py`, `backend/agent/state.py`, `tools/jira_tool.py`, `frontend/views/jira_settings.py` — **no changes required**.

---

## Step 1 — New Utility (`backend/utils/github_auth.py`)

Create a new file. Two public functions only.

### 1a — `get_local_github_token() -> str | None`

```python
import subprocess

def get_local_github_token() -> str | None:
    """Return the GitHub CLI token, or None on any failure."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        token = result.stdout.strip()
        return token if token else None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
```

**Context Budgeting note:** The token string is returned to the caller only; it is never logged or passed to the LLM context. The HTTP status endpoint (Step 3) returns only a boolean, not the token.

### 1b — `spawn_windows_auth_terminal() -> None`

```python
import subprocess

def spawn_windows_auth_terminal() -> None:
    """Open a new cmd.exe window for interactive 'gh auth login'.

    CREATE_NEW_CONSOLE is required: it forces Windows to physically open a
    new terminal window so the user can interact with gh's arrow-key prompts.
    Without it the subprocess inherits the parent's (hidden) console and
    the user sees nothing.
    """
    subprocess.Popen(
        ["cmd.exe", "/c", "gh auth login & echo. & pause"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
```

`subprocess.Popen` is non-blocking — it spawns the window and returns immediately, keeping the FastAPI event loop free.

---

## Step 2 — LLM Factory Deduplication (`backend/agent/llm_factory.py`)

### 2a — Remove the internal subprocess duplication

**Current `_get_copilot_token()` (lines 82–97):** Contains its own `subprocess.run` block with `FileNotFoundError` / `CalledProcessError` handling — a duplicate of Step 1a.

**Replace the function body:**

```python
from backend.utils.github_auth import get_local_github_token

def _get_copilot_token() -> str:
    token = get_local_github_token()
    if token is None:
        raise RuntimeError(
            "GitHub CLI not authenticated. Open a terminal and run 'gh auth login'."
        )
    return token
```

The function signature is unchanged (`-> str`), so the two call sites inside `build_llm()` and `build_summarizer_llm()` require no update.

**Remove** the `import subprocess` statement from `llm_factory.py` — it is now unused in that file.

---

## Step 3 — FastAPI Routes (`backend/main.py`)

### 3a — GitHub auth status endpoint

Add after the `/health` route:

```python
@app.get("/auth/github/status")
def github_auth_status() -> dict[str, bool]:
    from backend.utils.github_auth import get_local_github_token
    return {"authenticated": get_local_github_token() is not None}
```

Returns `{"authenticated": true}` or `{"authenticated": false}`. Does **not** expose the token value in the response.

### 3b — Terminal spawn endpoint

```python
@app.post("/auth/github/spawn-terminal")
def spawn_github_terminal() -> dict[str, str]:
    try:
        from backend.utils.github_auth import spawn_windows_auth_terminal
        spawn_windows_auth_terminal()
        return {"status": "ok", "message": "Terminal window opened."}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to open terminal: {e}. Ensure cmd.exe is accessible on this system.",
        )
```

Both endpoints are sync `def` (not `async def`). FastAPI runs them in a thread pool automatically; this is correct because `Popen` and `subprocess.run` are blocking OS calls.

### 3c — GitHub-auth pre-check in `/chat`

**Add to the top of the `chat()` handler, before the `try` block:**

```python
@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    # Pre-check: surface unauthenticated GitHub Copilot as 401 (not 500)
    from config.providers import load_active_provider
    from backend.utils.github_auth import get_local_github_token
    if load_active_provider() == "github_copilot" and get_local_github_token() is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "GitHub CLI not authenticated. "
                "Run 'gh auth login' to authenticate."
            ),
        )
    try:
        ...  # existing graph.ainvoke block unchanged
```

**Why this placement:** The pre-check runs before the LangGraph graph is invoked, giving the frontend a clean 401 signal rather than a buried 500 RuntimeError. The check is gated on `provider == "github_copilot"` so OpenAI and Anthropic users are never affected.

**`AgentState` impact:** None. `custom_jql`, `prefixes`, `mode`, and all other state keys are unchanged. No routing functions read auth state — no infinite loop risk.

---

## Step 4 — Frontend (`frontend/main.py`)

### 4a — Add `_open_github_auth_dialog()` local function inside `main()`

Add this function **inside** `async def main(page: ft.Page)`, after `rebuild_sidebar` is defined. It captures `page` from the enclosing scope.

```python
def _open_github_auth_dialog() -> None:
    async def on_open_terminal(e: ft.ControlEvent) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post("http://localhost:8000/auth/github/spawn-terminal")
        except Exception as exc:
            show_error_dialog(page, f"Could not open terminal: {exc}")

    async def on_refresh(e: ft.ControlEvent) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:8000/auth/github/status")
            if r.json().get("authenticated"):
                auth_dlg.open = False
                page.update()
            else:
                show_error_dialog(
                    page,
                    "Not yet authenticated. Complete 'gh auth login' in the terminal window, then click Refresh again.",
                )
        except Exception as exc:
            show_error_dialog(page, f"Status check failed: {exc}")

    auth_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Authentication Required", color=ft.Colors.ORANGE_400),
        content=ft.Text(
           content=ft.Text(
            "GitHub Copilot is not authenticated.\n\n"
            "1. Click 'Open Terminal & Log In'.\n"
            "2. Follow the prompts in the terminal window to authenticate.\n"
            "3. Once the terminal says 'Logged in', return here.\n"
            "4. Click 'Refresh / I'm Done' to verify and close this dialog."
        ),
        actions=[
            ft.ElevatedButton("Open Terminal & Log In", on_click=on_open_terminal),
            ft.TextButton("Refresh / I'm Done", on_click=on_refresh),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(auth_dlg)
    auth_dlg.open = True
    page.update()
```

### 4b — Update the 401 branch in `process_chat_message`

**Current (lines 113–123):**
```python
else:
    detail = r.json().get("detail", r.text)
    message_list.controls.remove(thinking)
    _status_hints: dict[int, str] = {
        401: "Token expired or invalid — update your PAT in Settings → Jira Personal Access Token.",
        ...
    }
    hint = _status_hints.get(r.status_code, "Check the terminal log for details.")
    ...
    show_error_dialog(page, f"Error {r.status_code}: {detail}\n\nRemediation: {hint}")
```

**New — split the 401 case:**
```python
else:
    detail = r.json().get("detail", r.text)
    message_list.controls.remove(thinking)

    if r.status_code == 401 and "GitHub CLI" in detail:
        _open_github_auth_dialog()
    else:
        _status_hints: dict[int, str] = {
            401: "Token expired or invalid — update your PAT in Settings → Jira Personal Access Token.",
            403: "Access denied — verify your Jira role has permission to read these issues.",
            404: "Endpoint not found — ensure the backend is the latest version.",
            500: "Backend internal error — check the terminal log for a Python traceback.",
        }
        hint = _status_hints.get(r.status_code, "Check the terminal log for details.")
        print(f"[on_send] HTTP {r.status_code}: {detail}")
        show_error_dialog(page, f"Error {r.status_code}: {detail}\n\nRemediation: {hint}")
```

The sentinel string `"GitHub CLI"` matches the exact `detail` value set in Step 3c. Jira-originated 401s (e.g., expired PAT from the Jira API layer) do not contain this string and continue to use the existing PAT hint.

---

## Data Flow After Implementation

```
User sends message (GitHub Copilot provider active)
  ↓  POST /chat  {prompt: "…", thread_id: "…", custom_jql: "…"}
FastAPI /chat pre-check:
  → load_active_provider() == "github_copilot"  → True
  → get_local_github_token()                    → None  (gh not authed)
  → raise HTTPException(401, "GitHub CLI not authenticated…")
  ↓
Flet frontend receives HTTP 401
  → "GitHub CLI" in detail                      → True
  → _open_github_auth_dialog()
      → "Open Terminal & Log In" clicked
          → POST /auth/github/spawn-terminal
          → subprocess.Popen(["cmd.exe", …], CREATE_NEW_CONSOLE)
          → visible cmd window opens for user
      → "Refresh / I'm Done" clicked
          → GET /auth/github/status
          → get_local_github_token() → "gho_…"  → {"authenticated": true}
          → dialog closes
  User retries message → now succeeds
```
## Post-Authentication User Guide

**What the user needs to do once implemented:**
1. **In the UI:** The user clicks "Open Terminal & Log In".
2. **In the spawned Terminal:** The user will be asked standard `gh` setup questions. The recommended path is:
   - *What account do you want to log into?* → `GitHub.com`
   - *What is your preferred protocol for Git operations?* → `HTTPS`
   - *Authenticate Git with your GitHub credentials?* → `Y`
   - *How would you like to authenticate?* → `Login with a web browser`
3. The user completes the login in their default browser and copies the one-time device code if prompted.
4. **Completion:** The terminal will display `Logged in as <username>` and prompt `Press any key to continue...`. Pressing any key will cleanly close the terminal window.
5. **Back in the UI:** The user clicks **"Refresh / I'm Done"**. The backend detects the token, Flet safely dismisses the dialog, and the user simply retries their message.
---

## What Does NOT Change

- `AgentState` TypedDict — no fields added or removed; all routing functions unaffected.
- `backend/agent/graph.py` — no changes; neither routing function reads auth state.
- `backend/agent/nodes.py` — no changes.
- `tools/jira_tool.py` — no changes.
- `frontend/views/jira_settings.py` — no changes.
- `backend/agent/llm_factory.py` `build_llm()` and `build_summarizer_llm()` call sites — unchanged; `_get_copilot_token()` signature is preserved.
- The `/compact` endpoint — out of scope; its error path would require a separate UI update to handle 401 gracefully.
- All existing Jira-401 error hints in the frontend — preserved; the GitHub-401 branch is additive only.

---

## Awaiting Explicit User Approval Before Any Code Is Written.
