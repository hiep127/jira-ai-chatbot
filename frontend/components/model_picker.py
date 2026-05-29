from __future__ import annotations

from collections.abc import Callable

import flet as ft
import httpx

from frontend.views.dialogs import show_error_dialog
from frontend.views.config import open_config_dialog


def open_model_picker(
    page: ft.Page,
    app_state: dict,
    on_model_selected: Callable[[], None],
    cached_models: list[dict] | None = None,
) -> None:
    _state: dict = {"models": [], "show_others": False}

    search_field = ft.TextField(hint_text="Search models...", expand=True, dense=True)
    refresh_btn = ft.IconButton(ft.Icons.REFRESH, tooltip="Refresh models")
    gear_btn = ft.IconButton(ft.Icons.SETTINGS, tooltip="Auth settings")
    spinner = ft.ProgressRing(visible=False, width=24, height=24, stroke_width=2)
    model_list = ft.ListView(expand=True, spacing=0, height=320)
    _others_label = ft.Text("▶ Other Models (0)", size=13)
    others_toggle = ft.TextButton(content=_others_label)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row(
            controls=[
                ft.Text("Select Model", expand=True),
                ft.IconButton(
                    ft.Icons.CLOSE,
                    tooltip="Close",
                    on_click=lambda e: page.pop_dialog(),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        content=ft.Column(
            [
                ft.Row([search_field, refresh_btn, gear_btn]),
                ft.Stack([model_list, ft.Row([spinner], alignment=ft.MainAxisAlignment.CENTER)]),
                others_toggle,
            ],
            width=360,
            tight=True,
            spacing=8,
        ),
    )

    def _select_model(model_id: str, name: str, tier: str) -> None:
        app_state["model_id"] = model_id
        app_state["model_name"] = name
        app_state["model_tier"] = tier
        page.pop_dialog()
        page.update()
        on_model_selected()

    def _build_row(model: dict, is_active: bool = False) -> ft.ListTile:
        return ft.ListTile(
            leading=ft.Icon(
                ft.Icons.CHECK,
                visible=is_active,
                color=ft.Colors.BLUE_400,
            ),
            title=ft.Text(
                model["name"],
                weight=ft.FontWeight.BOLD if is_active else None,
            ),
            trailing=ft.Text(model["tier"], color=ft.Colors.GREY_400, size=12),
            bgcolor=ft.Colors.BLUE_GREY_700 if is_active else None,
            on_click=lambda e, m=model: _select_model(m["id"], m["name"], m["tier"]),
        )

    def _rebuild_list() -> None:
        active_id = app_state.get("model_id", "")
        query = (search_field.value or "").lower()
        filtered = [
            m for m in _state["models"]
            if query in m["name"].lower() or query in m["id"].lower()
        ]

        if active_id:
            active_models = [m for m in filtered if m["id"] == active_id]
            non_active = [m for m in filtered if m["id"] != active_id]
        else:
            active_models = []
            non_active = filtered

        primary = [m for m in non_active if not m["is_other"]]
        others = [m for m in non_active if m["is_other"]]

        model_list.controls.clear()

        for m in active_models:
            model_list.controls.append(_build_row(m, is_active=True))
        if active_models:
            model_list.controls.append(ft.Divider(height=1, color=ft.Colors.BLUE_GREY_600))

        for m in primary:
            model_list.controls.append(_build_row(m, is_active=False))

        if _state["show_others"]:
            for m in others:
                model_list.controls.append(_build_row(m, is_active=False))

        arrow = "▼" if _state["show_others"] else "▶"
        _others_label.value = f"{arrow} Other Models ({len(others)})"
        page.update()

    def _toggle_others() -> None:
        _state["show_others"] = not _state["show_others"]
        _rebuild_list()

    async def _fetch_models(refresh: bool = False) -> None:
        try:
            spinner.visible = True
            model_list.visible = False
            page.update()
            params = {"refresh": "true"} if refresh else {}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get("http://localhost:8000/models", params=params)
            if r.status_code == 401:
                page.pop_dialog()
                open_config_dialog(page)
                return
            r.raise_for_status()
            models_data = r.json()
            _state["models"] = models_data
            app_state["models_cache"] = models_data
            _rebuild_list()
        except Exception as exc:
            show_error_dialog(page, f"Failed to fetch models: {exc}")
        finally:
            spinner.visible = False
            model_list.visible = True
            page.update()

    search_field.on_change = lambda e: _rebuild_list()
    refresh_btn.on_click = lambda e: page.run_task(_fetch_models, True)
    gear_btn.on_click = lambda e: open_config_dialog(page)
    others_toggle.on_click = lambda e: _toggle_others()

    page.show_dialog(dialog)
    if cached_models:
        _state["models"] = cached_models
        _rebuild_list()
    else:
        page.run_task(_fetch_models)
