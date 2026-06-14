from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Base model for Phase 0 language-level schemas."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)
