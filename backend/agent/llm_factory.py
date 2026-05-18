from __future__ import annotations

import httpx

from backend.utils.github_auth import get_local_github_token

_DEFAULT_MODEL = "gpt-4o"

_EDITOR_HEADERS = {
    "editor-version": "vscode/1.85.0",
    "editor-plugin-version": "copilot-chat/0.12.0",
    "openai-intent": "conversation-inline",
    "user-agent": "GitHubCopilotChat/0.12.0",
}


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

    # Use the GitHub OAuth token directly — api.githubcopilot.com accepts it as Bearer.
    # Do NOT exchange it via copilot_internal/v2/token: that endpoint is restricted to
    # tokens issued to the official Copilot VS Code OAuth app and returns 404 for gh CLI tokens.
    token = get_local_github_token()
    if not token:
        raise RuntimeError(
            "GitHub CLI not authenticated. Run 'gh auth login' and ensure Copilot is active."
        )

    try:
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
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            raise RuntimeError(
                "Copilot API call failed — No active GitHub Copilot subscription found on this "
                "account (HTTP 404). Visit github.com/settings/copilot to check your seat, or "
                "open Settings and configure an OpenAI/Anthropic API key instead."
            )
        elif status in (401, 403):
            raise RuntimeError(
                f"Copilot API call failed — GitHub token rejected (HTTP {status}). "
                "Re-run 'gh auth login' to refresh your credentials."
            )
        else:
            raise RuntimeError(f"Copilot API call failed — GitHub API error {status}: {e}")
    except httpx.ConnectError:
        raise RuntimeError(
            "Copilot API call failed — Cannot reach api.githubcopilot.com. "
            "Check your network connection."
        )
    except Exception as e:
        raise RuntimeError(
            f"Copilot API call failed — {e}. "
            "Verify 'gh auth login' has been run and the Copilot subscription is active."
        )
