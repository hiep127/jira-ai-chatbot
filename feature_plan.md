# Feature Plan: UI Refactoring v2 & Error Boundary Implementation

**Source requirements:** `req.md`
**Architecture laws:** `ARCHITECTURE.md` (all 5 rules), `CLAUDE.md` (Plan Mode)
**Planned:** 2026-05-06
**Status:** DRAFT v2 — awaiting approval before any code is written
**Changes from v1:** §5 (Req 4) fully rewritten to satisfy Rule 3 — Actionable Observability.

---

## 0. Architecture & Laws Compliance

| Rule | How This Plan Satisfies It |
|---|---|
| **1. Strict Layered Architecture** | All changes are purely frontend (Flet UI layer). No direct Jira API calls from the sidebar or error dialogs. Settings are saved/loaded via `config/providers.py` (credential layer). |
| **2. Context Budgeting** | Sidebar selection narrows `app_state["selected_filter_keys"]`; `on_send` intersects `filters` by selected keys before POST. No new LLM context pressure introduced. |
| **3. Actionable Observability** | Every `except` and non-200 path calls both `print()` with context tag AND `show_error_dialog` with a human-readable error string **plus a distinct remediation step**. Status-code-aware hint dicts provide specific guidance (401 → "update your PAT", 500 → "check terminal for traceback", connection error → exact `uvicorn` start command). No generic "An error occurred." messages. |
| **4. Mathematical Precision** | All file paths are exact (see §1). `app_state` gains no new keys; existing `selected_filter_keys` list is the single source of truth for sidebar checkbox state. `AgentState` is NOT changed — backend is already complete. |
| **5. Security** | No credentials stored in UI. No new packages. PAT stays in keyring. |

**New packages required:** None.

---

## 1. Files Touched

| # | File | Action |
|---|---|---|
| 1 | `frontend/views/jira_settings.py` | Add module-level `show_error_dialog`; move JQL section to top of `_build_dialog_content`; upgrade all SnackBar/text error paths to actionable dialog messages; add `on_settings_saved` callback param; harden `state["parent_link"]` access |
| 2 | `frontend/main.py` | Import `show_error_dialog`; add `sidebar_col` + `rebuild_sidebar()`; update layout to `ft.Row` (sidebar + chat); pass `rebuild_sidebar` to settings dialog; replace both error paths in `on_send` with actionable `show_error_dialog` calls |

**Files confirmed untouched:**
`backend/`, `config/`, `tools/`, `tests/`, `requirements.txt`, `frontend/views/config.py`

---

## 2. Req 1 — Prioritize "Import Filter from JQL"

### 2.1 `frontend/views/jira_settings.py` — `_build_dialog_content()`

**Current order:**
1. Filter Profile Name
2. Jira PAT
3. Jira Parent Link
4. Current Saved Filters
5. Additional Filter Rows
6. Import Filter from JQL  ← currently last

**New order:**
1. **Import Filter from JQL** ← moved to TOP, wrapped in `ft.Card` for visual distinction
2. Filter Profile Name
3. Jira Personal Access Token
4. Jira Parent Link (required)
5. Current Saved Filters
6. Additional Filter Rows

The JQL section is wrapped in an `ft.Card` with a heading `"Quick Import — paste a JQL string to auto-populate filters below."`. No change to function signature or parameters — only the order of `controls=[]` inside the returned `ft.Container` changes.

---

## 3. Req 2 — Side Menu for Active Filter Profiles

### 3.1 `frontend/main.py` — Sidebar column

Add a persistent left-side `ft.Column` (width=220) that always shows saved filter keys as checkboxes.

**New variable (inside `main()`):**
```python
sidebar_col = ft.Column(
    controls=[
        ft.Text("Active Filters", weight=ft.FontWeight.BOLD, size=14),
        ft.Divider(),
        ft.Text("No filters saved.", italic=True, color=ft.Colors.GREY_500, size=12),
    ],
    width=220,
    spacing=4,
)
```

