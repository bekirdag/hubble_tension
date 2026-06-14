from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import BaseModel

import hubble_tension.schemas as schemas
from hubble_tension.adversarial import (
    evaluate_adversarial_gate,
    phase12_registered_gate_attempts,
)
from hubble_tension.compressed_obs import PLANCK2018_CMB_REFERENCE, compare_cmb_perturbations
from hubble_tension.operations import (
    automated_transition_decision,
    build_report_index_entry,
    propose_external_transition,
    rerun_request_from_transition,
)
from hubble_tension.replication import IndependentReplicationReviewer
from hubble_tension.schemas import StableCandidateRegistryEntry
from hubble_tension.schemas.candidates import CandidateRecord
from hubble_tension.schemas.operations import (
    DatasetBacklogItem,
    ExternalEvidenceRecord,
    MaintenanceJobResult,
    OperatorDigest,
    ScaleOutProfile,
)
from hubble_tension.state import (
    CORE_TABLES,
    GENERATED_ARTIFACT_TABLES,
    PROMPT_TEMPLATE_IDS,
    STORAGE_COVERAGE_BY_MODEL,
    ArtifactProvenance,
    StateStore,
    prompt_template_hash,
    prompt_template_path,
)


def test_migrations_create_phase2_core_tables(tmp_path: Path) -> None:
    store = _store(tmp_path)

    tables = store.table_names()

    assert set(CORE_TABLES) <= tables
    assert "metric_packets" in tables
    assert "replication_queue" in tables
    assert "replication_reports" in tables
    assert "adversarial_queue" in tables
    assert "adversarial_reports" in tables
    assert "stable_candidate_registry" in tables
    assert "schema_migrations" in tables


def test_generated_artifact_tables_require_provenance_columns(tmp_path: Path) -> None:
    store = _store(tmp_path)
    required_columns = {
        "agent_id",
        "agent_version_hash",
        "prompt_template_id",
        "prompt_template_hash",
    }

    for table_name in GENERATED_ARTIFACT_TABLES:
        columns = store.table_columns(table_name)
        assert required_columns <= set(columns)
        for column_name in required_columns:
            assert columns[column_name]["notnull"] == 1


