from __future__ import annotations

import asyncio
import time

import httpx

from backend.utils.github_auth import get_local_github_token

_DEFAULT_MODEL = "gpt-4o"

_COPILOT_TOKEN: str | None = None
_COPILOT_TOKEN_EXPIRY: float = 0.0
_TOKEN_LOCK: asyncio.Lock | None = None

_EDITOR_HEADERS = {
    "editor-version": "vscode/1.85.0",
    "editor-plugin-version": "copilot-chat/0.12.0",
    "openai-intent": "conversation-inline",
    "user-agent": "GitHubCopilotChat/0.12.0",
}


def _token_lock() -> asyncio.Lock:
    global _TOKEN_LOCK
    if _TOKEN_LOCK is None:
        _TOKEN_LOCK = asyncio.Lock()
    return _TOKEN_LOCK


async def _get_copilot_token() -> str:
    global _COPILOT_TOKEN, _COPILOT_TOKEN_EXPIRY
    async with _token_lock():
        if _COPILOT_TOKEN and time.time() < _COPILOT_TOKEN_EXPIRY - 60:
            return _COPILOT_TOKEN

        oauth_token = get_local_github_token()
        if not oauth_token:
            raise RuntimeError(
                "GitHub CLI not authenticated. Run 'gh auth login' and ensure Copilot is active."
            )

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Authorization": f"Bearer {oauth_token}",
                    "Accept": "application/json",
                    **_EDITOR_HEADERS,
                },
            )
            r.raise_for_status()

        data = r.json()
        _COPILOT_TOKEN = data["token"]
        _COPILOT_TOKEN_EXPIRY = float(data.get("expires_at", time.time() + 1800))
        return _COPILOT_TOKEN


async def call_copilot(
    prompt: str,
    model_id: str = "",
    system_prompt: str = "",
) -> str:
    model = model_id if model_id else _DEFAULT_MODEL
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        token = await _get_copilot_token()
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "https://api.githubcopilot.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    **_EDITOR_HEADERS,
                },
                json={"model": model, "messages": messages},
            )
            r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(
            f"Copilot API call failed — {e}. "
            "Verify 'gh auth login' has been run and the Copilot subscription is active."
        )
