from __future__ import annotations

import subprocess

from langchain_core.language_models.chat_models import BaseChatModel

from config.providers import load_active_provider, load_key


def build_llm() -> BaseChatModel:
    """Instantiate the active provider's LangChain chat model.

    Called at request time so provider changes take effect without a restart.
    """
    provider = load_active_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=load_key("openai"), model="gpt-4o-mini")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(api_key=load_key("anthropic"), model="claude-haiku-4-5-20251001")

    if provider == "azure":
        # Endpoint URL config is deferred to Phase 4
        raise RuntimeError(
            "Azure requires an endpoint URL that is not yet configurable. "
            "Coming in Phase 4 — use OpenAI or Anthropic for now."
        )

    if provider == "github_copilot":
        token = _get_copilot_token()
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=token,
            base_url="https://api.githubcopilot.com",
            model="gpt-4o",
        )

    raise RuntimeError(
        "No AI provider configured. Open ⚙ Settings to add your API key."
    )


def build_summarizer_llm() -> BaseChatModel:
    """Cheaper/faster variant for high-fan-out sub-agent tasks.

    Uses gpt-4o-mini / claude-haiku instead of the heavier orchestrator model
    because sub-agents perform a constrained, repeatable extraction task.
    """
    provider = load_active_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=load_key("openai"), model="gpt-4o-mini")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(api_key=load_key("anthropic"), model="claude-haiku-4-5-20251001")

    if provider == "azure":
        raise RuntimeError(
            "Azure requires an endpoint URL that is not yet configurable. "
            "Coming in Phase 4 — use OpenAI or Anthropic for now."
        )

    if provider == "github_copilot":
        token = _get_copilot_token()
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=token,
            base_url="https://api.githubcopilot.com",
            model="gpt-4o-mini",
        )

    raise RuntimeError(
        "No AI provider configured. Open ⚙ Settings to add your API key."
    )


def _get_copilot_token() -> str:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        token = result.stdout.strip()
        if not token:
            raise RuntimeError("'gh auth token' returned empty output.")
        return token
    except FileNotFoundError:
        raise RuntimeError(
            "GitHub CLI ('gh') not found. Install it and run 'gh auth login'."
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"'gh auth token' failed: {e.stderr.strip()}")
