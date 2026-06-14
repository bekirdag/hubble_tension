from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from hubble_tension.adversarial import (
    MIN_DISTINCT_ATTEMPTS,
    MIN_REGISTERED_CHECKS,
    MIN_REQUIRED_CHECK_TYPES,
    REGISTERED_ADVERSARIAL_CHECKS,
    build_adversarial_queue,
    evaluate_adversarial_gate,
    phase12_registered_gate_attempts,
    registered_check_ids,
)
from hubble_tension.schemas.adversarial import (
    AdversarialValidationReport,
    StableCandidateRegistryEntry,
)
from hubble_tension.schemas.candidates import CandidateRecord


def test_registered_adversarial_checks_are_code_defined_and_immutable() -> None:
    check = REGISTERED_ADVERSARIAL_CHECKS[0]

    assert registered_check_ids() == (
        "StricterToleranceRerun",
        "OutOfPriorAudit",
        "LikelihoodCrashAudit",
        "AlternateDatasetSplit",
    )
    assert check.code_defined is True
    assert check.tolerance_multiplier == 0.5
    assert len(check.registration_hash) == 64
    with pytest.raises(FrozenInstanceError):
        check.check_id = "rewritten-by-lab-head"  # type: ignore[misc]


def test_adversarial_queue_selects_replicated_candidates_needing_l9() -> None:
    queued = build_adversarial_queue(
        [
            _candidate("cand-ready", candidate_status="adversarial_validation"),
            _candidate("cand-promising", candidate_status="promising_internal"),
            _candidate("cand-unreplicated", replication_status="unreplicated_timeout"),
            _candidate("cand-passed", adversarial_status="passed_registered_gate"),
        ]
    )

    assert [item.candidate_id for item in queued] == ["cand-ready", "cand-promising"]
    assert queued[0].priority < queued[1].priority


def test_adversarial_registered_gate_requires_attempt_counts_and_categories() -> None:
    candidate = _candidate("cand-phase12")
    attempts = phase12_registered_gate_attempts(candidate.candidate_id)
    report = evaluate_adversarial_gate(
        candidate,
        report_id="adv-cand-phase12",
        attempts=attempts,
    )

    assert report.adversarial_status == "passed_registered_gate"
    assert report.distinct_attempt_count == MIN_DISTINCT_ATTEMPTS
    assert report.required_type_count >= MIN_REQUIRED_CHECK_TYPES
    assert report.preregistered_count >= MIN_REGISTERED_CHECKS
    assert len({attempt.attempt_id for attempt in attempts}) == MIN_DISTINCT_ATTEMPTS


def test_adversarial_budget_exhaustion_is_inconclusive_not_pass() -> None:
    candidate = _candidate("cand-budget")
    report = evaluate_adversarial_gate(
        candidate,
        report_id="adv-budget",
        attempts=phase12_registered_gate_attempts(candidate.candidate_id),
        budget_exhausted=True,
    )

    assert report.adversarial_status == "inconclusive_adversarial_budget"


def test_adversarial_schema_rejects_pass_with_short_or_failed_attempts() -> None:
    candidate = _candidate("cand-short")
    short_attempts = phase12_registered_gate_attempts(candidate.candidate_id)[:4]

    with pytest.raises(ValidationError):
        AdversarialValidationReport(
            report_id="adv-short",
            candidate_id=candidate.candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            adversarial_status="passed_registered_gate",
            replication_status=candidate.replication_status,
            replication_scope=candidate.replication_scope,
            attempts=short_attempts,
            distinct_attempt_count=4,
            required_type_count=4,
            preregistered_count=4,
        )

    failed_attempt = phase12_registered_gate_attempts(candidate.candidate_id)[0].model_copy(
        update={"status": "failed", "failure_reason": "neutral score returned"}
    )
    failed_attempts = (failed_attempt,) + phase12_registered_gate_attempts(
        candidate.candidate_id
    )[1:]
    with pytest.raises(ValidationError):
        AdversarialValidationReport(
            report_id="adv-failed",
            candidate_id=candidate.candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            adversarial_status="passed_registered_gate",
            replication_status=candidate.replication_status,
            replication_scope=candidate.replication_scope,
            attempts=failed_attempts,
            distinct_attempt_count=12,
            required_type_count=7,
            preregistered_count=4,
        )


def test_adversarial_schema_rejects_forged_code_defined_attempts() -> None:
    candidate = _candidate("cand-forged")
    forged_attempts = tuple(
        attempt.model_copy(update={"code_defined": True, "check_id": f"fake-{index}"})
        for index, attempt in enumerate(
            phase12_registered_gate_attempts(candidate.candidate_id),
            start=1,
        )
    )

    with pytest.raises(ValidationError):
        AdversarialValidationReport(
            report_id="adv-forged",
            candidate_id=candidate.candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            adversarial_status="passed_registered_gate",
            replication_status=candidate.replication_status,
            replication_scope=candidate.replication_scope,
            attempts=forged_attempts,
            distinct_attempt_count=12,
            required_type_count=7,
            preregistered_count=12,
        )


def test_stable_candidate_registry_entry_requires_stable_status() -> None:
    with pytest.raises(ValidationError):
        StableCandidateRegistryEntry(
            candidate_id="cand-not-stable",
            hypothesis_id="hyp-not-stable",
            candidate_status="adversarial_validation",
            replication_status="passed_independent_path",
            replication_scope="compressed_observable",
            adversarial_status="passed_registered_gate",
            datasets_passed_json={"planck2018": True},
        )


def _candidate(
    candidate_id: str,
    *,
    candidate_status: str = "adversarial_validation",
    replication_status: str = "passed_independent_path",
    adversarial_status: str = "not_run",
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        hypothesis_id=f"hyp-{candidate_id}",
        concept_name=f"concept-{candidate_id}",
        wildness_level="W3",
        candidate_status=candidate_status,  # type: ignore[arg-type]
        replication_status=replication_status,  # type: ignore[arg-type]
        replication_scope="compressed_observable",
        adversarial_status=adversarial_status,  # type: ignore[arg-type]
        datasets_passed_json={"planck2018": True, "bao": True},
        metrics_json={"model_family": "lambda_cdm"},
    )
