from __future__ import annotations

import flet as ft


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
