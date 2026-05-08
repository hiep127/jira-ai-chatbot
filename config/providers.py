from __future__ import annotations

import json
from pathlib import Path

import keyring
import keyring.errors

KEYRING_SERVICE = "ai-agent-app"

_SETTINGS_PATH = Path(__file__).parent / "settings.json"

JIRA_PAT_KEY = "jira_pat"


def get_jira_pat() -> str | None:
    return keyring.get_password(KEYRING_SERVICE, JIRA_PAT_KEY)


def set_jira_pat(pat: str) -> None:
    keyring.set_password(KEYRING_SERVICE, JIRA_PAT_KEY, pat)


def save_active_provider(provider: str) -> None:
    _SETTINGS_PATH.write_text(json.dumps({"active": provider}), encoding="utf-8")
