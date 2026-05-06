# Feature Plan: UI Refactoring v3 — Validation & Quick Actions

**Source requirements:** `req.md`
**Architecture laws:** `CLAUDE.md` (Plan Mode, DRY, Actionable Observability)
**Planned:** 2026-05-06
**Status:** DRAFT — awaiting approval before any code is written

---

## 0. Architecture & Laws Compliance

| Rule | How This Plan Satisfies It |
|---|---|
| **Plan Mode** | No code written until user explicitly approves this document. |
| **DRY** | Req 3 explicitly refactors `on_send` to avoid duplicating the HTTP POST logic inside the new button callback. All chat dispatch flows through one shared `process_chat_message()` function. |
| **Actionable Observability** | Req 2 replaces the silent SnackBar path with `show_error_dialog` carrying an exact remediation string. |
| **Minimal stack** | No new packages. All changes use only existing Flet primitives. |
| **Credentials / Security** | No change to credential storage paths. |

**New packages required:** None.

---

## 1. Files Touched

| # | File | Requirement(s) |
|---|---|---|
| 1 | `frontend/views/jira_settings.py` | Req 1 (reorder), Req 2 (validation) |
| 2 | `frontend/main.py` | Req 3 (DRY refactor + Daily Summary button) |

**Files confirmed untouched:** `backend/`, `config/`, `tests/`, `requirements.txt`

---

## 2. Req 1 — Reorder Settings Dialog (Credentials First)

### 2.1 Current order in `_build_dialog_content()` (`jira_settings.py:373–413`)

1. `ft.Card` — JQL Quick Import (jql_input + import_btn)  ← currently FIRST
2. Divider
3. "Filter Profile Name" label + `profile_name_field`
4. Divider
5. "Jira Personal Access Token" label + `pat_field`
6. Divider
7. "Jira Parent Link (required)" label + `parent_link_field`
8. Divider
9. "Current Saved Filters..." label + `saved_filters_col`
10. Divider
11. "Additional Filter Rows" label + `filter_rows_column`
12. `ft.TextButton("+ Add Filter")`

### 2.2 New order (target)

1. "Profile Name \*" label + `profile_name_field`
2. Divider
3. "Jira PAT \*" label + `pat_field`
4. Divider
5. "Jira Parent Link \*" label + `parent_link_field`
6. Divider
7. `ft.Card` — JQL Quick Import (unchanged card content)
8. Divider
9. "Current Saved Filters..." label + `saved_filters_col`
10. Divider
11. "Additional Filter Rows" label + `filter_rows_column`
12. `ft.TextButton("+ Add Filter")`

### 2.3 Label changes

Two layers carry the field label — the `ft.Text` section heading inside `_build_dialog_content` AND the `label=` on the `ft.TextField` widget itself (defined higher up in `open_jira_settings_dialog`). Both must be updated.

| Widget | Current `label` | New `label` |
|---|---|---|
| `profile_name_field` (`jira_settings.py:52`) | `"Filter Profile Name"` | `"Profile Name *"` |
| `pat_field` (`jira_settings.py:60`) | `"Jira Personal Access Token"` | `"Jira PAT *"` |
| `parent_link_field` (`jira_settings.py:82`) | `"Jira Parent Link (required)"` | `"Jira Parent Link *"` |

And the `ft.Text` section headings in `_build_dialog_content` updated to match: `"Profile Name *"`, `"Jira PAT *"`, `"Jira Parent Link *"`.

### 2.4 Implementation notes

- Only the `controls=[]` list ordering and the three label strings change in `_build_dialog_content`. The function signature is unchanged.
- No change to widget creation logic, event handlers, or state management.

---

## 3. Req 2 — Mandatory Field Validation in `on_save`

### 3.1 Current state (`jira_settings.py:243–278`)

`on_save` currently:
1. Checks only `parent_link_field.value.strip()` — shows a `ft.SnackBar` on failure.
2. Does **not** check `profile_name_field` or `pat_field`.
3. Allows saving with empty profile name and/or empty PAT.

### 3.2 Target state

Replace the single `parent_link` SnackBar check with a combined validation block at the very top of `on_save`, before any state mutation:

```
if any of (profile_name_field, pat_field, parent_link_field) is empty/whitespace:
    call show_error_dialog(page, <exact message below>)
    return   ← halt completely, no state written
```

**Exact error message string (verbatim from req.md):**
```
Validation Error: Missing Required Fields.\n\nRemediation: You must provide a Profile Name, Jira PAT, and Parent Link before saving.
```

### 3.3 Implementation notes

- The existing `ft.SnackBar` block (lines 244–252) is **removed** and replaced by the new combined check.
- The existing `try/except` block that wraps state writes remains in place — the validation block sits above it, outside the try.
- The check uses `.strip()` to reject whitespace-only values.
- `show_error_dialog` is already defined in the same file and is already imported where needed — no new imports required.

### 3.4 Resulting `on_save` structure

```
def on_save(e):
    # --- NEW: Combined required-field validation ---
    if not profile_name_field.value.strip() \
       or not pat_field.value.strip() \
       or not parent_link_field.value.strip():
        show_error_dialog(page,
            "Validation Error: Missing Required Fields.\n\n"
            "Remediation: You must provide a Profile Name, Jira PAT, and "
            "Parent Link before saving.")
        return
    # --- EXISTING: filter-row validation (unchanged) ---
    if filter_rows and not validate_filters():
        return
    # --- EXISTING: try/except state-write block (unchanged) ---
    try:
        ...
    except Exception as exc:
        ...
```

---

## 4. Req 3 — "Generate Daily Summary" Quick-Action Button

