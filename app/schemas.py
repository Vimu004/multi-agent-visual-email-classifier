"""Pydantic schemas for API IO and agent wiring."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EmailSubmission(BaseModel):
    sender: str
    subject: str
    body: str


class DraftResponse(BaseModel):
    subject: str
    body: str
    requires_approval: bool = False


class ClassificationResult(BaseModel):
    category: Literal[
        "spam",
        "sales",
        "technical_support",
        "billing_support",
        "account_access",
        "general",
        "human_review",
    ]
    confidence: float = Field(ge=0, le=1)
    priority: Literal["low", "medium", "high"]
    summary: str
    requested_action: str | None = None
    sensitive_action: bool = False
    requires_human_review: bool = False


class SpecialistAnalysis(BaseModel):
    specialist: str
    analysis: str
    recommended_action: str
    information_needed: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"]
    requires_human_review: bool = False


class SupervisorDecision(BaseModel):
    selected_specialist: Literal[
        "spam",
        "sales",
        "technical_support",
        "billing_support",
        "account_access",
        "general",
    ]
    reason: str
    notes: str | None = None


class ReviewerDecision(BaseModel):
    decision: Literal["approved", "revise", "human_review", "rejected"]
    approved: bool
    grounded: bool
    tone_ok: bool
    issues: list[str] = Field(default_factory=list)
    feedback: str


class ApprovalRequest(BaseModel):
    edited_response: Optional[DraftResponse] = None


class RejectionRequest(BaseModel):
    reason: str


class WorkflowSummary(BaseModel):
    id: str
    subject: str
    category: Optional[str]
    status: str
    requires_human_approval: bool
    updated_at: datetime


class TraceEvent(BaseModel):
    agent_name: str
    event_type: str
    input_summary: str
    output_summary: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: str


class WorkflowDetail(BaseModel):
    id: str
    sender: str
    subject: str
    body: str
    category: Optional[str]
    selected_specialist: Optional[str]
    status: str
    requires_human_approval: bool
    approval_reason: Optional[str]
    human_decision: Optional[str]
    final_response: Optional[DraftResponse | dict]
    created_at: datetime
    updated_at: datetime
    state_json: dict[str, Any] | None
    trace: list[TraceEvent] = Field(default_factory=list)


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    status: str
    classification: Optional[ClassificationResult] = None
    selected_specialist: Optional[str] = None
    draft_response: Optional[DraftResponse] = None
    approval_reason: Optional[str] = None
    final_response: Optional[DraftResponse | dict] = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
