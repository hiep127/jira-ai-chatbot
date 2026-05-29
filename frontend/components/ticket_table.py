from __future__ import annotations

from typing import Any

import flet as ft


def _make_row(t: dict, app_state: dict[str, Any], page: ft.Page) -> ft.DataRow:
    row = ft.DataRow(
        selected=False,
        cells=[
            ft.DataCell(
                ft.TextButton(
                    t["key"],
                    style=ft.ButtonStyle(padding=ft.Padding(left=0, right=0, top=0, bottom=0)),
                    on_click=lambda e, u=t.get("url", ""): page.launch_url(u) if u else None,
                )
            ),
            ft.DataCell(ft.Text(t["instance"])),
            ft.DataCell(ft.Text(t["status"])),
            ft.DataCell(
                ft.Container(
                    content=ft.Text(t["summary"], max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
                    width=400,
                )
            ),
            ft.DataCell(ft.Container(content=ft.Text(t["blocker"]), width=150)),
            ft.DataCell(ft.Text(t["updated"])),
            ft.DataCell(ft.Text(t["aging"])),
        ],
    )

    def on_select_changed(e: ft.ControlEvent) -> None:
        row.selected = not row.selected
        row.update()
        key = t["key"]
        if row.selected:
            app_state["selected_tickets"].append(key)
        else:
            app_state["selected_tickets"] = [
                k for k in app_state["selected_tickets"] if k != key
            ]

    row.on_select_changed = on_select_changed
    return row


def build_ticket_table(
    tickets: list[dict],
    app_state: dict[str, Any],
    page: ft.Page,
) -> ft.Container:
    rows = [_make_row(t, app_state, page) for t in tickets]

    table = ft.DataTable(
        show_checkbox_column=True,
        border=ft.Border(
            top=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
            right=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
            bottom=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
            left=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
        ),
        data_row_color={ft.ControlState.SELECTED: ft.Colors.BLUE_GREY_800},
        columns=[
            ft.DataColumn(ft.Text("KEY",          weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("INSTANCE",     weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("STATUS",       weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("SUMMARY",      weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("BLOCKER",      weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("LAST UPDATED", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("AGING",        weight=ft.FontWeight.BOLD)),
        ],
        rows=rows,
    )

    def _on_process_selected(e: ft.ControlEvent) -> None:
        selected = app_state.get("selected_tickets", [])
        label = ", ".join(selected) if selected else "none"
        page.show_dialog(
            ft.SnackBar(ft.Text(f"Selected tickets: {label}"))
        )

    action_btn = ft.ElevatedButton(
        "Process Selected",
        icon=ft.Icons.CHECKLIST,
        on_click=_on_process_selected,
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[table],
                    scroll=ft.ScrollMode.AUTO,
                ),
                ft.Row(
                    controls=[action_btn],
                    alignment=ft.MainAxisAlignment.END,
                ),
            ],
        ),
        bgcolor=ft.Colors.GREY_800,
        border_radius=12,
        padding=ft.Padding(left=12, right=12, top=12, bottom=12),
    )