### 4.1 Step A — Refactor `on_send` into `process_chat_message`

**Current `on_send` shape (`frontend/main.py:103–166`):**

```
async def on_send(e):
    text = input_field.value.strip()
    if not text: return
    input_field.value = ""
    input_field.disabled = True
    send_btn.disabled = True
    message_list.controls.append(_make_bubble(text, "user"))
    thinking = ft.Text("Thinking...", ...)
    message_list.controls.append(thinking)
    page.update()
    <build active_filters from app_state>
    try:
        <HTTP POST to /chat>
        <handle 200 or non-200>
    except:
        <handle connection error>
    input_field.disabled = False
    send_btn.disabled = False
    input_field.focus()
    page.update()
```

**Target: extract a new shared function**

```python
async def process_chat_message(prompt_text: str) -> None:
    """Core dispatch: show user bubble, call backend, render reply."""
    input_field.disabled = True
    send_btn.disabled = True
    message_list.controls.append(_make_bubble(prompt_text, "user"))
    thinking = ft.Text("Thinking...", italic=True, color=ft.Colors.GREY_400)
    message_list.controls.append(thinking)
    page.update()

    selected_keys = app_state.get("selected_filter_keys", [])
    active_filters = (
        {k: v for k, v in app_state["filters"].items() if k in selected_keys}
        if selected_keys
        else app_state["filters"]
    )

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "http://localhost:8000/chat",
                json={
                    "prompt":               prompt_text,
                    "thread_id":            thread_id,
                    "prefixes":             [app_state["jira_env"]] if app_state["jira_env"] else [],
                    "mode":                 "TEAM",
                    "parent_link":          app_state["parent_link"],
                    "filters":              active_filters,
                    "selected_filter_keys": selected_keys,
                },
            )
        if r.status_code == 200:
            reply = r.json()["response"]
            message_list.controls.remove(thinking)
            message_list.controls.append(_make_bubble(reply, "assistant"))
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
    except Exception as exc:
        message_list.controls.remove(thinking)
        print(f"[on_send] Exception: {exc}")
        show_error_dialog(
            page,
            f"Connection error: {exc}\n\n"
            "Remediation: start the backend with:\n"
            "  uvicorn backend.main:app --reload --port 8000",
        )

    input_field.disabled = False
    send_btn.disabled = False
    input_field.focus()
    page.update()
```

### 4.2 Step B — Slim down `on_send`

```python
async def on_send(e: ft.ControlEvent | None = None) -> None:
    text = input_field.value.strip()
    if not text:
        return
    input_field.value = ""
    await process_chat_message(text)
```

`on_send` is now a thin wrapper — read, guard, clear, delegate.

### 4.3 Step C — Create the button

```python
summary_btn = ft.ElevatedButton(
    "Generate Daily Summary",
    icon=ft.Icons.AUTO_AWESOME,
    on_click=on_daily_summary,
)
```

**Placement:** inside the header `ft.Row` alongside `title_text` and `settings_btn`:

```python
ft.Row(
    [title_text, summary_btn, settings_btn],
    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
)
```

This keeps the button visually anchored to the app chrome without disrupting the chat input row.

### 4.4 Step D — The trigger handler

```python
async def on_daily_summary(e: ft.ControlEvent) -> None:
    await process_chat_message(
        "Please generate a detailed daily summary based on my currently active Jira filters."
    )
```

This is an `async def` so Flet can await it. It makes exactly one call to `process_chat_message` — the HTTP POST logic is **not** duplicated.

---

## 5. Data Flow (post-change)

```
User types and presses Send / Enter
  └─► on_send(e)
        └─► strips & guards text
        └─► clears input_field.value
        └─► await process_chat_message(text)
              └─► disables input_field + send_btn
              └─► appends user bubble + "Thinking..."
              └─► POST /chat
              └─► appends reply or calls show_error_dialog
              └─► re-enables input_field + send_btn

User clicks "Generate Daily Summary"
  └─► on_daily_summary(e)
        └─► await process_chat_message("Please generate a detailed daily summary...")
              └─► (same shared path as above)
```

---

## 6. Verification Checklist

### Req 1 — Settings reorder
- [ ] `_build_dialog_content` lists `profile_name_field` before `pat_field` before `parent_link_field` before the JQL `ft.Card`
- [ ] `profile_name_field.label` is `"Profile Name *"`
- [ ] `pat_field.label` is `"Jira PAT *"`
- [ ] `parent_link_field.label` is `"Jira Parent Link *"`
- [ ] `ft.Text` section headings in `_build_dialog_content` match the new labels

### Req 2 — Mandatory field validation
- [ ] `on_save` checks all three fields (profile_name, pat, parent_link) before any state write
- [ ] Any empty/whitespace field triggers `show_error_dialog` with the exact verbatim message from req.md
- [ ] `on_save` returns immediately after showing the dialog (no partial state writes)
- [ ] The old `ft.SnackBar` parent_link-only check is removed
- [ ] `filter_rows` validation remains in place, below the new combined check

### Req 3 — Daily Summary button
- [ ] `process_chat_message(prompt_text: str)` defined inside `main()`, contains all HTTP logic
- [ ] `on_send` is a thin 4-line wrapper: strip, guard, clear, delegate
- [ ] `summary_btn = ft.ElevatedButton("Generate Daily Summary", icon=ft.Icons.AUTO_AWESOME)` exists
- [ ] `on_daily_summary` calls `process_chat_message` with the exact prompt string from req.md
- [ ] HTTP POST logic appears exactly **once** in `frontend/main.py`
- [ ] No new packages added