def test_generated_artifact_insert_missing_provenance_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with store.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO lab_notes(note_id, note_type, content, created_at)
                VALUES ('note-missing-provenance', 'lab_note', 'missing provenance', 'now')
                """
            )


def test_hypothesis_requires_parent_or_root_seed(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(sqlite3.IntegrityError):
        store.insert_hypothesis(
            hypothesis_id="hyp-bad",
            title="Missing parent",
            provenance=_provenance(),
            is_root_seed=False,
        )

    store.insert_hypothesis(
        hypothesis_id="hyp-root",
        title="Root hypothesis",
        provenance=_provenance(),
        is_root_seed=True,
    )
    store.insert_hypothesis(
        hypothesis_id="hyp-child",
        title="Child hypothesis",
        provenance=_provenance(),
        is_root_seed=False,
        parent_hypothesis_id="hyp-root",
    )


def test_state_transition_records_event_checkpoint_and_reopens(tmp_path: Path) -> None:
    store = _store(tmp_path)
    state = {
        "active_attempt_id": "attempt-1",
        "active_branch_id": "branch-1",
        "active_run_id": "run-1",
        "status": "running",
    }

    checkpoint_id = store.record_state_transition(
        status="running",
        reason="fresh_start",
        state=state,
        attempt_id="attempt-1",
        branch_id="branch-1",
        run_id="run-1",
    )
    reopened = StateStore(tmp_path / "lab.sqlite3")

    assert checkpoint_id is not None
    assert reopened.restore_latest_checkpoint() == state
    with reopened.connect() as connection:
        event_count = connection.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
        checkpoint_count = connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        runtime_status = connection.execute(
            "SELECT status FROM runtime_state WHERE state_key = 'default'"
        ).fetchone()[0]
        attempt_status = connection.execute(
            "SELECT status FROM attempts WHERE attempt_id = 'attempt-1'"
        ).fetchone()[0]
        run_row = connection.execute(
            "SELECT attempt_id, status FROM runs WHERE run_id = 'run-1'"
        ).fetchone()
    assert event_count == 1
    assert checkpoint_count == 1
    assert runtime_status == "running"
    assert attempt_status == "running"
    assert tuple(run_row) == ("attempt-1", "running")


def test_lab_notebook_append_safe_reopens(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append_lab_note(
        note_id="note-1",
        content="first observation",
        provenance=_provenance(),
    )
    store.append_lab_note(
        note_id="note-2",
        content="second observation",
        provenance=_provenance(),
    )

    reopened = StateStore(tmp_path / "lab.sqlite3")
    notes = reopened.list_lab_notes()

    assert [str(row["content"]) for row in notes] == [
        "first observation",
        "second observation",
    ]


def test_failed_branch_tuning_events_are_queryable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_hypothesis(
        hypothesis_id="hyp-root",
        title="Root hypothesis",
        provenance=_provenance(),
        is_root_seed=True,
    )
    store.record_tuning_event(
        tuning_event_id="tune-continue",
        hypothesis_id="hyp-root",
        branch_id="branch-continue",
        decision="continue",
        event_json={"score": 0.5},
        provenance=_provenance(),
    )
    store.record_tuning_event(
        tuning_event_id="tune-failed",
        hypothesis_id="hyp-root",
        branch_id="branch-failed",
        decision="branch_failed",
        event_json={"reason": "constraint regression"},
        provenance=_provenance(),
    )

    failed = store.failed_branch_events()

    assert len(failed) == 1
    assert failed[0].tuning_event_id == "tune-failed"
    assert failed[0].branch_id == "branch-failed"
    assert failed[0].decision == "branch_failed"
    assert failed[0].event_json == {"reason": "constraint regression"}


def test_report_registry_queries_by_hypothesis_candidate_external_status(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)

    store.register_report(
        report_id="report-1",
        hypothesis_id="hyp-1",
        candidate_id="cand-1",
        report_path="reports/cand-1.md",
        external_status="not_submitted",
        title="Candidate report",
        provenance=_provenance(),
    )

    assert store.reports_by_hypothesis("hyp-1")[0].report_path == "reports/cand-1.md"
    assert store.reports_by_candidate("cand-1")[0].report_id == "report-1"
    assert store.reports_by_external_status("not_submitted")[0].title == "Candidate report"


def test_candidate_banner_fields_are_available(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = CandidateRecord.model_validate(
        json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    )

    store.insert_candidate(candidate)

    fields = store.candidate_banner_fields("cand-000001")
    assert fields is not None
    assert fields["candidate_id"] == "cand-000001"
    assert fields["concept_name"] == "phase0-fixture"
    assert fields["candidate_status"] == "stable_internal_candidate"
    assert fields["replication_status"] == "passed_independent_path"
    assert fields["replication_scope"] == "compressed_observable"
    assert fields["adversarial_status"] == "passed_registered_gate"
    assert fields["datasets_passed_json"] == {"planck2018": True, "bao": True}


def test_replication_queue_and_reports_reopen(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = CandidateRecord.model_validate(
        json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    )
    cmb_report = compare_cmb_perturbations(
        {name: row.value for name, row in PLANCK2018_CMB_REFERENCE.items()}
    )
    report = IndependentReplicationReviewer().evaluate(
        candidate,
        model_family="lambda_cdm",
        cmb_report=cmb_report,
    )

    store.enqueue_replication(
        queue_id="queue-cand-000001",
        candidate_id=candidate.candidate_id,
        hypothesis_id=candidate.hypothesis_id,
        model_family="lambda_cdm",
        priority=10,
        reason="fixture candidate requires independent replay",
    )
    store.record_replication_report(report, provenance=_provenance())

    reopened = StateStore(tmp_path / "lab.sqlite3")
    queue = reopened.replication_queue(status="queued")
    reports = reopened.replication_reports_by_candidate(candidate.candidate_id)

    assert queue[0].candidate_id == candidate.candidate_id
    assert queue[0].model_family == "lambda_cdm"
    assert reports[0].replication_status == "passed_independent_path"
    assert reports[0].replication_scope == "compressed_observable"
    assert reports[0].blocks_stable_candidate is False
    assert reports[0].reference_checks_json["checks"][0]["observable_set"] == "cmb_perturbations"


def test_adversarial_queue_reports_and_stable_registry_reopen(tmp_path: Path) -> None:
    store = _store(tmp_path)
    candidate = CandidateRecord.model_validate(
        json.loads(Path("tests/fixtures/fake_stable_candidate.json").read_text())
    )
    report = evaluate_adversarial_gate(
        candidate,
        report_id="adv-report-cand-000001",
        attempts=phase12_registered_gate_attempts(candidate.candidate_id),
        negative_evidence_json={"failed_refutations": []},
        dataset_statuses_json={"planck2018": "passed", "bao": "passed"},
        metadata_json={"external_prior_art_search": "not_submitted"},
    )

    store.enqueue_adversarial(
        queue_id="adv-cand-000001",
        candidate_id=candidate.candidate_id,
        hypothesis_id=candidate.hypothesis_id,
        priority=10,
        reason="fixture candidate requires registered refutation checks",
    )
    store.register_adversarial_candidate_report(
        report,
        report_path="reports/cand-000001-adversarial.md",
        title="Adversarial candidate report",
        provenance=_provenance(),
    )
    store.register_stable_candidate(
        StableCandidateRegistryEntry(
            candidate_id=candidate.candidate_id,
            hypothesis_id=candidate.hypothesis_id,
            candidate_status=candidate.candidate_status,
            replication_status=candidate.replication_status,
            replication_scope=candidate.replication_scope,
            adversarial_status=report.adversarial_status,
            datasets_passed_json=candidate.datasets_passed_json,
            report_path=candidate.report_path,
            external_status="not_submitted",
            registry_json={"report_id": report.report_id},
        ),
        provenance=_provenance(),
    )

    reopened = StateStore(tmp_path / "lab.sqlite3")
    queue = reopened.adversarial_queue(status="queued")
    reports = reopened.adversarial_reports_by_candidate(candidate.candidate_id)
    candidate_reports = reopened.reports_by_candidate(candidate.candidate_id)
    stable = reopened.stable_candidate_by_id(candidate.candidate_id)

    assert queue[0].candidate_id == candidate.candidate_id
    assert reports[0].adversarial_status == "passed_registered_gate"
    assert reports[0].distinct_attempt_count == 12
    assert reports[0].required_type_count >= 5
    assert reports[0].preregistered_count >= 4
    assert reports[0].attempts_json["attempts"][0]["check_id"] == "StricterToleranceRerun"
    assert candidate_reports[0].report_path == "reports/cand-000001-adversarial.md"
    assert candidate_reports[0].external_status == "not_submitted"
    assert candidate_reports[0].metadata_json["replication_status"] == "passed_independent_path"
    assert candidate_reports[0].metadata_json["replication_scope"] == "compressed_observable"
    assert candidate_reports[0].metadata_json["adversarial_status"] == "passed_registered_gate"
    assert candidate_reports[0].metadata_json["dataset_statuses_json"] == {
        "bao": "passed",
        "planck2018": "passed",
    }
    assert candidate_reports[0].metadata_json["negative_evidence_json"] == {
        "failed_refutations": []
    }
    assert stable is not None
    assert stable.candidate_id == candidate.candidate_id
    assert stable.adversarial_status == "passed_registered_gate"


def test_phase13_operations_records_reopen_and_update_report_status(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    assert {
        "pending_external_transitions",
        "external_rerun_queue",
        "report_search_index",
        "dataset_backlog",
        "maintenance_jobs",
        "scale_out_profiles",
    } <= store.table_names()
    store.register_report(
        report_id="report-phase13",
        hypothesis_id="hyp-phase13",
        candidate_id="cand-phase13",
        report_path="reports/cand-phase13.md",
        external_status="unchecked",
        title="Phase 13 candidate report",
        provenance=_provenance(),
        metadata={
            "concept": "zoroto",
            "dataset_statuses": {"bao": "failed", "planck2018": "passed"},
        },
    )
    evidence = ExternalEvidenceRecord(
        evidence_id="evidence-refutes-zoroto",
        relation="refutes",
        source_title="Mocked external refutation",
        summary="The mocked literature record constrains the required H0 observable.",
        source_url="https://example.test/refutes-zoroto",
        observable="H0",
    )
    proposal = propose_external_transition(
        report_id="report-phase13",
        current_external_status="unchecked",
        evidence=[evidence],
        confidence=0.95,
        reason="mocked literature watcher found an explicit refutation",
        candidate_id="cand-phase13",
        hypothesis_id="hyp-phase13",
    )
    store.record_external_transition_proposal(proposal, provenance=_provenance())
    decided = store.decide_external_transition(
        proposal.proposal_id,
        decision="accepted",
        decision_reason="automated evidence rule accepted cited refutation",
    )
    rerun_request = rerun_request_from_transition(automated_transition_decision(proposal))
    assert rerun_request is not None
    store.record_external_rerun_request(rerun_request, provenance=_provenance())
    updated_report = store.report_by_id("report-phase13")
    assert updated_report is not None
    store.upsert_report_index_entry(
        build_report_index_entry(updated_report),
        provenance=_provenance(),
    )
    backlog_item = DatasetBacklogItem(
        backlog_id="backlog-report-phase13-bao",
        dataset_id="bao",
        reason="BAO failed the latest report and needs integration follow-up",
        source_kind="failed_screen",
        source_ref="report-phase13",
        priority=10,
        metadata_json={"dataset_status": "failed"},
    )
    store.record_dataset_backlog_item(backlog_item, provenance=_provenance())
    digest = OperatorDigest(
        digest_id="digest-phase13",
        digest_type="periodic_operations",
        content="reports=1; external_transitions=1; accepted_transitions=1; dataset_backlog=1",
        report_count=1,
        transition_count=1,
        backlog_count=1,
    )
    store.record_operator_digest(digest, provenance=_provenance())
    maintenance = MaintenanceJobResult(
        job_id="maintenance-phase13",
        job_type="stale_scratch_cleanup",
        status="completed",
        summary="removed scratch while preserving audit records",
        preserved_audit_records=4,
        removed_paths=("scratch/old.tmp",),
        artifacts_json={"dry_run": False},
    )
    store.record_maintenance_job(maintenance, provenance=_provenance())
    scale_out = ScaleOutProfile(
        profile_id="grid-phase13",
        enabled=True,
        worker_count=8,
        allowed_job_types=("sweep", "posterior", "replication", "adversarial"),
    )
    store.record_scale_out_profile(scale_out, provenance=_provenance())

    reopened = StateStore(tmp_path / "lab.sqlite3")
    reopened_report = reopened.report_by_id("report-phase13")

    assert decided.decision == "accepted"
    assert decided.target_external_status == "externally_refuted"
    assert reopened_report is not None
    assert reopened_report.external_status == "externally_refuted"
    assert reopened.external_transition_proposals(decision="accepted")[0].evidence_json[
        "evidence"
    ][0]["relation"] == "refutes"
    assert reopened.external_rerun_requests(status="queued")[0].evidence_ids_json == {
        "evidence_ids": ["evidence-refutes-zoroto"]
    }
    assert reopened.search_report_index("zoroto externally_refuted")[0].report_id == (
        "report-phase13"
    )
    assert reopened.dataset_backlog(status="queued")[0].dataset_id == "bao"
    assert "accepted_transitions=1" in reopened.operator_digests()[0].content
    assert reopened.maintenance_jobs(status="completed")[0].removed_paths_json == {
        "paths": ["scratch/old.tmp"]
    }
    assert reopened.scale_out_profiles()[0].profile_json["preserves_adversarial_gates"] is True


def test_schema_contract_covers_pydantic_models_and_tables(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tables = store.table_names()
    model_names = {
        name
        for name in schemas.__all__
        if inspect.isclass(getattr(schemas, name))
        and issubclass(getattr(schemas, name), BaseModel)
    }

    assert model_names <= set(STORAGE_COVERAGE_BY_MODEL)
    for coverage in STORAGE_COVERAGE_BY_MODEL.values():
        if coverage.table_name is None:
            assert coverage.non_persistent_reason
        else:
            assert coverage.table_name in tables


def test_prompt_templates_have_stable_hashes() -> None:
    prompt_dir = Path("prompts")

    for template_id in PROMPT_TEMPLATE_IDS:
        path = prompt_template_path(prompt_dir, template_id)
        digest = prompt_template_hash(prompt_dir, template_id)

        assert path.exists()
        assert len(digest) == 64
        int(digest, 16)


def _store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path / "lab.sqlite3")
    store.initialize()
    return store


def _provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        agent_id="codex",
        agent_version_hash="agent-version-hash",
        prompt_template_id="lab_head",
        prompt_template_hash="prompt-template-hash",
    )
