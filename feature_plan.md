# Feature Plan: Jira Filter UI Fix

**Source requirements:** `req.md`
**Architecture laws:** `ARCHITECTURE.md` (all 5 rules), `CLAUDE.md` (Plan Mode)
**Status:** AWAITING EXPLICIT USER APPROVAL — no code will be written until approved.

---

## 1. Root-Cause Diagnosis

| # | File | Line(s) | Bug |
|---|------|---------|-----|
| B1 | `frontend/views/jira_settings.py` | 22, 46 | `_PROJECT_OPTIONS` is **never defined** — `NameError` crash when settings dialog opens |
| B2 | `frontend/views/jira_settings.py` | 98 | `rd["field_ac"].value` — `ft.AutoComplete` has no reliable `.value` property; the confirmed selection is only available inside the `on_select` callback |
| B3 | `frontend/views/jira_settings.py` | 51–52 | `row_data["value_container"].content = new_ctrl` + `page.update()` — no guard on `value_container.page is not None`; raises `AssertionError` if the container is not yet mounted |
| B4 | `frontend/views/jira_settings.py` | 107 | `or "SPAWS"` hardcoded fallback overwrites user intent when the field is empty |
| B5 | `backend/main.py` | 17 | `prefixes: list[str] = ["SPAWS", "LGE"]` — hardcoded defaults survive even when the user sets no environment |
| B6 | `frontend/views/jira_settings.py` | — | `filter_profile_name` key exists in `app_state` but is never read or written by the dialog |
| B7 | `frontend/main.py` | 82 | `"prefixes": [app_state["jira_env"]]` — sends `[""]` when `jira_env` is empty, polluting the backend query |

---

## 2. Files to Touch (exactly 3)

| File | Action |
|---|---|
| `frontend/views/jira_settings.py` | PRIMARY — 8 targeted changes (see §4A) |
| `frontend/main.py` | MINOR — 1 line guard (see §4B) |
| `backend/main.py` | MINOR — 1 line default change (see §4C) |

**Files confirmed untouched:**
`backend/agent/state.py`, `backend/agent/graph.py`, `backend/agent/nodes.py`,
`tools/`, `config/`, `tests/`, `requirements.txt`

---

## 3. Architecture Compliance

| Rule | Compliance |
|---|---|
| **1 · Strict Layers** | All UI changes stay in `frontend/`. Backend change is in the API contract layer only. No backend imports from frontend. |
| **2 · Context Budgeting** | No new Jira API calls. `_collect_filters()` emits a compact `dict[str, list[str]]`. No raw Jira JSON reaches frontend or LLM. |
| **3 · Observability** | No new network calls. Existing `try/except` in `on_send` is unchanged and already provides actionable error text. |
| **4 · State Safety** | `AgentState` TypedDict is **not modified**. `filter_profile_name` is UI-only; it is not sent to the backend and does not touch any LangGraph node routing. |
| **5 · Security** | No credentials. Removing `_PROJECT_OPTIONS` removes hardcoded project-key leakage. |

---

## 4. Detailed Change Specifications

### 4A — `frontend/views/jira_settings.py` (primary)

#### 4A-1 · Delete `_PROJECT_OPTIONS` constant (fixes B1)
The constant on line 15 (`_PROJECT_OPTIONS: list[str] = ["SPAWS", "LGE"]`) does not exist in the current file — but every reference to it must be removed.
All three occurrences (line 22 in `env_dd`, line 46 in `_on_field_select`) are removed as part of changes below.

#### 4A-2 · Replace `env_dd` Dropdown → `env_field` TextField (fixes B1)
```python
# REMOVE
env_dd = ft.Dropdown(
    options=[ft.dropdown.Option(o) for o in _PROJECT_OPTIONS],
    value=state["jira_env"],
    width=200,
    content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
)

# ADD
env_field = ft.TextField(
    label="Project Key",
    hint_text="e.g. SPAWS  (leave blank for all projects)",
    value=state.get("jira_env", ""),
    expand=True,
    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
)
```

#### 4A-3 · Add `profile_name_field` TextField (fixes B6)
Add immediately before `env_field`:
```python
profile_name_field = ft.TextField(
    label="Filter Profile Name",
    hint_text="e.g. My Sprint View",
    value=state.get("filter_profile_name", ""),
    expand=True,
    content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
)
```

#### 4A-4 · Replace `_on_field_select` (AutoComplete) → `_on_field_change` (Dropdown) (fixes B2, B3)
```python
# REMOVE _on_field_select entirely

# ADD
def _on_field_change(e: ft.ControlEvent, row_data: dict[str, Any]) -> None:
    field: str = e.control.value or ""
    if field == "Status":
        new_ctrl: ft.Control = ft.Dropdown(
            options=[ft.dropdown.Option(o) for o in _STATUS_OPTIONS],
            width=200,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
        )
    else:
        new_ctrl = ft.TextField(hint_text="Enter value...", width=200)

    value_container = row_data["value_container"]
    value_container.content = new_ctrl
    if value_container.page is not None:   # guard: only call update when mounted
        value_container.update()
```

