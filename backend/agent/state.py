from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import MessagesState


class TicketState(TypedDict):
    ticket_id: str
    model_id: str


class AgentState(MessagesState):
    prefixes: list[str]
    mode: str
    tickets: list[dict]
    summaries: Annotated[list[str], operator.add]
    ticket_summaries: Annotated[list[str], operator.add]
    ticket_table_data: list[dict]
    parent_link: str
    custom_jql: str
    model_id: str


class SummarizerState(MessagesState):
    ticket: dict
    summaries: Annotated[list[str], operator.add]
