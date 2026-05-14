from __future__ import annotations

import flet as ft


def show_error_dialog(page: ft.Page, error_message: str) -> None:
    def _close(ev: ft.ControlEvent) -> None:
        page.pop_dialog()

    err_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Application Error", color=ft.Colors.RED),
        content=ft.Text(str(error_message)),
        actions=[ft.TextButton("OK", on_click=_close)],
    )
    page.show_dialog(err_dlg)
