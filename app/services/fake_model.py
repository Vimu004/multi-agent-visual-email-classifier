"""Deterministic fake model for offline demos."""
from __future__ import annotations

from typing import Type

from pydantic import BaseModel

_KEYWORDS = {
    "sales": ["pricing", "quote", "enterprise"],
    "technical_support": ["crash", "error", "not working", "bug", "issue"],
    "billing_support": ["charged", "invoice", "refund", "billing", "payment"],
    "account_access": ["login", "verification", "phone", "mfa", "code"],
    "spam": ["won", "prize", "password", "lottery"],
}


def _detect_category(text: str) -> str:
    lowered = text.lower()
    for category, tokens in _KEYWORDS.items():
        if any(token in lowered for token in tokens):
            return category
    return "general"


def _make_classification(text: str) -> dict:
    category = _detect_category(text)
    requires_review = category in {"account_access", "billing_support"}
    confidence = 0.92 if category != "general" else 0.85
    return {
        "category": category,
        "confidence": confidence,
        "priority": "high" if requires_review else "medium",
        "summary": f"Detected {category.replace('_', ' ')} request.",
        "requested_action": "Manual follow-up" if requires_review else "Provide information",
        "sensitive_action": requires_review,
        "requires_human_review": requires_review,
    }


def _make_supervisor(text: str) -> dict:
    category = _detect_category(text)
    return {
        "selected_specialist": category,
        "reason": f"Classification flagged {category}.",
        "notes": "" if category != "general" else "Simple question.",
    }


def _make_specialist(category: str) -> dict:
    high_risk = category in {"account_access", "billing_support"}
    return {
        "specialist": category,
        "analysis": f"Synthetic analysis for {category} request.",
        "recommended_action": "Follow policy guidelines",
        "information_needed": ["Confirmation details"],
        "risk": "high" if high_risk else "medium",
        "requires_human_review": high_risk,
    }


def _make_response(category: str, text: str) -> dict:
    approval = category in {"account_access", "billing_support"}
    return {
        "subject": f"Re: {text[:60]}",
        "body": (
            "Thank you for contacting us. This is a demo response tailored to your request. "
            "Sensitive actions require manual approval."
        ),
        "requires_approval": approval,
    }


def _make_review(category: str) -> dict:
    if category in {"account_access", "billing_support"}:
        return {
            "decision": "human_review",
            "approved": False,
            "grounded": True,
            "tone_ok": True,
            "issues": [],
            "feedback": "Sensitive request requires human approval.",
        }
    return {
        "decision": "approved",
        "approved": True,
        "grounded": True,
        "tone_ok": True,
        "issues": [],
        "feedback": "Looks good.",
    }


def _infer_category_from_prompt(prompt: str) -> str:
    return _detect_category(prompt)


async def generate_structured(system_prompt: str, user_prompt: str, response_model: Type[BaseModel]) -> BaseModel:
    """Return deterministic fake outputs for any schema."""

    category = _infer_category_from_prompt(user_prompt)
    payload: dict
    schema_name = response_model.__name__

    if "Classification" in schema_name:
        payload = _make_classification(user_prompt)
    elif "Supervisor" in schema_name or "Routing" in schema_name or "selected_specialist" in response_model.model_fields:
        payload = _make_supervisor(user_prompt)
    elif "Reviewer" in schema_name:
        payload = _make_review(category)
    elif "Response" in schema_name and "body" in response_model.model_fields:
        payload = _make_response(category, user_prompt)
    elif "specialist" in response_model.model_fields:
        payload = _make_specialist(category)
    else:
        payload = {"note": "Unsupported schema"}

    return response_model.model_validate(payload)
