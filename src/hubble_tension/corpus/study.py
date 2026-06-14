from __future__ import annotations

import re
import zlib
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hubble_tension.corpus.importer import BibliographyResolver, CorpusImportResult, CorpusPaper
from hubble_tension.schemas.paper_study import (
    BenchmarkReplayRecord,
    CitationSpan,
    FailureMemoryRecord,
    PaperStudyRecord,
    TextExtractionResult,
)
from hubble_tension.state import ArtifactProvenance, StateStore

MVP3_BENCHMARK_PAPER_IDS = (
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
)

REVIEW_OR_NO_GO_CATEGORY = "Reviews, Model Comparisons, and No-Go Results"
DISTANCE_LADDER_CATEGORY = "Distance-Ladder Calibration and Local Systematics"
INVERSE_LADDER_CATEGORY = "Inverse Distance Ladder, BAO, and Expansion History"
EARLY_UNIVERSE_CATEGORY = "Early-Universe and Pre-Recombination Solutions"
GROWTH_CATEGORY = "Growth, S8, Weak Lensing, Clusters, and CMB Lensing"
LOCAL_INHOMOGENEITY_CATEGORY = "Local Inhomogeneity and Light-Propagation Effects"

ROLE_LABELS_BY_CATEGORY = {
    EARLY_UNIVERSE_CATEGORY: "early_universe_constraint_or_solution",
    "Late-Universe Dark Energy and Modified Gravity": (
        "late_universe_dark_energy_or_modified_gravity"
    ),
    DISTANCE_LADDER_CATEGORY: "distance_ladder_calibration_or_systematics",
    "Independent Late-Universe H0 Probes": "independent_late_universe_h0_probe",
    "Local Inhomogeneity and Light-Propagation Effects": (
        "local_inhomogeneity_or_light_propagation"
    ),
    INVERSE_LADDER_CATEGORY: "inverse_distance_ladder_bao_expansion_history",
    GROWTH_CATEGORY: "growth_s8_lensing_structure_constraint",
    REVIEW_OR_NO_GO_CATEGORY: "review_model_comparison_or_no_go",
}

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_PAREN_TEXT_RE = re.compile(r"\(([^()\r\n]{4,})\)")
_WHITESPACE_RE = re.compile(r"\s+")
_NON_ASCII_RE = re.compile(r"[^\x20-\x7E]+")


@dataclass(frozen=True)
class PaperStudyError:
    paper_id: str
    message: str


