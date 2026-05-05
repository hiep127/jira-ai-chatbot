from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from frontend.views.config import open_config_dialog

_FIELD_SUGGESTIONS: list[str] = [
    "Project", "Assignee", "Status", "Reporter",
    "Priority", "Component", "Sprint", "Epic Link",
]
_STATUS_OPTIONS: list[str] = ["Open", "To Do", "In Progress", "Resolved", "Closed", "Done"]


def open_jira_settings_dialog(page: ft.Page, state: dict[str, Any]) -> None:
    filter_rows: list[dict[str, Any]] = []
    filter_rows_column = ft.Column(controls=[], spacing=6)

    profile_name_field = ft.TextField(
        label="Filter Profile Name",
        hint_text="e.g. My Sprint View",
        value=state.get("filter_profile_name", ""),
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    env_field = ft.TextField(
        label="Project Key",
        hint_text="e.g. SPAWS  (leave blank for all projects)",
        value=state.get("jira_env", ""),
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    parent_link_field = ft.TextField(
        hint_text="Jira Parent Link (e.g. PROJ-42)",
        value=state["parent_link"],
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
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

    def _add_filter_row(e: ft.ControlEvent | None = None) -> None:
        row_data: dict[str, Any] = {}

        field_dd = ft.Dropdown(
            options=[ft.dropdown.Option(f) for f in _FIELD_SUGGESTIONS],
            hint_text="Field",
            width=160,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
            on_change=lambda ev, rd=row_data: _on_field_change(ev, rd),
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
            controls=[field_dd, value_container, remove_btn],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

        row_data["field_dd"] = field_dd
        row_data["value_container"] = value_container
        row_data["row"] = row

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
        state["filter_profile_name"] = profile_name_field.value.strip()
        state["jira_env"]             = env_field.value.strip()
        state["parent_link"]          = parent_link_field.value.strip()
        state["filters"]              = _collect_filters()
        dialog.open = False
        page.update()

    def on_cancel(e: ft.ControlEvent) -> None:
        dialog.open = False
        page.update()

    def open_model_config(e: ft.ControlEvent) -> None:
        open_config_dialog(page)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Settings"),
        content=_build_dialog_content(
            profile_name_field, env_field, parent_link_field, filter_rows_column, _add_filter_row
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
