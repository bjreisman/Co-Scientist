"""Structured response parsing helpers shared by runner implementations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def validate_structured_metadata[TContent: BaseModel](
    metadata: Any,
    content_model: type[TContent],
    *,
    agent_name: str | None = None,
) -> TContent:
    """Validate structured response metadata for a declared content model."""
    if not metadata:
        if agent_name:
            raise ValueError(f"Agent {agent_name!r} returned empty metadata; expected {content_model.__name__} fields")
        raise ValueError(f"Structured response returned empty metadata; expected {content_model.__name__} fields")
    return content_model.model_validate(metadata)


def populate_result_from_metadata[TResult, TContent: BaseModel](
    result_obj: TResult,
    metadata: Any,
    content_model: type[TContent],
    *,
    agent_name: str | None = None,
) -> TResult:
    """Validate structured metadata and copy the resulting fields onto *result_obj*."""
    validated = validate_structured_metadata(metadata, content_model, agent_name=agent_name)
    for key, value in validated.model_dump().items():
        if key in content_model.model_fields:
            setattr(result_obj, key, value)
    return result_obj
