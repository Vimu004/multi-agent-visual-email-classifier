"""Typed LangGraph state definitions."""
from __future__ import annotations

from typing import TypedDict


class EmailAgentState(TypedDict, total=False):
    workflow_id: str

    sender: str
    subject: str
    body: str

    classification: dict
    selected_specialist: str

    knowledge: list[dict]
    specialist_result: dict

    draft_response: dict
    review_result: dict

    revision_count: int

    requires_human_approval: bool
    approval_reason: str | None
    human_decision: str | None

    status: str
    current_node: str

    trace: list[dict]
    final_response: dict | None
