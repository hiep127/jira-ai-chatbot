from __future__ import annotations

import operator
from typing import Annotated

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    prefixes: list[str]
    mode: str
    tickets: list[dict]
    summaries: Annotated[list[str], operator.add]
    parent_link: str
    filters: dict[str, list[str]]
    selected_filter_keys: list[str]


class SummarizerState(MessagesState):
    ticket: dict
    summaries: Annotated[list[str], operator.add]
