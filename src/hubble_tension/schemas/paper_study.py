from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from hubble_tension.schemas.base import StrictBaseModel

TextSourceKind = Literal["markdown", "pdf"]
TextExtractionStatus = Literal["extracted", "blocked"]
FailureKind = Literal[
    "no_go",
    "model_comparison",
    "known_rejected_model",
    "local_systematics",
    "calibration_warning",
    "growth_constraint",
    "inverse_ladder_constraint",
    "early_universe_constraint",
]
BenchmarkReplayStatus = Literal["ready", "blocked"]


class CitationSpan(StrictBaseModel):
    paper_id: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    row_ref: str = Field(min_length=1)
    field: str = Field(min_length=1)
    text: str = Field(min_length=1)


class TextExtractionResult(StrictBaseModel):
    source_kind: TextSourceKind
    source_path: str = Field(min_length=1)
    status: TextExtractionStatus
    text: str = ""
    text_char_count: int = Field(default=0, ge=0)
    blocker_reason: str | None = None

    @model_validator(mode="after")
    def require_text_or_blocker(self) -> Self:
        if self.status == "extracted" and not self.text.strip():
            raise ValueError("extracted text result must include text")
        if self.status == "blocked" and not self.blocker_reason:
            raise ValueError("blocked text result must include blocker_reason")
        if self.status == "extracted" and self.text_char_count != len(self.text):
            raise ValueError("text_char_count must match extracted text length")
        return self


class PaperStudyRecord(StrictBaseModel):
    schema_version: Literal["paper-study-v1"] = "paper-study-v1"
    paper_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    local_path: str = Field(min_length=1)
    category: str = Field(min_length=1)
    role_label: str | None = None
    blocker_reason: str | None = None
    model_families: list[str] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)
    priors: list[str] = Field(default_factory=list)
    datasets: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    citation_spans: list[CitationSpan] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    extraction_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_role_or_blocker_and_resolved_refs(self) -> Self:
        if self.role_label is None and self.blocker_reason is None:
            raise ValueError("paper study must include a role_label or blocker_reason")
        if self.paper_id not in self.source_refs:
            raise ValueError("paper study source_refs must include its own paper_id")
        for span in self.citation_spans:
            if span.paper_id != self.paper_id:
                raise ValueError("citation spans must reference the study paper_id")
        return self


class FailureMemoryRecord(StrictBaseModel):
    schema_version: Literal["failure-memory-v1"] = "failure-memory-v1"
    failure_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    failure_kind: FailureKind
    constraint_category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    applies_to: list[str] = Field(min_length=1)
    source_url: str = Field(min_length=1)
    citation_spans: list[CitationSpan] = Field(min_length=1)


class BenchmarkReplayRecord(StrictBaseModel):
    schema_version: Literal["benchmark-replay-v1"] = "benchmark-replay-v1"
    replay_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    role_label: str | None = None
    required_datasets: list[str] = Field(default_factory=list)
    required_constraints: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(min_length=1)
    status: BenchmarkReplayStatus
    blocker_reason: str | None = None

    @model_validator(mode="after")
    def require_blocker_for_blocked_replay(self) -> Self:
        if self.status == "blocked" and not self.blocker_reason:
            raise ValueError("blocked benchmark replay must include blocker_reason")
        if self.paper_id not in self.source_refs:
            raise ValueError("benchmark replay source_refs must include paper_id")
        return self
