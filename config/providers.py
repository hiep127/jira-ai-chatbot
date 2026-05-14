from __future__ import annotations

import keyring
import keyring.errors

KEYRING_SERVICE = "ai-agent-app"

JIRA_PAT_KEY = "jira_pat"


def get_jira_pat() -> str | None:
    return keyring.get_password(KEYRING_SERVICE, JIRA_PAT_KEY)


def set_jira_pat(pat: str) -> None:
    keyring.set_password(KEYRING_SERVICE, JIRA_PAT_KEY, pat)
