"""Standalone GitHub Copilot API test script. Run with: python tests/test_copilot_api.py"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
import keyring
from jira import JIRA

_EDITOR_HEADERS: dict[str, str] = {
    "editor-version": "vscode/1.85.0",
    "editor-plugin-version": "copilot-chat/0.12.0",
    "openai-intent": "conversation-inline",
    "user-agent": "GitHubCopilotChat/0.12.0",
}

_COPILOT_BASE = "https://api.githubcopilot.com"
_GITHUB_API = "https://api.github.com"


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


def list_models(token: str) -> tuple[list[dict], dict]:
    headers = {"Authorization": f"Bearer {token}", **_EDITOR_HEADERS}
    try:
        with httpx.Client() as client:
            response = client.get(f"{_COPILOT_BASE}/models", headers=headers)
    except httpx.ConnectError as exc:
        print(f"Network error: {exc}")
        sys.exit(1)

    if response.status_code in (401, 403):
        print("Token rejected — re-run 'gh auth login'")
        sys.exit(1)
    if response.status_code == 404:
        print("No Copilot subscription on this account")
        sys.exit(1)
    response.raise_for_status()

    return response.json()["data"], dict(response.headers)


def check_quota(token: str, response_headers: dict) -> None:
    # Rate limit / quota headers returned directly by the Copilot API
    ratelimit_keys = [
        k for k in response_headers
        if k.lower().startswith(("x-ratelimit", "x-copilot"))
    ]
    if ratelimit_keys:
        print("  Rate-limit headers from Copilot API:")
        for key in sorted(ratelimit_keys):
            val = response_headers[key]
            if "reset" in key.lower() and val.isdigit():
                readable = datetime.fromtimestamp(int(val)).strftime("%Y-%m-%d %H:%M:%S")
                val = f"{val}  ({readable} local)"
            print(f"    {key}: {val}")
    else:
        print("  No rate-limit headers found in Copilot API response.")

    # GitHub REST API — Copilot billing / subscription info
    print("\n  Fetching Copilot billing info from GitHub API...")
    gh_headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{_GITHUB_API}/user/copilot_billing", headers=gh_headers)
    except httpx.ConnectError as exc:
        print(f"  Network error: {exc}")
        return

    if resp.status_code == 404:
        print("  No Copilot subscription found (or endpoint not available for this account type).")
        return
    if resp.status_code in (401, 403):
        print(f"  Access denied ({resp.status_code}) — token may lack the 'copilot' scope.")
        return
    if not resp.is_success:
        print(f"  Unexpected status {resp.status_code}: {resp.text[:200]}")
        return

    print("  Copilot billing details:")
    _pretty_print_dict(resp.json(), indent=4)


def print_model_details(models: list[dict]) -> None:
    print(f"  Total models available: {len(models)}\n")
    for model in models:
        print(f"  {'─' * 52}")
        _pretty_print_dict(model, indent=4)
    print(f"  {'─' * 52}")


def _pretty_print_dict(data: dict, indent: int = 2) -> None:
    pad = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{pad}{key}:")
            _pretty_print_dict(value, indent + 2)
        elif isinstance(value, list):
            print(f"{pad}{key}: {json.dumps(value)}")
        else:
            print(f"{pad}{key}: {value}")


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


def test_chat(token: str, model_id: str) -> dict:
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

    if response.status_code in (401, 403):
        print("Token rejected — re-run 'gh auth login'")
        sys.exit(1)
    if response.status_code == 404:
        print("No Copilot subscription on this account")
        sys.exit(1)
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    print(f"\nResponse:\n{content}")
    return dict(response.headers)


def report_request_cost(headers_before: dict, headers_after: dict) -> None:
    _QUOTA_PREFIXES = ("x-ratelimit", "x-copilot")

    def _extract(headers: dict) -> dict:
        return {
            k.lower(): v for k, v in headers.items()
            if k.lower().startswith(_QUOTA_PREFIXES)
        }

    before = _extract(headers_before)
    after = _extract(headers_after)
    all_keys = sorted(set(before) | set(after))

    if not all_keys:
        print("  No quota/rate-limit headers returned by either endpoint.")
        print("  The API may not expose per-request cost through headers.")
        return

    consumed_any = False
    print(f"  {'Header':<45} {'Before':>12} {'After':>12} {'Delta':>8}")
    print(f"  {'─'*45} {'─'*12} {'─'*12} {'─'*8}")
    for key in all_keys:
        b_val = before.get(key, "—")
        a_val = after.get(key, "—")
        delta = ""
        if b_val.isdigit() and a_val.isdigit():
            diff = int(b_val) - int(a_val)
            if diff != 0:
                delta = f"{'-' if diff > 0 else '+'}{abs(diff)}"
                consumed_any = True
        print(f"  {key:<45} {b_val:>12} {a_val:>12} {delta:>8}")

    if consumed_any:
        print("\n  → Delta shows premium requests consumed by this single call.")
    else:
        print("\n  → No change detected — model may be free tier or quota not tracked here.")


def test_jira_fetch() -> None:
    settings_path = Path(__file__).resolve().parent.parent / "settings.json"
    if not settings_path.exists():
        print("  settings.json not found — add a Jira profile in Settings first.")
        return

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  Failed to read settings.json: {exc}")
        return

    profiles: list[dict] = settings.get("profiles", [])
    if not profiles:
        print("  No profiles found in settings.json — add a Jira profile in Settings first.")
        return

    for profile in profiles:
        name: str = profile.get("name", "")
        host: str = profile.get("host", "")
        jql_base: str = profile.get("custom_jql", "") or "resolution = Unresolved"
        jql = f"{jql_base} ORDER BY created ASC"

        if not name or not host:
            print(f"  Skipping incomplete profile: {profile}")
            continue

        pat = keyring.get_password("ai-agent-app", f"jira_pat_{name.lower()}")
        if not pat:
            print(f"  [{name}] No PAT found in Windows Credential Manager — save credentials in Settings first.")
            continue

        print(f"\n  Profile: {name}  ({host})")
        print(f"  JQL: {jql}")

        try:
            client = JIRA(server=host, token_auth=pat, options={"rest_api_version": "2"})
            issues = client.search_issues(jql, maxResults=5)
        except Exception as exc:
            print(f"  ERROR connecting to Jira: {exc}")
            continue

        if not issues:
            print("  No tickets matched.")
            continue

        print(f"  Fetched {len(issues)} ticket(s):")
        for issue in issues:
            print(f"    {issue.key}  {issue.fields.summary[:80]}")


def main() -> None:
    print("=== US1: GitHub Copilot CLI Authentication ===")
    token = authenticate()

    print("\n=== US2: Available Models ===")
    models, models_headers = list_models(token)
    model_id = prompt_model_choice(models)
    print(f"Selected: {model_id}")

    print("\n=== US2b: Premium Quota & Rate Limits ===")
    check_quota(token, models_headers)

    print("\n=== US2c: Model Details ===")
    print_model_details(models)

    print("\n=== US3: Test API Call ===")
    print('Prompt: "What is the weather like today in Da Nang, Vietnam?"')
    chat_headers = test_chat(token, model_id)

    print("\n=== US3b: Premium Request Cost for This Call ===")
    report_request_cost(models_headers, chat_headers)

    print("\n=== US4: Jira Ticket Fetch ===")
    test_jira_fetch()


if __name__ == "__main__":
    main()
