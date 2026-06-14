from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from hubble_tension.corpus import (
    EXPECTED_PAPER_COUNT,
    MVP3_BENCHMARK_PAPER_IDS,
    build_failure_memory_index,
    build_paper_studies,
    build_paper_study_record,
    extract_pdf_text,
    load_corpus,
    validate_paper_study_record,
    write_corpus_to_store,
    write_paper_studies_to_store,
)
from hubble_tension.schemas.paper_study import CitationSpan, PaperStudyRecord
from hubble_tension.state import ArtifactProvenance, StateStore


def test_phase4_builds_strict_paper_study_records_for_full_corpus() -> None:
    corpus = load_corpus(".")
    build = build_paper_studies(corpus)

    assert build.ok is True
    assert build.errors == ()
    assert len(build.studies) == EXPECTED_PAPER_COUNT
    assert {study.paper_id for study in build.studies} == {
        f"paper-{number:03d}" for number in range(1, EXPECTED_PAPER_COUNT + 1)
    }
    assert all(study.role_label or study.blocker_reason for study in build.studies)
    assert all(study.citation_spans for study in build.studies)
    assert all(study.paper_id in study.source_refs for study in build.studies)

    planck = build.studies[0]
    assert planck.paper_id == "paper-001"
    assert planck.role_label == "early_universe_constraint_or_solution"
    assert "Planck CMB" in planck.datasets
    assert "H0" in planck.parameters
    json.dumps(planck.model_dump())


def test_paper_study_references_resolve_against_scanned_bibliography() -> None:
    corpus = load_corpus(".")
    build = build_paper_studies(corpus)
    resolver = corpus.resolver

    for study in build.studies:
        assert validate_paper_study_record(study, resolver) == ()
        for source_ref in study.source_refs:
            assert resolver.require(source_ref).source_url.startswith("https://arxiv.org/abs/")


def test_failure_memory_builder_covers_no_go_reviews_and_calibration_warnings() -> None:
    build = build_paper_studies(load_corpus("."))
    memories_by_paper: dict[str, list[str]] = {}
    for memory in build.failure_memories:
        memories_by_paper.setdefault(memory.paper_id, []).append(memory.failure_kind)

    assert {
        "no_go",
        "model_comparison",
        "known_rejected_model",
        "local_systematics",
        "calibration_warning",
    } <= {memory.failure_kind for memory in build.failure_memories}
    assert "model_comparison" in memories_by_paper["paper-018"]
    assert "known_rejected_model" in memories_by_paper["paper-019"]
    assert "known_rejected_model" in memories_by_paper["paper-020"]
    assert "known_rejected_model" in memories_by_paper["paper-050"]
    assert "early_universe_constraint" in memories_by_paper["paper-051"]
    assert "local_systematics" in memories_by_paper["paper-013"]
    assert "calibration_warning" in memories_by_paper["paper-013"]
    assert "local_systematics" in memories_by_paper["paper-015"]
    assert "calibration_warning" in memories_by_paper["paper-015"]


def test_failure_memory_index_answers_constraining_papers_for_concept_category() -> None:
    build = build_paper_studies(load_corpus("."))
    index = build_failure_memory_index(build.failure_memories)

    late_time_papers = index.constraining_paper_ids("late time local new physics")
    calibration_papers = index.constraining_paper_ids("Cepheid TRGB calibration systematics")
    local_systematics_papers = index.constraining_paper_ids("local systematics photometry bias")
    growth_papers = index.constraining_paper_ids("S8 weak lensing growth model")

    assert "paper-019" in late_time_papers
    assert "paper-020" in late_time_papers
    assert "paper-013" in calibration_papers
    assert "paper-015" in calibration_papers
    assert "paper-013" in local_systematics_papers
    assert "paper-015" in local_systematics_papers
    assert any(paper_id.startswith("paper-") for paper_id in growth_papers)


