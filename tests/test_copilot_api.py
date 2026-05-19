"""Standalone GitHub Copilot API test script. Run with: python tests/test_copilot_api.py"""

import subprocess
import sys
from pathlib import Path

import httpx

_EDITOR_HEADERS: dict[str, str] = {
    "editor-version": "vscode/1.85.0",
    "editor-plugin-version": "copilot-chat/0.12.0",
    "openai-intent": "conversation-inline",
    "user-agent": "GitHubCopilotChat/0.12.0",
}

_COPILOT_BASE = "https://api.githubcopilot.com"


def _gh_exe() -> str:
    bundled = Path(__file__).parent.parent / "tools" / "gh.exe"
    if bundled.exists():
        return str(bundled)
    return "gh"


def authenticate() -> str:
    try:
        result = subprocess.run(
            [_gh_exe(), "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        token = result.stdout.strip()
    except Exception:
        print("ERROR: gh auth failed — run 'gh auth login' first.")
        sys.exit(1)

    if not token:
        print("ERROR: gh auth failed — run 'gh auth login' first.")
        sys.exit(1)

    print("[US1] GitHub CLI authenticated.")
    return token


def list_models(token: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}", **_EDITOR_HEADERS}
    try:
        with httpx.Client() as client:
            response = client.get(f"{_COPILOT_BASE}/models", headers=headers)
    except httpx.ConnectError as exc:
        print(f"Network error: {exc}")
        sys.exit(1)

    if response.status_code == 401 or response.status_code == 403:
        print("Token rejected — re-run 'gh auth login'")
        sys.exit(1)
    if response.status_code == 404:
        print("No Copilot subscription on this account")
        sys.exit(1)
    response.raise_for_status()

    return response.json()["data"]


def print_model_menu(models: list[dict]) -> None:
    print("[US2] Available models:")
    for i, model in enumerate(models, start=1):
        print(f"  [{i}]  {model['id']}")


def prompt_model_choice(models: list[dict]) -> str:
    print_model_menu(models)
    while True:
        raw = input("Enter number: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(models):
                return models[idx - 1]["id"]
        print(f"Invalid choice — enter a number between 1 and {len(models)}.")


def test_chat(token: str, model_id: str) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        **_EDITOR_HEADERS,
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "user", "content": "What is the weather like today in Da Nang, Vietnam?"}
        ],
    }
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{_COPILOT_BASE}/chat/completions", headers=headers, json=payload
            )
    except httpx.ConnectError as exc:
        print(f"Network error: {exc}")
        sys.exit(1)

    if response.status_code == 401 or response.status_code == 403:
        print("Token rejected — re-run 'gh auth login'")
        sys.exit(1)
    if response.status_code == 404:
        print("No Copilot subscription on this account")
        sys.exit(1)
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    print(f"\nResponse:\n{content}")


def main() -> None:
    print("=== US1: GitHub Copilot CLI Authentication ===")
    token = authenticate()

    print("\n=== US2: Available Models ===")
    models = list_models(token)
    model_id = prompt_model_choice(models)
    print(f"Selected: {model_id}")

    print("\n=== US3: Test API Call ===")
    print('Prompt: "What is the weather like today in Da Nang, Vietnam?"')
    test_chat(token, model_id)


if __name__ == "__main__":
    main()
