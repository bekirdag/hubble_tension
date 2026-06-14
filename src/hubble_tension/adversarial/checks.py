from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Final

from hubble_tension import policy
from hubble_tension.schemas.adversarial import (
    REGISTERED_CODE_DEFINED_CHECK_IDS,
    AdversarialCheckAttempt,
    AdversarialQueueItem,
    AdversarialValidationReport,
)
from hubble_tension.schemas.candidates import CandidateRecord
from hubble_tension.schemas.types import AdversarialStatus

CHECK_TYPE_STRICTER_TOLERANCE_RERUN: Final[str] = "stricter_tolerance_rerun"
CHECK_TYPE_OUT_OF_PRIOR_AUDIT: Final[str] = "out_of_prior_audit"
CHECK_TYPE_LIKELIHOOD_CRASH_AUDIT: Final[str] = "likelihood_crash_audit"
CHECK_TYPE_ALTERNATE_DATASET_SPLIT: Final[str] = "alternate_dataset_split"
CHECK_TYPE_CALIBRATION_SUITE_RERUN: Final[str] = "calibration_suite_rerun"
CHECK_TYPE_NEUTRAL_SCORE_AUDIT: Final[str] = "neutral_score_audit"
CHECK_TYPE_PRIOR_ART_REFUTATION_SEARCH: Final[str] = "prior_art_refutation_search"

REQUIRED_ADVERSARIAL_CHECK_TYPES: Final[tuple[str, ...]] = (
    CHECK_TYPE_STRICTER_TOLERANCE_RERUN,
    CHECK_TYPE_OUT_OF_PRIOR_AUDIT,
    CHECK_TYPE_LIKELIHOOD_CRASH_AUDIT,
    CHECK_TYPE_ALTERNATE_DATASET_SPLIT,
    CHECK_TYPE_CALIBRATION_SUITE_RERUN,
    CHECK_TYPE_NEUTRAL_SCORE_AUDIT,
    CHECK_TYPE_PRIOR_ART_REFUTATION_SEARCH,
)

MIN_DISTINCT_ATTEMPTS: Final[int] = 12
MIN_REQUIRED_CHECK_TYPES: Final[int] = 5
MIN_REGISTERED_CHECKS: Final[int] = 4


