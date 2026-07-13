"""LangGraph node implementations."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from ..schemas import (
    ClassificationResult,
    DraftResponse,
    ReviewerDecision,
    SpecialistAnalysis,
    SupervisorDecision,
)
from ..services.knowledge import resolve_knowledge
from ..services.tracing import TraceLogger
from .prompts import (
    CLASSIFICATION_PROMPT,
    RESPONSE_PROMPT,
    REVIEWER_PROMPT,
    SPECIALIST_PROMPTS,
    SUPERVISOR_PROMPT,
)
from .state import EmailAgentState


@dataclass
class WorkflowDependencies:
    """Shared helpers injected into LangGraph nodes."""

    model_call: Callable[[str, str, Type[BaseModel]], Awaitable[BaseModel]]
    tracer: TraceLogger


def _summarize(text: str, limit: int = 160) -> str:
    return text if len(text) <= limit else f"{text[:limit]}..."


def _format_email(state: EmailAgentState) -> str:
    return (
        f"Sender: {state['sender']}\n"
        f"Subject: {state['subject']}\n"
        f"Body: {state['body']}"
    )


def intake_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    with deps.tracer.span("intake", "node", "Email received") as record:
        record["output_summary"] = _summarize(state["subject"])
        record["status"] = "completed"
    state["status"] = "intake_complete"
    state.setdefault("trace", []).append({"agent": "Intake", "status": "completed"})
    return state


async def classification_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    email_text = _format_email(state)
    with deps.tracer.span("classification_agent", "agent", _summarize(email_text)) as record:
        result = await deps.model_call(CLASSIFICATION_PROMPT, email_text, ClassificationResult)
        record["output_summary"] = f"{result.category} ({result.confidence:.2f})"
        record["status"] = "completed"
    state["classification"] = result.model_dump()
    state["status"] = "classified"
    return state


async def supervisor_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    classification = state["classification"]
    prompt = (
        f"Classification: {classification}\n"
        f"Email: {state['body']}"
    )
    with deps.tracer.span("supervisor_agent", "agent", _summarize(prompt)) as record:
        result = await deps.model_call(SUPERVISOR_PROMPT, prompt, SupervisorDecision)
        record["output_summary"] = f"Routed to {result.selected_specialist}"
        record["status"] = "completed"
    state["selected_specialist"] = result.selected_specialist
    return state


async def specialist_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    specialist = state["selected_specialist"]
    knowledge = resolve_knowledge(specialist)
    state["knowledge"] = knowledge
    prompt = (
        f"Role: {specialist}\n"
        f"Email: {state['body']}\n"
        f"Classification: {state['classification']}\n"
        f"Knowledge: {knowledge}"
    )
    system_prompt = SPECIALIST_PROMPTS.get(specialist, SPECIALIST_PROMPTS["general"])
    with deps.tracer.span(f"{specialist}_agent", "agent", _summarize(prompt)) as record:
        result = await deps.model_call(system_prompt, prompt, SpecialistAnalysis)
        record["output_summary"] = result.analysis[:160]
        record["status"] = "completed"
    state["specialist_result"] = result.model_dump()
    return state


async def response_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    prompt = (
        f"Email: {state['body']}\n"
        f"Specialist: {state['specialist_result']}\n"
        f"Knowledge: {state.get('knowledge', [])}"
    )
    with deps.tracer.span("response_agent", "agent", _summarize(prompt)) as record:
        result = await deps.model_call(RESPONSE_PROMPT, prompt, DraftResponse)
        record["output_summary"] = _summarize(result.body)
        record["status"] = "completed"
    state["draft_response"] = result.model_dump()
    state["revision_pending"] = False
    return state


async def reviewer_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    prompt = (
        f"Draft: {state['draft_response']}\n"
        f"Classification: {state['classification']}\n"
        f"Specialist: {state['specialist_result']}"
    )
    with deps.tracer.span("reviewer_agent", "agent", _summarize(prompt)) as record:
        result = await deps.model_call(REVIEWER_PROMPT, prompt, ReviewerDecision)
        record["output_summary"] = f"Decision: {result.decision}"
        record["status"] = "completed"
    revisions = state.get("revision_count", 0)
    if result.decision == "revise" and revisions < 1:
        state["revision_count"] = revisions + 1
        state["revision_pending"] = True
    elif result.decision == "revise" and revisions >= 1:
        # escalate to human review after one attempt
        overridden = result.model_copy(update={"decision": "human_review", "approved": False})
        result = overridden
        state["revision_pending"] = False
    else:
        state["revision_pending"] = False
    state["review_result"] = result.model_dump()
    return state


def approval_gate_node(state: EmailAgentState, *_: WorkflowDependencies) -> EmailAgentState:
    classification = state.get("classification", {})
    specialist = state.get("specialist_result", {})
    draft = state.get("draft_response", {})
    review = state.get("review_result", {})
    body_text = state.get("body", "").lower()
    knowledge = state.get("knowledge", [])

    reasons: list[str] = []
    if classification.get("confidence", 1) < 0.8:
        reasons.append("Classifier confidence below 0.80")
    if classification.get("category") in {"human_review"}:
        reasons.append("Explicit human_review classification")
    if classification.get("sensitive_action"):
        reasons.append("Sensitive action flag set")
    if classification.get("requires_human_review"):
        reasons.append("Classifier requested human review")
    if specialist.get("risk") == "high":
        reasons.append("Specialist marked request as high risk")
    if specialist.get("requires_human_review"):
        reasons.append("Specialist requested human review")
    if draft.get("requires_approval"):
        reasons.append("Draft response signaled approval requirement")
    if review.get("decision") in {"human_review", "rejected"}:
        reasons.append("Reviewer decision demands human oversight")
    if not knowledge and classification.get("category") not in {"general", "spam"}:
        reasons.append("No matching policy entry was available")
    if any(keyword in body_text for keyword in ["refund", "chargeback", "delete", "erase", "remove my data", "phone number", "verification"]):
        reasons.append("Body text contains sensitive account or billing request")

    needs_review = bool(reasons)
    state["requires_human_approval"] = needs_review
    state["approval_reason"] = "; ".join(reasons) if needs_review else None
    state["status"] = "pending_approval" if needs_review else "ready_for_completion"
    return state


def human_pause_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    with deps.tracer.span("human_pause", "node", "Awaiting human approval") as record:
        record["output_summary"] = state.get("approval_reason", "Awaiting decision")
        record["status"] = "pending"
    state["status"] = "pending_approval"
    return state


def finalize_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    with deps.tracer.span("finalize", "node", "Completing workflow") as record:
        state["final_response"] = state.get("draft_response")
        state["status"] = "completed"
        record["output_summary"] = "Workflow completed"
        record["status"] = "completed"
    return state


def rejection_node(state: EmailAgentState, deps: WorkflowDependencies) -> EmailAgentState:
    with deps.tracer.span("finalize_rejected", "node", "Rejected by human") as record:
        state["status"] = "rejected"
        record["output_summary"] = state.get("approval_reason", "Rejected")
        record["status"] = "completed"
    return state