#### 4A-5 · Replace `ft.AutoComplete` → `ft.Dropdown` in `_add_filter_row` (fixes B2)
```python
# REMOVE
field_ac = ft.AutoComplete(
    suggestions=[ft.AutoCompleteSuggestion(key=f, value=f) for f in _FIELD_SUGGESTIONS],
    on_select=lambda ev, rd=row_data: _on_field_select(ev, rd),
)

# ADD
field_dd = ft.Dropdown(
    options=[ft.dropdown.Option(f) for f in _FIELD_SUGGESTIONS],
    hint_text="Field",
    width=160,
    content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
    on_change=lambda ev, rd=row_data: _on_field_change(ev, rd),
)
```
Row dict key: `row_data["field_ac"]` → `row_data["field_dd"]`.
Row controls list: replace `field_ac` with `field_dd`.

#### 4A-6 · Fix `_collect_filters` (fixes B2)
```python
# BEFORE
field: str | None = rd["field_ac"].value

# AFTER
field: str | None = rd["field_dd"].value  # Dropdown .value is the confirmed selection
```

#### 4A-7 · Fix `on_save` (fixes B4, B6)
```python
# BEFORE
state["jira_env"] = env_dd.value or "SPAWS"

# AFTER
state["filter_profile_name"] = profile_name_field.value.strip()
state["jira_env"]             = env_field.value.strip()     # no hardcoded fallback
# parent_link and filters lines unchanged
```

#### 4A-8 · Update `_build_dialog_content` signature and layout
```python
# BEFORE signature
def _build_dialog_content(
    env_dd: ft.Dropdown,
    parent_link_field: ft.TextField,
    filter_rows_column: ft.Column,
    add_filter_row_fn: Callable[[ft.ControlEvent | None], None],
) -> ft.Column:

# AFTER signature
def _build_dialog_content(
    profile_name_field: ft.TextField,
    env_field: ft.TextField,
    parent_link_field: ft.TextField,
    filter_rows_column: ft.Column,
    add_filter_row_fn: Callable[[ft.ControlEvent | None], None],
) -> ft.Column:
    return ft.Column(
        controls=[
            ft.Text("1. Filter Profile Name", weight=ft.FontWeight.BOLD),
            profile_name_field,
            ft.Divider(),
            ft.Text("2. Target Jira Project Key", weight=ft.FontWeight.BOLD),
            env_field,
            ft.Divider(),
            ft.Text("3. Jira Parent Link (optional)", weight=ft.FontWeight.BOLD),
            parent_link_field,
            ft.Divider(),
            ft.Text("4. Additional Filters", weight=ft.FontWeight.BOLD),
            filter_rows_column,
            ft.TextButton("+ Add Filter", on_click=add_filter_row_fn),
        ],
        width=440,
        spacing=14,
    )
```
Call site in `open_jira_settings_dialog` updated to pass `profile_name_field` and `env_field`.

---

### 4B — `frontend/main.py` (minor, fixes B7)

> Note: `app_state` initialization (lines 52–57) already contains `filter_profile_name`, `jira_env`, `parent_link`, `filters` with empty defaults — **no change needed there**.

**Change — guard empty `jira_env` (line 82):**
```python
# BEFORE
"prefixes": [app_state["jira_env"]],

# AFTER
"prefixes": [app_state["jira_env"]] if app_state["jira_env"] else [],
```

---

### 4C — `backend/main.py` (minor, fixes B5)

**Change — remove hardcoded prefixes default (line 17):**
```python
# BEFORE
prefixes: list[str] = ["SPAWS", "LGE"]

# AFTER
prefixes: list[str] = []
```

---

## 5. End-to-End Data Flow After Changes

```
Settings dialog (jira_settings.py)
  profile_name_field  →  state["filter_profile_name"]   UI label only; not sent to backend
  env_field           →  state["jira_env"]               single project key or ""
  parent_link_field   →  state["parent_link"]
  _collect_filters()  →  state["filters"]               dict[str, list[str]]

on_send() in frontend/main.py
  POST /chat {
    prefixes:    [state["jira_env"]] if state["jira_env"] else [],
    parent_link: state["parent_link"],
    filters:     state["filters"],
  }

ChatRequest (backend/main.py) — Pydantic validates, no change to model fields
  prefixes: list[str]            ✅
  parent_link: str               ✅
  filters: dict[str, list[str]]  ✅

AgentState (backend/agent/state.py) — NOT modified
  prefixes, parent_link, filters already declared ✅
```

---

## 6. Open Questions (resolve before implementation)

1. **Multi-project support**: Should `env_field` accept comma-separated keys (`"SPAWS, LGE"`) and split on save, or is one key per session enough?
2. **Profile persistence**: Should filter profiles survive app restart (e.g., saved to a local JSON or `keyring`)?
3. **Header display**: Should the active profile name appear in the chat header (`"AI Agent — My Sprint View"`)?

---

**Waiting for explicit approval before any code is written.**
