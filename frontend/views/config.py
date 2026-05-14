from __future__ import annotations

from collections.abc import Callable

import flet as ft
import httpx

from frontend.views.dialogs import show_error_dialog


def open_config_dialog(page: ft.Page, on_closed: Callable[[], None] | None = None) -> None:
    # --- Controls (defined first so all handlers can reference them) ---
    copilot_status_ok = ft.Text(
        "✅ GitHub Copilot is authenticated and ready.",
        color=ft.Colors.GREEN,
        size=13,
        visible=False,
    )
    copilot_instructions = ft.Text(
        "GitHub Copilot is not authenticated.\n\n"
        "1. Click 'Open Terminal & Log In' below.\n"
        "2. Follow the prompts to run 'gh auth login'.\n"
        "3. Once complete, click 'Refresh' to verify.",
        size=13,
        visible=False,
    )
    open_terminal_btn = ft.ElevatedButton("Open Terminal & Log In", visible=False)
    refresh_auth_btn  = ft.TextButton("Refresh", visible=False)

    github_auth_container = ft.Column(
        controls=[copilot_status_ok, copilot_instructions, open_terminal_btn, refresh_auth_btn],
        spacing=8,
        visible=True,
    )
    status_text = ft.Text("", size=12)
    close_btn = ft.TextButton("Close")

    # --- Helpers ---
    def set_status(msg: str, color: str = "") -> None:
        status_text.value = msg
        status_text.color = color or None

    # --- Async helpers ---
    async def _check_copilot_status(force: bool = False) -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    "http://localhost:8000/auth/github/status",
                    params={"force": "true"} if force else {},
                )
            authenticated = r.json().get("authenticated", False)
            if authenticated:
                copilot_status_ok.visible    = True
                copilot_instructions.visible = False
                open_terminal_btn.visible    = False
                refresh_auth_btn.visible     = False
                set_status("Authenticated.", "green")
            else:
                copilot_status_ok.visible    = False
                copilot_instructions.visible = True
                open_terminal_btn.visible    = True
                refresh_auth_btn.visible     = True
                set_status("")
        except Exception as exc:
            set_status(
                f"Status check failed: {exc}. "
                "Remediation: ensure the backend is running on localhost:8000.",
                "red",
            )
        page.update()

    async def on_open_terminal(e: ft.ControlEvent) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post("http://localhost:8000/auth/github/spawn-terminal")
        except Exception as exc:
            set_status(
                f"Could not open terminal: {exc}. "
                "Remediation: ensure cmd.exe is accessible on this system.",
                "red",
            )
            page.update()

    async def on_refresh_auth(e: ft.ControlEvent) -> None:
        set_status("Checking authentication…")
        page.update()
        await _check_copilot_status(force=True)

    # --- Assign handlers ---
    open_terminal_btn.on_click = on_open_terminal
    refresh_auth_btn.on_click  = on_refresh_auth

    # --- Build dialog ---
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Model Settings — GitHub Copilot"),
        content=ft.Column(
            controls=[github_auth_container, status_text],
            tight=True,
            spacing=12,
            width=380,
        ),
        actions=[close_btn],
        actions_alignment=ft.MainAxisAlignment.END,
        on_dismiss=lambda e: on_closed() if on_closed else None,
    )

    async def on_close(e: ft.ControlEvent) -> None:
        try:
            page.pop_dialog()
            page.update()
            if on_closed:
                on_closed()
        except Exception as exc:
            show_error_dialog(page, f"Error closing dialog: {exc}")

    close_btn.on_click = on_close

    # --- Initialize state and show ---
    set_status("Checking authentication…")
    page.show_dialog(dialog)
    page.run_task(_check_copilot_status)
