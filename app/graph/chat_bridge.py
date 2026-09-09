"""Bridges langgraph-supervisor's message-passing API onto this app's
structured `generate_structured(system_prompt, user_prompt, response_model)`
model layer, so the same fake/Azure model callable that powers every other
node also powers the supervisor + department agents. No new model provider
is introduced.
"""
from __future__ import annotations

import json
import uuid
from typing import List, Optional

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ..schemas import SpecialistAnalysis, SupervisorDecision
from .nodes import WorkflowDependencies
from .prompts import SPECIALIST_PROMPTS, SUPERVISOR_PROMPT


def _last_human_text(messages: List[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return str(messages[-1].content) if messages else ""


class _NoToolBindingChatModel(BaseChatModel):
    """LangChain requires `.bind_tools()` to exist; our routing logic decides
    tool calls directly from structured output rather than inspecting tool
    schemas, so binding is a no-op."""

    model_config = {"arbitrary_types_allowed": True}

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001 - matches BaseChatModel signature
        return self

    def _generate(self, *args, **kwargs):  # pragma: no cover - async-only in this app
        raise NotImplementedError("Synchronous generation is not used; call the async path.")


class SupervisorBridgeModel(_NoToolBindingChatModel):
    """Acts as the supervisor's LLM: makes exactly one routing decision per
    run (reusing the existing SupervisorDecision call), then hands back
    control once a department agent has replied."""

    deps: WorkflowDependencies

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> ChatResult:
        already_routed = any(getattr(m, "name", None) and m.name.endswith("_agent") for m in messages)
        if already_routed:
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="Department has responded; finishing up."))]
            )

        prompt = _last_human_text(messages)
        with self.deps.tracer.span("supervisor_agent", "agent", prompt[:160]) as record:
            decision: SupervisorDecision = await self.deps.model_call(SUPERVISOR_PROMPT, prompt, SupervisorDecision)
            record["output_summary"] = f"Routed to {decision.selected_specialist}"
            record["status"] = "completed"

        tool_name = f"transfer_to_{decision.selected_specialist}_agent"
        msg = AIMessage(
            content=f"Routing to {decision.selected_specialist}: {decision.reason}",
            tool_calls=[{"name": tool_name, "args": {}, "id": f"call_{uuid.uuid4().hex[:8]}"}],
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "supervisor-bridge"


class DepartmentBridgeModel(_NoToolBindingChatModel):
    """Acts as one department agent's LLM: analyzes the email and decides an
    action (not just drafts text) via the existing SpecialistAnalysis call."""

    department: str
    deps: WorkflowDependencies

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> ChatResult:
        prompt = _last_human_text(messages)
        system_prompt = SPECIALIST_PROMPTS.get(self.department, SPECIALIST_PROMPTS["general"])
        with self.deps.tracer.span(f"{self.department}_agent", "agent", prompt[:160]) as record:
            result: SpecialistAnalysis = await self.deps.model_call(system_prompt, prompt, SpecialistAnalysis)
            record["output_summary"] = f"{result.action} ({result.risk} risk)"
            record["status"] = "completed"

        payload = result.model_dump()
        payload["specialist"] = self.department
        msg = AIMessage(content=json.dumps(payload), name=f"{self.department}_agent")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return f"department-bridge-{self.department}"