### 3.2 `frontend/main.py` — `rebuild_sidebar()`

New function defined inside `main()`:
```python
def rebuild_sidebar() -> None:
    sidebar_col.controls.clear()
    sidebar_col.controls.append(ft.Text("Active Filters", weight=ft.FontWeight.BOLD, size=14))
    sidebar_col.controls.append(ft.Divider())
    if not app_state["filters"]:
        sidebar_col.controls.append(
            ft.Text("No filters saved.", italic=True, color=ft.Colors.GREY_500, size=12)
        )
    else:
        for key in app_state["filters"]:
            is_checked = (
                key in app_state["selected_filter_keys"]
                if app_state["selected_filter_keys"]
                else True
            )
            def _on_cb(ev, k=key):
                if ev.control.value:
                    if k not in app_state["selected_filter_keys"]:
                        app_state["selected_filter_keys"].append(k)
                else:
                    app_state["selected_filter_keys"] = [
                        x for x in app_state["selected_filter_keys"] if x != k
                    ]
            sidebar_col.controls.append(
                ft.Checkbox(label=key, value=is_checked, on_change=_on_cb)
            )
    if sidebar_col.page:
        sidebar_col.update()
```

### 3.3 `frontend/main.py` — Layout update

Replace the top-level `ft.Column(expand=True, ...)` in `page.add(...)` with a `ft.Row`:

```python
page.add(
    ft.Row(
        controls=[
            ft.Container(
                content=sidebar_col,
                width=220,
                padding=ft.padding.symmetric(horizontal=8, vertical=10),
                border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_800)),
            ),
            ft.Column(
                controls=[
                    ft.Row([title_text, settings_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    message_list,
                    ft.Row([input_field, send_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
                expand=True,
            ),
        ],
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
)
```

Window width increased from `800` to `1050` to accommodate the sidebar.

### 3.4 `frontend/main.py` — Settings button callback

Update the settings `ft.IconButton` `on_click`:
```python
on_click=lambda e: open_jira_settings_dialog(page, app_state, on_settings_saved=rebuild_sidebar),
```

### 3.5 `frontend/views/jira_settings.py` — `open_jira_settings_dialog` signature

Add optional callback parameter:
```python
def open_jira_settings_dialog(
    page: ft.Page,
    state: dict[str, Any],
    on_settings_saved: Callable[[], None] | None = None,
) -> None:
```

In `on_save()`, after `dialog.open = False` and before `page.update()`:
```python
if on_settings_saved:
    on_settings_saved()
```

---

## 4. Req 3 — Fix `AttributeError: 'NoneType'` in `on_send`

### 4.1 Verification

The current `frontend/main.py` (line 52) already initializes `app_state` with all required keys. The specific crash described (`jira_settings.get("target_server")`) is from an older code path that no longer exists. No changes are needed to `app_state` initialization.

### 4.2 Hardening in `frontend/views/jira_settings.py`

Two direct key accesses must be made safe to prevent `KeyError` if `state` is ever partially initialized:

| Line | Before | After |
|---|---|---|
| 65 | `value=state["parent_link"],` | `value=state.get("parent_link", ""),` |
| 73 | `if state["parent_link"]:` | `if state.get("parent_link"):` |

---

## 5. Req 4 — Global Exception Handling & Error Dialogs

> **v2 change:** All error strings now include a distinct **Remediation:** line with a concrete, actionable step. Status-code-specific hint dicts replace generic messages. Both error paths in `on_send` (non-200 HTTP and connection exception) are converted to `show_error_dialog`.

### 5.1 `frontend/views/jira_settings.py` — `show_error_dialog()`

Add module-level function before `open_jira_settings_dialog`. The function itself is unchanged from v1 — only the *call sites* (§§5.3–5.5) carry the actionable text.

