"""Email analysis API endpoints."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Callable, Type

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..config import get_settings
from ..database import engine, get_session
from ..graph.nodes import WorkflowDependencies
from ..graph.state import EmailAgentState
from ..graph.workflow import build_main_graph
from ..models import WorkflowRecord
from ..schemas import DraftResponse, EmailSubmission, WorkflowRunResponse
from ..services import azure_model, fake_model
from ..services.tracing import TraceLogger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/emails", tags=["emails"])

SettingsModelFn = Callable[[str, str, Type[BaseModel]], object]


def _select_model_callable() -> SettingsModelFn:
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
        raise HTTPException(
            status_code=500,
            detail="Azure AI credentials are missing. Configure .env or enable USE_FAKE_MODEL=true.",
        )
    return azure_model.generate_structured


def _build_initial_state(workflow_id: str, payload: EmailSubmission) -> EmailAgentState:
    return EmailAgentState(
        workflow_id=workflow_id,
        sender=payload.sender,
        subject=payload.subject,
        body=payload.body,
        trace=[],
        revision_count=0,
        status="created",
    )


async def _run_workflow(workflow_id: str, payload: EmailSubmission, model_callable: SettingsModelFn) -> None:
    """Execute the LangGraph workflow in the background.

    Trace events are committed span-by-span (see ``TraceLogger``) so the
    dashboard can poll ``/api/workflows/{id}`` and render progress live.
    """

    session = Session(engine)
    try:
        initial_state = _build_initial_state(workflow_id, payload)
        tracer = TraceLogger(workflow_id=workflow_id, session=session, accumulator=initial_state["trace"])
        deps = WorkflowDependencies(model_call=model_callable, tracer=tracer)
        graph = build_main_graph(deps)
        result_state = await graph.ainvoke(initial_state)

        record = session.get(WorkflowRecord, workflow_id)
        if record is None:  # pragma: no cover - defensive
            return
        record.category = (result_state.get("classification") or {}).get("category")
        record.selected_specialist = result_state.get("selected_specialist")
        record.status = result_state.get("status", "completed")
        record.requires_human_approval = result_state.get("requires_human_approval", False)
        record.approval_reason = result_state.get("approval_reason")
        record.state_json = result_state
        record.final_response = result_state.get("final_response")
        session.add(record)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - surface failure to the dashboard
        logger.exception("Workflow %s failed", workflow_id)
        session.rollback()
        record = session.get(WorkflowRecord, workflow_id)
        if record is not None:
            record.status = "error"
            record.approval_reason = f"Workflow error: {exc}"
            session.add(record)
            session.commit()
    finally:
        session.close()


@router.post("/analyze", response_model=WorkflowRunResponse)
async def analyze_email(payload: EmailSubmission) -> WorkflowRunResponse:
    workflow_id = f"wf_{uuid.uuid4().hex[:10]}"
    model_callable = _select_model_callable()  # validates credentials before kicking off

    with get_session() as session:
        record = WorkflowRecord(
            id=workflow_id,
            sender=payload.sender,
            subject=payload.subject,
            body=payload.body,
            status="processing",
        )
        session.add(record)

    # Fire-and-forget: the workflow runs on the event loop while the client polls.
    asyncio.create_task(_run_workflow(workflow_id, payload, model_callable))

    return WorkflowRunResponse(workflow_id=workflow_id, status="processing")
