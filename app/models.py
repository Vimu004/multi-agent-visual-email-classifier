"""Database models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column, DateTime, text
from sqlmodel import Field, SQLModel


class WorkflowRecord(SQLModel, table=True):
    """Stores workflow submissions and state."""

    __tablename__ = "workflows"

    id: str = Field(primary_key=True, index=True)
    sender: str
    subject: str
    body: str
    category: Optional[str] = Field(default=None)
    selected_specialist: Optional[str] = Field(default=None)
    status: str = Field(default="created")
    mode: str = Field(default="multi_agentic")
    requires_human_approval: bool = Field(default=False)
    approval_reason: Optional[str] = Field(default=None)
    human_decision: Optional[str] = Field(default=None)
    final_response: Optional[dict] = Field(sa_column=Column(JSON, nullable=True))
    state_json: Optional[dict] = Field(sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            onupdate=datetime.utcnow,
        )
    )


class TraceEventRecord(SQLModel, table=True):
    """Stores per-agent execution traces."""

    __tablename__ = "trace_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    workflow_id: str = Field(index=True)
    agent_name: str
    event_type: str
    input_summary: str
    output_summary: str
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    status: str
