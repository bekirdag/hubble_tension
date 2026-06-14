from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hubble_tension.operations import (
    automated_transition_decision,
    build_operator_digest,
    build_report_index_entry,
    build_report_regeneration_result,
    cleanup_stale_scratch,
    compact_state_storage,
    dataset_backlog_from_statuses,
    default_scale_out_profile,
    infer_external_status,
    monitor_external_status_for_reports,
    propose_external_transition,
    rerun_request_from_transition,
    search_report_entries,
)
from hubble_tension.schemas.operations import (
    ExternalEvidenceRecord,
    ExternalTransitionProposal,
    OperatorDigest,
    ScaleOutProfile,
)
from hubble_tension.state import ReportRecord


@pytest.mark.parametrize(
    ("relation", "expected_status"),
    [
        ("refutes", "externally_refuted"),
        ("constrains", "externally_refuted"),
        ("contradicts_required_observable", "externally_refuted"),
        ("independent_support", "externally_supported"),
        ("reproduces_prediction", "externally_supported"),
        ("superseding_dataset", "superseded"),
        ("superseding_likelihood", "superseded"),
    ],
)
def test_external_status_rules_from_mocked_literature_records(
    relation: str,
    expected_status: str,
) -> None:
    evidence = _evidence(relation=relation)

    proposal = propose_external_transition(
        report_id="report-candidate-1",
        current_external_status="unchecked",
        evidence=[evidence],
        confidence=0.9,
        reason="mock literature watcher found a cited status change",
        candidate_id="cand-1",
        hypothesis_id="hyp-1",
    )
    decided = automated_transition_decision(proposal)

    assert infer_external_status([evidence]) == expected_status
    assert proposal.target_external_status == expected_status
    assert decided.decision == "accepted"
    assert decided.rerun_required is True


def test_external_transition_proposals_require_cited_evidence() -> None:
    with pytest.raises(ValidationError):
        ExternalTransitionProposal(
            proposal_id="proposal-bad",
            report_id="report-1",
            target_external_status="externally_refuted",
            confidence=0.8,
            reason="missing cited constraint evidence",
        )

    with pytest.raises(ValidationError):
        ExternalEvidenceRecord(
            evidence_id="evidence-unresolved",
            relation="context",
            source_title="Unresolved source",
            summary="No resolvable paper, arXiv id, or URL.",
        )


def test_unchecked_and_low_confidence_external_transition_decisions() -> None:
    unchecked = propose_external_transition(report_id="report-1", confidence=0.0)
    accepted_unchecked = automated_transition_decision(unchecked)

    low_confidence = propose_external_transition(
        report_id="report-2",
        evidence=[_evidence(relation="independent_support")],
        confidence=0.1,
    )
    rejected = automated_transition_decision(low_confidence, min_confidence=0.5)

    assert accepted_unchecked.decision == "accepted"
    assert accepted_unchecked.rerun_required is False
    assert rejected.decision == "rejected"
    assert rejected.rerun_required is False


def test_external_status_monitor_batches_cited_report_changes() -> None:
    reports = (
        _report(
            report_id="report-1",
            candidate_id="cand-zoroto",
            external_status="unchecked",
        ),
        _report(
            report_id="report-2",
            candidate_id="cand-stable",
            external_status="externally_refuted",
        ),
        _report(
            report_id="report-3",
            candidate_id="cand-quiet",
            external_status="unchecked",
        ),
    )
    evidence_by_report_id = {
        "report-1": (_evidence(relation="superseding_likelihood"),),
        "report-2": (_evidence(relation="refutes"),),
    }

    proposals = monitor_external_status_for_reports(reports, evidence_by_report_id)

    assert [proposal.report_id for proposal in proposals] == ["report-1"]
    assert proposals[0].target_external_status == "superseded"
    assert proposals[0].current_external_status == "unchecked"
    assert proposals[0].candidate_id == "cand-zoroto"


def test_accepted_external_transition_creates_rerun_request() -> None:
    decided = automated_transition_decision(
        propose_external_transition(
            report_id="report-1",
            evidence=[_evidence(relation="independent_support")],
            confidence=0.9,
            candidate_id="cand-1",
            hypothesis_id="hyp-1",
        )
    )
    rejected = automated_transition_decision(
        propose_external_transition(
            report_id="report-2",
            evidence=[_evidence(relation="refutes")],
            confidence=0.1,
        )
    )

    request = rerun_request_from_transition(decided)

    assert request is not None
    assert request.report_id == "report-1"
    assert request.candidate_id == "cand-1"
    assert request.status == "queued"
    assert request.evidence_ids == ("evidence-independent_support",)
    assert rerun_request_from_transition(rejected) is None


def test_digest_generation_never_requires_operator_acknowledgement() -> None:
    report = _report(
        report_id="report-1",
        candidate_id="cand-1",
        metadata_json={"dataset_statuses": {"bao": "passed"}},
    )
    transition = automated_transition_decision(
        propose_external_transition(
            report_id=report.report_id,
            evidence=[_evidence(relation="superseding_dataset")],
            confidence=0.9,
        )
    )
    backlog = dataset_backlog_from_statuses(
        source_ref=report.report_id,
        dataset_statuses={"new-likelihood": "inconclusive"},
    )

    digest = build_operator_digest(
        digest_id="digest-1",
        reports=[report],
        transitions=[transition],
        backlog=backlog,
    )

    assert digest.requires_acknowledgement is False
    assert "reports=1" in digest.content
    assert "accepted_transitions=1" in digest.content
    with pytest.raises(ValidationError):
        OperatorDigest(
            digest_id="bad-digest",
            digest_type="periodic_operations",
            content="bad",
            report_count=0,
            transition_count=0,
            backlog_count=0,
            requires_acknowledgement=True,
        )


