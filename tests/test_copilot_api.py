"""Standalone GitHub Copilot API test script. Run with: python tests/test_copilot_api.py"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx

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


def _chat_models(models: list[dict]) -> list[dict]:
    return [
        m for m in models
        if m.get("capabilities", {}).get("type") == "chat"
        and m.get("model_picker_enabled", False)
    ]


def print_model_menu(models: list[dict]) -> None:
    print("[US2] Available models:")
    print(f"  {'#':>3}  {'Model ID':<32}  {'Context':>8}  {'Max Out':>8}  Name")
    print(f"  {'─'*3}  {'─'*32}  {'─'*8}  {'─'*8}  {'─'*24}")
    for i, m in enumerate(models, start=1):
        limits = m.get("capabilities", {}).get("limits", {})
        ctx = limits.get("max_context_window_tokens", 0)
        out = limits.get("max_output_tokens", 0)
        ctx_str = f"{ctx // 1000}k" if ctx else "—"
        out_str = f"{out // 1000}k" if out else "—"
        print(f"  [{i:>2}]  {m['id']:<32}  {ctx_str:>8}  {out_str:>8}  {m.get('name', '')}")


def prompt_model_choice(models: list[dict]) -> str:
    chat_models = _chat_models(models)
    print_model_menu(chat_models)
    while True:
        raw = input("Enter number: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(chat_models):
                return chat_models[idx - 1]["id"]
        print(f"Invalid choice — enter a number between 1 and {len(chat_models)}.")


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


def test_jira_fetch() -> list[dict]:
    import os
    import sys

    # Add project root to path so config.* and tools.* are importable when
    # running the script directly from any working directory.
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from config.providers import get_jira_pat_for_profile

    candidates = [
        project_root / "settings.json",
        project_root / "dist" / "JiraAgent" / "settings.json",
    ]
    settings_path = next((p for p in candidates if p.exists()), None)
    if settings_path is None:
        print("  settings.json not found — add a Jira profile in Settings first.")
        print(f"  Searched: {', '.join(str(p) for p in candidates)}")
        return []

    profiles: list[dict] = json.loads(settings_path.read_text(encoding="utf-8")).get("profiles", [])
    if not profiles:
        print("  No profiles found — add a Jira profile in Settings first.")
        return []

    # Build JIRA_PROFILES_JSON exactly as _build_mcp_env() does in backend/main.py.
    payload = [
        {
            "name": p["name"],
            "host": p.get("host", ""),
            "token": get_jira_pat_for_profile(p["name"]) or "",
            "jql": p.get("custom_jql", ""),
        }
        for p in profiles
        if p.get("name")
    ]
    os.environ["JIRA_PROFILES_JSON"] = json.dumps(payload)

    # Import after env var is set — jira_tool reads it at module level.
    # Use importlib to avoid caching a stale module if the env var changed.
    import importlib
    import tools.jira_tool as jira_tool
    importlib.reload(jira_tool)

    from tools.jira_tool import get_tickets_by_batch, BatchScanArgs

    print(f"  Profiles loaded: {[p['name'] for p in payload]}")
    result_json = get_tickets_by_batch(BatchScanArgs())
    result = json.loads(result_json)

    if result.get("status") != "SUCCESS":
        print(f"  ERROR: {result.get('message', result_json)}")
        return []

    all_tickets: list[dict] = []
    for profile_name, tickets in result["data"].items():
        if isinstance(tickets, dict) and "error" in tickets:
            print(f"\n  [{profile_name}] ERROR: {tickets['error']}")
            continue
        print(f"\n  [{profile_name}] Fetched {len(tickets)} ticket(s):")
        for t in tickets:
            print(f"    {t['key']}  {t['summary'][:80]}")
            all_tickets.append({"key": t["key"], "summary": t["summary"], "profile": profile_name})

    return all_tickets


def list_tickets_menu(tickets: list[dict]) -> None:
    print("[US5] All tickets from configured filters:")
    for i, t in enumerate(tickets, start=1):
        summary = t["summary"][:70]
        print(f"  [{i:>3}]  {t['key']:<18}  {summary:<70}  ({t['profile']})")


def prompt_ticket_choice(tickets: list[dict]) -> str | None:
    list_tickets_menu(tickets)
    while True:
        raw = input("\nEnter ticket number to investigate (or press Enter to skip): ").strip()
        if raw == "":
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(tickets):
                return tickets[idx - 1]["key"]
        print(f"  Invalid choice — enter a number between 1 and {len(tickets)}, or press Enter to skip.")


def test_investigate_ticket(ticket_key: str, token: str, model_id: str, max_prompt_tokens: int) -> None:
    from tools.jira_tool import fetch_ticket_metadata, TicketMetadataArgs

    print(f"  Fetching metadata for {ticket_key}...")
    result_json = fetch_ticket_metadata(TicketMetadataArgs(ticket_key=ticket_key))
    result = json.loads(result_json)

    if result.get("status") != "SUCCESS":
        print(f"  ERROR: {result.get('message', result_json)}")
        return

    data = result["data"]
    print(f"\n  Key       : {data['key']}")
    print(f"  Status    : {data['status']}")
    print(f"  Assignee  : {data['assignee']}")
    print(f"  Summary   : {data['summary']}")
    print(f"\n  Description:\n")
    for line in (data.get("description") or "No description.").splitlines():
        print(f"    {line}")

    comments = data.get("comments", [])
    if comments:
        print(f"\n  Recent comments ({len(comments)}):")
        for c in comments:
            print(f"\n    [{c['date']}] {c['author']}:")
            for line in c["body"].splitlines():
                print(f"      {line}")
    else:
        print("\n  No comments.")

    print(f"\n=== US5c: Copilot Investigation ===")
    run_investigator_agent(data, token, model_id, max_prompt_tokens)


def run_investigator_agent(data: dict, token: str, model_id: str, max_prompt_tokens: int) -> None:
    comments = data.get("comments", [])
    comments_block = ""
    if comments:
        lines = []
        for c in comments:
            lines.append(f"[{c['date']}] {c['author']}:\n{c['body']}")
        comments_block = "\n\n".join(lines)
    else:
        comments_block = "(no comments)"

    user_message = (
        f"Ticket: {data['key']}\n"
        f"Status: {data['status']}\n"
        f"Assignee: {data['assignee']}\n"
        f"Summary: {data['summary']}\n\n"
        f"Description:\n{data.get('description') or 'No description.'}\n\n"
        f"Recent comments:\n{comments_block}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        **_EDITOR_HEADERS,
    }
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior support engineer investigating a Jira ticket. "
                    "Analyze the details provided and give:\n"
                    "1. Likely root cause\n"
                    "2. Suggested next investigation steps\n"
                    "3. Any patterns recognized from the description and comments"
                ),
            },
            {"role": "user", "content": user_message},
        ],
    }

    # Rough guard: 1 token ≈ 4 chars. Reserve ~500 tokens for system prompt + overhead.
    char_budget = (max_prompt_tokens - 500) * 4
    if len(user_message) > char_budget:
        user_message = user_message[:char_budget]
        print(f"  (prompt truncated to fit {max_prompt_tokens:,}-token limit)\n")

    print(f"  Sending to {model_id}...\n")
    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{_COPILOT_BASE}/chat/completions", headers=headers, json=payload
            )
    except httpx.ConnectError as exc:
        print(f"  Network error: {exc}")
        return

    if not response.is_success:
        print(f"  API error {response.status_code}: {response.text[:300]}")
        return

    analysis = response.json()["choices"][0]["message"]["content"]
    for line in analysis.splitlines():
        print(f"  {line}")


def main() -> None:
    print("=== US1: GitHub Copilot CLI Authentication ===")
    token = authenticate()

    print("\n=== US2: Available Models ===")
    models, models_headers = list_models(token)
    model_id = prompt_model_choice(models)
    print(f"Selected: {model_id}")
    _sel = next((m for m in _chat_models(models) if m["id"] == model_id), {})
    max_prompt_tokens = _sel.get("capabilities", {}).get("limits", {}).get("max_prompt_tokens", 64000)

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
    tickets = test_jira_fetch()

    print("\n=== US5: Select Ticket to Investigate ===")
    if tickets:
        ticket_key = prompt_ticket_choice(tickets)
        if ticket_key:
            print(f"\n=== US5b: Investigating {ticket_key} ===")
            test_investigate_ticket(ticket_key, token, model_id, max_prompt_tokens)
        else:
            print("  Skipped.")
    else:
        print("  No tickets available to investigate.")


if __name__ == "__main__":
    main()
