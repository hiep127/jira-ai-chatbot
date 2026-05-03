from unittest.mock import patch

import keyring.errors
import pytest


def test_save_and_load_key():
    import config.providers as providers

    with patch("keyring.set_password") as mock_set, \
         patch("keyring.get_password", return_value="sk-test-key") as mock_get:
        providers.save_key("openai", "sk-test-key")
        result = providers.load_key("openai")

    mock_set.assert_called_once_with("ai-agent-app", "openai", "sk-test-key")
    mock_get.assert_called_once_with("ai-agent-app", "openai")
    assert result == "sk-test-key"


def test_load_missing_key():
    import config.providers as providers

    with patch("keyring.get_password", return_value=None):
        result = providers.load_key("anthropic")

    assert result is None


def test_delete_key():
    import config.providers as providers

    with patch("keyring.delete_password") as mock_del:
        providers.delete_key("openai")

    mock_del.assert_called_once_with("ai-agent-app", "openai")


def test_delete_key_silent_on_missing():
    import config.providers as providers

    with patch(
        "keyring.delete_password",
        side_effect=keyring.errors.PasswordDeleteError("openai"),
    ):
        providers.delete_key("openai")  # must not raise


def test_active_provider_roundtrip(tmp_path, monkeypatch):
    import config.providers as providers

    monkeypatch.setattr(providers, "_SETTINGS_PATH", tmp_path / "settings.json")
    providers.save_active_provider("anthropic")
    assert providers.load_active_provider() == "anthropic"


def test_load_active_provider_missing_file(tmp_path, monkeypatch):
    import config.providers as providers

    monkeypatch.setattr(providers, "_SETTINGS_PATH", tmp_path / "nonexistent.json")
    assert providers.load_active_provider() is None
