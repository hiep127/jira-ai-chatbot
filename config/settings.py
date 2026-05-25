from __future__ import annotations

import json
import logging
from typing import Any

from config.paths import get_base_path, migrate_legacy_settings

migrate_legacy_settings()

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
    "profiles",
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


def _update_settings_key(key: str, value: Any) -> None:
    path = get_base_path() / _SETTINGS_FILE
    try:
        existing: dict[str, Any] = {}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
        existing[key] = value
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("[settings] Failed to update '%s' in %s: %s", key, path, exc)


def get_profiles() -> list[dict]:
    return load_filter_settings().get("profiles", [])


def save_profiles(profiles: list[dict]) -> None:
    _update_settings_key("profiles", profiles)


def get_active_profiles() -> list[str] | None:
    return load_filter_settings().get("active_profiles")


def save_active_profiles(names: list[str]) -> None:
    _update_settings_key("active_profiles", names)
