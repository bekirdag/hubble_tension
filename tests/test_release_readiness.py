from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from hubble_tension.readiness import (
    DEFAULT_VALIDATION_COMMANDS,
    build_release_readiness_report,
    default_phase_completion_records,
    passing_validation_evidence,
)
from hubble_tension.schemas.release import (
    PhaseCompletionRecord,
    ReleaseReadinessReport,
    ValidationEvidenceRecord,
)
from hubble_tension.state import ArtifactProvenance, StateStore


def test_phase14_readiness_report_is_automated_and_non_claiming() -> None:
    report = build_release_readiness_report()

    assert report.release_phase == 14
    assert report.status == "ready"
    assert report.required_phase_count == 15
    assert report.completed_phase_count == 15
    assert report.no_human_review_required is True
    assert report.no_scientific_claim is True
    assert report.launch_command == "./hubble_tension.sh"
    assert [record.phase for record in report.phase_records] == list(range(15))
    assert report.phase_records[-1].name == "Release Readiness and Closure"
    assert report.manifest_json["automated_only"] is True
    assert report.manifest_json["scientific_claim"] is False
    assert report.required_validation_commands == DEFAULT_VALIDATION_COMMANDS
    assert report.manifest_json["required_validation_commands"] == list(
        DEFAULT_VALIDATION_COMMANDS
    )


def test_phase14_readiness_blocks_failed_evidence_or_incomplete_phase() -> None:
    phase_records = list(default_phase_completion_records())
    phase_records[10] = PhaseCompletionRecord(
        phase=10,
        name="Supported Solver and Posterior Path",
        status="blocked",
        evidence_refs=("solver bootstrap unavailable",),
    )
    evidence = (
        ValidationEvidenceRecord(
            command=".venv/bin/python -m pytest -q",
            status="failed",
            summary="fixture failure",
        ),
    )

    report = build_release_readiness_report(
        phase_records=phase_records,
        validation_evidence=evidence,
    )

    assert report.status == "blocked"
    assert report.completed_phase_count == 14
    assert any("phase 10" in blocker for blocker in report.blockers)
    assert any("pytest" in blocker for blocker in report.blockers)


def test_phase14_readiness_schema_rejects_human_review_or_scientific_claim() -> None:
    report_kwargs = _valid_ready_report_kwargs()
    with pytest.raises(ValidationError, match="human review"):
        ReleaseReadinessReport(
            **report_kwargs,
            no_human_review_required=False,
        )
    with pytest.raises(ValidationError, match="scientific solution"):
        ReleaseReadinessReport(
            **report_kwargs,
            no_scientific_claim=False,
        )


def test_phase14_readiness_schema_rejects_wrong_phase_or_missing_commands() -> None:
    report_kwargs = _valid_ready_report_kwargs()
    with pytest.raises(ValidationError):
        ReleaseReadinessReport(**report_kwargs, release_phase=cast(Any, 13))
    with pytest.raises(ValidationError, match="required validation commands"):
        ReleaseReadinessReport(
            **{
                **report_kwargs,
                "validation_evidence": passing_validation_evidence(
                    DEFAULT_VALIDATION_COMMANDS[:-1]
                ),
            }
        )


def test_phase14_readiness_persists_with_provenance(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "lab.sqlite3")
    store.initialize()
    report = build_release_readiness_report()

    store.record_release_readiness_report(report, provenance=_provenance())
    reopened = StateStore(tmp_path / "lab.sqlite3")
    rows = reopened.release_readiness_reports(status="ready")

    assert rows[0].report_id == "phase14-release-readiness"
    assert rows[0].completed_phase_count == 15
    assert rows[0].required_phase_count == 15
    assert rows[0].report_json["release_phase"] == 14
    assert rows[0].report_json["manifest_json"]["operator_surface"] == "./hubble_tension.sh"
    assert rows[0].agent_id == "codex"
    assert rows[0].agent_version_hash == "agent-version-hash"
    assert rows[0].prompt_template_id == "lab_head"
    assert rows[0].prompt_template_hash == "prompt-template-hash"


def _valid_ready_report_kwargs() -> dict[str, Any]:
    return {
        "report_id": "valid-ready",
        "status": "ready",
        "required_phase_count": 15,
        "completed_phase_count": 15,
        "phase_records": default_phase_completion_records(),
        "validation_evidence": passing_validation_evidence(),
    }


def _provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        agent_id="codex",
        agent_version_hash="agent-version-hash",
        prompt_template_id="lab_head",
        prompt_template_hash="prompt-template-hash",
    )
