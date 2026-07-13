"""Human approval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..database import get_session
from ..graph.nodes import WorkflowDependencies
from ..graph.workflow import build_rejection_graph, build_resume_graph
from ..models import WorkflowRecord
from ..schemas import ApprovalRequest, DraftResponse, RejectionRequest, WorkflowRunResponse
from ..services import azure_model, fake_model
from ..services.tracing import TraceLogger

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _model_callable():
    settings = get_settings()
    if settings.use_fake_model:
        return fake_model.generate_structured
    if not all(
        [
            settings.azure_ai_project_endpoint,
            settings.azure_ai_api_key,
            settings.azure_ai_model_deployment_name,
        ]
    ):
        raise HTTPException(status_code=500, detail="Azure AI credentials missing.")
    return azure_model.generate_structured


@router.post("/{workflow_id}/approve", response_model=WorkflowRunResponse)
async def approve_workflow(workflow_id: str, payload: ApprovalRequest) -> WorkflowRunResponse:
    model_callable = _model_callable()
    with get_session() as session:
        record = session.get(WorkflowRecord, workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        state = record.state_json or {}
        state.setdefault("trace", [])
        if payload.edited_response:
            state["draft_response"] = payload.edited_response.model_dump()
        state["human_decision"] = "approved"
        state["requires_human_approval"] = False

        tracer = TraceLogger(workflow_id=workflow_id, session=session, accumulator=state["trace"])
        deps = WorkflowDependencies(model_call=model_callable, tracer=tracer)
        graph = build_resume_graph(deps)
        result_state = await graph.ainvoke(state)

        record.status = result_state.get("status", "completed")
        record.final_response = result_state.get("final_response")
        record.requires_human_approval = False
        record.human_decision = "approved"
        record.state_json = result_state
        session.add(record)

        final_response = result_state.get("final_response")
        return WorkflowRunResponse(
            workflow_id=workflow_id,
            status=record.status,
            classification=result_state.get("classification"),
            selected_specialist=result_state.get("selected_specialist"),
            final_response=DraftResponse(**final_response) if final_response else None,
            approval_reason=None,
            draft_response=None,
        )


@router.post("/{workflow_id}/reject", response_model=WorkflowRunResponse)
async def reject_workflow(workflow_id: str, payload: RejectionRequest) -> WorkflowRunResponse:
    model_callable = _model_callable()
    with get_session() as session:
        record = session.get(WorkflowRecord, workflow_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        state = record.state_json or {}
        state.setdefault("trace", [])
        state["human_decision"] = "rejected"
        state["approval_reason"] = payload.reason

        tracer = TraceLogger(workflow_id=workflow_id, session=session, accumulator=state["trace"])
        deps = WorkflowDependencies(model_call=model_callable, tracer=tracer)
        graph = build_rejection_graph(deps)
        result_state = await graph.ainvoke(state)

        record.status = result_state.get("status", "rejected")
        record.requires_human_approval = False
        record.human_decision = "rejected"
        record.approval_reason = payload.reason
        record.state_json = result_state
        session.add(record)

        return WorkflowRunResponse(
            workflow_id=workflow_id,
            status=record.status,
            classification=result_state.get("classification"),
            selected_specialist=result_state.get("selected_specialist"),
            approval_reason=payload.reason,
            draft_response=None,
            final_response=None,
        )
