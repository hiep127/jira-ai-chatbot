# Flet 0.84 Implementation & API Rules

**Installed version: `flet==0.84.0`**
DO NOT guess Flet properties. Every rule below is verified against the installed version.

## 1. Dialogs and SnackBars

* **DO NOT** use `page.open()` or `page.close()` — these methods do **not exist** in 0.84 and will raise `AttributeError`.
* **DO NOT** use `page.dialog = ...` or `page.snack_bar = ...` (deprecated).
* **CORRECT:** `page.show_dialog(control)` to display, `page.pop_dialog()` to close from inside a handler.

```python
# Show a dialog
dialog = ft.AlertDialog(modal=True, title=ft.Text("Error"), ...)
page.show_dialog(dialog)

# Close from inside an action button
def _close(e):
    page.pop_dialog()
```

`ft.SnackBar` is also a `DialogControl` and can be passed to `page.show_dialog()`.

## 2. Icons

* **DO NOT** use `ft.icons.*` (lowercase module) — `ft.icons.DELETE` raises `AttributeError`.
* **CORRECT:** Use the `ft.Icons` enum class (capitalized).

```python
ft.IconButton(icon=ft.Icons.DELETE)
ft.Icon(ft.Icons.SETTINGS)
ft.IconButton(ft.Icons.SEND)
```

## 3. Colors

* **DO NOT** use `ft.colors.*` (lowercase) — deprecated in 0.84.
* **CORRECT:** Use the `ft.Colors` enum class (capitalized).

```python
ft.Text("hello", color=ft.Colors.GREY_400)
ft.Container(bgcolor=ft.Colors.BLUE_700)
```

## 4. Spacing and Layout Helpers

* **DO NOT** use `ft.padding.all()`, `ft.margin.all()`, `ft.border_radius.all()`, or `ft.border.only()` — these helpers were removed.
* **CORRECT:** Instantiate the dataclasses directly.

```python
ft.Padding(left=10, right=10, top=8, bottom=8)
ft.Margin(left=80, right=0, top=0, bottom=0)
ft.Border(right=ft.BorderSide(1, ft.Colors.GREY_800))
ft.BorderRadius(top_left=12, top_right=12, bottom_left=12, bottom_right=12)
```

## 5. Alignment

* `ft.alignment.center` does **not** exist (no `center` attribute on the module).
* **CORRECT:** Use the `ft.Alignment` class constant or constructor.

```python
ft.Container(alignment=ft.Alignment.CENTER)   # named constant
ft.Container(alignment=ft.Alignment(0, 0))    # equivalent constructor
```

## 6. Dropdown Options

* **DO NOT** pass raw strings to `Dropdown.options` — it will crash.
* **CORRECT:** Wrap every option in `ft.dropdown.Option()`.

```python
ft.Dropdown(options=[
    ft.dropdown.Option("Project"),
    ft.dropdown.Option("Assignee"),
])
```

## 7. Scrollable Chat / Large Lists

* **DO NOT** use `ft.Column(scroll=True)` for chat history — causes lag.
* **CORRECT:** Use `ft.ListView(expand=True, auto_scroll=True)`.

## 8. Button Text

* **DO NOT** pass `text=` as a keyword argument to `ft.TextButton`, `ft.ElevatedButton`, or `ft.OutlinedButton` — raises `TypeError: __init__() got an unexpected keyword argument 'text'`.
* **CORRECT:** Pass the label as the first **positional** argument, or use `content=ft.Text(...)` for rich content.

```python
# Correct — positional
ft.TextButton("Open Ticket", on_click=handler)
ft.ElevatedButton("Process Selected", icon=ft.Icons.CHECKLIST, on_click=handler)

# Correct — rich content
ft.TextButton(content=ft.Text("Open Ticket", color=ft.Colors.BLUE_400), on_click=handler)

# Wrong — raises TypeError
ft.TextButton(text="Open Ticket", on_click=handler)  # ❌
```

## 9. Background Async Tasks

* **DO NOT** use bare `asyncio.create_task()` inside Flet event handlers.
* **CORRECT:** Use `page.run_task(my_async_fn)` so Flet can manage the event loop.

## 10. DataTable Row Selection

* `ft.DataTable(show_checkbox_column=True)` is **silently non-functional** in Flet 0.84 — the column never renders.
* **CORRECT:** Add `ft.Checkbox` as the first `ft.DataCell` in each row with a matching `ft.DataColumn` header. Wire `on_change` to update state and sync `row.selected` for the highlight. Remove `row.on_select_changed` to avoid double-toggle.

```python
checkbox = ft.Checkbox(value=False)
row = ft.DataRow(cells=[ft.DataCell(checkbox), ...])

def _on_check(e):
    if checkbox.value:
        app_state["selected"].append(key)
        row.selected = True
    else:
        app_state["selected"] = [k for k in app_state["selected"] if k != key]
        row.selected = False
    row.update()

checkbox.on_change = _on_check
# NO row.on_select_changed assignment
```

## 11. AlertDialog Close Button in Title

* `ft.AlertDialog.title` accepts any control, not just `ft.Text`.
* To place an X close button in the dialog header, replace the plain `ft.Text(...)` title with an `ft.Row` containing the title text (`expand=True`) and an `ft.IconButton(ft.Icons.CLOSE, on_click=lambda e: page.pop_dialog())`.

```python
title=ft.Row(
    controls=[
        ft.Text("Select Model", expand=True),
        ft.IconButton(ft.Icons.CLOSE, tooltip="Close", on_click=lambda e: page.pop_dialog()),
    ],
    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    vertical_alignment=ft.CrossAxisAlignment.CENTER,
),
```
