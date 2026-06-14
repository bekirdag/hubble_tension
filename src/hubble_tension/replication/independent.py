from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from hubble_tension.policy import PROMISING_INTERNAL, REQUIRED_REPLICATION_STATUS
from hubble_tension.schemas.candidates import CandidateRecord
from hubble_tension.schemas.replication import (
    CompressedObservableReport,
    IndependentImplementationRecord,
    ReplicationReport,
)
from hubble_tension.schemas.types import ReplicationScope, ReplicationStatus

INDEPENDENT_PARSER_ID: Final[str] = "phase11_independent_parser_v1"
INDEPENDENT_FIXTURE_SET_ID: Final[str] = "phase11_independent_fixtures_v1"
INDEPENDENT_REVIEWER_ID: Final[str] = "phase11_rule_based_reviewer_v1"
INDEPENDENT_GENERATED_ROOT: Final[str] = "experiments/replication/generated_models"
LAMBDA_CDM_REPLICATION_BENCHMARK_ID: Final[str] = "lambda_cdm_phase10_observable_replay"
FIRST_EDE_REPLICATION_BENCHMARK_ID: Final[str] = "first_ede_phase10_failure_replay"

BACKGROUND_ONLY_FAMILIES: Final[frozenset[str]] = frozenset(
    {"background_only", "phenomenological_background"}
)
CMB_COMPRESSED_FAMILIES: Final[frozenset[str]] = frozenset(
    {"lambda_cdm", "lambdacdm", "early_dark_energy", "ede", "axi_ede", "axion_ede"}
)
RECOMBINATION_FAMILIES: Final[frozenset[str]] = frozenset(
    {"recombination_history", "recombination_model", "hyrec_recombination"}
)
BENCHMARK_REPLICATION_COVERAGE: Final[MappingProxyType[str, str]] = MappingProxyType(
    {
        "lambda_cdm": LAMBDA_CDM_REPLICATION_BENCHMARK_ID,
        "lambdacdm": LAMBDA_CDM_REPLICATION_BENCHMARK_ID,
        "early_dark_energy": FIRST_EDE_REPLICATION_BENCHMARK_ID,
        "ede": FIRST_EDE_REPLICATION_BENCHMARK_ID,
        "axi_ede": FIRST_EDE_REPLICATION_BENCHMARK_ID,
        "axion_ede": FIRST_EDE_REPLICATION_BENCHMARK_ID,
    }
)


@dataclass(frozen=True)
class ReplicationQueueItem:
    queue_id: str
    candidate_id: str
    hypothesis_id: str
    model_family: str
    priority: int
    reason: str


def build_replication_queue(
    candidates: Iterable[CandidateRecord],
) -> tuple[ReplicationQueueItem, ...]:
    """Return L8 replication queue items for candidates worth independent replay."""

    queued: list[ReplicationQueueItem] = []
    for candidate in candidates:
        if candidate.replication_status == REQUIRED_REPLICATION_STATUS:
            continue
        if candidate.candidate_status not in {PROMISING_INTERNAL, "adversarial_validation"}:
            continue
        model_family = str(candidate.metrics_json.get("model_family", "background_only"))
        priority = 10 if candidate.candidate_status == "adversarial_validation" else 20
        queued.append(
            ReplicationQueueItem(
                queue_id=f"replicate-{candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                hypothesis_id=candidate.hypothesis_id,
                model_family=model_family,
                priority=priority,
                reason="candidate reached L8 replication queue before stable promotion",
            )
        )
    return tuple(sorted(queued, key=lambda item: (item.priority, item.candidate_id)))


def independent_implementation_for(
    candidate: CandidateRecord,
    *,
    run_root: Path | None = None,
) -> IndependentImplementationRecord:
    """Describe the separate implementation path used by the replication runner."""

    root = Path(INDEPENDENT_GENERATED_ROOT) if run_root is None else run_root
    generated_code_path = root / candidate.candidate_id / "independent_model.py"
    return IndependentImplementationRecord(
        generated_code_path=generated_code_path.as_posix(),
        parser_id=INDEPENDENT_PARSER_ID,
        fixture_set_id=INDEPENDENT_FIXTURE_SET_ID,
        reviewer_id=INDEPENDENT_REVIEWER_ID,
        uses_shared_generated_model_code=False,
    )


def benchmark_replication_coverage_for(model_family: str) -> str | None:
    """Return the Phase 10 benchmark covered by the independent replay path."""

    return BENCHMARK_REPLICATION_COVERAGE.get(model_family.casefold())


