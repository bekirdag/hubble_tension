from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hubble_tension.schemas import (
    AssumptionDiff,
    CandidateRecord,
    DatasetChi2,
    H0Measurement,
    H0Relief,
    LabHeadDecision,
    MetricPacket,
    RuntimeState,
)


def test_candidate_fixture_validates() -> None:
    data = json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    candidate = CandidateRecord.model_validate(data)

    assert candidate.candidate_status == "stable_internal_candidate"
    assert candidate.replication_status == "passed_independent_path"


def test_assumption_diff_requires_visible_content() -> None:
    with pytest.raises(ValidationError):
        AssumptionDiff()

    diff = AssumptionDiff(kept=["baseline"], added=["fixture"])
    assert diff.added == ["fixture"]


def test_metric_packet_completeness_reports_missing_entries() -> None:
    packet = MetricPacket(
        chi2_min_by_dataset={
            "planck2018": DatasetChi2(chi2=1.0, dof=1, n_data=1, status="ok")
        },
        best_fit_h0_by_dataset={
            "planck2018": H0Measurement(value=67.4, sigma=0.5, source="fit")
        },
        covariance_policy="owned_observables",
        h0_relief=H0Relief(
            early_late_gap_sigma_before=5.0,
            early_late_gap_sigma_after=4.8,
            delta_sigma=-0.2,
            method="summary",
        ),
        wildness_level="W0",
    )

    assert packet.validate_completeness({"planck2018"}) == []
    assert packet.validate_completeness({"planck2018", "bao"}) == [
        "missing chi2 for bao",
        "missing H0 for bao",
    ]


def test_metric_packet_blocks_display_only_unknown_covariance_gates() -> None:
    packet = MetricPacket(
        chi2_min_by_dataset={
            "planck2018": DatasetChi2(chi2=1.0, dof=1, n_data=1, status="ok")
        },
        best_fit_h0_by_dataset={
            "planck2018": H0Measurement(value=67.4, sigma=0.5, source="fit")
        },
        h0_relief=H0Relief(
            early_late_gap_sigma_before=5.0,
            early_late_gap_sigma_after=4.8,
            delta_sigma=-0.2,
            method="summary",
        ),
        wildness_level="W0",
    )

    assert packet.validate_completeness({"planck2018"}) == [
        "display-only unknown covariance cannot be used for gates"
    ]


def test_lab_head_decision_requires_agent_and_prompt_provenance() -> None:
    decision = LabHeadDecision(
        hypothesis_id="hyp-1",
        agent_id="stub",
        agent_version_hash="agent-hash",
        prompt_template_id="phase0",
        prompt_template_hash="prompt-hash",
        decision="archive",
        rationale="fixture decision",
        uncertainty="low",
        next_step="stop",
    )

    assert decision.prompt_template_hash == "prompt-hash"

    invalid_decision = {
        "hypothesis_id": "hyp-1",
        "agent_id": "stub",
        "agent_version_hash": "agent-hash",
        "prompt_template_id": "phase0",
        "decision": "archive",
        "rationale": "fixture decision",
        "uncertainty": "low",
        "next_step": "stop",
    }
    with pytest.raises(ValidationError):
        LabHeadDecision.model_validate(invalid_decision)


def test_runtime_state_phase0_bootstrap_status() -> None:
    runtime = RuntimeState(status="bootstrap_needed", updated_at="2026-06-14T00:00:00Z")

    assert runtime.status == "bootstrap_needed"


def test_runtime_state_phase1_supervisor_fields() -> None:
    runtime = RuntimeState(
        status="stopped",
        active_attempt_id="attempt-000001",
        active_branch_id="branch-000000",
        active_test_id="test-000000",
        active_run_id="run-000001",
        active_run_dir="/tmp/run-000001",
        budget_exhausted_reason="cpu_percent",
        budget_limits={"max_sustained_cpu_percent": 80},
        budget_usage={"cpu_percent": 80.1},
        bootstrap_blocker=None,
        checkpoint_count=2,
        integrations={
            "agents": "integration_pending",
            "python_dependencies": "available",
            "sandbox": "sandbox_unavailable",
        },
        log_path="/tmp/run-000001/lab.log",
        started_at="2026-06-14T00:00:00Z",
        state_path="/tmp/runtime_state.json",
        stop_requested=True,
        stop_reason="stop_file",
        updated_at="2026-06-14T00:00:00Z",
    )

    assert runtime.status == "stopped"
    assert runtime.stop_requested is True
