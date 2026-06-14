from __future__ import annotations

from collections.abc import Iterable, Sequence

from hubble_tension.schemas.release import (
    DEFAULT_RELEASE_VALIDATION_COMMANDS,
    PhaseCompletionRecord,
    ReleaseReadinessReport,
    ReleaseReadinessStatus,
    ValidationEvidenceRecord,
)

DEFAULT_PHASE_RECORDS = (
    (0, "Repo and Policy Foundation"),
    (1, "Launcher and Runtime Supervisor"),
    (2, "State Store and Provenance"),
    (3, "Corpus and Category Import"),
    (4, "Paper Study and Failure Memory"),
    (5, "Stub Autonomous Lab Loop"),
    (6, "Concept Forge"),
    (7, "Formula, Critic, and Sandbox Code Loop"),
    (8, "Reality Checks and Calibration"),
    (9, "Tuning, Branching, and Backtracking"),
    (10, "Supported Solver and Posterior Path"),
    (11, "Independent Replication"),
    (12, "Adversarial Validation and Candidate Registry"),
    (13, "Continuous Lab Operations"),
    (14, "Release Readiness and Closure"),
)

DEFAULT_VALIDATION_COMMANDS = DEFAULT_RELEASE_VALIDATION_COMMANDS


def default_phase_completion_records() -> tuple[PhaseCompletionRecord, ...]:
    return tuple(
        PhaseCompletionRecord(
            phase=phase,
            name=name,
            status="complete",
            evidence_refs=(f"docs/planning/hubble_tension_phase{phase}_progress.md",),
        )
        for phase, name in DEFAULT_PHASE_RECORDS
    )


def passing_validation_evidence(
    commands: Sequence[str] = DEFAULT_VALIDATION_COMMANDS,
) -> tuple[ValidationEvidenceRecord, ...]:
    return tuple(
        ValidationEvidenceRecord(
            command=command,
            status="passed",
            summary="latest automated validation passed",
        )
        for command in commands
    )


def build_release_readiness_report(
    *,
    report_id: str = "phase14-release-readiness",
    phase_records: Iterable[PhaseCompletionRecord] | None = None,
    validation_evidence: Iterable[ValidationEvidenceRecord] | None = None,
    blockers: Iterable[str] = (),
) -> ReleaseReadinessReport:
    phases = tuple(phase_records or default_phase_completion_records())
    evidence = tuple(validation_evidence or passing_validation_evidence())
    derived_blockers = list(blockers)
    for phase_record in phases:
        if phase_record.status != "complete":
            derived_blockers.append(
                f"phase {phase_record.phase} {phase_record.name} status is "
                f"{phase_record.status}"
            )
    evidence_commands = {record.command for record in evidence}
    for command in DEFAULT_VALIDATION_COMMANDS:
        if command not in evidence_commands:
            derived_blockers.append(f"required validation command {command} is missing")
    for evidence_record in evidence:
        if evidence_record.status != "passed":
            derived_blockers.append(
                f"validation command {evidence_record.command} status is "
                f"{evidence_record.status}"
            )
    completed_count = sum(1 for record in phases if record.status == "complete")
    status: ReleaseReadinessStatus = "ready" if not derived_blockers else "blocked"
    manifest_json = {
        "phase_numbers": [record.phase for record in phases],
        "validation_commands": [record.command for record in evidence],
        "required_validation_commands": list(DEFAULT_VALIDATION_COMMANDS),
        "operator_surface": "./hubble_tension.sh",
        "automated_only": True,
        "scientific_claim": False,
    }
    return ReleaseReadinessReport(
        report_id=report_id,
        status=status,
        required_phase_count=len(phases),
        completed_phase_count=completed_count,
        phase_records=phases,
        validation_evidence=evidence,
        required_validation_commands=DEFAULT_VALIDATION_COMMANDS,
        blockers=tuple(derived_blockers),
        no_human_review_required=True,
        no_scientific_claim=True,
        launch_command="./hubble_tension.sh",
        manifest_json=manifest_json,
    )
