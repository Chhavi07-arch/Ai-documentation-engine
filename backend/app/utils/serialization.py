"""JSON (de)serialization helpers used for the JSON columns on models."""

from __future__ import annotations

import json
from typing import Any


def dump_json(value: Any) -> str:
    """Serialize ``value`` to a compact JSON string."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_json(value: str | None, default: Any = None) -> Any:
    """Deserialize a JSON string, returning ``default`` on empty/invalid input."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
