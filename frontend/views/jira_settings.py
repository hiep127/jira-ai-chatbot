from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import flet as ft

from config.providers import get_jira_pat, set_jira_pat
from config.settings import save_filter_settings
from frontend.views.config import open_config_dialog
from frontend.views.dialogs import show_error_dialog


def open_jira_settings_dialog(
    page: ft.Page,
    state: dict[str, Any],
    on_settings_saved: Callable[[], None] | None = None,
    on_auth_change: Callable[[], None] | None = None,
) -> None:
    profile_name_field = ft.TextField(
        label="Profile Name *",
        hint_text="e.g. My Sprint View",
        value=state.get("filter_profile_name", ""),
        expand=True,
        content_padding=ft.Padding(left=10, right=10, top=8, bottom=8),
    )

    pat_field = ft.TextField(
        label="Jira PAT *",
        password=True,
        can_reveal_password=True,
        value=get_jira_pat() or "",
        expand=True,
        content_padding=ft.Padding(left=10, right=10, top=8, bottom=8),
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
        label="Jira Parent Link *",
        hint_text="e.g. https://jira.lge.com/browse/PROJ-42",
        value=state.get("parent_link", ""),
        expand=True,
        content_padding=ft.Padding(left=10, right=10, top=8, bottom=8),
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

    custom_jql_field = ft.TextField(
        label="Custom JQL Query",
        multiline=True,
        min_lines=3,
        hint_text="e.g., assignee in (hang2.le, hiep.tran) AND resolution = Unresolved ORDER BY updated DESC",
        value=state.get("custom_jql", ""),
        expand=True,
        content_padding=ft.Padding(left=10, right=10, top=8, bottom=8),
    )

    def _make_filter_row(field: str = "", value: str = "") -> ft.Row:
        row: ft.Row = ft.Row(controls=[])

        def _remove_row(e: ft.ControlEvent) -> None:
            try:
                filter_rows_column.controls.remove(row)
                page.update()
            except Exception as exc:
                show_error_dialog(page, f"Could not remove filter row: {exc}")

        row.controls = [
            ft.Dropdown(
                value=field or None,
                options=[
                    ft.dropdown.Option("Project"),
                    ft.dropdown.Option("Assignee"),
                    ft.dropdown.Option("Status"),
                ],
                expand=True,
            ),
            ft.Text("="),
            ft.TextField(value=value, expand=True),
            ft.IconButton(icon=ft.Icons.DELETE, on_click=_remove_row),
        ]
        return row

    filter_rows_column = ft.Column(controls=[], spacing=8)
    for k, v in state.get("filters", {}).items():
        filter_rows_column.controls.append(_make_filter_row(k, v))

    def _add_filter_row(e: ft.ControlEvent) -> None:
        try:
            filter_rows_column.controls.append(_make_filter_row())
            page.update()
        except Exception as exc:
            show_error_dialog(page, f"Could not add filter row: {exc}")

    add_filter_btn = ft.TextButton("+ Add Filter", on_click=_add_filter_row)

    async def on_save(e: ft.ControlEvent) -> None:
        if (
            not profile_name_field.value.strip()
            or not pat_field.value.strip()
            or not parent_link_field.value.strip()
        ):
            show_error_dialog(
                page,
                "Validation Error: Missing Required Fields.\n\n"
                "Remediation: You must provide a Profile Name, Jira PAT, and "
                "Parent Link before saving.",
            )
            return
        try:
            state["filter_profile_name"] = profile_name_field.value.strip()
            state["jira_env"]             = _parsed_jira_env
            state["parent_link"]          = parent_link_field.value.strip()
            state["custom_jql"]           = custom_jql_field.value.strip()
            filters: dict[str, str] = {}
            for row in filter_rows_column.controls:
                key = (row.controls[0].value or "").strip()
                val = (row.controls[2].value or "").strip()
                if key and val:
                    filters[key] = val
            state["filters"] = filters
            pat = pat_field.value.strip()
            if pat:
                set_jira_pat(pat)
            save_filter_settings(state)
            page.pop_dialog()
            if on_auth_change:
                on_auth_change()
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

    async def on_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        if on_auth_change:
            on_auth_change()
        page.update()

    async def open_model_config(e: ft.ControlEvent) -> None:
        try:
            open_config_dialog(page, on_closed=on_auth_change)
        except Exception as exc:
            print(f"[open_model_config] {exc}")
            show_error_dialog(
                page,
                f"Failed to open Model Settings: {exc}\n\n"
                "Remediation: restart the application.",
            )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Settings"),
        content=_build_dialog_content(
            profile_name_field,
            pat_field,
            parent_link_field,
            custom_jql_field,
            filter_rows_column,
            add_filter_btn,
        ),
        actions=[
            ft.ElevatedButton("Save & Close", on_click=on_save),
            ft.TextButton("Model Settings", on_click=open_model_config),
            ft.TextButton("Cancel", on_click=on_cancel),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)


def _build_dialog_content(
    profile_name_field: ft.TextField,
    pat_field: ft.TextField,
    parent_link_field: ft.TextField,
    custom_jql_field: ft.TextField,
    filter_rows_column: ft.Column,
    add_filter_btn: ft.TextButton,
) -> ft.Container:
    column = ft.Column(
        controls=[
            ft.Text("Profile Name *", weight=ft.FontWeight.BOLD),
            profile_name_field,
            ft.Divider(),
            ft.Text("Jira PAT *", weight=ft.FontWeight.BOLD),
            pat_field,
            ft.Divider(),
            ft.Text("Jira Parent Link *", weight=ft.FontWeight.BOLD),
            parent_link_field,
            ft.Divider(),
            ft.Text("Custom JQL Query", weight=ft.FontWeight.BOLD),
            custom_jql_field,
            ft.Divider(),
            ft.Row(
                controls=[
                    ft.Text("Filters", weight=ft.FontWeight.BOLD),
                    add_filter_btn,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            filter_rows_column,
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=14,
    )
    return ft.Container(content=column, width=800)
