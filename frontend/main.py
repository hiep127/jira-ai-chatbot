import asyncio
import threading
import uuid
from typing import Any

import httpx
import uvicorn
import flet as ft
from config.settings import (
    get_active_profiles,
    get_profiles,
    load_filter_settings,
    save_active_profiles,
)
from frontend.views.jira_settings import open_jira_settings_dialog
from frontend.views.dialogs import show_error_dialog
from frontend.components.model_picker import open_model_picker
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
        border_radius=12,
        padding=ft.Padding(left=14, right=14, top=10, bottom=10),
        margin=ft.Margin(left=80 if is_user else 0, right=0 if is_user else 80, top=0, bottom=0),
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
        "model_id":            "",
        "model_name":          "",
        "model_tier":          "",
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
        if _profiles:
            sidebar_col.controls.append(
                ft.Text("Active Profiles", weight=ft.FontWeight.BOLD, size=14)
            )
            sidebar_col.controls.append(
                ft.Row(controls=_build_profile_chips(_profiles), wrap=True, spacing=4)
            )
            sidebar_col.controls.append(ft.Divider())
        sidebar_col.controls.append(
            ft.Text("Active Query", weight=ft.FontWeight.BOLD, size=14)
        )
        jql = app_state.get("custom_jql", "")
        if jql:
            sidebar_col.controls.append(
                ft.Text(jql, size=12, color=ft.Colors.GREY_100, selectable=True, no_wrap=False)
            )
        else:
            sidebar_col.controls.append(
                ft.Text("No JQL configured.", italic=True, color=ft.Colors.GREY_500, size=12)
            )
        if sidebar_col.page:
            sidebar_col.update()

    message_list = ft.ListView(expand=True, spacing=8, padding=10, auto_scroll=True)

    auth_guard_container = ft.Container(
        content=ft.Column(
            controls=[
                ft.Icon(ft.Icons.SETTINGS, size=48, color=ft.Colors.ORANGE_400),
                ft.Text(
                    "GitHub Copilot is not authenticated. Please click the "
                    "Settings icon → Model Settings to set up your Copilot account first.",
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.GREY_400,
                    size=14,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        ),
        visible=False,
        expand=True,
        alignment=ft.Alignment.CENTER,
    )

    async def process_chat_message(prompt_text: str) -> None:
        input_field.disabled = True
        send_btn.disabled = True
        summary_btn.disabled = True
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
                        "prefixes":    list(app_state["active_profiles"]),
                        "mode":        "TEAM",
                        "parent_link": app_state.get("parent_link", ""),
                        "custom_jql":  app_state.get("custom_jql", ""),
                        "model_id":    app_state.get("model_id", ""),
                    },
                )
            if r.status_code == 200:
                reply = r.json()["response"]
                message_list.controls.remove(thinking)
                message_list.controls.append(_make_bubble(reply, "assistant"))
            else:
                detail = r.json().get("detail", r.text)
                message_list.controls.remove(thinking)

                if r.status_code == 401 and "GitHub CLI" in detail:
                    page.show_dialog(
                        ft.SnackBar(
                            ft.Text(
                                "GitHub Copilot is not authenticated. "
                                "Re-authenticate in Settings → Model Settings."
                            ),
                            bgcolor=ft.Colors.ORANGE_700,
                        )
                    )
                else:
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
        summary_btn.disabled = False
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
                    json={"thread_id": thread_id, "model_id": app_state.get("model_id", "")},
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
                        padding=ft.Padding(left=14, right=14, top=4, bottom=4),
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
    model_chip_label = ft.Text("Select model", size=13)
    model_chip = ft.TextButton(
        content=model_chip_label,
        on_click=lambda e: open_model_picker(page, app_state, _on_model_selected),
    )

    def _on_model_selected() -> None:
        name = app_state.get("model_name", "")
        tier = app_state.get("model_tier", "")
        model_chip_label.value = f"{name} · {tier}" if name else "Select model"
        page.update()

    _profiles: list[dict] = get_profiles()

    def _build_profile_chips(current_profiles: list[dict]) -> list[ft.Chip]:
        return [
            ft.Chip(
                label=ft.Text(p["name"]),
                selected=p["name"] in app_state["active_profiles"],
                on_select=lambda e, name=p["name"]: _toggle_profile(name, e.control.selected),
            )
            for p in current_profiles
        ]

    def _toggle_profile(name: str, is_selected: bool) -> None:
        if is_selected:
            app_state["active_profiles"].add(name)
        else:
            app_state["active_profiles"].discard(name)
        save_active_profiles(list(app_state["active_profiles"]))
        page.update()

    saved = load_filter_settings()
    if saved:
        app_state.update(saved)
        name = app_state.get("model_name", "")
        tier = app_state.get("model_tier", "")
        model_chip_label.value = f"{name} · {tier}" if name else "Select model"
        app_state["active_profiles"] = (
            set(saved["active_profiles"]) if "active_profiles" in saved else {p["name"] for p in _profiles}
        )
    else:
        app_state["active_profiles"] = {p["name"] for p in _profiles}

    async def _prefetch_models() -> None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.get("http://localhost:8000/models")
        except Exception:
            pass

    async def refresh_auth_state() -> None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:8000/auth/github/status")
            authenticated = r.json()["authenticated"]
        except Exception:
            authenticated = False

        auth_guard_container.visible = not authenticated
        message_list.visible = authenticated
        input_field.disabled = not authenticated
        send_btn.disabled = not authenticated
        compact_btn.disabled = not authenticated
        summary_btn.disabled = not authenticated
        page.update()

        if authenticated:
            page.run_task(_prefetch_models)

    def _on_settings_saved() -> None:
        fresh = get_profiles()
        existing_names = {p["name"] for p in _profiles}
        for p in fresh:
            if p["name"] not in existing_names:
                app_state["active_profiles"].add(p["name"])
        _profiles.clear()
        _profiles.extend(fresh)
        rebuild_sidebar()
        page.update()

    async def on_settings(e: ft.ControlEvent) -> None:
        try:
            open_jira_settings_dialog(
                page,
                app_state,
                on_settings_saved=_on_settings_saved,
                on_auth_change=lambda: page.run_task(refresh_auth_state),
            )
        except Exception as exc:
            print(f"[on_settings] {exc}")
            show_error_dialog(
                page,
                f"Failed to open Settings: {exc}\n\nRemediation: restart the application.",
            )

    settings_btn = ft.IconButton(
        ft.Icons.SETTINGS,
        tooltip="Settings",
        on_click=on_settings,
    )

    await refresh_auth_state()

    page.add(
        ft.Row(
            controls=[
                ft.Container(
                    content=sidebar_col,
                    width=220,
                    bgcolor=ft.Colors.GREY_900,
                    padding=ft.Padding(left=8, right=8, top=10, bottom=10),
                    border=ft.Border(right=ft.BorderSide(1, ft.Colors.GREY_700)),
                ),
                ft.Column(
                    controls=[
                        ft.Row([title_text, summary_btn, settings_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        auth_guard_container,
                        message_list,
                        ft.Row([model_chip, input_field, compact_btn, send_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ],
                    expand=True,
                ),
            ],
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )
    rebuild_sidebar()


ft.app(target=main)
