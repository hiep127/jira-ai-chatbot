from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_SUMMARIZER_MODEL = "gpt-4o-mini"


def build_llm(model_id: str = "") -> BaseChatModel:
    token = _get_copilot_token()
    return ChatOpenAI(
        api_key=token,
        base_url="https://api.githubcopilot.com",
        model=model_id if model_id else _DEFAULT_MODEL,
    )


def build_summarizer_llm(model_id: str = "") -> BaseChatModel:
    token = _get_copilot_token()
    return ChatOpenAI(
        api_key=token,
        base_url="https://api.githubcopilot.com",
        model=model_id if model_id else _DEFAULT_SUMMARIZER_MODEL,
    )


def _get_copilot_token() -> str:
    from backend.utils.github_auth import get_local_github_token
    token = get_local_github_token()
    if token is None:
        raise RuntimeError(
            "GitHub CLI not authenticated. Open a terminal and run 'gh auth login'."
        )
    return token
