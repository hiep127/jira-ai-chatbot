# Feature Plan: Windows CLI-Based GitHub Authentication

**Objective:** Implement a GitHub authentication flow relying on the local GitHub CLI (`gh`). The app is strictly for Windows. When authentication is needed, the app must automatically spawn a visible Command Prompt window for the user to complete the interactive `gh auth login` process.

## 1. Backend Implementation (FastAPI / Utils)
**Target:** Create token retrieval and terminal spawning utilities in `backend/utils/github_auth.py`.

* **Token Fetcher:** Write `get_local_github_token() -> str | None`. Use `subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)`. Catch `FileNotFoundError` (if `gh` isn't installed) or non-zero exit codes, returning `None` on failure.
* **Terminal Spawner:** Write a new function `spawn_windows_auth_terminal()`.
    * Use `subprocess.Popen` to launch the auth flow.
    * Command: `["cmd.exe", "/c", "gh auth login & echo. & pause"]` (The pause ensures the user sees the success/failure message before the window closes).
    * **Crucial:** You MUST import `subprocess` and use the argument `creationflags=subprocess.CREATE_NEW_CONSOLE`. This forces Windows to open a new, physically visible terminal window so the user can interact with the arrow-key prompts.

## 2. API Route Update
**Target:** Secure the relevant FastAPI routes.

* Call `get_local_github_token()`. If it returns `None`, raise an `HTTPException(status_code=401, detail="GitHub CLI not authenticated")`.

## 3. Frontend Implementation (Flet UI)
**Target:** Intercept the 401 error and trigger the Windows terminal popup.

* When Flet receives the `401 Unauthorized` error, open an `ft.AlertDialog`.
* **Message:** "Authentication Required. A secure terminal window will open for you to log in to GitHub."
* **Action Button:** A button labeled "Open Terminal & Log In". 
* **Event:** When clicked, it hits a backend endpoint that triggers `spawn_windows_auth_terminal()`. 
* **Follow-up:** Provide a "Refresh / I'm Done" button in the dialog so the Flet UI can re-check the token once the user finishes in the terminal.