```python
def show_error_dialog(page: ft.Page, error_message: str) -> None:
    def _close(ev: ft.ControlEvent) -> None:
        err_dlg.open = False
        page.update()

    err_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Application Error", color=ft.Colors.RED),
        content=ft.Text(str(error_message)),
        actions=[ft.TextButton("OK", on_click=_close)],
    )
    page.overlay.append(err_dlg)
    err_dlg.open = True
    page.update()
```

### 5.2 `frontend/main.py` — Import

Update the existing import line:
```python
from frontend.views.jira_settings import open_jira_settings_dialog, show_error_dialog
```

### 5.3 `frontend/main.py` — `on_send` (BOTH error paths rewritten)

The current `on_send` has two separate error paths (lines 96–110). Both must be upgraded.

**Path A — Non-200 HTTP response** (replaces the `else` branch at lines 100–105):

```python
else:
    detail = r.json().get("detail", r.text)
    message_list.controls.remove(thinking)
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

**Path B — Connection / uncaught exception** (replaces the `except` block at lines 106–110):

```python
except Exception as exc:
    message_list.controls.remove(thinking)
    print(f"[on_send] Exception: {exc}")
    show_error_dialog(
        page,
        f"Connection error: {exc}\n\n"
        "Remediation: start the backend with:\n"
        "  uvicorn backend.main:app --reload --port 8000",
    )
```

### 5.4 `frontend/views/jira_settings.py` — `on_import_jql` (both paths)

Replace both `ft.SnackBar` calls with actionable `show_error_dialog` calls.

**Non-200 HTTP path** (replaces lines 285–290 in current `jira_settings.py`):
```python
detail = r.json().get("detail", r.text)
print(f"[on_import_jql] HTTP {r.status_code}: {detail}")
show_error_dialog(
    page,
    f"JQL parse failed (HTTP {r.status_code}): {detail}\n\n"
    "Remediation: verify the JQL syntax in Jira's issue navigator first, "
    "then confirm the /api/filters/parse-jql endpoint is reachable at "
    "http://127.0.0.1:8000.",
)
```

**Connection / uncaught exception path** (replaces lines 290–294 in current `jira_settings.py`):
```python
except Exception as exc:
    print(f"[on_import_jql] Exception: {exc}")
    show_error_dialog(
        page,
        f"Connection error: {exc}\n\n"
        "Remediation: start the backend with:\n"
        "  uvicorn backend.main:app --reload --port 8000",
    )
```

### 5.5 `frontend/views/jira_settings.py` — `on_save` exception guard

Wrap the body of `on_save` (after validation) in a try/except with an actionable credential-specific hint:

```python
def on_save(e: ft.ControlEvent) -> None:
    # Validation block is unchanged and stays outside the try
    if not parent_link_field.value.strip():
        page.open(ft.SnackBar(...))
        return
    if filter_rows and not validate_filters():
        return
    try:
        state["filter_profile_name"] = profile_name_field.value.strip()
        state["jira_env"]             = _parsed_jira_env
        state["parent_link"]          = parent_link_field.value.strip()
        state["filters"]              = _collect_filters()
        state["selected_filter_keys"] = [
            f for f, cb in _selection_checkboxes.items() if cb.value
        ]
        pat = pat_field.value.strip()
        if pat:
            set_jira_pat(pat)
        dialog.open = False
        if on_settings_saved:
            on_settings_saved()
        page.update()
    except Exception as exc:
        print(f"[on_save] Exception: {exc}")
        show_error_dialog(
            page,
            f"Failed to save settings: {exc}\n\n"
            "Remediation: if this is a credential error, ensure Windows Credential "
            "Manager is accessible (Control Panel → Credential Manager → "
            "Windows Credentials).",
        )
```

---

## 6. Data Flow

```
App startup
  └─► app_state initialized: {filter_profile_name: "", jira_env: "", parent_link: "",
                               filters: {}, selected_filter_keys: []}
  └─► sidebar_col shows "No filters saved."

