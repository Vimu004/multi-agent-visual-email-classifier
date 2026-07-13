"""Local JSON knowledge base loader."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import get_settings

settings = get_settings()
BASE_PATH = Path(settings.knowledge_base_path)


@lru_cache(maxsize=32)
def load_category(category: str) -> list[dict[str, Any]]:
    """Return the knowledge entries for a category."""

    file_path = BASE_PATH / f"{category}.json"
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


def resolve_knowledge(category: str) -> list[dict[str, Any]]:
    """Public helper with graceful fallback."""

    try:
        return load_category(category)
    except json.JSONDecodeError:
        return []
