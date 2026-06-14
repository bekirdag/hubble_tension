from __future__ import annotations

from pathlib import Path

from hubble_tension.compressed_obs import (
    HYREC2_RECOMBINATION_REFERENCE,
    PLANCK2018_CMB_REFERENCE,
    compare_cmb_perturbations,
    compare_recombination_history,
)
from hubble_tension.replication import (
    FIRST_EDE_REPLICATION_BENCHMARK_ID,
    INDEPENDENT_FIXTURE_SET_ID,
    INDEPENDENT_PARSER_ID,
    INDEPENDENT_REVIEWER_ID,
    LAMBDA_CDM_REPLICATION_BENCHMARK_ID,
    IndependentReplicationReviewer,
    benchmark_replication_coverage_for,
    build_replication_queue,
    independent_implementation_for,
)
from hubble_tension.schemas.candidates import CandidateRecord
from hubble_tension.schemas.types import CandidateStatus, ReplicationStatus


def test_replication_queue_selects_promising_unreplicated_candidates() -> None:
    queued = build_replication_queue(
        [
            _candidate("cand-promising", "promising_internal", "not_run"),
            _candidate(
                "cand-adversarial",
                "adversarial_validation",
                "failed_independent_path",
            ),
            _candidate(
                "cand-replicated",
                "promising_internal",
                "passed_independent_path",
            ),
        ]
    )

    assert [item.candidate_id for item in queued] == ["cand-adversarial", "cand-promising"]
    assert queued[0].priority < queued[1].priority


def test_independent_implementation_uses_separate_code_parser_and_fixtures() -> None:
    implementation = independent_implementation_for(_candidate("cand-1"))

    assert implementation.uses_shared_generated_model_code is False
    assert implementation.parser_id == INDEPENDENT_PARSER_ID
    assert implementation.fixture_set_id == INDEPENDENT_FIXTURE_SET_ID
    assert implementation.reviewer_id == INDEPENDENT_REVIEWER_ID
    assert Path(implementation.generated_code_path).parts[:2] == ("experiments", "replication")


def test_lambda_cdm_and_first_ede_benchmarks_have_replication_coverage() -> None:
    reviewer = IndependentReplicationReviewer()
    cmb_report = compare_cmb_perturbations(
        {name: row.value for name, row in PLANCK2018_CMB_REFERENCE.items()}
    )
    expectations = {
        "lambda_cdm": LAMBDA_CDM_REPLICATION_BENCHMARK_ID,
        "early_dark_energy": FIRST_EDE_REPLICATION_BENCHMARK_ID,
    }

    for model_family, benchmark_id in expectations.items():
        report = reviewer.evaluate(
            _candidate(f"cand-{model_family}"),
            model_family=model_family,
            cmb_report=cmb_report,
        )

        assert benchmark_replication_coverage_for(model_family) == benchmark_id
        assert report.replication_status == "passed_independent_path"
        assert report.replication_scope == "compressed_observable"
        assert report.metadata_json["benchmark_id"] == benchmark_id
        assert report.metadata_json["replication_coverage"] == (
            "phase11_independent_compressed_observable"
        )
        assert report.metadata_json["reviewer_id"] == INDEPENDENT_REVIEWER_ID


def test_cmb_family_requires_compressed_observable_report() -> None:
    candidate = _candidate("cand-cmb")
    reviewer = IndependentReplicationReviewer()
    missing = reviewer.evaluate(candidate, model_family="early_dark_energy")

    assert missing.replication_status == "failed_independent_path"
    assert missing.replication_scope == "not_recorded"
    assert missing.blocks_stable_candidate is True
    assert missing.route_on_failure == "backtrack_or_abandon"

    cmb_report = compare_cmb_perturbations(
        {name: row.value for name, row in PLANCK2018_CMB_REFERENCE.items()}
    )
    passed = reviewer.evaluate(
        candidate,
        model_family="early_dark_energy",
        cmb_report=cmb_report,
    )

    assert passed.replication_status == "passed_independent_path"
    assert passed.replication_scope == "compressed_observable"
    assert passed.blocks_stable_candidate is False


def test_recombination_family_requires_recombination_reference_report() -> None:
    candidate = _candidate("cand-rec")
    reviewer = IndependentReplicationReviewer()
    recombination_report = compare_recombination_history(
        {name: row.value for name, row in HYREC2_RECOMBINATION_REFERENCE.items()}
    )

    passed = reviewer.evaluate(
        candidate,
        model_family="recombination_history",
        recombination_report=recombination_report,
    )

    assert passed.replication_status == "passed_independent_path"
    assert passed.replication_scope == "compressed_observable"
    assert passed.reference_checks[0].observable_set == "recombination_history"


def test_background_only_replication_cannot_support_stable_candidate() -> None:
    report = IndependentReplicationReviewer().evaluate(
        _candidate("cand-background"),
        model_family="phenomenological_background",
    )

    assert report.replication_status == "passed_independent_path"
    assert report.replication_scope == "background_only"
    assert report.blocks_stable_candidate is True


def test_replication_timeout_is_not_a_pass() -> None:
    report = IndependentReplicationReviewer().evaluate(
        _candidate("cand-timeout"),
        model_family="lambda_cdm",
        timed_out=True,
    )

    assert report.replication_status == "unreplicated_timeout"
    assert report.replication_scope == "not_recorded"
    assert report.blocks_stable_candidate is True
    assert "future_compute" in report.route_on_failure


def _candidate(
    candidate_id: str,
    candidate_status: CandidateStatus = "promising_internal",
    replication_status: ReplicationStatus = "not_run",
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        hypothesis_id=f"hyp-{candidate_id}",
        concept_name=f"concept-{candidate_id}",
        wildness_level="W3",
        candidate_status=candidate_status,
        replication_status=replication_status,
        replication_scope="not_recorded",
        adversarial_status="not_run",
        datasets_passed_json={"planck2018": True},
        metrics_json={"model_family": "lambda_cdm"},
    )
