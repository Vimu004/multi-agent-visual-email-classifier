"""Workflow data APIs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..database import get_session
from ..models import TraceEventRecord, WorkflowRecord
from ..schemas import TraceEvent, WorkflowDetail, WorkflowSummary

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowSummary])
def list_workflows() -> list[WorkflowSummary]:
    with get_session() as session:
        statement = select(WorkflowRecord).order_by(WorkflowRecord.updated_at.desc()).limit(50)
        results = session.exec(statement).all()
        return [
            WorkflowSummary(
                id=wf.id,
                subject=wf.subject,
                category=wf.category,
                status=wf.status,
                requires_human_approval=wf.requires_human_approval,
                updated_at=wf.updated_at,
            )
            for wf in results
        ]


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: str) -> WorkflowDetail:
    with get_session() as session:
        record = session.get(WorkflowRecord, workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        trace_stmt = (
            select(TraceEventRecord)
            .where(TraceEventRecord.workflow_id == workflow_id)
            .order_by(TraceEventRecord.started_at)
        )
        trace_records = session.exec(trace_stmt).all()
        trace = [
            TraceEvent(
                agent_name=t.agent_name,
                event_type=t.event_type,
                input_summary=t.input_summary,
                output_summary=t.output_summary,
                started_at=t.started_at,
                completed_at=t.completed_at,
                duration_ms=t.duration_ms,
                status=t.status,
            )
            for t in trace_records
        ]
        return WorkflowDetail(
            id=record.id,
            sender=record.sender,
            subject=record.subject,
            body=record.body,
            category=record.category,
            selected_specialist=record.selected_specialist,
            status=record.status,
            requires_human_approval=record.requires_human_approval,
            approval_reason=record.approval_reason,
            human_decision=record.human_decision,
            final_response=record.final_response,
            created_at=record.created_at,
            updated_at=record.updated_at,
            state_json=record.state_json,
            trace=trace,
        )
