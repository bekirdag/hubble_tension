from __future__ import annotations

from typing import Any

from pydantic import Field

from hubble_tension.schemas.base import StrictBaseModel
from hubble_tension.schemas.types import (
    AdversarialStatus,
    CandidateStatus,
    ReplicationScope,
    ReplicationStatus,
    WildnessLevel,
)


class NoveltyProfile(StrictBaseModel):
    structural_hash_distance: float | None = Field(default=None, ge=0.0)
    prior_hypothesis_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    observable_distance_if_available: float | None = Field(default=None, ge=0.0)


class CandidateRecord(StrictBaseModel):
    candidate_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    concept_name: str = Field(min_length=1)
    wildness_level: WildnessLevel
    candidate_status: CandidateStatus
    replication_status: ReplicationStatus
    replication_scope: ReplicationScope = "not_recorded"
    adversarial_status: AdversarialStatus
    datasets_passed_json: dict[str, bool] = Field(default_factory=dict)
    report_path: str | None = None
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    novelty_profile: NoveltyProfile | None = None