@dataclass(frozen=True)
class PaperStudyBuildResult:
    studies: tuple[PaperStudyRecord, ...]
    failure_memories: tuple[FailureMemoryRecord, ...]
    benchmark_replays: tuple[BenchmarkReplayRecord, ...]
    errors: tuple[PaperStudyError, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


class FailureMemoryIndex:
    def __init__(self, memories: Sequence[FailureMemoryRecord]) -> None:
        self._memories = tuple(memories)

    def search(self, concept_category: str) -> tuple[FailureMemoryRecord, ...]:
        query_terms = _token_set(concept_category)
        matches: list[FailureMemoryRecord] = []
        for memory in self._memories:
            searchable = " ".join(
                (
                    memory.category,
                    memory.constraint_category,
                    memory.failure_kind,
                    memory.summary,
                    " ".join(memory.applies_to),
                )
            )
            if query_terms & _token_set(searchable):
                matches.append(memory)
        return tuple(matches)

    def constraining_paper_ids(self, concept_category: str) -> tuple[str, ...]:
        return tuple(sorted({memory.paper_id for memory in self.search(concept_category)}))


def extract_markdown_text(paper: CorpusPaper) -> TextExtractionResult:
    why = _metadata_str(paper.metadata, "why_included")
    readme_why = _metadata_str(paper.metadata, "readme_why_included")
    category_source = _metadata_str(paper.metadata, "category_source_file")
    text = _normal_text(
        " ".join(
            part
            for part in (
                paper.title,
                paper.category,
                why,
                readme_why,
                category_source,
                " ".join(_metadata_list(paper.metadata, "dataset_hints")),
            )
            if part
        )
    )
    return TextExtractionResult(
        source_kind="markdown",
        source_path=paper.source_file,
        status="extracted",
        text=text,
        text_char_count=len(text),
    )


def extract_pdf_text(path: str | Path, *, max_bytes: int = 1_000_000) -> TextExtractionResult:
    pdf_path = Path(path)
    if not pdf_path.exists():
        return TextExtractionResult(
            source_kind="pdf",
            source_path=str(pdf_path),
            status="blocked",
            blocker_reason="pdf_path_missing",
        )
    if max_bytes <= 0:
        return TextExtractionResult(
            source_kind="pdf",
            source_path=str(pdf_path),
            status="blocked",
            blocker_reason="pdf_text_extraction_skipped",
        )

    payload = pdf_path.read_bytes()[:max_bytes]
    text = _normal_text(" ".join(_extract_pdf_text_candidates(payload)))
    if not text:
        return TextExtractionResult(
            source_kind="pdf",
            source_path=str(pdf_path),
            status="blocked",
            blocker_reason="pdf_text_unavailable_with_stdlib_fallback",
        )
    return TextExtractionResult(
        source_kind="pdf",
        source_path=str(pdf_path),
        status="extracted",
        text=text,
        text_char_count=len(text),
    )


def build_paper_study_record(
    paper: CorpusPaper,
    *,
    repo_root: str | Path = ".",
    include_pdf_text: bool = False,
) -> PaperStudyRecord:
    markdown_text = extract_markdown_text(paper)
    pdf_text = (
        extract_pdf_text(Path(repo_root) / paper.local_path)
        if include_pdf_text
        else TextExtractionResult(
            source_kind="pdf",
            source_path=paper.local_path,
            status="blocked",
            blocker_reason="pdf_text_extraction_skipped",
        )
    )
    combined_text = _normal_text(f"{markdown_text.text} {pdf_text.text}")
    role_label = ROLE_LABELS_BY_CATEGORY.get(paper.category)
    citation_spans = _citation_spans(paper)
    dataset_hints = _dataset_labels(paper, combined_text)
    failure_modes = _failure_modes(paper, combined_text)

    extraction_notes = [
        "phase4_deterministic_metadata_extraction",
        "scientific_fields_are_seeded_from_tracked_markdown_and_category_metadata",
    ]
    if pdf_text.status == "blocked":
        extraction_notes.append(f"pdf:{pdf_text.blocker_reason}")
    else:
        extraction_notes.append("pdf:stdlib_text_recovered")

    return PaperStudyRecord(
        paper_id=paper.paper_id,
        title=paper.title,
        source_url=paper.source_url,
        local_path=paper.local_path,
        category=paper.category,
        role_label=role_label,
        blocker_reason=None if role_label else "unknown_category_role",
        model_families=_model_families(paper, combined_text),
        equations=_equation_labels(paper.category, combined_text),
        parameters=_parameter_labels(paper.category, combined_text),
        priors=_prior_labels(combined_text),
        datasets=dataset_hints,
        results=_result_labels(paper, combined_text),
        failure_modes=failure_modes,
        citation_spans=citation_spans,
        source_refs=[paper.paper_id],
        extraction_notes=extraction_notes,
    )


def build_paper_studies(
    corpus: CorpusImportResult,
    *,
    repo_root: str | Path = ".",
    include_pdf_text: bool = False,
) -> PaperStudyBuildResult:
    studies: list[PaperStudyRecord] = []
    errors: list[PaperStudyError] = []
    resolver = corpus.resolver

    for paper in corpus.papers:
        try:
            study = build_paper_study_record(
                paper,
                repo_root=repo_root,
                include_pdf_text=include_pdf_text,
            )
            errors.extend(
                PaperStudyError(study.paper_id, message)
                for message in validate_paper_study_record(study, resolver)
            )
            studies.append(study)
        except ValueError as exc:
            errors.append(PaperStudyError(paper.paper_id, str(exc)))

    failure_memories = build_failure_memories(studies)
    benchmark_replays = build_benchmark_replay_suite(studies)
    missing_benchmark_ids = sorted(
        set(MVP3_BENCHMARK_PAPER_IDS) - {replay.paper_id for replay in benchmark_replays}
    )
    errors.extend(
        PaperStudyError(paper_id, "benchmark paper missing from study records")
        for paper_id in missing_benchmark_ids
    )

    return PaperStudyBuildResult(
        studies=tuple(studies),
        failure_memories=failure_memories,
        benchmark_replays=benchmark_replays,
        errors=tuple(errors),
    )


def validate_paper_study_record(
    record: PaperStudyRecord,
    resolver: BibliographyResolver,
) -> tuple[str, ...]:
    errors: list[str] = []
    if resolver.get(record.paper_id) is None:
        errors.append(f"unknown paper reference {record.paper_id}")
    for source_ref in record.source_refs:
        if resolver.get(source_ref) is None:
            errors.append(f"unknown source_ref {source_ref}")
    for span in record.citation_spans:
        if resolver.get(span.paper_id) is None:
            errors.append(f"unknown citation paper reference {span.paper_id}")
    return tuple(errors)


def build_failure_memories(
    studies: Iterable[PaperStudyRecord],
) -> tuple[FailureMemoryRecord, ...]:
    memories: list[FailureMemoryRecord] = []
    for study in studies:
        for index, descriptor in enumerate(_failure_memory_descriptors(study), start=1):
            memories.append(
                FailureMemoryRecord(
                    failure_id=f"failure-{study.paper_id}-{index:02d}",
                    paper_id=study.paper_id,
                    category=study.category,
                    failure_kind=descriptor["failure_kind"],
                    constraint_category=descriptor["constraint_category"],
                    title=study.title,
                    summary=descriptor["summary"],
                    applies_to=descriptor["applies_to"],
                    source_url=study.source_url,
                    citation_spans=study.citation_spans,
                )
            )
    return tuple(memories)


def build_benchmark_replay_suite(
    studies: Sequence[PaperStudyRecord],
) -> tuple[BenchmarkReplayRecord, ...]:
    study_by_id = {study.paper_id: study for study in studies}
    replays: list[BenchmarkReplayRecord] = []
    for paper_id in MVP3_BENCHMARK_PAPER_IDS:
        study = study_by_id.get(paper_id)
        if study is None:
            continue
        required_constraints = sorted(
            {
                memory.constraint_category
                for memory in build_failure_memories((study,))
            }
        )
        if study.role_label is not None:
            replays.append(
                BenchmarkReplayRecord(
                    replay_id=f"mvp3-{paper_id}",
                    paper_id=paper_id,
                    role_label=study.role_label,
                    required_datasets=study.datasets,
                    required_constraints=required_constraints,
                    source_refs=study.source_refs,
                    status="ready",
                )
            )
        else:
            replays.append(
                BenchmarkReplayRecord(
                    replay_id=f"mvp3-{paper_id}",
                    paper_id=paper_id,
                    role_label=study.role_label,
                    required_datasets=study.datasets,
                    required_constraints=required_constraints,
                    source_refs=study.source_refs,
                    status="blocked",
                    blocker_reason=study.blocker_reason,
                )
            )
    return tuple(replays)


def build_failure_memory_index(
    memories: Sequence[FailureMemoryRecord],
) -> FailureMemoryIndex:
    return FailureMemoryIndex(memories)


def write_paper_studies_to_store(
    store: StateStore,
    studies: Sequence[PaperStudyRecord],
    failure_memories: Sequence[FailureMemoryRecord],
    provenance: ArtifactProvenance,
) -> None:
    memories_by_paper: dict[str, list[FailureMemoryRecord]] = defaultdict(list)
    for memory in failure_memories:
        memories_by_paper[memory.paper_id].append(memory)

    for study in studies:
        store.upsert_paper_extraction(
            extraction_id=f"paper-study-{study.paper_id}-v1",
            paper_id=study.paper_id,
            method_json={
                "schema_version": study.schema_version,
                "role_label": study.role_label,
                "blocker_reason": study.blocker_reason,
                "model_families": study.model_families,
                "equations": study.equations,
                "parameters": study.parameters,
                "citation_spans": [span.model_dump() for span in study.citation_spans],
                "source_refs": study.source_refs,
                "extraction_notes": study.extraction_notes,
            },
            datasets_json={"datasets": study.datasets},
            priors_json={"priors": study.priors},
            results_json={"results": study.results},
            no_go_lessons_json={
                "failure_modes": study.failure_modes,
                "failure_memories": [
                    memory.model_dump() for memory in memories_by_paper[study.paper_id]
                ],
            },
            provenance=provenance,
        )


def _extract_pdf_text_candidates(payload: bytes) -> tuple[str, ...]:
    candidates: list[str] = [_decode_pdf_text(payload)]
    for stream in _STREAM_RE.findall(payload)[:40]:
        stream_payload = stream.strip()
        candidates.append(_decode_pdf_text(stream_payload))
        try:
            candidates.append(_decode_pdf_text(zlib.decompress(stream_payload)))
        except zlib.error:
            continue
    return tuple(candidate for candidate in candidates if candidate)


def _decode_pdf_text(payload: bytes) -> str:
    decoded = payload.decode("latin-1", errors="ignore")
    paren_text = " ".join(match.group(1) for match in _PAREN_TEXT_RE.finditer(decoded))
    printable = _NON_ASCII_RE.sub(" ", decoded)
    words = " ".join(word for word in printable.split() if len(word) > 3)
    return _normal_text(f"{paren_text} {words}")


def _citation_spans(paper: CorpusPaper) -> list[CitationSpan]:
    spans = [
        CitationSpan(
            paper_id=paper.paper_id,
            source_file=paper.source_file,
            row_ref=str(_metadata_value(paper.metadata, "scanned_line_number", "unknown")),
            field="why_included",
            text=_metadata_str(paper.metadata, "why_included") or paper.title,
        ),
        CitationSpan(
            paper_id=paper.paper_id,
            source_file=_metadata_str(paper.metadata, "readme_source_file") or "papers/README.md",
            row_ref=str(_metadata_value(paper.metadata, "readme_line_number", "unknown")),
            field="readme_why_included",
            text=_metadata_str(paper.metadata, "readme_why_included") or paper.title,
        ),
    ]
    category_source = _metadata_str(paper.metadata, "category_source_file")
    category_line = _metadata_value(paper.metadata, "category_line_number", None)
    if category_source and category_line is not None:
        spans.append(
            CitationSpan(
                paper_id=paper.paper_id,
                source_file=category_source,
                row_ref=str(category_line),
                field="category_assignment",
                text=paper.category,
            )
        )
    return spans


def _model_families(paper: CorpusPaper, text: str) -> list[str]:
    labels: list[str] = []
    lowered = text.lower()
    if "planck" in lowered or "cmb" in lowered or "act " in lowered or "spt" in lowered:
        labels.append("CMB/Lambda-CDM baseline or extension")
    if "early dark energy" in lowered or "pre-recombination" in lowered:
        labels.append("early dark energy or pre-recombination expansion")
    if "recombination" in lowered:
        labels.append("modified recombination history")
    if "dark energy" in lowered or "modified gravity" in lowered:
        labels.append("late dark energy or modified gravity")
    if "cepheid" in lowered or "trgb" in lowered or "jagb" in lowered:
        labels.append("local distance-ladder calibration")
    if "bao" in lowered or "inverse distance ladder" in lowered:
        labels.append("BAO and inverse distance ladder")
    if "s8" in lowered or "weak lensing" in lowered or "cluster" in lowered:
        labels.append("growth and lensing constraints")
    if "standard siren" in lowered or "time-delay" in lowered or "frb" in lowered:
        labels.append("independent late-universe H0 probe")
    if "void" in lowered or "inhomogene" in lowered or "light propagation" in lowered:
        labels.append("local inhomogeneity or light propagation")
    if "no-go" in lowered or "review" in lowered or "ranking" in lowered:
        labels.append("review, model comparison, or no-go analysis")
    if not labels:
        labels.append(ROLE_LABELS_BY_CATEGORY.get(paper.category, "uncategorized model family"))
    return _dedupe(labels)


def _equation_labels(category: str, text: str) -> list[str]:
    labels = ["H0 early-vs-late consistency target"]
    if category == EARLY_UNIVERSE_CATEGORY:
        labels.extend(["CMB acoustic scale theta_s", "sound horizon r_s modification"])
    if category == INVERSE_LADDER_CATEGORY:
        labels.extend(["BAO distance ratios D_M/r_d and H(z)r_d", "inverse-distance ladder"])
    if category == DISTANCE_LADDER_CATEGORY:
        labels.extend(["distance modulus ladder", "standard-candle calibration"])
    if category == GROWTH_CATEGORY:
        labels.extend(["S8 = sigma8 sqrt(Omega_m/0.3)", "growth/lensing likelihood"])
    if "dark energy" in text.lower() or "modified gravity" in text.lower():
        labels.append("late-time H(z) modification")
    if "standard siren" in text.lower():
        labels.append("luminosity-distance gravitational-wave H0 likelihood")
    return _dedupe(labels)


def _parameter_labels(category: str, text: str) -> list[str]:
    parameters = ["H0", "Omega_m"]
    lowered = text.lower()
    if category == EARLY_UNIVERSE_CATEGORY or "cmb" in lowered:
        parameters.extend(["r_s", "omega_b", "omega_cdm", "n_s", "tau"])
    if "dark energy" in lowered or category == "Late-Universe Dark Energy and Modified Gravity":
        parameters.extend(["w0", "wa"])
    if "s8" in lowered or category == GROWTH_CATEGORY:
        parameters.extend(["sigma8", "S8"])
    if "cepheid" in lowered or "trgb" in lowered or "jagb" in lowered:
        parameters.extend(["distance_anchor", "calibration_zero_point"])
    if "bao" in lowered:
        parameters.append("r_d")
    return _dedupe(parameters)


def _prior_labels(text: str) -> list[str]:
    labels = ["paper-specific priors require full likelihood replay before numeric use"]
    lowered = text.lower()
    if "prior" in lowered:
        labels.append("published prior choice is scientifically relevant")
    if "lambda-cdm" in lowered or "lambdacdm" in lowered:
        labels.append("Lambda-CDM baseline prior")
    if "calibration" in lowered or "anchor" in lowered:
        labels.append("local calibration prior or anchor")
    return _dedupe(labels)


def _dataset_labels(paper: CorpusPaper, text: str) -> list[str]:
    labels = list(_metadata_list(paper.metadata, "dataset_hints"))
    lowered = text.lower()
    keyword_map = {
        "planck": "Planck CMB",
        "sh0es": "SH0ES distance ladder",
        "h0dn": "H0DN local distance network",
        "pantheon": "Pantheon/Pantheon+ supernovae",
        "desi": "DESI BAO",
        "boss": "BOSS/eBOSS BAO",
        "act": "ACT CMB",
        "spt": "SPT CMB",
        "jwst": "JWST calibration",
        "cepheid": "Cepheid ladder",
        "trgb": "TRGB calibration",
        "jagb": "JAGB calibration",
        "frb": "FRB H0 probe",
        "standard siren": "standard siren H0 probe",
        "weak lensing": "weak-lensing survey",
        "kids": "KiDS weak lensing",
        "des ": "DES survey",
    }
    for keyword, label in keyword_map.items():
        if keyword in lowered:
            labels.append(label)
    if not labels:
        labels.append(paper.category)
    return _dedupe(labels)


def _result_labels(paper: CorpusPaper, text: str) -> list[str]:
    why = _metadata_str(paper.metadata, "why_included")
    labels = [why] if why else []
    lowered = text.lower()
    if "h0 ~= 67" in lowered or "67.4" in lowered:
        labels.append("early-universe baseline H0 near 67-68 km/s/Mpc")
    if "h0 ~= 73" in lowered or "73.04" in lowered or "73.50" in lowered:
        labels.append("local late-universe H0 near 73 km/s/Mpc")
    if "lower local h0" in lowered or "lower local h0 range" in lowered:
        labels.append("lower local H0 calibration route")
    if "no-go" in lowered or "cannot solve" in lowered or "difficulties" in lowered:
        labels.append("reported rejection or severe constraint on a solution class")
    return _dedupe(labels)


def _failure_modes(paper: CorpusPaper, text: str) -> list[str]:
    lowered = text.lower()
    modes: list[str] = []
    if paper.category == REVIEW_OR_NO_GO_CATEGORY:
        modes.append("solution classes must pass combined-data model comparison")
    if "no-go" in lowered or "cannot solve" in lowered or "difficulties" in lowered:
        modes.append("model-independent or comparative no-go constraint")
    if paper.category == DISTANCE_LADDER_CATEGORY:
        modes.append("local calibration or systematic explanation must match ladder cross-checks")
    if "crowding" in lowered or "cepheid" in lowered or "trgb" in lowered or "jagb" in lowered:
        modes.append("distance-ladder calibration warning")
    if paper.category == INVERSE_LADDER_CATEGORY or "bao" in lowered:
        modes.append("inverse-distance-ladder and BAO consistency constraint")
    if paper.category == GROWTH_CATEGORY or "s8" in lowered or "weak lensing" in lowered:
        modes.append("growth or lensing consistency constraint")
    if paper.category == EARLY_UNIVERSE_CATEGORY and (
        "bbn" in lowered or "desi" in lowered or "act" in lowered or "spt" in lowered
    ):
        modes.append("early-universe extension must satisfy external CMB/BBN/BAO checks")
    return _dedupe(modes)


def _failure_memory_descriptors(study: PaperStudyRecord) -> list[dict[str, Any]]:
    text = _normal_text(" ".join((study.title, study.category, " ".join(study.failure_modes))))
    lowered = text.lower()
    descriptors: list[dict[str, Any]] = []
    if study.category == REVIEW_OR_NO_GO_CATEGORY:
        title_lowered = study.title.lower()
        kind = (
            "no_go"
            if "no-go" in title_lowered
            or "obstruction" in title_lowered
            or "difficulties" in title_lowered
            else "model_comparison"
        )
        descriptors.append(
            {
                "failure_kind": kind,
                "constraint_category": "model_comparison_and_no_go",
                "summary": (
                    "Use this paper as a reusable rejection map for solution classes "
                    "that fail combined-data or model-comparison checks."
                ),
                "applies_to": [
                    "late_time_new_physics",
                    "local_scale_new_physics",
                    "pre_recombination_changes",
                    "distance_ladder_systematics",
                ],
            }
        )
    if "no-go" in lowered or "obstruction" in lowered or "difficulties" in lowered:
        descriptors.append(
            {
                "failure_kind": "known_rejected_model",
                "constraint_category": "known_rejected_solution_class",
                "summary": (
                    "Future hypotheses in this class need explicit evidence against this "
                    "rejection."
                ),
                "applies_to": _applies_to_from_study(study),
            }
        )
    if study.category in {DISTANCE_LADDER_CATEGORY, LOCAL_INHOMOGENEITY_CATEGORY} or any(
        token in lowered
        for token in (
            "systematic",
            "crowding",
            "selection effect",
            "local environment",
            "local hole",
            "local void",
        )
    ):
        descriptors.append(
            {
                "failure_kind": "local_systematics",
                "constraint_category": "local_systematics",
                "summary": (
                    "Local explanations must survive independent checks of photometry, "
                    "selection, environment, and nearby-structure systematics."
                ),
                "applies_to": [
                    "local_systematics",
                    "distance_ladder_systematics",
                    "local_environment",
                    "photometry_bias",
                ],
            }
        )
    if study.category == DISTANCE_LADDER_CATEGORY or any(
        token in lowered for token in ("cepheid", "trgb", "jagb", "crowding", "calibration")
    ):
        descriptors.append(
            {
                "failure_kind": "calibration_warning",
                "constraint_category": "local_distance_ladder_calibration",
                "summary": (
                    "Local-H0 explanations must pass calibration, anchor, crowding, "
                    "and independent-standard-candle checks."
                ),
                "applies_to": ["distance_ladder_systematics", "local_h0_calibration"],
            }
        )
    if study.category == INVERSE_LADDER_CATEGORY or "bao" in lowered:
        descriptors.append(
            {
                "failure_kind": "inverse_ladder_constraint",
                "constraint_category": "bao_inverse_distance_ladder",
                "summary": (
                    "Late-time expansion changes must remain consistent with "
                    "BAO/inverse-ladder data."
                ),
                "applies_to": ["late_time_new_physics", "dark_energy", "modified_gravity"],
            }
        )
    if study.category == GROWTH_CATEGORY:
        descriptors.append(
            {
                "failure_kind": "growth_constraint",
                "constraint_category": "growth_s8_lensing",
                "summary": (
                    "H0-relief models must not worsen S8, lensing, cluster, or growth "
                    "observables."
                ),
                "applies_to": ["growth_modification", "dark_sector", "modified_gravity"],
            }
        )
    if study.category == EARLY_UNIVERSE_CATEGORY and any(
        token in lowered for token in ("bbn", "desi", "act", "spt", "recombination")
    ):
        descriptors.append(
            {
                "failure_kind": "early_universe_constraint",
                "constraint_category": "early_universe_external_consistency",
                "summary": (
                    "Pre-recombination changes need CMB, BBN, and BAO consistency checks "
                    "before H0 relief can be trusted."
                ),
                "applies_to": ["early_dark_energy", "recombination_modification", "sound_horizon"],
            }
        )
    return descriptors


def _applies_to_from_study(study: PaperStudyRecord) -> list[str]:
    lowered = _normal_text(" ".join((study.title, study.category))).lower()
    applies: list[str] = []
    if "late" in lowered or "dark energy" in lowered:
        applies.append("late_time_new_physics")
    if "local" in lowered or "void" in lowered:
        applies.append("local_scale_new_physics")
    if "recombination" in lowered or "early" in lowered:
        applies.append("pre_recombination_changes")
    if not applies:
        applies.append(study.role_label or study.category)
    return _dedupe(applies)


def _metadata_value(metadata: Mapping[str, Any], key: str, default: object) -> object:
    return metadata.get(key, default)


def _metadata_str(metadata: Mapping[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value if isinstance(value, str) else ""


def _metadata_list(metadata: Mapping[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normal = _normal_text(value)
        if normal and normal not in seen:
            seen.add(normal)
            deduped.append(normal)
    return deduped


def _token_set(value: str) -> set[str]:
    tokens = {token for token in re.split(r"[^a-z0-9]+", value.lower()) if len(token) >= 3}
    synonyms = {
        "ede": "early",
        "cmb": "early",
        "bao": "inverse",
        "ladder": "calibration",
        "cepheid": "calibration",
        "trgb": "calibration",
        "jagb": "calibration",
        "s8": "growth",
        "lensing": "growth",
    }
    tokens.update(synonyms[token] for token in tuple(tokens) if token in synonyms)
    return tokens


def _normal_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()
