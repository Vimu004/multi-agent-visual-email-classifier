"""LangGraph workflow orchestration."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    WorkflowDependencies,
    approval_gate_node,
    classification_node,
    finalize_node,
    finalize_routing_node,
    human_pause_node,
    intake_node,
    multiagent_node,
    rejection_node,
    response_node,
    reviewer_node,
    route_node,
)
from .state import EmailAgentState


def build_agentic_graph(deps: WorkflowDependencies):
    """Mode A: one agent, one Think-Act-Observe pass. Classify, then forward
    to the department's shared inbox. No risk check, no task execution, no
    human-in-the-loop — the naive baseline the multi-agentic mode contrasts
    against."""

    graph = StateGraph(EmailAgentState)

    graph.add_node("intake_node", lambda state: intake_node(state, deps))

    async def classification_wrapper(state: EmailAgentState):
        return await classification_node(state, deps)

    graph.add_node("classification_node", classification_wrapper)
    graph.add_node("route_node", lambda state: route_node(state, deps))
    graph.add_node("finalize_routing_node", lambda state: finalize_routing_node(state, deps))

    graph.set_entry_point("intake_node")
    graph.add_edge("intake_node", "classification_node")
    graph.add_edge("classification_node", "route_node")
    graph.add_edge("route_node", "finalize_routing_node")
    graph.add_edge("finalize_routing_node", END)

    return graph.compile()


def build_multiagent_graph(deps: WorkflowDependencies):
    """Mode B: classify, then a real langgraph-supervisor supervisor hands
    the email off to one department agent, which analyzes it and decides an
    action, then response/review/approval as before."""

    graph = StateGraph(EmailAgentState)

    graph.add_node("intake_node", lambda state: intake_node(state, deps))

    async def classification_wrapper(state: EmailAgentState):
        return await classification_node(state, deps)

    async def multiagent_wrapper(state: EmailAgentState):
        return await multiagent_node(state, deps)

    async def response_wrapper(state: EmailAgentState):
        return await response_node(state, deps)

    async def reviewer_wrapper(state: EmailAgentState):
        return await reviewer_node(state, deps)

    graph.add_node("classification_node", classification_wrapper)
    graph.add_node("multiagent_node", multiagent_wrapper)
    graph.add_node("response_node", response_wrapper)
    graph.add_node("reviewer_node", reviewer_wrapper)
    graph.add_node("approval_gate_node", lambda state: approval_gate_node(state, deps))
    graph.add_node("human_pause_node", lambda state: human_pause_node(state, deps))
    graph.add_node("finalize_node", lambda state: finalize_node(state, deps))

    graph.set_entry_point("intake_node")
    graph.add_edge("intake_node", "classification_node")
    graph.add_edge("classification_node", "multiagent_node")
    graph.add_edge("multiagent_node", "response_node")
    graph.add_edge("response_node", "reviewer_node")

    graph.add_conditional_edges(
        "reviewer_node",
        lambda state: "revise" if state.get("revision_pending") else "continue",
        {"revise": "response_node", "continue": "approval_gate_node"},
    )

    graph.add_conditional_edges(
        "approval_gate_node",
        lambda state: "pause" if state.get("requires_human_approval") else "finalize",
        {"pause": "human_pause_node", "finalize": "finalize_node"},
    )

    graph.add_edge("human_pause_node", END)
    graph.add_edge("finalize_node", END)

    return graph.compile()


def build_resume_graph(deps: WorkflowDependencies):
    graph = StateGraph(EmailAgentState)
    graph.add_node("finalize_node", lambda state: finalize_node(state, deps))
    graph.set_entry_point("finalize_node")
    graph.add_edge("finalize_node", END)
    return graph.compile()


def build_rejection_graph(deps: WorkflowDependencies):
    graph = StateGraph(EmailAgentState)
    graph.add_node("reject_node", lambda state: rejection_node(state, deps))
    graph.set_entry_point("reject_node")
    graph.add_edge("reject_node", END)
    return graph.compile()