class IndependentReplicationReviewer:
    """Deterministic automated reviewer for Phase 11 replication reports."""

    def evaluate(
        self,
        candidate: CandidateRecord,
        *,
        model_family: str,
        cmb_report: CompressedObservableReport | None = None,
        recombination_report: CompressedObservableReport | None = None,
        timed_out: bool = False,
    ) -> ReplicationReport:
        normalized_family = model_family.casefold()
        implementation = independent_implementation_for(candidate)
        reference_checks = tuple(
            report
            for report in (cmb_report, recombination_report)
            if report is not None
        )

        if timed_out:
            return self._report(
                candidate=candidate,
                model_family=model_family,
                replication_status="unreplicated_timeout",
                replication_scope="not_recorded",
                implementation=implementation,
                reference_checks=reference_checks,
                route_on_failure="retry_with_future_compute_or_simplify_model",
                blocks_stable_candidate=True,
                timed_out=True,
            )

        if normalized_family in BACKGROUND_ONLY_FAMILIES:
            return self._report(
                candidate=candidate,
                model_family=model_family,
                replication_status="passed_independent_path",
                replication_scope="background_only",
                implementation=implementation,
                reference_checks=reference_checks,
                route_on_failure="continue_background_screening_without_stable_promotion",
                blocks_stable_candidate=True,
            )

        if normalized_family in CMB_COMPRESSED_FAMILIES:
            return self._from_required_report(
                candidate=candidate,
                model_family=model_family,
                required_report=cmb_report,
                implementation=implementation,
                reference_checks=reference_checks,
            )

        if normalized_family in RECOMBINATION_FAMILIES:
            return self._from_required_report(
                candidate=candidate,
                model_family=model_family,
                required_report=recombination_report,
                implementation=implementation,
                reference_checks=reference_checks,
            )

        return self._report(
            candidate=candidate,
            model_family=model_family,
            replication_status="failed_independent_path",
            replication_scope="not_recorded",
            implementation=implementation,
            reference_checks=reference_checks,
            route_on_failure="backtrack_or_abandon",
            blocks_stable_candidate=True,
            metadata_json={"failure_reason": "unsupported_model_family"},
        )

    def _from_required_report(
        self,
        *,
        candidate: CandidateRecord,
        model_family: str,
        required_report: CompressedObservableReport | None,
        implementation: IndependentImplementationRecord,
        reference_checks: tuple[CompressedObservableReport, ...],
    ) -> ReplicationReport:
        if required_report is None or not required_report.passed():
            return self._report(
                candidate=candidate,
                model_family=model_family,
                replication_status="failed_independent_path",
                replication_scope="not_recorded",
                implementation=implementation,
                reference_checks=reference_checks,
                route_on_failure="backtrack_or_abandon",
                blocks_stable_candidate=True,
                metadata_json={"failure_reason": "required_compressed_observable_not_passed"},
            )

        return self._report(
            candidate=candidate,
            model_family=model_family,
            replication_status="passed_independent_path",
            replication_scope="compressed_observable",
            implementation=implementation,
            reference_checks=reference_checks,
            route_on_failure="advance_to_adversarial_or_stable_policy_check",
            blocks_stable_candidate=False,
        )

    def _report(
        self,
        *,
        candidate: CandidateRecord,
        model_family: str,
        replication_status: ReplicationStatus,
        replication_scope: ReplicationScope,
        implementation: IndependentImplementationRecord,
        reference_checks: tuple[CompressedObservableReport, ...],
        route_on_failure: str,
        blocks_stable_candidate: bool,
        timed_out: bool = False,
        metadata_json: dict[str, object] | None = None,
    ) -> ReplicationReport:
        metadata = dict(metadata_json or {})
        benchmark_id = benchmark_replication_coverage_for(model_family)
        if benchmark_id is not None:
            metadata.setdefault("benchmark_id", benchmark_id)
            metadata.setdefault(
                "replication_coverage",
                "phase11_independent_compressed_observable",
            )
        metadata.setdefault("reviewer_id", INDEPENDENT_REVIEWER_ID)
        return ReplicationReport(
            report_id=f"replication-{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            model_family=model_family,
            replication_status=replication_status,
            replication_scope=replication_scope,
            independent_implementation=implementation,
            reference_checks=reference_checks,
            route_on_failure=route_on_failure,
            blocks_stable_candidate=blocks_stable_candidate,
            timed_out=timed_out,
            metadata_json=metadata,
        )
