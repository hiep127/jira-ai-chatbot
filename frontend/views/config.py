from __future__ import annotations

import flet as ft

from config.providers import KEY_PROVIDERS, delete_key, load_key, save_active_provider, save_key

_PROVIDER_LABELS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "azure": "Azure OpenAI",
    "github_copilot": "GitHub Copilot SDK",
}


def open_config_dialog(page: ft.Page) -> None:
    # --- Controls (defined first so all handlers can reference them) ---
    provider_dropdown = ft.Dropdown(
        label="Provider",
        value="openai",
        options=[
            ft.dropdown.Option(key=k, text=v) for k, v in _PROVIDER_LABELS.items()
        ],
        width=300,
    )
    key_field = ft.TextField(
        hint_text="Enter API key",
        password=True,
        can_reveal_password=True,
        expand=True,
    )
    copilot_info = ft.Text(
        "Authentication is handled automatically via your local\n"
        "GitHub Copilot CLI. No API key is needed.",
        size=13,
        italic=True,
        visible=False,
    )
    status_text = ft.Text("", size=12)
    save_btn = ft.ElevatedButton("Save")
    clear_btn = ft.TextButton("Clear Key")
    close_btn = ft.TextButton("Close")

    # --- Helpers ---
    def set_status(msg: str, color: str = "") -> None:
        status_text.value = msg
        status_text.color = color or None

    def refresh_for_provider(provider: str) -> None:
        is_copilot = provider == "github_copilot"
        key_field.visible = not is_copilot
        copilot_info.visible = is_copilot
        clear_btn.visible = not is_copilot
        key_field.value = ""
        if not is_copilot:
            has_key = load_key(provider) is not None
            set_status("Key is configured" if has_key else "No key stored")
        else:
            set_status("")

    # --- Event handlers ---
    def on_provider_change(e: ft.ControlEvent) -> None:
        refresh_for_provider(e.control.value)
        page.update()

    def on_save(e: ft.ControlEvent) -> None:
        provider = provider_dropdown.value
        if provider in KEY_PROVIDERS:
            key = key_field.value.strip()
            if not key:
                set_status("Key cannot be empty.", "red")
                page.update()
                return
            save_key(provider, key)
            save_active_provider(provider)
            key_field.value = ""
            set_status("Key saved.", "green")
        else:
            save_active_provider(provider)
            set_status("GitHub Copilot set as active provider.", "green")
        page.update()

    def on_clear(e: ft.ControlEvent) -> None:
        delete_key(provider_dropdown.value)
        key_field.value = ""
        set_status("Key removed.", "orange")
        page.update()

    # --- Assign handlers ---
    provider_dropdown.on_change = on_provider_change
    save_btn.on_click = on_save
    clear_btn.on_click = on_clear

    # --- Build dialog ---
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Configure AI Provider"),
        content=ft.Column(
            controls=[provider_dropdown, key_field, copilot_info, status_text],
            tight=True,
            spacing=12,
            width=350,
        ),
        actions=[save_btn, clear_btn, close_btn],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def on_close(e: ft.ControlEvent) -> None:
        dialog.open = False
        page.update()

    close_btn.on_click = on_close

    # --- Initialize state and show ---
    refresh_for_provider("openai")
    page.overlay.append(dialog)
    dialog.open = True
    page.update()
