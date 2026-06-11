"""Contracts for start-request artifacts created by natural-language run bootstrap."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


StartInteractionMode = Literal["guided", "direct", "brief_import"]
StartRequestStatus = Literal["completed"]


class StartRequestContract(BaseModel):
    """Stable contract for `state/START_REQUEST.json`."""

    model_config = ConfigDict(extra="ignore")

    status: StartRequestStatus = Field(default="completed")
    runId: str = Field(default="")
    requestText: str = Field(default="")
    interactionMode: StartInteractionMode = Field(default="direct")
    explicitControls: dict[str, str] = Field(default_factory=dict)
    inferredControls: dict[str, str] = Field(default_factory=dict)
    briefSource: str = Field(default="")
    notesSource: str = Field(default="")
    createdAt: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> StartRequestContract:
        """Validate a raw start-request payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> StartRequestContract:
        """Load and validate a start-request artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