def test_mvp3_benchmark_replay_suite_uses_build_plan_paper_ids_verbatim() -> None:
    build = build_paper_studies(load_corpus("."))

    assert tuple(replay.paper_id for replay in build.benchmark_replays) == MVP3_BENCHMARK_PAPER_IDS
    assert len(build.benchmark_replays) == 20
    assert all(replay.status == "ready" for replay in build.benchmark_replays)
    assert all(replay.required_datasets for replay in build.benchmark_replays)
    assert all(replay.required_constraints for replay in build.benchmark_replays)
    assert {
        "paper-001",
        "paper-002",
        "paper-003",
        "paper-005",
        "paper-006",
        "paper-010",
        "paper-013",
        "paper-015",
        "paper-018",
        "paper-019",
        "paper-020",
        "paper-021",
        "paper-022",
        "paper-023",
        "paper-024",
        "paper-025",
        "paper-029",
        "paper-030",
        "paper-050",
        "paper-051",
    } == set(MVP3_BENCHMARK_PAPER_IDS)


def test_sample_manual_free_replay_of_five_papers_validates_and_stores(
    tmp_path: Path,
) -> None:
    corpus = load_corpus(".")
    build = build_paper_studies(corpus)
    sample_studies = tuple(
        study
        for study in build.studies
        if study.paper_id in {"paper-001", "paper-002", "paper-010", "paper-018", "paper-019"}
    )
    store = StateStore(tmp_path / "lab.sqlite3")
    store.initialize()

    write_corpus_to_store(store, corpus)
    write_paper_studies_to_store(store, sample_studies, build.failure_memories, _provenance())
    write_paper_studies_to_store(store, sample_studies, build.failure_memories, _provenance())

    with store.connect() as connection:
        extraction_count = connection.execute(
            "SELECT COUNT(*) FROM paper_extractions"
        ).fetchone()[0]

    assert extraction_count == 5
    extraction = store.paper_extraction_by_id("paper-study-paper-001-v1")
    assert extraction is not None
    assert extraction["method_json"]["role_label"] == "early_universe_constraint_or_solution"
    assert extraction["datasets_json"]["datasets"]
    assert extraction["priors_json"]["priors"]
    assert extraction["results_json"]["results"]

    no_go = store.paper_extraction_by_id("paper-study-paper-019-v1")
    assert no_go is not None
    assert no_go["no_go_lessons_json"]["failure_memories"]


def test_stdlib_pdf_text_extractor_recovers_simple_pdf_text(tmp_path: Path) -> None:
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj <<>> stream\n"
        b"BT (Hubble tension local calibration text) Tj ET\n"
        b"endstream\n%%EOF"
    )

    result = extract_pdf_text(pdf)

    assert result.status == "extracted"
    assert "Hubble tension local calibration text" in result.text


def test_real_local_pdf_pipeline_runs_when_requested() -> None:
    corpus = load_corpus(".")
    planck = corpus.resolver.require("paper-001")

    study = build_paper_study_record(planck, repo_root=".", include_pdf_text=True)

    assert any(note.startswith("pdf:") for note in study.extraction_notes)
    assert all("pdf_text_extraction_skipped" not in note for note in study.extraction_notes)


def test_paper_study_schema_rejects_records_without_role_or_blocker() -> None:
    citation = CitationSpan(
        paper_id="paper-001",
        source_file="SCANNED_PAPERS.md",
        row_ref="1",
        field="why_included",
        text="fixture citation",
    )

    try:
        PaperStudyRecord(
            paper_id="paper-001",
            title="Fixture",
            source_url="https://arxiv.org/abs/fixture",
            local_path="papers/fixture.pdf",
            category="Fixture",
            citation_spans=[citation],
            source_refs=["paper-001"],
        )
    except ValidationError as exc:
        assert "role_label or blocker_reason" in str(exc)
    else:
        raise AssertionError("PaperStudyRecord accepted missing role/blocker")


def _provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        agent_id="codex",
        agent_version_hash="agent-version-hash",
        prompt_template_id="lab_head",
        prompt_template_hash="prompt-template-hash",
    )
