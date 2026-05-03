from __future__ import annotations

import json
from pathlib import Path

import keyring
import keyring.errors

KEYRING_SERVICE = "ai-agent-app"
KEY_PROVIDERS = ["openai", "anthropic", "azure"]
ALL_PROVIDERS = KEY_PROVIDERS + ["github_copilot"]

_SETTINGS_PATH = Path(__file__).parent / "settings.json"


def save_key(provider: str, api_key: str) -> None:
    keyring.set_password(KEYRING_SERVICE, provider, api_key)


def load_key(provider: str) -> str | None:
    return keyring.get_password(KEYRING_SERVICE, provider)


def delete_key(provider: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, provider)
    except keyring.errors.PasswordDeleteError:
        pass


def save_active_provider(provider: str) -> None:
    _SETTINGS_PATH.write_text(json.dumps({"active": provider}), encoding="utf-8")


def load_active_provider() -> str | None:
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return data.get("active")
    except (FileNotFoundError, json.JSONDecodeError):
        return None
