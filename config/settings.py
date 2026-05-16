from __future__ import annotations

import json
import logging
from typing import Any

from config.paths import get_base_path

logger = logging.getLogger(__name__)

_SETTINGS_FILE = "settings.json"
_PERSIST_KEYS = (
    "filter_profile_name",
    "jira_env",
    "parent_link",
    "custom_jql",
    "filters",
    "model_id",
    "model_name",
    "model_tier",
)


def load_filter_settings() -> dict[str, Any]:
    path = get_base_path() / _SETTINGS_FILE
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[settings] Failed to load %s: %s", path, exc)
    return {}


def save_filter_settings(state: dict[str, Any]) -> None:
    path = get_base_path() / _SETTINGS_FILE
    try:
        data = {k: state[k] for k in _PERSIST_KEYS if k in state}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("[settings] Failed to save %s: %s", path, exc)
