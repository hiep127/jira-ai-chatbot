from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def build_llm() -> BaseChatModel:
    token = _get_copilot_token()
    return ChatOpenAI(
        api_key=token,
        base_url="https://api.githubcopilot.com",
        model="gpt-4o",
    )


def build_summarizer_llm() -> BaseChatModel:
    token = _get_copilot_token()
    return ChatOpenAI(
        api_key=token,
        base_url="https://api.githubcopilot.com",
        model="gpt-4o-mini",
    )


def _get_copilot_token() -> str:
    from backend.utils.github_auth import get_local_github_token
    token = get_local_github_token()
    if token is None:
        raise RuntimeError(
            "GitHub CLI not authenticated. Open a terminal and run 'gh auth login'."
        )
    return token
