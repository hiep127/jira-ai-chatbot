import asyncio
import threading
import uuid

import httpx
import uvicorn
import flet as ft
from frontend.views.config import open_config_dialog
# Imported directly so the compiled binary can run the backend in-process.
# subprocess.Popen(sys.executable) would fork-bomb the packaged .exe.
from backend.main import app as _backend_app

_STATUS_OPTIONS  = ["Open", "To Do", "In Progress", "Resolved", "Closed", "Done"]
_PROJECT_OPTIONS = ["SPAWS", "LGE"]


async def _start_backend() -> None:
    config = uvicorn.Config(_backend_app, host="127.0.0.1", port=8000, log_level="error", log_config=None)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            async with httpx.AsyncClient(timeout=1) as client:
                r = await client.get("http://127.0.0.1:8000/health")
                if r.status_code == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(0.1)
    raise RuntimeError("Backend failed to start within 10 seconds.")


def _make_bubble(text: str, role: str) -> ft.Container:
    is_user = role == "user"
    return ft.Container(
        content=ft.Text(text, color=ft.Colors.WHITE, selectable=True),
        bgcolor=ft.Colors.BLUE_700 if is_user else ft.Colors.GREY_800,
        border_radius=ft.border_radius.all(12),
        padding=ft.padding.symmetric(horizontal=14, vertical=10),
        margin=ft.margin.only(
            left=80 if is_user else 0,
            right=0 if is_user else 80,
        ),
    )


async def main(page: ft.Page) -> None:
    page.title = "AI Agent"
    page.window.width = 800
    page.window.height = 700
    await _start_backend()
    thread_id = str(uuid.uuid4())

    message_list = ft.ListView(expand=True, spacing=8, padding=ft.padding.all(10), auto_scroll=True)

    parent_link_field = ft.TextField(
        hint_text="Jira Parent Link (e.g. PROJ-42)",
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
    )

    # Filter builder state — each entry holds refs to the row's controls
    filter_rows: list[dict] = []
    filter_rows_column = ft.Column(controls=[], spacing=6)

    def _on_field_change(e, row_data: dict) -> None:
        selected = e.control.value
        if selected == "Status":
            new_ctrl = ft.Dropdown(
                options=[ft.dropdown.Option(o) for o in _STATUS_OPTIONS],
                width=200,
                content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
            )
        elif selected == "Project":
            new_ctrl = ft.Dropdown(
                options=[ft.dropdown.Option(o) for o in _PROJECT_OPTIONS],
                width=200,
                content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
            )
        else:  # Assignee or any future text field
            new_ctrl = ft.TextField(hint_text="Enter value...", width=200)
        row_data["value_container"].content = new_ctrl
        page.update()

    def _remove_row(row_data: dict) -> None:
        filter_rows.remove(row_data)
        filter_rows_column.controls.remove(row_data["row"])
        page.update()

    def _add_filter_row(e=None) -> None:
        row_data: dict = {}

        field_dd = ft.Dropdown(
            options=[
                ft.dropdown.Option("Project"),
                ft.dropdown.Option("Assignee"),
                ft.dropdown.Option("Status"),
            ],
            hint_text="Field",
            width=150,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=4),
            on_change=lambda ev: _on_field_change(ev, row_data),
        )

        value_container = ft.Container(
            content=ft.TextField(hint_text="Enter value...", width=200),
        )

        remove_btn = ft.IconButton(
            ft.Icons.REMOVE_CIRCLE_OUTLINE,
            tooltip="Remove filter",
            icon_color=ft.Colors.RED_400,
            on_click=lambda ev: _remove_row(row_data),
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
        for row_data in filter_rows:
            field = row_data["field_dd"].value
            ctrl  = row_data["value_container"].content
            value = ctrl.value if ctrl and ctrl.value else None
            if field and value:
                if field not in result:
                    result[field] = []
                if value not in result[field]:  # prevent exact duplicates
                    result[field].append(value)
        return result

    async def on_send(e=None) -> None:
        text = input_field.value.strip()
        if not text:
            return

        input_field.value = ""
        input_field.disabled = True
        send_btn.disabled = True
        message_list.controls.append(_make_bubble(text, "user"))
        thinking = ft.Text("Thinking...", italic=True, color=ft.Colors.GREY_400)
        message_list.controls.append(thinking)
        page.update()

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "http://localhost:8000/chat",
                    json={
                        "prompt":      text,
                        "thread_id":   thread_id,
                        "prefixes":    ["SPAWS", "LGE"],
                        "mode":        "TEAM",
                        "parent_link": parent_link_field.value.strip(),
                        "filters":     _collect_filters(),
                    },
                )
            if r.status_code == 200:
                reply = r.json()["response"]
                message_list.controls.remove(thinking)
                message_list.controls.append(_make_bubble(reply, "assistant"))
            else:
                detail = r.json().get("detail", r.text)
                message_list.controls.remove(thinking)
                message_list.controls.append(
                    ft.Text(f"Error {r.status_code}: {detail}", color=ft.Colors.RED_400)
                )
        except Exception as exc:
            message_list.controls.remove(thinking)
            message_list.controls.append(
                ft.Text(f"Connection error: {exc}", color=ft.Colors.RED_400)
            )

        input_field.disabled = False
        send_btn.disabled = False
        input_field.focus()
        page.update()

    input_field = ft.TextField(
        hint_text="Type a message...",
        expand=True,
        on_submit=on_send,
        shift_enter=True,
    )
    send_btn = ft.IconButton(ft.Icons.SEND, on_click=on_send)

    page.add(
        ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("AI Agent", size=20, weight=ft.FontWeight.BOLD),
                        ft.IconButton(
                            ft.Icons.SETTINGS,
                            tooltip="Configure Model",
                            on_click=lambda e: open_config_dialog(page),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Row(
                    controls=[parent_link_field],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    controls=[
                        ft.Text("Filter Builder", size=13, color=ft.Colors.GREY_400),
                        ft.TextButton("+ Add Filter", on_click=_add_filter_row),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                filter_rows_column,
                message_list,
                ft.Row(
                    controls=[input_field, send_btn],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            expand=True,
        )
    )


ft.app(target=main)
