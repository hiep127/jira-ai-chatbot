import asyncio
import threading
import uuid
from typing import Any

import httpx
import uvicorn
import flet as ft
from frontend.views.jira_settings import open_jira_settings_dialog
# Imported directly so the compiled binary can run the backend in-process.
# subprocess.Popen(sys.executable) would fork-bomb the packaged .exe.
from backend.main import app as _backend_app


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

    app_state: dict[str, Any] = {
        "filter_profile_name": "",
        "jira_env":            "",
        "parent_link":         "",
        "filters":             {},
    }

    message_list = ft.ListView(expand=True, spacing=8, padding=ft.padding.all(10), auto_scroll=True)

    async def on_send(e: ft.ControlEvent | None = None) -> None:
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
                        "prefixes":    [app_state["jira_env"]] if app_state["jira_env"] else [],
                        "mode":        "TEAM",
                        "parent_link": app_state["parent_link"],
                        "filters":     app_state["filters"],
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
                            tooltip="Settings",
                            on_click=lambda e: open_jira_settings_dialog(page, app_state),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
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
