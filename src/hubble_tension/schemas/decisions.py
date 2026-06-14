from __future__ import annotations

from typing import Any

from pydantic import Field

from hubble_tension.schemas.base import StrictBaseModel
from hubble_tension.schemas.types import Decision, Uncertainty


class LabHeadDecision(StrictBaseModel):
    hypothesis_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_version_hash: str = Field(min_length=1)
    prompt_template_id: str = Field(min_length=1)
    prompt_template_hash: str = Field(min_length=1)
    decision: Decision
    rationale: str = Field(min_length=1)
    uncertainty: Uncertainty
    observation_json: dict[str, Any] = Field(default_factory=dict)
    actions_json: dict[str, Any] = Field(default_factory=dict)
    next_step: str = Field(min_length=1)
