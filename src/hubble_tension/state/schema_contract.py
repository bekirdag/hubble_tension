from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True)
class StorageCoverage:
    model_name: str
    table_name: str | None
    non_persistent_reason: str | None = None


STORAGE_COVERAGE: Final[dict[str, StorageCoverage]] = {
    "AdversarialCheckAttempt": StorageCoverage(
        "AdversarialCheckAttempt",
        None,
        "Embedded inside AdversarialValidationReport.attempts.",
    ),
    "AdversarialQueueItem": StorageCoverage(
        "AdversarialQueueItem",
        "adversarial_queue",
    ),
    "AdversarialValidationReport": StorageCoverage(
        "AdversarialValidationReport",
        "adversarial_reports",
    ),
    "AssumptionDiff": StorageCoverage("AssumptionDiff", "assumption_sets"),
    "BenchmarkReplayRecord": StorageCoverage(
        "BenchmarkReplayRecord",
        None,
        "Derived from paper-study records and replayed by Phase 4 benchmark code.",
    ),
    "CandidateRecord": StorageCoverage("CandidateRecord", "candidates"),
    "CitationSpan": StorageCoverage(
        "CitationSpan",
        None,
        "Embedded inside PaperStudyRecord and FailureMemoryRecord payloads.",
    ),
    "ConstraintFailure": StorageCoverage("ConstraintFailure", "constraints"),
    "DatasetChi2": StorageCoverage(
        "DatasetChi2",
        None,
        "Embedded inside MetricPacket.packet_json.",
    ),
    "DatasetBacklogItem": StorageCoverage(
        "DatasetBacklogItem",
        "dataset_backlog",
    ),
    "ExternalEvidenceRecord": StorageCoverage(
        "ExternalEvidenceRecord",
        None,
        "Embedded inside ExternalTransitionProposal.evidence_json.",
    ),
    "ExternalRerunRequest": StorageCoverage(
        "ExternalRerunRequest",
        "external_rerun_queue",
    ),
    "ExternalTransitionProposal": StorageCoverage(
        "ExternalTransitionProposal",
        "pending_external_transitions",
    ),
    "FailureMemoryRecord": StorageCoverage(
        "FailureMemoryRecord",
        "paper_extractions",
    ),
    "H0Measurement": StorageCoverage(
        "H0Measurement",
        None,
        "Embedded inside MetricPacket.packet_json.",
    ),
    "H0Relief": StorageCoverage(
        "H0Relief",
        None,
        "Embedded inside MetricPacket.packet_json.",
    ),
    "IndependentImplementationRecord": StorageCoverage(
        "IndependentImplementationRecord",
        None,
        "Embedded inside ReplicationReport.",
    ),
    "JointChi2": StorageCoverage(
        "JointChi2",
        None,
        "Embedded inside MetricPacket.packet_json.",
    ),
    "LambdaCDMDelta": StorageCoverage(
        "LambdaCDMDelta",
        None,
        "Embedded inside MetricPacket.packet_json.",
    ),
    "LabHeadDecision": StorageCoverage("LabHeadDecision", "lab_head_decisions"),
    "MaintenanceJobResult": StorageCoverage(
        "MaintenanceJobResult",
        "maintenance_jobs",
    ),
    "MetricPacket": StorageCoverage("MetricPacket", "metric_packets"),
    "NoveltyProfile": StorageCoverage(
        "NoveltyProfile",
        None,
        "Embedded inside candidates or metric packets.",
    ),
    "ObservableShift": StorageCoverage(
        "ObservableShift",
        None,
        "Embedded inside MetricPacket.packet_json.",
    ),
    "OperatorDigest": StorageCoverage("OperatorDigest", "operator_digests"),
    "PaperStudyRecord": StorageCoverage("PaperStudyRecord", "paper_extractions"),
    "ReferenceComparison": StorageCoverage(
        "ReferenceComparison",
        None,
        "Embedded inside CompressedObservableReport.",
    ),
    "CompressedObservableReport": StorageCoverage(
        "CompressedObservableReport",
        None,
        "Embedded inside ReplicationReport.reference_checks.",
    ),
    "ReplicationReport": StorageCoverage("ReplicationReport", "replication_reports"),
    "ReleaseReadinessReport": StorageCoverage(
        "ReleaseReadinessReport",
        "release_readiness_reports",
    ),
    "ReportIndexEntry": StorageCoverage("ReportIndexEntry", "report_search_index"),
    "RuntimeState": StorageCoverage("RuntimeState", "runtime_state"),
    "ScaleOutProfile": StorageCoverage("ScaleOutProfile", "scale_out_profiles"),
    "StableCandidateRegistryEntry": StorageCoverage(
        "StableCandidateRegistryEntry",
        "stable_candidate_registry",
    ),
    "TextExtractionResult": StorageCoverage(
        "TextExtractionResult",
        None,
        "Transient extraction status embedded into Phase 4 extraction notes.",
    ),
    "PhaseCompletionRecord": StorageCoverage(
        "PhaseCompletionRecord",
        None,
        "Embedded inside ReleaseReadinessReport.report_json.",
    ),
    "ValidationEvidenceRecord": StorageCoverage(
        "ValidationEvidenceRecord",
        None,
        "Embedded inside ReleaseReadinessReport.report_json.",
    ),
}

STORAGE_COVERAGE_BY_MODEL: Final[MappingProxyType[str, StorageCoverage]] = MappingProxyType(
    STORAGE_COVERAGE
)
