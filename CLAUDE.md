# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow: Plan Mode

**Always operate in Plan Mode.** Before writing any code or modifying files:
1. **Read `STATUS.md` first** — it is the authoritative record of what is built, what is pending, and known fixes. Use it to understand the current state of every file before touching anything.
2. Deeply analyze the request and identify all affected components
3. Outline the full architectural approach, data flow, and tool/schema definitions
4. List every file that will be created or changed
5. Wait for **explicit user approval** before implementing anything

This is a hard constraint — it exists to protect the user's API budget and ensure alignment before any code is generated.

**After implementation:** run `/status-updater` to update `STATUS.md`. This applies after **any** code change — bug fixes, refactors, new features, config changes — not only after a jira-planner session. Do not skip this step.

## Deployment & Testing Environment

**This app is built to run on a separate target computer, not the development machine.**

The Jira integration requires VPN access that is only available on the target machine. This means:

- **Do not suggest running the full app locally** as a way to verify Jira-related features — it will not work on the dev machine without VPN.
- **Do not treat the inability to run the app locally as a bug.** It is expected behavior.
- Code correctness is verified by reading the code, not by running it. Flag logic issues through analysis, not live execution.
- The build output (`dist/JiraAgent/Jira AI.exe`) is what gets deployed to the target machine for real testing.

## Project Overview

Autonomous AI agent desktop app for Windows. A Flet desktop UI connects to a local FastAPI backend. The agent loop makes direct HTTPS calls to `api.githubcopilot.com` using the OAuth token from the local GitHub CLI (`gh auth token`) — no third-party AI SDK is used. All external tool invocations are routed through the Model Context Protocol (MCP).

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop UI | Flet 0.84.0 (Python) |
| Backend API | FastAPI (Python) |
| Agent loop | Direct `httpx` calls to `api.githubcopilot.com` (GitHub CLI OAuth token) |
| Tool routing | MCP via `langchain-mcp-adapters` + `MultiServerMCPClient` |
| Jira integration | Jira REST API v3 |
| Dependency management | `pip` + `requirements.txt` |

## Model Provider Configuration

The app has a configuration window where users securely set up their AI provider. Two authentication modes must coexist:

- **Direct API key**: OpenAI, Anthropic, Azure OpenAI — store keys securely (Windows Credential Manager preferred over plaintext files)
- **GitHub Copilot CLI**: No API key; the SDK reads tokens from the local Copilot CLI installation. Used for enterprise model access.

## Intended Architecture

```
AI Chatbot/
├── frontend/
│   ├── main.py              # Flet app entry point, launches UI and starts backend
│   ├── views/
│   │   ├── chat.py          # Main chat view
│   │   └── config.py        # Provider configuration window
│   └── components/          # Reusable Flet controls
├── backend/
│   ├── main.py              # FastAPI app, routes, lifespan
│   ├── agent/
│   │   └── runner.py        # github-copilot-sdk agent loop
│   ├── tools/               # MCP tool definitions (one file per tool/service)
│   └── integrations/
│       └── jira.py          # Jira REST API client
├── config/
│   └── providers.py         # Provider credential read/write (Windows Credential Manager)
├── tests/
└── requirements.txt
```

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run backend (FastAPI + Uvicorn)
uvicorn backend.main:app --reload --port 8000

# Run frontend (Flet desktop app)
python frontend/main.py

# Run all tests
pytest

# Run a single test
pytest tests/path/to/test_file.py::test_function_name -v
```

## Key Constraints

- **MCP first**: All agent tool calls must go through MCP via the SDK's native support. Do not build custom tool dispatch outside of MCP.
- **Minimal stack**: Do not introduce packages beyond what is required. Propose additions in the plan step and wait for approval.
- **Credentials**: Never write API keys to plaintext files. Use `keyring` (wraps Windows Credential Manager) for all secret storage.
- **No global state in FastAPI**: Pass configuration through dependency injection, not module-level globals.
- **Flet ↔ FastAPI**: The Flet app communicates with FastAPI over `localhost` HTTP. Flet should not import backend modules directly.
- **UI/UX design (MANDATORY)**: Before planning or writing any frontend (`frontend/`) code, read `DESIGN.md` in full. All UI changes must follow the design system defined there — dark theme, color palette, typography, spacing, and component rules (table borders, button styles, dialog sizing, etc.). Where DESIGN.md and the Flet API rules conflict on syntax (e.g. `ft.Colors.*` vs `ft.colors.*`), the Flet API rules take precedence; the design intent still applies.
- **Flet API rules (MANDATORY)**: Before planning or writing any frontend (`frontend/`) code, read `docs/flet_implementation_rules.md` in full. The installed version is `flet==0.84.0`. Key differences from older Flet: dialogs use `page.show_dialog()` / `page.pop_dialog()` (NOT `page.open()` / `page.close()`); icons use `ft.Icons.*` (NOT `ft.icons.*`); colors use `ft.Colors.*` (NOT `ft.colors.*`); layout helpers like `ft.padding.all()` / `ft.border.only()` do not exist — use `ft.Padding()` / `ft.Border()` directly.
- **Coding standards (MANDATORY)**: Read `CODING_STANDARDS.md` in full before writing any backend or frontend code, including small changes. All code must comply with the rules defined there.
- **Living standards (MANDATORY)**: Whenever a bug, crash, or wrong API usage is discovered and fixed — regardless of how small — immediately update the relevant standards file (`docs/flet_implementation_rules.md`, `CODING_STANDARDS.md`, or `DESIGN.md`) with a new rule or example that prevents the same mistake in future. Do this as part of the same change, not as a follow-up. This keeps the standards files as a true record of known pitfalls.
