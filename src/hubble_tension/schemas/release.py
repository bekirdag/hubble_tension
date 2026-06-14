from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from hubble_tension.schemas.base import StrictBaseModel

PhaseCompletionStatus = Literal["complete", "incomplete", "blocked"]
ValidationEvidenceStatus = Literal["passed", "failed", "skipped"]
ReleaseReadinessStatus = Literal["ready", "blocked"]

DEFAULT_RELEASE_VALIDATION_COMMANDS: tuple[str, ...] = (
    ".venv/bin/python -m pytest -q",
    ".venv/bin/python -m ruff check .",
    ".venv/bin/python -m mypy src tests",
    "docdexd run-tests --repo .",
    "docdexd hook pre-commit --repo .",
    "docdexd impact-diagnostics --repo .",
)


class PhaseCompletionRecord(StrictBaseModel):
    phase: int = Field(ge=0)
    name: str = Field(min_length=1)
    status: PhaseCompletionStatus
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def completed_phases_need_evidence(self) -> PhaseCompletionRecord:
        if self.status == "complete" and not self.evidence_refs:
            raise ValueError("complete phases require evidence references")
        return self


class ValidationEvidenceRecord(StrictBaseModel):
    command: str = Field(min_length=1)
    status: ValidationEvidenceStatus
    summary: str = Field(min_length=1)
    artifact_ref: str | None = None


class ReleaseReadinessReport(StrictBaseModel):
    report_id: str = Field(min_length=1)
    release_phase: Literal[14] = 14
    status: ReleaseReadinessStatus
    required_phase_count: int = Field(ge=1)
    completed_phase_count: int = Field(ge=0)
    phase_records: tuple[PhaseCompletionRecord, ...]
    validation_evidence: tuple[ValidationEvidenceRecord, ...]
    required_validation_commands: tuple[str, ...] = Field(
        default=DEFAULT_RELEASE_VALIDATION_COMMANDS,
        min_length=1,
    )
    blockers: tuple[str, ...] = Field(default_factory=tuple)
    no_human_review_required: bool = True
    no_scientific_claim: bool = True
    launch_command: str = "./hubble_tension.sh"
    manifest_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def readiness_report_matches_policy_and_evidence(self) -> ReleaseReadinessReport:
        if not self.no_human_review_required:
            raise ValueError("release readiness cannot require human review")
        if not self.no_scientific_claim:
            raise ValueError("release readiness cannot claim a scientific solution")
        if self.launch_command != "./hubble_tension.sh":
            raise ValueError("release readiness must preserve the no-argument launcher")
        if self.required_phase_count != self.release_phase + 1:
            raise ValueError("required_phase_count must cover phases 0 through 14")
        if self.required_phase_count != len(self.phase_records):
            raise ValueError("required_phase_count must match phase_records")
        phase_numbers = tuple(record.phase for record in self.phase_records)
        if phase_numbers != tuple(range(self.release_phase + 1)):
            raise ValueError("phase_records must cover phases 0 through 14 in order")
        completed = sum(1 for record in self.phase_records if record.status == "complete")
        if self.completed_phase_count != completed:
            raise ValueError("completed_phase_count must match complete phase records")
        evidence_commands = {record.command for record in self.validation_evidence}
        missing_commands = [
            command
            for command in self.required_validation_commands
            if command not in evidence_commands
        ]
        validation_passed = all(
            record.status == "passed" for record in self.validation_evidence
        )
        phases_complete = completed == self.required_phase_count
        if self.status == "ready" and missing_commands:
            raise ValueError(
                "ready release reports require all required validation commands"
            )
        if self.status == "ready" and (
            self.blockers or not validation_passed or not phases_complete
        ):
            raise ValueError("ready release reports require no blockers and passing evidence")
        return self
