import asyncio
import threading
import uuid
from typing import Any

import httpx
import uvicorn
import flet as ft
from frontend.views.jira_settings import open_jira_settings_dialog, show_error_dialog
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
    page.window.width = 1050
    page.window.height = 700
    await _start_backend()
    thread_id = str(uuid.uuid4())

    app_state: dict[str, Any] = {
        "filter_profile_name": "",
        "jira_env":            "",
        "parent_link":         "",
        "custom_jql":          "",
    }

    sidebar_col = ft.Column(
        controls=[
            ft.Text("Active Query", weight=ft.FontWeight.BOLD, size=14),
            ft.Divider(),
            ft.Text("No JQL configured.", italic=True, color=ft.Colors.GREY_500, size=12),
        ],
        width=220,
        spacing=4,
    )

    def rebuild_sidebar() -> None:
        sidebar_col.controls.clear()
        sidebar_col.controls.append(ft.Text("Active Query", weight=ft.FontWeight.BOLD, size=14))
        sidebar_col.controls.append(ft.Divider())
        jql = app_state.get("custom_jql", "")
        if jql:
            sidebar_col.controls.append(
                ft.Text(jql, size=11, color=ft.Colors.GREY_300, selectable=True)
            )
        else:
            sidebar_col.controls.append(
                ft.Text("No JQL configured.", italic=True, color=ft.Colors.GREY_500, size=12)
            )
        if sidebar_col.page:
            sidebar_col.update()

    message_list = ft.ListView(expand=True, spacing=8, padding=ft.padding.all(10), auto_scroll=True)

    async def process_chat_message(prompt_text: str) -> None:
        input_field.disabled = True
        send_btn.disabled = True
        message_list.controls.append(_make_bubble(prompt_text, "user"))
        thinking = ft.Text("Thinking...", italic=True, color=ft.Colors.GREY_400)
        message_list.controls.append(thinking)
        page.update()

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "http://localhost:8000/chat",
                    json={
                        "prompt":      prompt_text,
                        "thread_id":   thread_id,
                        "prefixes":    [app_state["jira_env"]] if app_state["jira_env"] else [],
                        "mode":        "TEAM",
                        "parent_link": app_state["parent_link"],
                        "custom_jql":  app_state.get("custom_jql", ""),
                    },
                )
            if r.status_code == 200:
                reply = r.json()["response"]
                message_list.controls.remove(thinking)
                message_list.controls.append(_make_bubble(reply, "assistant"))
            else:
                detail = r.json().get("detail", r.text)
                message_list.controls.remove(thinking)
                _status_hints: dict[int, str] = {
                    401: "Token expired or invalid — update your PAT in Settings → Jira Personal Access Token.",
                    403: "Access denied — verify your Jira role has permission to read these issues.",
                    404: "Endpoint not found — ensure the backend is the latest version.",
                    500: "Backend internal error — check the terminal log for a Python traceback.",
                }
                hint = _status_hints.get(r.status_code, "Check the terminal log for details.")
                print(f"[on_send] HTTP {r.status_code}: {detail}")
                show_error_dialog(page, f"Error {r.status_code}: {detail}\n\nRemediation: {hint}")
        except Exception as exc:
            message_list.controls.remove(thinking)
            print(f"[on_send] Exception: {exc}")
            show_error_dialog(
                page,
                f"Connection error: {exc}\n\n"
                "Remediation: start the backend with:\n"
                "  uvicorn backend.main:app --reload --port 8000",
            )

        input_field.disabled = False
        send_btn.disabled = False
        input_field.focus()
        page.update()

    async def on_send(e: ft.ControlEvent | None = None) -> None:
        text = input_field.value.strip()
        if not text:
            return
        input_field.value = ""
        await process_chat_message(text)

    async def on_daily_summary(e: ft.ControlEvent) -> None:
        if not app_state.get("custom_jql"):
            show_error_dialog(
                page,
                "Cannot generate summary: No JQL query configured.\n\n"
                "Remediation: Please open Settings (the gear icon) and enter a "
                "Custom JQL Query before requesting a summary."
            )
            return
        await process_chat_message(
            "Please generate a detailed daily summary based on my currently active Jira filters."
        )

    async def on_compact(e: ft.ControlEvent) -> None:
        input_field.disabled = True
        send_btn.disabled = True
        compact_btn.disabled = True
        compressing_bubble = _make_bubble("Compressing context...", "assistant")
        message_list.controls.append(compressing_bubble)
        page.update()

        bubble_removed = False

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    "http://localhost:8000/compact",
                    json={"thread_id": thread_id},
                )
            message_list.controls.remove(compressing_bubble)
            bubble_removed = True

            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "skipped":
                    notice_text = data.get("message", "Not enough messages to compress.")
                else:
                    notice_text = "System: Chat history compacted to save tokens."
                message_list.controls.append(
                    ft.Container(
                        content=ft.Text(notice_text, italic=True, size=11, color=ft.Colors.GREY_500),
                        padding=ft.padding.symmetric(horizontal=14, vertical=4),
                    )
                )
            else:
                detail = r.json().get("detail", r.text)
                show_error_dialog(page, f"Compact failed ({r.status_code}): {detail} If this persists, check the application logs for more detail.")

        except httpx.ConnectError:
            if not bubble_removed:
                message_list.controls.remove(compressing_bubble)
            show_error_dialog(page, "Could not reach the backend. Ensure the server is running.")
        except Exception as exc:
            if not bubble_removed:
                message_list.controls.remove(compressing_bubble)
            show_error_dialog(page, f"Compact request failed: {exc}. If this persists, check the application logs for more detail.")

        input_field.disabled = False
        send_btn.disabled = False
        compact_btn.disabled = False
        page.update()

    input_field = ft.TextField(
        hint_text="Type a message...",
        expand=True,
        on_submit=on_send,
        shift_enter=True,
    )
    send_btn = ft.IconButton(ft.Icons.SEND, on_click=on_send)
    compact_btn = ft.IconButton(
        ft.Icons.COMPRESS,
        tooltip="Compact Chat History",
        on_click=on_compact,
    )
    summary_btn = ft.ElevatedButton(
        "Generate Daily Summary",
        icon=ft.Icons.AUTO_AWESOME,
        on_click=on_daily_summary,
    )

    title_text = ft.Text("AI Agent", size=20, weight=ft.FontWeight.BOLD)
    settings_btn = ft.IconButton(
        ft.Icons.SETTINGS,
        tooltip="Settings",
        on_click=lambda e: open_jira_settings_dialog(page, app_state, on_settings_saved=rebuild_sidebar),
    )

    page.add(
        ft.Row(
            controls=[
                ft.Container(
                    content=sidebar_col,
                    width=220,
                    padding=ft.padding.symmetric(horizontal=8, vertical=10),
                    border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_800)),
                ),
                ft.Column(
                    controls=[
                        ft.Row([title_text, summary_btn, settings_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        message_list,
                        ft.Row([input_field, compact_btn, send_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )


ft.app(target=main)
