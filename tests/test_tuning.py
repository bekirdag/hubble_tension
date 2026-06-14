from __future__ import annotations

from pathlib import Path

from hubble_tension.runners import (
    BacktrackingPlanner,
    BranchManager,
    EvolutionarySearch,
    GeneratorHealthTracker,
    ParameterSweeper,
    abandonment_threshold,
    branch_priority,
    generator_quarantine_route,
    mutate_formula_same_assumptions,
)
from hubble_tension.state import ArtifactProvenance, StateStore


def test_parameter_sweep_formula_mutation_and_priority_policy() -> None:
    sweep = ParameterSweeper().sweep({"alpha": (0.0, 1.0), "z": (10.0, 20.0)})
    priority = branch_priority(
        h0_relief_delta_sigma=-1.0,
        constraint_penalty=0.0,
        compute_cost=0.0,
        novelty=1.0,
    )

    assert sweep == {"alpha": 0.5, "z": 15.0}
    assert mutate_formula_same_assumptions("alpha_zoroto + z") == "min(alpha_zoroto, 1.0) + z"
    assert priority.score == 0.2
    assert priority.novelty_tiebreaker == 1.0
    assert branch_priority(
        h0_relief_delta_sigma=-5.0,
        constraint_penalty=0.0,
        compute_cost=0.0,
        novelty=1.0,
        hard_rejected=True,
    ).score == 0.0


def test_evolutionary_search_is_bounded_deterministic_and_scored() -> None:
    bounds = {"alpha": (0.0, 1.0), "z": (10.0, 20.0)}
    candidates = EvolutionarySearch().search(bounds, generations=2, population_size=3)
    repeated = EvolutionarySearch().search(bounds, generations=2, population_size=3)

    assert len(candidates) == 6
    assert candidates == repeated
    assert {candidate.strategy for candidate in candidates} == {"evolutionary_bounded"}
    assert max(candidate.score for candidate in candidates) == 1.0
    for candidate in candidates:
        assert 0.0 <= candidate.parameters["alpha"] <= 1.0
        assert 10.0 <= candidate.parameters["z"] <= 20.0


def test_backtracking_planner_uses_metric_and_rejection_evidence() -> None:
    decision = BacktrackingPlanner().plan(
        parent_hypothesis_id="hyp-parent",
        parent_checkpoint_id="checkpoint-parent",
        metric_packet_id="metric-l2-001",
        rejection_level="L2",
        metric_evidence={"delta_chi2": 14.2, "h0_delta_sigma": -0.1},
        rejection_evidence={
            "failed_observable": "bao",
            "reason": "BAO fit worsened after tuning",
        },
    )

    assert decision.parent_checkpoint_id == "checkpoint-parent"
    assert decision.failed_observable == "bao"
    assert decision.metric_packet_id == "metric-l2-001"
    assert decision.evidence_json["metric_evidence"]["delta_chi2"] == 14.2
    assert decision.evidence_json["rejection_evidence"]["reason"] == (
        "BAO fit worsened after tuning"
    )
    assert "checkpointed parent" in decision.reason


def test_abandonment_thresholds_and_generator_quarantine() -> None:
    assert abandonment_threshold("W0") == 1
    assert abandonment_threshold("W5") == 5

    health = GeneratorHealthTracker().evaluate(
        agent_id="stub",
        agent_version_hash="agent-hash",
        prompt_template_hash="prompt-hash",
        l2_passes=[False] * 100,
    )

    assert health.status == "generator_quarantine"
    assert health.rolling_l2_pass_rate == 0.0
    route = generator_quarantine_route(health)
    recovered = generator_quarantine_route(health, automated_health_gate_passed=True)
    migrated = generator_quarantine_route(health, versioned_config_migration=True)

    assert route.route == "deterministic_templates_and_calibration_replay_only"
    assert route.recovery_allowed is False
    assert recovered.route == "active_generation"
    assert recovered.status == "recovered_by_automated_health_gate"
    assert migrated.route == "active_generation"
    assert migrated.status == "cleared_by_versioned_config_migration"


def test_branch_manager_records_tuning_branch_and_abandonment(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "lab.sqlite3")
    store.initialize()
    provenance = _provenance()
    store.insert_hypothesis(
        hypothesis_id="hyp-root",
        title="Root",
        provenance=provenance,
        is_root_seed=True,
    )
    manager = BranchManager(store, provenance)

    manager.record_same_assumption_tuning(
        tuning_event_id="tune-1",
        hypothesis_id="hyp-root",
        branch_id="branch-1",
        event_json={"parameter": "alpha"},
    )
    edge_id = manager.create_branch_for_assumption_change(
        parent_hypothesis_id="hyp-root",
        child_hypothesis_id="hyp-child",
        title="Child",
        assumption_diff={"added": ["hidden_sector"]},
    )
    manager.record_abandonment(
        tuning_event_id="abandon-1",
        hypothesis_id="hyp-root",
        branch_id="branch-1",
        failed_level="L2",
        failed_observable="bao",
        lesson="BAO mismatch persisted",
    )

    failed = store.failed_branch_events()
    lessons = store.abandoned_branch_lessons(
        failed_level="L2",
        failed_observable="bao",
        lesson_query="persisted",
    )
    mismatched_lessons = store.abandoned_branch_lessons(
        failed_level="L3",
        failed_observable="bao",
        lesson_query="persisted",
    )
    with store.connect() as connection:
        edge_count = connection.execute(
            "SELECT COUNT(*) FROM hypothesis_edges WHERE edge_id = ?",
            (edge_id,),
        ).fetchone()[0]

    assert edge_count == 1
    assert failed[0].event_json["failed_level"] == "L2"
    assert failed[0].event_json["lesson"] == "BAO mismatch persisted"
    assert [record.tuning_event_id for record in lessons] == ["abandon-1"]
    assert mismatched_lessons == []


def _provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        agent_id="stub",
        agent_version_hash="agent-hash",
        prompt_template_id="lab_head",
        prompt_template_hash="prompt-hash",
    )
