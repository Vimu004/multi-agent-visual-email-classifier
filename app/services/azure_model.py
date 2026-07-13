"""Azure GPT-5.4 Nano client wrapper using the OpenAI SDK."""
from __future__ import annotations

from typing import Type
from urllib.parse import urlparse

import anyio
from openai import AzureOpenAI
from pydantic import BaseModel

from ..config import get_settings

_settings = get_settings()
_client: AzureOpenAI | None = None
# Azure AI Foundry exposes the OpenAI v1 surface (incl. the Responses API) under
# the resource root, addressed with the "preview" api-version.
API_VERSION = "preview"


def _get_base_url() -> str:
    """Derive the Foundry OpenAI v1 base URL from the configured endpoint.

    The configured endpoint is the Foundry *project* URL
    (e.g. https://<resource>.services.ai.azure.com/api/projects/<project>),
    but the OpenAI-compatible API lives at the resource root:
    https://<resource>.services.ai.azure.com/openai/v1/.
    """

    endpoint = (_settings.azure_ai_project_endpoint or "").strip()
    if not endpoint:
        raise RuntimeError("AZURE_AI_PROJECT_ENDPOINT is not configured")
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"AZURE_AI_PROJECT_ENDPOINT is not a valid URL: {endpoint!r}")
    return f"{parsed.scheme}://{parsed.netloc}/openai/v1/"


def _get_client() -> AzureOpenAI:
    if not _settings.azure_ai_api_key:
        raise RuntimeError("AZURE_AI_API_KEY is not configured")
    if not _settings.azure_ai_model_deployment_name:
        raise RuntimeError("AZURE_AI_MODEL_DEPLOYMENT_NAME is not configured")
    global _client
    if _client is None:
        _client = AzureOpenAI(
            api_key=_settings.azure_ai_api_key,
            base_url=_get_base_url(),
            api_version=API_VERSION,
        )
    return _client


async def generate_structured(system_prompt: str, user_prompt: str, response_model: Type[BaseModel]) -> BaseModel:
    """Call the Azure Foundry deployment and return a validated structured response.

    Uses the Responses API structured-output support (``text_format``), which
    forces the model to emit JSON conforming to ``response_model``'s schema, so
    enum/required-field mismatches cannot occur.
    """

    client = _get_client()

    def _invoke() -> BaseModel:
        response = client.responses.parse(
            model=_settings.azure_ai_model_deployment_name,
            input=[
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            text_format=response_model,
        )
        parsed = response.output_parsed
        if parsed is None:  # pragma: no cover - depends on model output
            raise ValueError(f"Azure response could not be parsed into {response_model.__name__}")
        return parsed

    return await anyio.to_thread.run_sync(_invoke)