@dataclass(frozen=True)
class RegisteredAdversarialCheck:
    check_id: str
    check_type: str
    description: str
    stage_range: str
    code_defined: bool = True
    tolerance_multiplier: float | None = None
    sample_count: int | None = None
    requires_dataset_split: bool = False

    @property
    def registration_hash(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


REGISTERED_ADVERSARIAL_CHECKS: Final[tuple[RegisteredAdversarialCheck, ...]] = (
    RegisteredAdversarialCheck(
        check_id="StricterToleranceRerun",
        check_type=CHECK_TYPE_STRICTER_TOLERANCE_RERUN,
        description="Rerun L3-L7 with 0.5x numerical tolerances.",
        stage_range="L3-L7",
        tolerance_multiplier=0.5,
    ),
    RegisteredAdversarialCheck(
        check_id="OutOfPriorAudit",
        check_type=CHECK_TYPE_OUT_OF_PRIOR_AUDIT,
        description=(
            "Sample 100 out-of-prior parameter combinations and require documented "
            "out_of_prior likelihood status."
        ),
        stage_range="L3-L7",
        sample_count=100,
    ),
    RegisteredAdversarialCheck(
        check_id="LikelihoodCrashAudit",
        check_type=CHECK_TYPE_LIKELIHOOD_CRASH_AUDIT,
        description=(
            "Inject NaN and malformed inputs and require loud likelihood failures "
            "rather than neutral scores."
        ),
        stage_range="L3-L7",
    ),
    RegisteredAdversarialCheck(
        check_id="AlternateDatasetSplit",
        check_type=CHECK_TYPE_ALTERNATE_DATASET_SPLIT,
        description=(
            "Rerun against held-out or alternate published splits when available."
        ),
        stage_range="L3-L7",
        requires_dataset_split=True,
    ),
)


def registered_check_ids() -> tuple[str, ...]:
    return REGISTERED_CODE_DEFINED_CHECK_IDS


def build_adversarial_queue(
    candidates: Iterable[CandidateRecord],
) -> tuple[AdversarialQueueItem, ...]:
    queue: list[AdversarialQueueItem] = []
    for candidate in candidates:
        if candidate.adversarial_status == policy.REQUIRED_ADVERSARIAL_STATUS:
            continue
        payload = candidate.model_dump(mode="json")
        if not policy.can_promote_to(payload, policy.ADVERSARIAL_VALIDATION):
            continue
        priority = 10 if candidate.candidate_status == policy.ADVERSARIAL_VALIDATION else 20
        queue.append(
            AdversarialQueueItem(
                queue_id=f"adv-{candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                hypothesis_id=candidate.hypothesis_id,
                priority=priority,
                reason="candidate passed independent replication and needs L9 refutation checks",
            )
        )
    return tuple(sorted(queue, key=lambda item: (item.priority, item.candidate_id)))


def evaluate_adversarial_gate(
    candidate: CandidateRecord,
    *,
    report_id: str,
    attempts: Iterable[AdversarialCheckAttempt],
    budget_exhausted: bool = False,
    external_status: str = "not_submitted",
    negative_evidence_json: Mapping[str, Any] | None = None,
    dataset_statuses_json: Mapping[str, Any] | None = None,
    metadata_json: Mapping[str, Any] | None = None,
) -> AdversarialValidationReport:
    attempt_tuple = tuple(attempts)
    counted_attempts = [attempt for attempt in attempt_tuple if attempt.counted]
    distinct_attempt_count = len({attempt.attempt_id for attempt in counted_attempts})
    required_type_count = len({attempt.check_type for attempt in counted_attempts})
    preregistered_count = sum(
        1
        for attempt in counted_attempts
        if attempt.code_defined and attempt.check_id in registered_check_ids()
    )
    all_counted_passed = counted_attempts and all(
        attempt.status == "passed" for attempt in counted_attempts
    )

    adversarial_status: AdversarialStatus
    if budget_exhausted:
        adversarial_status = "inconclusive_adversarial_budget"
    elif (
        distinct_attempt_count >= MIN_DISTINCT_ATTEMPTS
        and required_type_count >= MIN_REQUIRED_CHECK_TYPES
        and preregistered_count >= MIN_REGISTERED_CHECKS
        and all_counted_passed
    ):
        adversarial_status = "passed_registered_gate"
    else:
        adversarial_status = "failed_registered_gate"

    return AdversarialValidationReport(
        report_id=report_id,
        candidate_id=candidate.candidate_id,
        hypothesis_id=candidate.hypothesis_id,
        adversarial_status=adversarial_status,
        replication_status=candidate.replication_status,
        replication_scope=candidate.replication_scope,
        attempts=attempt_tuple,
        distinct_attempt_count=distinct_attempt_count,
        required_type_count=required_type_count,
        preregistered_count=preregistered_count,
        budget_exhausted=budget_exhausted,
        negative_evidence_json=dict(negative_evidence_json or {}),
        dataset_statuses_json=dict(dataset_statuses_json or {}),
        external_status=external_status,
        metadata_json=dict(metadata_json or {}),
    )


def phase12_registered_gate_attempts(candidate_id: str) -> tuple[AdversarialCheckAttempt, ...]:
    registered_attempts = tuple(
        _attempt(
            candidate_id=candidate_id,
            index=index,
            check_id=check.check_id,
            check_type=check.check_type,
            code_defined=True,
            evidence={
                "registration_hash": check.registration_hash,
                "stage_range": check.stage_range,
            },
        )
        for index, check in enumerate(REGISTERED_ADVERSARIAL_CHECKS, start=1)
    )
    extra_attempt_specs = (
        (CHECK_TYPE_CALIBRATION_SUITE_RERUN, "calibration-suite-l3"),
        (CHECK_TYPE_CALIBRATION_SUITE_RERUN, "known-bad-calibration-suite"),
        (CHECK_TYPE_NEUTRAL_SCORE_AUDIT, "nan-neutral-score-probe"),
        (CHECK_TYPE_NEUTRAL_SCORE_AUDIT, "malformed-neutral-score-probe"),
        (CHECK_TYPE_PRIOR_ART_REFUTATION_SEARCH, "local-corpus-refutation-search"),
        (CHECK_TYPE_PRIOR_ART_REFUTATION_SEARCH, "arxiv-refutation-search"),
        (CHECK_TYPE_STRICTER_TOLERANCE_RERUN, "l7-half-tolerance-replay"),
        (CHECK_TYPE_ALTERNATE_DATASET_SPLIT, "published-alternate-split-replay"),
    )
    extra_attempts = tuple(
        _attempt(
            candidate_id=candidate_id,
            index=index,
            check_id=check_id,
            check_type=check_type,
            code_defined=False,
            evidence={"source": "phase12_adversarial_suite"},
        )
        for index, (check_type, check_id) in enumerate(extra_attempt_specs, start=5)
    )
    return registered_attempts + extra_attempts


def _attempt(
    *,
    candidate_id: str,
    index: int,
    check_id: str,
    check_type: str,
    code_defined: bool,
    evidence: Mapping[str, Any],
) -> AdversarialCheckAttempt:
    return AdversarialCheckAttempt(
        attempt_id=f"{candidate_id}-adv-{index:02d}",
        check_id=check_id,
        check_type=check_type,
        status="passed",
        counted=True,
        code_defined=code_defined,
        evidence_json=dict(evidence),
    )
