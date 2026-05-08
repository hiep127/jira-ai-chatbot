from __future__ import annotations

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
    from backend.utils.github_auth import get_local_github_token
    token = get_local_github_token()
    if token is None:
        raise RuntimeError(
            "GitHub CLI not authenticated. Open a terminal and run 'gh auth login'."
        )
    return token
