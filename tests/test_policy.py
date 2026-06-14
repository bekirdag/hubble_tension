from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from hubble_tension import policy
from hubble_tension.schemas.types import CandidateStatus, RuntimeStatus


def test_novelty_cannot_affect_gate_score() -> None:
    assert policy.NOVELTY_GATING_WEIGHT == 0.0
    assert policy.gate_score(data_fit_score=10.0, novelty_score=0.0) == 10.0
    assert policy.gate_score(data_fit_score=10.0, novelty_score=999999.0) == 10.0


def test_candidate_gate_requires_replication_and_adversarial_status() -> None:
    candidate = json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())

    assert policy.candidate_passed_configured_gates(candidate)
    assert policy.can_promote_to(candidate, policy.STABLE_INTERNAL_CANDIDATE)

    candidate["replication_status"] = "unreplicated_timeout"
    assert not policy.candidate_passed_configured_gates(candidate)
    assert not policy.can_promote_to(candidate, policy.STABLE_INTERNAL_CANDIDATE)

    candidate["replication_status"] = "passed_independent_path"
    candidate["replication_scope"] = "background_only"
    assert not policy.candidate_passed_configured_gates(candidate)
    assert not policy.can_promote_to(candidate, policy.STABLE_INTERNAL_CANDIDATE)


def test_scientific_status_labels_and_promotion_rules_are_executable() -> None:
    assert policy.SCREENING_ONLY_LOCAL_PRIOR in policy.CANDIDATE_STATUS_LABELS
    assert policy.STABLE_INTERNAL_CANDIDATE in policy.CANDIDATE_STATUS_LABELS
    assert policy.status_label(policy.STABLE_INTERNAL_CANDIDATE) == "Stable internal candidate"

    requirements = policy.promotion_requirements_for(policy.STABLE_INTERNAL_CANDIDATE)
    assert "replication_status:passed_independent_path" in requirements
    assert "replication_scope:compressed_observable_or_full_supported_family" in requirements
    assert "adversarial_status:passed_registered_gate" in requirements
    assert policy.promotion_requirements_for("not_a_status") == ()


def test_policy_status_labels_match_schema_literals() -> None:
    assert set(policy.CANDIDATE_STATUS_LABELS) == set(get_args(CandidateStatus))
    assert set(policy.RUNTIME_STATUS_LABELS) == set(get_args(RuntimeStatus))


def test_stable_banner_is_not_a_scientific_claim() -> None:
    candidate = json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    banner = policy.StableCandidateBanner.render(candidate)

    assert "CANDIDATE PASSED ALL CONFIGURED GATES" in banner
    assert policy.NON_CLAIM_TEXT in banner
    assert "HUBBLE TENSION SOLUTION FOUND" not in banner
    assert "passed_independent_path" in banner
    assert "passed_registered_gate" in banner


def test_stable_banner_for_unreplicated_timeout_does_not_render_passed_gate() -> None:
    candidate = json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    candidate["replication_status"] = "unreplicated_timeout"
    banner = policy.StableCandidateBanner.render(candidate)

    assert policy.NOT_PASSED_CONFIGURED_GATES_TEXT in banner
    assert policy.CONFIGURED_GATES_TEXT not in banner
    assert "Replication: unreplicated_timeout" in banner
    assert "Replication: passed_independent_path" not in banner


def test_generated_code_path_allowlist() -> None:
    assert policy.is_allowed_generated_code_path("src/hubble_tension/generated_models/foo.py")
    assert policy.is_allowed_generated_code_path("experiments/runs/run-1/model.py")
    assert not policy.is_allowed_generated_code_path("src/hubble_tension/policy.py")
    assert not policy.is_allowed_generated_code_path("README.md")


def test_policy_contains_no_required_human_gate() -> None:
    assert "human_approval_required" in policy.PROHIBITED_REVIEW_GATES
    assert "manual_review_required" in policy.PROHIBITED_REVIEW_GATES


def test_core_state_transitions_do_not_request_human_approval() -> None:
    labels = set(policy.CORE_STATE_TRANSITIONS)
    for targets in policy.CORE_STATE_TRANSITIONS.values():
        labels.update(targets)

    for label in labels:
        assert "human" not in label
        assert "manual" not in label
        assert "approval" not in label

    for prohibited in policy.PROHIBITED_REVIEW_GATES:
        assert prohibited not in labels
