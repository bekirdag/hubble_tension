from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import Field, model_validator

from hubble_tension.schemas.base import StrictBaseModel
from hubble_tension.schemas.types import (
    AdversarialStatus,
    CandidateStatus,
    ReplicationScope,
    ReplicationStatus,
)

AdversarialAttemptStatus = Literal["passed", "failed", "inconclusive", "not_applicable"]

REGISTERED_CODE_DEFINED_CHECK_IDS: Final[tuple[str, ...]] = (
    "StricterToleranceRerun",
    "OutOfPriorAudit",
    "LikelihoodCrashAudit",
    "AlternateDatasetSplit",
)


class AdversarialQueueItem(StrictBaseModel):
    queue_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    status: str = Field(default="queued", min_length=1)
    priority: int = Field(ge=0)
    reason: str = Field(min_length=1)


class AdversarialCheckAttempt(StrictBaseModel):
    attempt_id: str = Field(min_length=1)
    check_id: str = Field(min_length=1)
    check_type: str = Field(min_length=1)
    status: AdversarialAttemptStatus
    counted: bool = True
    code_defined: bool = False
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None


class AdversarialValidationReport(StrictBaseModel):
    report_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    adversarial_status: AdversarialStatus
    replication_status: ReplicationStatus
    replication_scope: ReplicationScope
    attempts: tuple[AdversarialCheckAttempt, ...] = Field(default_factory=tuple)
    distinct_attempt_count: int = Field(ge=0)
    required_type_count: int = Field(ge=0)
    preregistered_count: int = Field(ge=0)
    budget_exhausted: bool = False
    negative_evidence_json: dict[str, Any] = Field(default_factory=dict)
    dataset_statuses_json: dict[str, Any] = Field(default_factory=dict)
    external_status: str = Field(default="not_submitted", min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def gate_counts_match_attempts(self) -> AdversarialValidationReport:
        counted_attempts = [attempt for attempt in self.attempts if attempt.counted]
        distinct_attempt_count = len({attempt.attempt_id for attempt in counted_attempts})
        required_type_count = len({attempt.check_type for attempt in counted_attempts})
        unregistered_code_defined = [
            attempt.check_id
            for attempt in counted_attempts
            if attempt.code_defined and attempt.check_id not in REGISTERED_CODE_DEFINED_CHECK_IDS
        ]
        preregistered_count = sum(
            1
            for attempt in counted_attempts
            if attempt.code_defined and attempt.check_id in REGISTERED_CODE_DEFINED_CHECK_IDS
        )

        if unregistered_code_defined:
            raise ValueError("code_defined attempts must use registered check ids")
        if self.distinct_attempt_count != distinct_attempt_count:
            raise ValueError("distinct_attempt_count must match counted unique attempts")
        if self.required_type_count != required_type_count:
            raise ValueError("required_type_count must match counted check types")
        if self.preregistered_count != preregistered_count:
            raise ValueError("preregistered_count must match counted code-defined checks")
        if self.budget_exhausted and self.adversarial_status != "inconclusive_adversarial_budget":
            raise ValueError("budget exhaustion must be inconclusive_adversarial_budget")
        if (
            not self.budget_exhausted
            and self.adversarial_status == "inconclusive_adversarial_budget"
        ):
            raise ValueError("inconclusive_adversarial_budget requires budget exhaustion")
        if self.adversarial_status == "passed_registered_gate":
            if self.distinct_attempt_count < 12:
                raise ValueError("passed adversarial gate requires at least 12 counted attempts")
            if self.required_type_count < 5:
                raise ValueError("passed adversarial gate requires at least 5 check types")
            if self.preregistered_count < 4:
                raise ValueError("passed adversarial gate requires 4 code-defined checks")
            if any(attempt.status != "passed" for attempt in counted_attempts):
                raise ValueError("passed adversarial gate cannot include failed counted attempts")
        return self


class StableCandidateRegistryEntry(StrictBaseModel):
    candidate_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    candidate_status: CandidateStatus
    replication_status: ReplicationStatus
    replication_scope: ReplicationScope
    adversarial_status: AdversarialStatus
    datasets_passed_json: dict[str, bool] = Field(default_factory=dict)
    report_path: str | None = None
    external_status: str = Field(default="not_submitted", min_length=1)
    registry_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def stable_entry_must_pass_configured_gates(self) -> StableCandidateRegistryEntry:
        if self.candidate_status != "stable_internal_candidate":
            raise ValueError("stable registry entries require stable_internal_candidate status")
        if self.replication_status != "passed_independent_path":
            raise ValueError("stable registry entries require passed independent replication")
        if self.replication_scope not in {"compressed_observable", "full_supported_family"}:
            raise ValueError("stable registry entries require broad enough replication scope")
        if self.adversarial_status != "passed_registered_gate":
            raise ValueError("stable registry entries require passed adversarial validation")
        if not any(self.datasets_passed_json.values()):
            raise ValueError("stable registry entries require at least one passed dataset")
        return self
