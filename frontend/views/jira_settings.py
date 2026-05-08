from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import flet as ft

from config.providers import get_jira_pat, set_jira_pat
from frontend.views.config import open_config_dialog


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
    profile_name_field = ft.TextField(
        label="Profile Name *",
        hint_text="e.g. My Sprint View",
        value=state.get("filter_profile_name", ""),
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    pat_field = ft.TextField(
        label="Jira PAT *",
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
        label="Jira Parent Link *",
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

    custom_jql_field = ft.TextField(
        label="Custom JQL Query",
        multiline=True,
        min_lines=3,
        hint_text="e.g., assignee in (hang2.le, hiep.tran) AND resolution = Unresolved ORDER BY updated DESC",
        value=state.get("custom_jql", ""),
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    def on_save(e: ft.ControlEvent) -> None:
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

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Settings"),
        content=_build_dialog_content(
            profile_name_field,
            pat_field,
            parent_link_field,
            custom_jql_field,
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
    custom_jql_field: ft.TextField,
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
        ],
        scroll=ft.ScrollMode.AUTO,
        spacing=14,
    )
    return ft.Container(content=column, width=800)
