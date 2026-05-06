from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import flet as ft
import httpx

from config.providers import get_jira_pat, set_jira_pat
from frontend.views.config import open_config_dialog

_FIELD_SUGGESTIONS: list[str] = [
    "Project", "Assignee", "Status", "Reporter",
    "Priority", "Component", "Sprint", "Epic Link",
]
_STATUS_OPTIONS: list[str] = ["Open", "To Do", "In Progress", "Resolved", "Closed", "Done"]
_OPERATOR_OPTIONS: list[str] = ["=", "!=", "IN", "NOT IN", "~", "!~"]


class _MockControlEvent:
    def __init__(self, value: str) -> None:
        self.control = self
        self.value = value


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


def open_jira_settings_dialog(
    page: ft.Page,
    state: dict[str, Any],
    on_settings_saved: Callable[[], None] | None = None,
) -> None:
    filter_rows: list[dict[str, Any]] = []
    filter_rows_column = ft.Column(controls=[], spacing=6)

    profile_name_field = ft.TextField(
        label="Filter Profile Name",
        hint_text="e.g. My Sprint View",
        value=state.get("filter_profile_name", ""),
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    pat_field = ft.TextField(
        label="Jira Personal Access Token",
        password=True,
        can_reveal_password=True,
        value=get_jira_pat() or "",
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    _parsed_jira_env: str = state.get("jira_env", "")

    def _on_parent_link_change(e: ft.ControlEvent) -> None:
        nonlocal _parsed_jira_env
        raw = (e.control.value or "").strip()
        try:
            parsed = urlparse(raw)
            if parsed.scheme and parsed.netloc:
                _parsed_jira_env = f"{parsed.scheme}://{parsed.netloc}"
            else:
                _parsed_jira_env = ""
        except Exception:
            _parsed_jira_env = ""

    parent_link_field = ft.TextField(
        label="Jira Parent Link (required)",
        hint_text="e.g. https://jira.lge.com/browse/PROJ-42",
        value=state.get("parent_link", ""),
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
        on_change=_on_parent_link_change,
    )

    # Parse pre-filled parent_link on init
    _parsed_jira_env = ""
    if state.get("parent_link"):
        try:
            parsed = urlparse(state["parent_link"])
            if parsed.scheme and parsed.netloc:
                _parsed_jira_env = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass

    # Build saved-filter checkboxes from current state
    _selection_checkboxes: dict[str, ft.Checkbox] = {}
    saved_filters_col = ft.Column(controls=[], spacing=4)

    existing_selected: set[str] = set(state.get("selected_filter_keys", []))
    for field, values in state.get("filters", {}).items():
        is_checked = field in existing_selected if existing_selected else True
        cb = ft.Checkbox(
            label=f"{field}:  {', '.join(str(v) for v in values)}",
            value=is_checked,
        )
        _selection_checkboxes[field] = cb
        saved_filters_col.controls.append(cb)

    if not state.get("filters"):
        saved_filters_col.controls.append(
            ft.Text(
                "No saved filters yet. Add filters above and save.",
                italic=True,
                color=ft.Colors.GREY_500,
            )
        )

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
        if value_container.page is not None:
            value_container.update()

    def _remove_row(row_data: dict[str, Any]) -> None:
        filter_rows.remove(row_data)
        filter_rows_column.controls.remove(row_data["row"])
        page.update()

    def close_validation_dialog(e: ft.ControlEvent) -> None:
        validation_dialog.open = False
        page.update()

    validation_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Validation Error", color=ft.Colors.RED),
        content=ft.Text(
            "Filter criteria cannot be empty. "
            "Please populate all fields before proceeding."
        ),
        actions=[ft.TextButton("OK", on_click=close_validation_dialog)],
    )

    def validate_filters() -> bool:
        for rd in filter_rows:
            field = (rd["field_dd"].value or "").strip()
            op = (rd["operator_dd"].value or "").strip()
            ctrl = rd["value_container"].content
            val = (ctrl.value or "").strip() if ctrl else ""
            if not field or not op or not val:
                page.open(validation_dialog)
                return False
        return True

    def _add_filter_row(
        e: ft.ControlEvent | None = None,
        field: str | None = None,
        operator: str | None = None,
        value: str | None = None,
    ) -> None:
        if filter_rows and not validate_filters():
            return

        row_data: dict[str, Any] = {}

        field_dd = ft.Dropdown(
            options=[ft.dropdown.Option(f) for f in _FIELD_SUGGESTIONS],
            hint_text="Field",
            width=160,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
            on_change=lambda ev, rd=row_data: _on_field_change(ev, rd),
        )

        operator_dd = ft.Dropdown(
            options=[ft.dropdown.Option(op) for op in _OPERATOR_OPTIONS],
            hint_text="Op",
            width=110,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
        )

        value_container = ft.Container(
            content=ft.TextField(hint_text="Enter value...", width=200),
        )

        remove_btn = ft.IconButton(
            ft.Icons.REMOVE_CIRCLE_OUTLINE,
            tooltip="Remove filter",
            icon_color=ft.Colors.RED_400,
            on_click=lambda ev, rd=row_data: _remove_row(rd),
        )

        row = ft.Row(
            controls=[field_dd, operator_dd, value_container, remove_btn],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

        row_data["field_dd"] = field_dd
        row_data["operator_dd"] = operator_dd
        row_data["value_container"] = value_container
        row_data["row"] = row

        if field:
            field_dd.value = field
            if field == "Status":
                _on_field_change(_MockControlEvent(field), row_data)
        if operator:
            operator_dd.value = operator
        if value and value_container.content:
            value_container.content.value = value

        filter_rows.append(row_data)
        filter_rows_column.controls.append(row)
        page.update()

    def _collect_filters() -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for rd in filter_rows:
            field: str | None = rd["field_dd"].value
            ctrl = rd["value_container"].content
            value: str | None = ctrl.value if ctrl and ctrl.value else None
            if field and value:
                result.setdefault(field, [])
                if value not in result[field]:
                    result[field].append(value)
        return result

    def on_save(e: ft.ControlEvent) -> None:
        if not parent_link_field.value.strip():
            page.open(ft.SnackBar(
                content=ft.Text(
                    "Jira Parent Link is required. "
                    "Enter a full URL (e.g. https://jira.lge.com/browse/PROJ-42)."
                ),
                bgcolor=ft.Colors.RED_700,
            ))
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

    def on_cancel(e: ft.ControlEvent) -> None:
        dialog.open = False
        page.update()

    def open_model_config(e: ft.ControlEvent) -> None:
        open_config_dialog(page)

    jql_input = ft.TextField(
        hint_text="e.g., project = SPAWS AND status = 'In Progress' AND assignee = currentUser()",
        multiline=True,
        min_lines=2,
        max_lines=4,
        expand=True,
    )

    async def on_import_jql(e: ft.ControlEvent) -> None:
        raw = jql_input.value.strip()
        if not raw:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    "http://127.0.0.1:8000/api/filters/parse-jql",
                    json={"jql": raw},
                )
            if r.status_code == 200:
                parsed_rows = r.json()["rows"]
                filter_rows.clear()
                filter_rows_column.controls.clear()
                for row in parsed_rows:
                    _add_filter_row(
                        field=row["field"],
                        operator=row["operator"],
                        value=", ".join(row["value"]) if row["value"] else "",
                    )
                page.update()
            else:
                detail = r.json().get("detail", r.text)
                print(f"[on_import_jql] HTTP {r.status_code}: {detail}")
                show_error_dialog(
                    page,
                    f"JQL parse failed (HTTP {r.status_code}): {detail}\n\n"
                    "Remediation: verify the JQL syntax in Jira's issue navigator first, "
                    "then confirm the /api/filters/parse-jql endpoint is reachable at "
                    "http://127.0.0.1:8000.",
                )
        except Exception as exc:
            print(f"[on_import_jql] Exception: {exc}")
            show_error_dialog(
                page,
                f"Connection error: {exc}\n\n"
                "Remediation: start the backend with:\n"
                "  uvicorn backend.main:app --reload --port 8000",
            )

    import_btn = ft.ElevatedButton("Import & Apply", on_click=on_import_jql)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Settings"),
        content=_build_dialog_content(
            profile_name_field,
            pat_field,
            parent_link_field,
            saved_filters_col,
            filter_rows_column,
            _add_filter_row,
            jql_input,
            import_btn,
        ),
        actions=[
            ft.ElevatedButton("Save & Close", on_click=on_save),
            ft.TextButton("Model Settings", on_click=open_model_config),
            ft.TextButton("Cancel", on_click=on_cancel),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()


def _build_dialog_content(
    profile_name_field: ft.TextField,
    pat_field: ft.TextField,
    parent_link_field: ft.TextField,
    saved_filters_col: ft.Column,
    filter_rows_column: ft.Column,
    add_filter_row_fn: Callable[[ft.ControlEvent | None], None],
    jql_input: ft.TextField,
    import_btn: ft.ElevatedButton,
) -> ft.Container:
    column = ft.Column(
        controls=[
            ft.Card(
                content=ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Quick Import — paste a JQL string to auto-populate filters below.",
                                weight=ft.FontWeight.BOLD,
                            ),
                            jql_input,
                            import_btn,
                        ],
                        spacing=8,
                    ),
                    padding=ft.padding.all(12),
                ),
            ),
            ft.Divider(),
            ft.Text("Filter Profile Name", weight=ft.FontWeight.BOLD),
            profile_name_field,
            ft.Divider(),
            ft.Text("Jira Personal Access Token", weight=ft.FontWeight.BOLD),
            pat_field,
            ft.Divider(),
            ft.Text("Jira Parent Link (required)", weight=ft.FontWeight.BOLD),
            parent_link_field,
            ft.Divider(),
            ft.Text(
                "Current Saved Filters (check to include in agent queries)",
                weight=ft.FontWeight.BOLD,
            ),
            saved_filters_col,
            ft.Divider(),
            ft.Text("Additional Filter Rows", weight=ft.FontWeight.BOLD),
            filter_rows_column,
            ft.TextButton("+ Add Filter", on_click=add_filter_row_fn),
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=14,
    )
    return ft.Container(content=column, width=800)
