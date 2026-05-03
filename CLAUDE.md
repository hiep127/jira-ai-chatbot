# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow: Plan Mode

**Always operate in Plan Mode.** Before writing any code or modifying files:
1. Deeply analyze the request and identify all affected components
2. Outline the full architectural approach, data flow, and tool/schema definitions
3. List every file that will be created or changed
4. Wait for **explicit user approval** before implementing anything

This is a hard constraint — it exists to protect the user's API budget and ensure alignment before any code is generated.

## Project Overview

Autonomous AI agent desktop app for Windows. A Flet desktop UI connects to a local FastAPI backend. The agent loop is powered by the `github-copilot-sdk` Python package, which authenticates via the local GitHub Copilot CLI to access enterprise models. All external tool invocations are routed through the Model Context Protocol (MCP).

## Tech Stack

| Layer | Technology |
|---|---|
| Desktop UI | Flet (Python) |
| Backend API | FastAPI (Python) |
| Agent loop | `github-copilot-sdk` (Python) |
| Tool routing | MCP — use the SDK's native MCP support |
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
