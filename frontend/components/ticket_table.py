from __future__ import annotations

from typing import Any

import flet as ft

_CELL_TEXT = {"color": ft.Colors.WHITE}
_HEADER_TEXT = {"color": ft.Colors.WHITE, "weight": ft.FontWeight.BOLD}


def _make_row(t: dict, app_state: dict[str, Any], page: ft.Page) -> ft.DataRow:
    checkbox = ft.Checkbox(value=False)

    row = ft.DataRow(
        selected=False,
        cells=[
            ft.DataCell(checkbox),
            ft.DataCell(
                ft.TextButton(
                    t["key"],
                    style=ft.ButtonStyle(padding=ft.Padding(left=0, right=0, top=0, bottom=0)),
                    on_click=lambda e, u=t.get("url", ""): page.launch_url(u) if u else None,
                )
            ),
            ft.DataCell(ft.Text(t["instance"], **_CELL_TEXT)),
            ft.DataCell(ft.Text(t["status"], **_CELL_TEXT)),
            ft.DataCell(
                ft.Container(
                    content=ft.Text(t["summary"], max_lines=3, overflow=ft.TextOverflow.ELLIPSIS, **_CELL_TEXT),
                    width=400,
                )
            ),
            ft.DataCell(ft.Container(content=ft.Text(t["blocker"], **_CELL_TEXT), width=150)),
            ft.DataCell(ft.Text(t["updated"], **_CELL_TEXT)),
            ft.DataCell(ft.Text(t["aging"], **_CELL_TEXT)),
        ],
    )

    def _on_check(e: ft.ControlEvent) -> None:
        key = t["key"]
        if checkbox.value:
            app_state["selected_tickets"].append(key)
            row.selected = True
        else:
            app_state["selected_tickets"] = [k for k in app_state["selected_tickets"] if k != key]
            row.selected = False
        row.update()

    checkbox.on_change = _on_check
    return row


def build_ticket_table(
    tickets: list[dict],
    app_state: dict[str, Any],
    page: ft.Page,
) -> ft.Container:
    rows = [_make_row(t, app_state, page) for t in tickets]

    table = ft.DataTable(
        border=ft.Border(
            top=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
            right=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
            bottom=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
            left=ft.BorderSide(1, ft.Colors.BLUE_GREY_800),
        ),
        data_row_color={ft.ControlState.SELECTED: ft.Colors.BLUE_GREY_800},
        columns=[
            ft.DataColumn(ft.Text("✓",            **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("KEY",          **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("INSTANCE",     **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("STATUS",       **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("SUMMARY",      **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("BLOCKER",      **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("LAST UPDATED", **_HEADER_TEXT)),
            ft.DataColumn(ft.Text("AGING",        **_HEADER_TEXT)),
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
        bgcolor=ft.Colors.BLUE_GREY_900,
        border_radius=12,
        padding=ft.Padding(left=12, right=12, top=12, bottom=12),
    )