User opens Settings (⚙ button)
  └─► open_jira_settings_dialog(page, app_state, on_settings_saved=rebuild_sidebar)
  └─► Dialog renders with JQL import at TOP (ft.Card, visually primary)
  └─► User pastes JQL → on_import_jql() → POST /api/filters/parse-jql → filter rows populated
  └─► on_import_jql HTTP error → print([on_import_jql] HTTP …) + show_error_dialog (JQL + /api endpoint hint)
  └─► on_import_jql connection error → print([on_import_jql] …) + show_error_dialog (uvicorn start command)
  └─► User fills profile name, parent link, PAT → clicks "Save & Close"
  └─► on_save() validates → try block → updates app_state → set_jira_pat → calls on_settings_saved()
  └─► on_save exception → print([on_save] …) + show_error_dialog (Credential Manager hint)
  └─► rebuild_sidebar() → clears sidebar_col → adds ft.Checkbox per filter key → sidebar_col.update()

User toggles sidebar checkbox
  └─► _on_cb() → mutates app_state["selected_filter_keys"] (append or filter out)

User sends message
  └─► on_send()
      └─► selected_keys = app_state["selected_filter_keys"]
      └─► active_filters = {k:v for k,v in filters.items() if k in selected_keys}
                          (or all filters if selected_keys is empty)
      └─► POST /chat with active_filters + selected_filter_keys
      └─► HTTP non-200 → print([on_send] HTTP …) + show_error_dialog (status-code hint dict)
      └─► Exception   → print([on_send] Exception …) + show_error_dialog (uvicorn start command)
```

---

## 7. Verification Checklist

### Req 1 — JQL Import Priority
- [ ] JQL import section is the FIRST item in `_build_dialog_content`, wrapped in `ft.Card`
- [ ] Card heading reads "Quick Import — paste a JQL string to auto-populate filters below."
- [ ] All other settings sections follow in original order after JQL import

### Req 2 — Sidebar
- [ ] Sidebar `ft.Column` (width=220) is always visible on the left of the main window
- [ ] Sidebar shows "No filters saved." when `app_state["filters"]` is empty
- [ ] After saving settings, sidebar shows one `ft.Checkbox` per key in `app_state["filters"]`
- [ ] Toggling a sidebar checkbox mutates `app_state["selected_filter_keys"]` immediately
- [ ] `on_send` uses sidebar-driven `selected_filter_keys` to narrow `active_filters` before POST
- [ ] Window width set to `1050` to accommodate sidebar
- [ ] `open_jira_settings_dialog` accepts optional `on_settings_saved: Callable | None = None`

### Req 3 — NoneType guard
- [ ] `state.get("parent_link", "")` used in `jira_settings.py` at both bare-access sites (line 65, 73)

### Req 4 — Actionable Observability (Rule 3 compliance)
- [ ] `show_error_dialog` defined in `jira_settings.py`, imported in `main.py`
- [ ] `on_send` **non-200 path**: calls `print(f"[on_send] HTTP …")` + `show_error_dialog` with status-code hint dict
- [ ] `on_send` **exception path**: calls `print(f"[on_send] Exception …")` + `show_error_dialog` with exact `uvicorn` start command
- [ ] `on_send` no longer appends `ft.Text` error bubbles directly to `message_list`
- [ ] `on_import_jql` **non-200 path**: calls `print(f"[on_import_jql] HTTP …")` + `show_error_dialog` with JQL + endpoint hint
- [ ] `on_import_jql` **exception path**: calls `print(f"[on_import_jql] Exception …")` + `show_error_dialog` with `uvicorn` start command
- [ ] `on_import_jql` uses no `ft.SnackBar` calls
- [ ] `on_save` body (post-validation) is wrapped in try/except; exception path calls `print(f"[on_save] …")` + `show_error_dialog` with Windows Credential Manager path
- [ ] No error message in the entire diff contains the phrase "An error occurred" or omits a Remediation line
- [ ] No new packages added to `requirements.txt`
- [ ] No backend files modified
