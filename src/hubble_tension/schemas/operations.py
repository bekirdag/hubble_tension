from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from hubble_tension.schemas.base import StrictBaseModel

ReportExternalStatus = Literal[
    "not_submitted",
    "unchecked",
    "externally_refuted",
    "externally_supported",
    "superseded",
]
TransitionTargetStatus = Literal[
    "unchecked",
    "externally_refuted",
    "externally_supported",
    "superseded",
]
ExternalEvidenceRelation = Literal[
    "refutes",
    "constrains",
    "contradicts_required_observable",
    "independent_support",
    "reproduces_prediction",
    "superseding_dataset",
    "superseding_likelihood",
    "context",
]
ExternalTransitionDecision = Literal["pending", "accepted", "rejected"]
ExternalRerunStatus = Literal["queued", "running", "completed", "skipped", "failed"]
DatasetBacklogStatus = Literal["queued", "running", "resolved", "superseded"]
MaintenanceJobStatus = Literal["completed", "dry_run", "failed"]
MaintenanceJobType = Literal[
    "storage_compaction",
    "stale_scratch_cleanup",
    "report_regeneration",
]


class ExternalEvidenceRecord(StrictBaseModel):
    evidence_id: str = Field(min_length=1)
    relation: ExternalEvidenceRelation
    source_title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_url: str | None = None
    paper_id: str | None = None
    arxiv_id: str | None = None
    dataset_id: str | None = None
    observable: str | None = None

    @model_validator(mode="after")
    def evidence_has_resolvable_source(self) -> ExternalEvidenceRecord:
        if not (self.source_url or self.paper_id or self.arxiv_id):
            raise ValueError("external evidence requires source_url, paper_id, or arxiv_id")
        return self


class ExternalTransitionProposal(StrictBaseModel):
    proposal_id: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    target_external_status: TransitionTargetStatus
    current_external_status: ReportExternalStatus = "unchecked"
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    evidence: tuple[ExternalEvidenceRecord, ...] = Field(default_factory=tuple)
    candidate_id: str | None = None
    hypothesis_id: str | None = None
    decision: ExternalTransitionDecision = "pending"
    decision_reason: str | None = None
    rerun_required: bool = True

    @model_validator(mode="after")
    def target_status_has_required_evidence(self) -> ExternalTransitionProposal:
        relations = {record.relation for record in self.evidence}
        if self.target_external_status == "unchecked":
            return self
        if self.target_external_status == "externally_refuted" and not relations & {
            "refutes",
            "constrains",
            "contradicts_required_observable",
        }:
            raise ValueError("externally_refuted requires refutation or constraint evidence")
        if self.target_external_status == "externally_supported" and not relations & {
            "independent_support",
            "reproduces_prediction",
        }:
            raise ValueError("externally_supported requires independent support evidence")
        if self.target_external_status == "superseded" and not relations & {
            "superseding_dataset",
            "superseding_likelihood",
        }:
            raise ValueError("superseded requires newer dataset or likelihood evidence")
        return self


class OperatorDigest(StrictBaseModel):
    digest_id: str = Field(min_length=1)
    digest_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    report_count: int = Field(ge=0)
    transition_count: int = Field(ge=0)
    backlog_count: int = Field(ge=0)
    requires_acknowledgement: bool = False

    @model_validator(mode="after")
    def digest_must_not_require_acknowledgement(self) -> OperatorDigest:
        if self.requires_acknowledgement:
            raise ValueError("operator digests must not require acknowledgement")
        return self


class ExternalRerunRequest(StrictBaseModel):
    rerun_id: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    report_id: str = Field(min_length=1)
    target_external_status: TransitionTargetStatus
    reason: str = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    candidate_id: str | None = None
    hypothesis_id: str | None = None
    status: ExternalRerunStatus = "queued"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def rerun_requests_need_cited_evidence(self) -> ExternalRerunRequest:
        if not self.evidence_ids:
            raise ValueError("external rerun requests require cited evidence ids")
        return self


class ReportIndexEntry(StrictBaseModel):
    report_id: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    external_status: ReportExternalStatus
    search_text: str = Field(min_length=1)
    title: str | None = None
    hypothesis_id: str | None = None
    candidate_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DatasetBacklogItem(StrictBaseModel):
    backlog_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    status: DatasetBacklogStatus = "queued"
    priority: int = Field(ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ScaleOutProfile(StrictBaseModel):
    profile_id: str = Field(min_length=1)
    enabled: bool
    worker_count: int = Field(ge=0)
    allowed_job_types: tuple[str, ...] = Field(default_factory=tuple)
    preserves_sandbox: bool = True
    preserves_provenance: bool = True
    preserves_metric_gates: bool = True
    preserves_replication_gates: bool = True
    preserves_adversarial_gates: bool = True

    @model_validator(mode="after")
    def scale_out_cannot_bypass_gates(self) -> ScaleOutProfile:
        if self.enabled and self.worker_count < 1:
            raise ValueError("enabled scale-out profiles require at least one worker")
        prohibited_jobs = {"stable_promotion", "gate_override", "unsandboxed_model_run"}
        if prohibited_jobs & set(self.allowed_job_types):
            raise ValueError("scale-out profiles cannot run promotion or gate override jobs")
        gates = (
            self.preserves_sandbox,
            self.preserves_provenance,
            self.preserves_metric_gates,
            self.preserves_replication_gates,
            self.preserves_adversarial_gates,
        )
        if not all(gates):
            raise ValueError("scale-out profiles must preserve all automated gates")
        return self


class MaintenanceJobResult(StrictBaseModel):
    job_id: str = Field(min_length=1)
    job_type: MaintenanceJobType
    status: MaintenanceJobStatus
    summary: str = Field(min_length=1)
    preserved_audit_records: int = Field(ge=0)
    removed_paths: tuple[str, ...] = Field(default_factory=tuple)
    artifacts_json: dict[str, Any] = Field(default_factory=dict)
