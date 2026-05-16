from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlparse

import flet as ft
import httpx

from config.providers import (
    delete_jira_pat_for_profile,
    get_jira_pat_for_profile,
    set_jira_pat_for_profile,
)
from config.settings import get_profiles, save_profiles
from frontend.views.config import open_config_dialog
from frontend.views.dialogs import show_error_dialog

logger = logging.getLogger(__name__)


def open_jira_settings_dialog(
    page: ft.Page,
    state: dict,
    on_settings_saved: Callable[[], None] | None = None,
    on_auth_change: Callable[[], None] | None = None,
) -> None:
    profiles: list[dict] = [dict(p) for p in get_profiles()]
    selected_idx: list[int] = [-1]

    # --- Form fields ---
    name_field = ft.TextField(label="Name *", hint_text="e.g. SPAWS", expand=True)
    host_field = ft.TextField(label="Host URL *", hint_text="https://jira.example.com", expand=True)
    pat_field = ft.TextField(
        label="PAT *",
        password=True,
        can_reveal_password=True,
        expand=True,
        hint_text="Leave blank to keep existing PAT",
    )
    jql_field = ft.TextField(
        label="Custom JQL",
        multiline=True,
        min_lines=3,
        expand=True,
        hint_text="assignee IN (...) AND resolution = Unresolved",
    )

    profile_list_view = ft.ListView(expand=True)
    right_panel = ft.Container(expand=True, padding=ft.Padding(left=16, right=0, top=0, bottom=0))

    def _build_list_tiles() -> list[ft.ListTile]:
        return [
            ft.ListTile(
                title=ft.Text(p.get("name") or "(unnamed)"),
                selected=(i == selected_idx[0]),
                on_click=lambda e, i=i: _select_profile(e, i),
                dense=True,
            )
            for i, p in enumerate(profiles)
        ]

    def _show_placeholder() -> None:
        right_panel.content = ft.Container(
            content=ft.Text(
                "Select a profile or click + Add Profile.",
                color=ft.Colors.GREY_500,
            ),
            alignment=ft.Alignment(0, 0),
            expand=True,
        )

    def _show_form() -> None:
        right_panel.content = _build_form_column()

    def _build_form_column() -> ft.Column:
        return ft.Column(
            controls=[
                name_field,
                host_field,
                pat_field,
                jql_field,
                ft.Row(
                    controls=[
                        ft.ElevatedButton(
                            "Save Profile",
                            on_click=_save_profile,
                            icon=ft.Icons.SAVE,
                        ),
                        ft.TextButton(
                            "Delete Profile",
                            on_click=_delete_profile,
                            style=ft.ButtonStyle(color=ft.Colors.RED_400),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=12,
        )

    def _clear_form() -> None:
        name_field.value = ""
        host_field.value = ""
        pat_field.value = ""
        jql_field.value = ""

    def _add_profile(e: ft.ControlEvent) -> None:
        profiles.append({"name": "", "host": "", "custom_jql": ""})
        selected_idx[0] = len(profiles) - 1
        _clear_form()
        profile_list_view.controls = _build_list_tiles()
        _show_form()
        page.update()

    def _select_profile(e: ft.ControlEvent, i: int) -> None:
        selected_idx[0] = i
        p = profiles[i]
        name_field.value = p.get("name", "")
        host_field.value = p.get("host", "")
        jql_field.value = p.get("custom_jql", "")
        pat_field.value = ""
        profile_list_view.controls = _build_list_tiles()
        _show_form()
        page.update()

    async def _save_profile(e: ft.ControlEvent) -> None:
        name = name_field.value.strip()
        host = host_field.value.strip()

        if not name:
            show_error_dialog(
                page,
                "Validation Error: Name is required.\n\nRemediation: Enter a unique profile name (e.g. SPAWS).",
            )
            return

        if not host:
            show_error_dialog(
                page,
                "Validation Error: Host URL is required.\n\nRemediation: Enter the full Jira server URL (e.g. https://jira.example.com).",
            )
            return

        try:
            parsed = urlparse(host)
            if not (parsed.scheme and parsed.netloc):
                raise ValueError("Missing scheme or host")
        except Exception:
            show_error_dialog(
                page,
                "Validation Error: Host URL is invalid.\n\nRemediation: Use a full URL including https:// (e.g. https://jira.example.com).",
            )
            return

        profiles[selected_idx[0]] = {
            "name": name,
            "host": host,
            "custom_jql": jql_field.value.strip(),
        }

        pat = pat_field.value.strip()
        if pat:
            try:
                set_jira_pat_for_profile(name, pat)
            except Exception as exc:
                show_error_dialog(
                    page,
                    f"Failed to save PAT for '{name}': {exc}\n\n"
                    "Remediation: Check that Windows Credential Manager is accessible "
                    "(Control Panel → Credential Manager → Windows Credentials).",
                )
                return

        try:
            save_profiles(profiles)
        except Exception as exc:
            show_error_dialog(page, f"Failed to save profiles: {exc}")
            return

        profile_list_view.controls = _build_list_tiles()
        page.show_dialog(ft.SnackBar(ft.Text("Profile saved."), open=True))
        page.update()

    async def _delete_profile(e: ft.ControlEvent) -> None:
        if selected_idx[0] < 0:
            return

        name = profiles[selected_idx[0]].get("name", "")
        try:
            delete_jira_pat_for_profile(name)
        except Exception:
            pass

        profiles.pop(selected_idx[0])
        save_profiles(profiles)
        selected_idx[0] = -1
        _clear_form()
        _show_placeholder()
        profile_list_view.controls = _build_list_tiles()
        page.update()

    async def on_save_and_close(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        if on_auth_change:
            on_auth_change()

        async def _fire_reload() -> None:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post("http://localhost:8000/reload-profiles")
            except Exception as exc:
                logger.warning(
                    "[jira_settings] reload-profiles failed: %s. App restart may be required.", exc
                )

        page.run_task(_fire_reload)
        if on_settings_saved:
            on_settings_saved()
        page.update()

    async def on_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        if on_auth_change:
            on_auth_change()
        page.update()

    async def open_model_settings(e: ft.ControlEvent) -> None:
        try:
            open_config_dialog(page, on_closed=on_auth_change)
        except Exception as exc:
            show_error_dialog(
                page,
                f"Failed to open Model Settings: {exc}\n\nRemediation: restart the application.",
            )

    _show_placeholder()
    profile_list_view.controls = _build_list_tiles()

    left_panel = ft.Container(
        content=ft.Column(
            controls=[
                ft.Text("Profiles", weight=ft.FontWeight.BOLD, size=12),
                profile_list_view,
                ft.TextButton("+ Add Profile", on_click=_add_profile),
            ],
            expand=True,
        ),
        width=160,
        border=ft.Border(right=ft.BorderSide(1, ft.Colors.GREY_700)),
        padding=ft.Padding(left=0, right=8, top=0, bottom=0),
    )

    content = ft.Container(
        content=ft.Row(
            controls=[left_panel, right_panel],
            expand=True,
        ),
        width=860,
        height=480,
    )

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Jira Profile Settings"),
        content=content,
        actions=[
            ft.ElevatedButton("Save & Close", on_click=on_save_and_close),
            ft.TextButton("Model Settings", on_click=open_model_settings),
            ft.TextButton("Cancel", on_click=on_cancel),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)