def test_report_index_search_finds_status_hypothesis_dataset_and_candidate_terms() -> None:
    entries = (
        build_report_index_entry(
            _report(
                report_id="report-1",
                candidate_id="cand-zoroto",
                hypothesis_id="hyp-zoroto",
                external_status="externally_refuted",
                metadata_json={
                    "dataset_statuses": {"bao": "failed"},
                    "failure": "growth_constraint_regression",
                    "paper_ids": ["paper-042"],
                    "branch_id": "branch-zoroto-7",
                },
            )
        ),
        build_report_index_entry(
            _report(
                report_id="report-2",
                candidate_id="cand-mirror",
                hypothesis_id="hyp-mirror",
                metadata_json={"dataset_statuses": {"planck": "passed"}},
            )
        ),
    )

    results = search_report_entries(
        entries,
        "zoroto externally_refuted bao paper-042 branch-zoroto-7 growth_constraint",
    )

    assert [entry.report_id for entry in results] == ["report-1"]


def test_dataset_backlog_is_driven_by_failed_or_inconclusive_screens() -> None:
    backlog = dataset_backlog_from_statuses(
        source_ref="report-1",
        dataset_statuses={
            "bao": "failed_l2_constraint",
            "pantheon": "inconclusive_posterior",
            "planck": "passed",
        },
    )

    assert [item.dataset_id for item in backlog] == ["bao", "pantheon"]
    assert backlog[0].source_kind == "failed_screen"
    assert backlog[0].priority < backlog[1].priority
    assert backlog[1].source_kind == "inconclusive_screen"


def test_scale_out_profile_preserves_all_automated_gates() -> None:
    profile = default_scale_out_profile(enabled=True, worker_count=4)

    assert profile.enabled is True
    assert profile.worker_count == 4
    assert set(profile.allowed_job_types) == {
        "sweep",
        "posterior",
        "replication",
        "adversarial",
    }
    with pytest.raises(ValidationError):
        ScaleOutProfile(
            profile_id="bad-workers",
            enabled=True,
            worker_count=0,
        )
    with pytest.raises(ValidationError):
        ScaleOutProfile(
            profile_id="bad-gate",
            enabled=True,
            worker_count=2,
            allowed_job_types=("gate_override",),
        )
    with pytest.raises(ValidationError):
        ScaleOutProfile(
            profile_id="bad-provenance",
            enabled=True,
            worker_count=2,
            preserves_provenance=False,
        )


def test_storage_cleanup_removes_stale_scratch_and_preserves_audit_records(
    tmp_path: Path,
) -> None:
    for audit_name in ("lab_state.sqlite3", "runtime_state.json", "stable_candidate.json"):
        (tmp_path / audit_name).write_text("audit", encoding="utf-8")
    for audit_dir in ("checkpoints", "reports", "runs"):
        (tmp_path / audit_dir).mkdir()
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "old.tmp").write_text("stale", encoding="utf-8")
    (tmp_path / "tmp").write_text("stale", encoding="utf-8")
    (tmp_path / "keep").mkdir()

    result = cleanup_stale_scratch(tmp_path)

    assert result.status == "completed"
    assert result.preserved_audit_records == 6
    assert not (tmp_path / "scratch").exists()
    assert not (tmp_path / "tmp").exists()
    assert (tmp_path / "reports").exists()
    assert (tmp_path / "keep").exists()


def test_storage_compaction_and_report_regeneration_maintenance_jobs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "lab.sqlite3"
    import sqlite3

    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE audit_record(id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO audit_record(id) VALUES ('audit-1')")

    compaction = compact_state_storage(db_path)
    regeneration = build_report_regeneration_result(["report-b", "report-a"])

    assert compaction.job_type == "storage_compaction"
    assert compaction.status == "completed"
    assert compaction.preserved_audit_records == 1
    assert regeneration.job_type == "report_regeneration"
    assert regeneration.artifacts_json["report_ids"] == ["report-a", "report-b"]
    assert regeneration.preserved_audit_records == 2


def _evidence(relation: str) -> ExternalEvidenceRecord:
    return ExternalEvidenceRecord(
        evidence_id=f"evidence-{relation}",
        relation=relation,  # type: ignore[arg-type]
        source_title=f"Mocked literature record for {relation}",
        summary=f"Mocked source says this record {relation} the candidate.",
        source_url=f"https://example.test/{relation}",
        observable="H0",
    )


def _report(
    *,
    report_id: str,
    candidate_id: str,
    hypothesis_id: str = "hyp-1",
    external_status: str = "unchecked",
    metadata_json: dict[str, object] | None = None,
) -> ReportRecord:
    return ReportRecord(
        report_id=report_id,
        hypothesis_id=hypothesis_id,
        candidate_id=candidate_id,
        report_path=f"reports/{report_id}.md",
        external_status=external_status,
        title=f"Candidate report {candidate_id}",
        metadata_json=dict(metadata_json or {}),
    )
