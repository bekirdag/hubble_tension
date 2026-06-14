from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from hubble_tension.schemas.base import StrictBaseModel
from hubble_tension.schemas.types import ReplicationScope, ReplicationStatus


class ReferenceComparison(StrictBaseModel):
    observable: str = Field(min_length=1)
    value: float
    reference: float
    tolerance: float = Field(gt=0.0)
    deviation: float = Field(ge=0.0)
    passed: bool
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def deviation_matches_values(self) -> ReferenceComparison:
        if abs(abs(self.value - self.reference) - self.deviation) > 1e-9:
            raise ValueError("deviation must equal abs(value - reference)")
        return self


class CompressedObservableReport(StrictBaseModel):
    observable_set: str = Field(min_length=1)
    status: str = Field(min_length=1)
    comparisons: tuple[ReferenceComparison, ...] = Field(default_factory=tuple)
    failed_observables: tuple[str, ...] = Field(default_factory=tuple)
    missing_observables: tuple[str, ...] = Field(default_factory=tuple)
    approximation_limit: str = Field(min_length=1)

    def passed(self) -> bool:
        return (
            self.status == "passed_reference_table"
            and not self.failed_observables
            and not self.missing_observables
            and bool(self.comparisons)
        )


class IndependentImplementationRecord(StrictBaseModel):
    generated_code_path: str = Field(min_length=1)
    parser_id: str = Field(min_length=1)
    fixture_set_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    uses_shared_generated_model_code: bool = False

    @model_validator(mode="after")
    def rejects_shared_generated_model_code(self) -> IndependentImplementationRecord:
        normalized = self.generated_code_path.replace("\\", "/")
        if self.uses_shared_generated_model_code:
            raise ValueError("independent replication cannot share generated model code")
        if "/generated_models/" in normalized and "/replication/" not in normalized:
            raise ValueError("independent replication path must not use primary generated_models")
        return self


class ReplicationReport(StrictBaseModel):
    report_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    replication_status: ReplicationStatus
    replication_scope: ReplicationScope
    independent_implementation: IndependentImplementationRecord
    reference_checks: tuple[CompressedObservableReport, ...] = Field(default_factory=tuple)
    route_on_failure: str = Field(min_length=1)
    blocks_stable_candidate: bool
    timed_out: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def stable_blocking_matches_scope(self) -> ReplicationReport:
        full_enough = self.replication_scope in {
            "compressed_observable",
            "full_supported_family",
        }
        passed = self.replication_status == "passed_independent_path"
        if (not passed or not full_enough) and not self.blocks_stable_candidate:
            raise ValueError("non-passing or narrow replication must block stable candidates")
        if self.timed_out and self.replication_status != "unreplicated_timeout":
            raise ValueError("timed_out reports must use unreplicated_timeout")
        return self
