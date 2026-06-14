from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from hubble_tension.schemas.adversarial import (
    AdversarialValidationReport,
    StableCandidateRegistryEntry,
)
from hubble_tension.schemas.candidates import CandidateRecord
from hubble_tension.schemas.operations import (
    DatasetBacklogItem,
    ExternalRerunRequest,
    ExternalTransitionProposal,
    MaintenanceJobResult,
    OperatorDigest,
    ReportIndexEntry,
    ScaleOutProfile,
)
from hubble_tension.schemas.release import ReleaseReadinessReport
from hubble_tension.schemas.replication import ReplicationReport

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class _GeneratorHealthLike(Protocol):
    def as_json(self) -> dict[str, Any]:
        ...

PROMPT_TEMPLATE_IDS = (
    "lab_head",
    "reviewer",
    "concept_forge",
    "formula",
    "code_generation",
    "reporting",
)

FAILED_BRANCH_DECISIONS = (
    "abandoned",
    "branch_failed",
    "dead_end",
    "failed",
    "refuted",
)

CORE_TABLES = (
    "papers",
    "paper_extractions",
    "concept_seeds",
    "prior_art_checks",
    "assumption_sets",
    "hypotheses",
    "formal_models",
    "implementations",
    "datasets",
    "constraints",
    "runtime_state",
    "attempts",
    "runs",
    "tuning_events",
    "hypothesis_edges",
    "lab_notes",
    "lab_head_decisions",
    "event_log",
    "checkpoints",
    "candidates",
    "reports",
    "replication_queue",
    "replication_reports",
    "adversarial_queue",
    "adversarial_reports",
    "stable_candidate_registry",
    "operator_digests",
    "pending_external_transitions",
    "external_rerun_queue",
    "report_search_index",
    "dataset_backlog",
    "maintenance_jobs",
    "scale_out_profiles",
    "release_readiness_reports",
    "fiction_sources",
    "motif_ab_cycles",
    "generator_health",
)

GENERATED_ARTIFACT_TABLES = (
    "paper_extractions",
    "concept_seeds",
    "prior_art_checks",
    "assumption_sets",
    "hypotheses",
    "formal_models",
    "implementations",
    "tuning_events",
    "lab_notes",
    "lab_head_decisions",
    "reports",
    "replication_reports",
    "adversarial_reports",
    "stable_candidate_registry",
    "operator_digests",
    "pending_external_transitions",
    "external_rerun_queue",
    "report_search_index",
    "dataset_backlog",
    "maintenance_jobs",
    "scale_out_profiles",
    "release_readiness_reports",
    "metric_packets",
    "motif_ab_cycles",
)


@dataclass(frozen=True)
class ArtifactProvenance:
    agent_id: str
    agent_version_hash: str
    prompt_template_id: str
    prompt_template_hash: str


@dataclass(frozen=True)
class ReportRecord:
    report_id: str
    hypothesis_id: str | None
    candidate_id: str | None
    report_path: str
    external_status: str
    title: str | None
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class ExternalTransitionRecord:
    proposal_id: str
    report_id: str
    hypothesis_id: str | None
    candidate_id: str | None
    current_external_status: str
    target_external_status: str
    confidence: float
    evidence_json: dict[str, Any]
    reason: str
    decision: str
    decision_reason: str | None
    rerun_required: bool


@dataclass(frozen=True)
class ExternalRerunRecord:
    rerun_id: str
    proposal_id: str
    report_id: str
    hypothesis_id: str | None
    candidate_id: str | None
    target_external_status: str
    reason: str
    evidence_ids_json: dict[str, Any]
    status: str
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class ReportIndexRecord:
    report_id: str
    hypothesis_id: str | None
    candidate_id: str | None
    report_path: str
    external_status: str
    title: str | None
    search_text: str
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class DatasetBacklogRecord:
    backlog_id: str
    dataset_id: str
    reason: str
    source_kind: str
    source_ref: str
    status: str
    priority: int
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class OperatorDigestRecord:
    digest_id: str
    digest_type: str
    content: str


@dataclass(frozen=True)
class MaintenanceJobRecord:
    job_id: str
    job_type: str
    status: str
    summary: str
    preserved_audit_records: int
    removed_paths_json: dict[str, Any]
    artifacts_json: dict[str, Any]


@dataclass(frozen=True)
class ScaleOutProfileRecord:
    profile_id: str
    enabled: bool
    worker_count: int
    profile_json: dict[str, Any]


@dataclass(frozen=True)
class ReleaseReadinessRecord:
    report_id: str
    status: str
    completed_phase_count: int
    required_phase_count: int
    report_json: dict[str, Any]
    agent_id: str
    agent_version_hash: str
    prompt_template_id: str
    prompt_template_hash: str


@dataclass(frozen=True)
class ReplicationQueueRecord:
    queue_id: str
    candidate_id: str
    hypothesis_id: str
    model_family: str
    status: str
    priority: int
    reason: str


@dataclass(frozen=True)
class ReplicationReportRecord:
    report_id: str
    candidate_id: str
    hypothesis_id: str
    replication_status: str
    replication_scope: str
    model_family: str
    independent_code_path: str
    parser_id: str
    fixture_set_id: str
    reviewer_id: str
    reference_checks_json: dict[str, Any]
    route_on_failure: str
    blocks_stable_candidate: bool
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class AdversarialQueueRecord:
    queue_id: str
    candidate_id: str
    hypothesis_id: str
    status: str
    priority: int
    reason: str


@dataclass(frozen=True)
class AdversarialReportRecord:
    report_id: str
    candidate_id: str
    hypothesis_id: str
    adversarial_status: str
    replication_status: str
    replication_scope: str
    distinct_attempt_count: int
    required_type_count: int
    preregistered_count: int
    budget_exhausted: bool
    attempts_json: dict[str, Any]
    negative_evidence_json: dict[str, Any]
    dataset_statuses_json: dict[str, Any]
    external_status: str
    metadata_json: dict[str, Any]


@dataclass(frozen=True)
class StableCandidateRegistryRecord:
    candidate_id: str
    hypothesis_id: str
    candidate_status: str
    replication_status: str
    replication_scope: str
    adversarial_status: str
    datasets_passed_json: dict[str, Any]
    report_path: str | None
    external_status: str
    registry_json: dict[str, Any]


@dataclass(frozen=True)
class TuningEventRecord:
    tuning_event_id: str
    hypothesis_id: str
    branch_id: str | None
    decision: str
    event_json: dict[str, Any]


@dataclass(frozen=True)
class LabHeadDecisionRecord:
    decision_id: str
    hypothesis_id: str
    decision: str
    rationale: str
    uncertainty: str
    next_step: str
    observation_json: dict[str, Any]
    actions_json: dict[str, Any]


class StateStore:
    """SQLite-backed Phase 2 state and provenance store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        migrations_dir = Path(__file__).resolve().parent / "migrations"
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                str(row["version"])
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(migrations_dir.glob("*.sql")):
                version = migration.stem
                if version in applied:
                    continue
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )

    def table_names(self) -> set[str]:
        with self.connect() as connection:
            return {
                str(row["name"])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

    def table_columns(self, table_name: str) -> dict[str, sqlite3.Row]:
        with self.connect() as connection:
            return {
                str(row["name"]): row
                for row in connection.execute(f"PRAGMA table_info({table_name})")
            }

    def record_state_transition(
        self,
        *,
        status: str,
        reason: str,
        state: Mapping[str, Any],
        attempt_id: str | None = None,
        branch_id: str | None = None,
        test_id: str | None = None,
        run_id: str | None = None,
        checkpoint_required: bool = True,
    ) -> str | None:
        now = utc_now()
        state_json = _json(state)
        checkpoint_id = str(uuid.uuid4()) if checkpoint_required else None
        started_at = _optional_str(state.get("started_at")) or now
        state_path = _optional_str(state.get("state_path"))
        log_path = _optional_str(state.get("log_path"))
        state_metadata = _json({"latest_reason": reason})
        with self.connect() as connection:
            if attempt_id is not None:
                connection.execute(
                    """
                    INSERT INTO attempts(attempt_id, status, started_at, metadata_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(attempt_id) DO UPDATE SET
                        status = excluded.status,
                        metadata_json = excluded.metadata_json
                    """,
                    (attempt_id, status, started_at, state_metadata),
                )
            if run_id is not None:
                connection.execute(
                    """
                    INSERT INTO runs(
                        run_id, attempt_id, status, state_path, log_path,
                        started_at, metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        attempt_id = excluded.attempt_id,
                        status = excluded.status,
                        state_path = excluded.state_path,
                        log_path = excluded.log_path,
                        metadata_json = excluded.metadata_json
                    """,
                    (run_id, attempt_id, status, state_path, log_path, started_at, state_metadata),
                )
            connection.execute(
                """
                INSERT INTO runtime_state(state_key, status, state_json, updated_at)
                VALUES ('default', ?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (status, state_json, now),
            )
            connection.execute(
                """
                INSERT INTO event_log(
                    event_id, attempt_id, branch_id, test_id, event_type,
                    reason, status, payload_json, recorded_at
                )
                VALUES (?, ?, ?, ?, 'state_transition', ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    attempt_id,
                    branch_id,
                    test_id,
                    reason,
                    status,
                    state_json,
                    now,
                ),
            )
            if checkpoint_id is not None:
                connection.execute(
                    """
                    INSERT INTO checkpoints(
                        checkpoint_id, runtime_state_key, attempt_id, run_id,
                        reason, state_json, recorded_at
                    )
                    VALUES (?, 'default', ?, ?, ?, ?, ?)
                    """,
                    (checkpoint_id, attempt_id, run_id, reason, state_json, now),
                )
        return checkpoint_id

    def upsert_paper(
        self,
        *,
        paper_id: str,
        title: str,
        source_url: str,
        local_path: str | None,
        category: str | None,
        source_file: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO papers(
                    paper_id, title, source_url, local_path, category,
                    source_file, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    title = excluded.title,
                    source_url = excluded.source_url,
                    local_path = excluded.local_path,
                    category = excluded.category,
                    source_file = excluded.source_file,
                    metadata_json = excluded.metadata_json
                """,
                (
                    paper_id,
                    title,
                    source_url,
                    local_path,
                    category,
                    source_file,
                    _json(metadata or {}),
                    utc_now(),
                ),
            )

    def paper_by_id(self, paper_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT paper_id, title, source_url, local_path, category,
                       source_file, metadata_json, created_at
                FROM papers
                WHERE paper_id = ?
                """,
                (paper_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["metadata_json"] = _dict_json(payload["metadata_json"])
        return payload

    def upsert_paper_extraction(
        self,
        *,
        extraction_id: str,
        paper_id: str,
        method_json: Mapping[str, Any] | None,
        datasets_json: Mapping[str, Any] | None,
        priors_json: Mapping[str, Any] | None,
        results_json: Mapping[str, Any] | None,
        no_go_lessons_json: Mapping[str, Any] | None,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_extractions(
                    extraction_id, paper_id, method_json, datasets_json,
                    priors_json, results_json, no_go_lessons_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(extraction_id) DO UPDATE SET
                    paper_id = excluded.paper_id,
                    method_json = excluded.method_json,
                    datasets_json = excluded.datasets_json,
                    priors_json = excluded.priors_json,
                    results_json = excluded.results_json,
                    no_go_lessons_json = excluded.no_go_lessons_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    extraction_id,
                    paper_id,
                    _json(method_json or {}),
                    _json(datasets_json or {}),
                    _json(priors_json or {}),
                    _json(results_json or {}),
                    _json(no_go_lessons_json or {}),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def paper_extraction_by_id(self, extraction_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT extraction_id, paper_id, method_json, datasets_json,
                       priors_json, results_json, no_go_lessons_json,
                       agent_id, agent_version_hash, prompt_template_id,
                       prompt_template_hash, created_at
                FROM paper_extractions
                WHERE extraction_id = ?
                """,
                (extraction_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        for key in (
            "method_json",
            "datasets_json",
            "priors_json",
            "results_json",
            "no_go_lessons_json",
        ):
            payload[key] = _dict_json(payload[key])
        return payload

    def upsert_dataset(
        self,
        *,
        dataset_id: str,
        name: str,
        source_url: str | None = None,
        local_path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO datasets(
                    dataset_id, name, source_url, local_path,
                    metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    name = excluded.name,
                    source_url = excluded.source_url,
                    local_path = excluded.local_path,
                    metadata_json = excluded.metadata_json
                """,
                (dataset_id, name, source_url, local_path, _json(metadata or {}), utc_now()),
            )

    def dataset_by_id(self, dataset_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT dataset_id, name, source_url, local_path,
                       metadata_json, created_at
                FROM datasets
                WHERE dataset_id = ?
                """,
                (dataset_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["metadata_json"] = _dict_json(payload["metadata_json"])
        return payload

    def restore_latest_checkpoint(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT state_json
                FROM checkpoints
                ORDER BY recorded_at DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["state_json"]))
        if not isinstance(payload, dict):
            raise ValueError("checkpoint state_json must decode to an object")
        return payload

    def append_lab_note(
        self,
        *,
        note_id: str,
        content: str,
        provenance: ArtifactProvenance,
        hypothesis_id: str | None = None,
        note_type: str = "lab_note",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO lab_notes(
                    note_id, hypothesis_id, note_type, content,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    hypothesis_id,
                    note_type,
                    content,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def list_lab_notes(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(
                connection.execute("SELECT * FROM lab_notes ORDER BY created_at, rowid")
            )

    def record_tuning_event(
        self,
        *,
        tuning_event_id: str,
        hypothesis_id: str,
        decision: str,
        provenance: ArtifactProvenance,
        branch_id: str | None = None,
        event_json: Mapping[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tuning_events(
                    tuning_event_id, hypothesis_id, branch_id, decision,
                    event_json, agent_id, agent_version_hash,
                    prompt_template_id, prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tuning_event_id,
                    hypothesis_id,
                    branch_id,
                    decision,
                    _json(event_json or {}),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def insert_concept_seed(
        self,
        *,
        seed_id: str,
        source_kind: str,
        source_ref: str | None,
        concept_text: str,
        wildness_level: str,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO concept_seeds(
                    seed_id, source_kind, source_ref, concept_text, wildness_level,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(seed_id) DO UPDATE SET
                    source_kind = excluded.source_kind,
                    source_ref = excluded.source_ref,
                    concept_text = excluded.concept_text,
                    wildness_level = excluded.wildness_level,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    seed_id,
                    source_kind,
                    source_ref,
                    concept_text,
                    wildness_level,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def record_prior_art_check(
        self,
        *,
        check_id: str,
        verdict: str,
        prior_art_json: Mapping[str, Any],
        provenance: ArtifactProvenance,
        hypothesis_id: str | None = None,
        concept_seed_id: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO prior_art_checks(
                    check_id, hypothesis_id, concept_seed_id, prior_art_json, verdict,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(check_id) DO UPDATE SET
                    hypothesis_id = excluded.hypothesis_id,
                    concept_seed_id = excluded.concept_seed_id,
                    prior_art_json = excluded.prior_art_json,
                    verdict = excluded.verdict,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    check_id,
                    hypothesis_id,
                    concept_seed_id,
                    _json(prior_art_json),
                    verdict,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def insert_assumption_set(
        self,
        *,
        assumption_set_id: str,
        assumptions_json: Mapping[str, Any],
        diff_json: Mapping[str, Any],
        provenance: ArtifactProvenance,
        hypothesis_id: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO assumption_sets(
                    assumption_set_id, hypothesis_id, assumptions_json, diff_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(assumption_set_id) DO UPDATE SET
                    hypothesis_id = excluded.hypothesis_id,
                    assumptions_json = excluded.assumptions_json,
                    diff_json = excluded.diff_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    assumption_set_id,
                    hypothesis_id,
                    _json(assumptions_json),
                    _json(diff_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def failed_branch_events(self) -> list[TuningEventRecord]:
        placeholders = ",".join("?" for _ in FAILED_BRANCH_DECISIONS)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT tuning_event_id, hypothesis_id, branch_id, decision, event_json
                FROM tuning_events
                WHERE decision IN ({placeholders})
                ORDER BY created_at, rowid
                """,
                FAILED_BRANCH_DECISIONS,
            ).fetchall()
        return [
            TuningEventRecord(
                tuning_event_id=str(row["tuning_event_id"]),
                hypothesis_id=str(row["hypothesis_id"]),
                branch_id=_optional_str(row["branch_id"]),
                decision=str(row["decision"]),
                event_json=_dict_json(row["event_json"]),
            )
            for row in rows
        ]

    def abandoned_branch_lessons(
        self,
        *,
        failed_level: str | None = None,
        failed_observable: str | None = None,
        lesson_query: str | None = None,
    ) -> list[TuningEventRecord]:
        lesson_needle = lesson_query.casefold() if lesson_query else None
        filtered: list[TuningEventRecord] = []
        for record in self.failed_branch_events():
            event = record.event_json
            if failed_level is not None and event.get("failed_level") != failed_level:
                continue
            if (
                failed_observable is not None
                and event.get("failed_observable") != failed_observable
            ):
                continue
            if lesson_needle is not None:
                lesson = str(event.get("lesson", "")).casefold()
                if lesson_needle not in lesson:
                    continue
            filtered.append(record)
        return filtered

    def insert_hypothesis(
        self,
        *,
        hypothesis_id: str,
        title: str,
        provenance: ArtifactProvenance,
        is_root_seed: bool,
        parent_hypothesis_id: str | None = None,
        root_seed_id: str | None = None,
        concept_seed_id: str | None = None,
        assumption_set_id: str | None = None,
        status: str = "screening_only_local_prior",
        hypothesis_json: Mapping[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO hypotheses(
                    hypothesis_id, parent_hypothesis_id, is_root_seed, title,
                    status, root_seed_id, concept_seed_id, assumption_set_id,
                    hypothesis_json, agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis_id,
                    parent_hypothesis_id,
                    1 if is_root_seed else 0,
                    title,
                    status,
                    root_seed_id,
                    concept_seed_id,
                    assumption_set_id,
                    _json(hypothesis_json or {}),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def insert_formal_model(
        self,
        *,
        model_id: str,
        hypothesis_id: str,
        equations_json: Mapping[str, Any],
        model_json: Mapping[str, Any],
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO formal_models(
                    model_id, hypothesis_id, equations_json, model_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    equations_json = excluded.equations_json,
                    model_json = excluded.model_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    model_id,
                    hypothesis_id,
                    _json(equations_json),
                    _json(model_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def insert_implementation(
        self,
        *,
        implementation_id: str,
        hypothesis_id: str,
        model_id: str | None,
        path: str,
        code_hash: str,
        status: str,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO implementations(
                    implementation_id, hypothesis_id, model_id, path, code_hash,
                    status, agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(implementation_id) DO UPDATE SET
                    model_id = excluded.model_id,
                    path = excluded.path,
                    code_hash = excluded.code_hash,
                    status = excluded.status,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    implementation_id,
                    hypothesis_id,
                    model_id,
                    path,
                    code_hash,
                    status,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def record_hypothesis_edge(
        self,
        *,
        edge_id: str,
        source_hypothesis_id: str,
        target_hypothesis_id: str,
        edge_type: str,
        rationale: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO hypothesis_edges(
                    edge_id, source_hypothesis_id, target_hypothesis_id,
                    edge_type, rationale, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    edge_type = excluded.edge_type,
                    rationale = excluded.rationale
                """,
                (
                    edge_id,
                    source_hypothesis_id,
                    target_hypothesis_id,
                    edge_type,
                    rationale,
                    utc_now(),
                ),
            )

    def record_metric_packet(
        self,
        *,
        metric_packet_id: str,
        hypothesis_id: str,
        packet_json: Mapping[str, Any],
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO metric_packets(
                    metric_packet_id, hypothesis_id, packet_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(metric_packet_id) DO UPDATE SET
                    packet_json = excluded.packet_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    metric_packet_id,
                    hypothesis_id,
                    _json(packet_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def metric_packet_by_id(self, metric_packet_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT metric_packet_id, hypothesis_id, packet_json,
                       agent_id, agent_version_hash, prompt_template_id,
                       prompt_template_hash, created_at
                FROM metric_packets
                WHERE metric_packet_id = ?
                """,
                (metric_packet_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["packet_json"] = _dict_json(payload["packet_json"])
        return payload

    def record_lab_head_decision(
        self,
        *,
        decision_id: str,
        hypothesis_id: str,
        decision: str,
        rationale: str,
        uncertainty: str,
        observation_json: Mapping[str, Any],
        actions_json: Mapping[str, Any],
        next_step: str,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO lab_head_decisions(
                    decision_id, hypothesis_id, decision, rationale, uncertainty,
                    observation_json, actions_json, next_step, agent_id,
                    agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    decision = excluded.decision,
                    rationale = excluded.rationale,
                    uncertainty = excluded.uncertainty,
                    observation_json = excluded.observation_json,
                    actions_json = excluded.actions_json,
                    next_step = excluded.next_step,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    decision_id,
                    hypothesis_id,
                    decision,
                    rationale,
                    uncertainty,
                    _json(observation_json),
                    _json(actions_json),
                    next_step,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def lab_head_decision_by_id(self, decision_id: str) -> LabHeadDecisionRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT decision_id, hypothesis_id, decision, rationale, uncertainty,
                       next_step, observation_json, actions_json
                FROM lab_head_decisions
                WHERE decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
        if row is None:
            return None
        return LabHeadDecisionRecord(
            decision_id=str(row["decision_id"]),
            hypothesis_id=str(row["hypothesis_id"]),
            decision=str(row["decision"]),
            rationale=str(row["rationale"]),
            uncertainty=str(row["uncertainty"]),
            next_step=str(row["next_step"]),
            observation_json=_dict_json(row["observation_json"]),
            actions_json=_dict_json(row["actions_json"]),
        )

    def record_fiction_source(
        self,
        *,
        source_id: str,
        title: str,
        license_kind: str,
        status: str,
        consecutive_failed_ab_cycles: int,
        disabled_reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO fiction_sources(
                    source_id, title, license_kind, status, disabled_reason,
                    consecutive_failed_ab_cycles, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    title = excluded.title,
                    license_kind = excluded.license_kind,
                    status = excluded.status,
                    disabled_reason = excluded.disabled_reason,
                    consecutive_failed_ab_cycles = excluded.consecutive_failed_ab_cycles,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    source_id,
                    title,
                    license_kind,
                    status,
                    disabled_reason,
                    consecutive_failed_ab_cycles,
                    _json(metadata or {}),
                    now,
                    now,
                ),
            )

    def record_motif_ab_cycle(
        self,
        *,
        cycle_id: str,
        source_id: str,
        status: str,
        metrics_json: Mapping[str, Any],
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO motif_ab_cycles(
                    cycle_id, source_id, status, metrics_json, agent_id,
                    agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cycle_id) DO UPDATE SET
                    status = excluded.status,
                    metrics_json = excluded.metrics_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    cycle_id,
                    source_id,
                    status,
                    _json(metrics_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def record_generator_health(self, health: _GeneratorHealthLike) -> None:
        payload = health.as_json()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO generator_health(
                    generator_key, agent_id, agent_version_hash,
                    prompt_template_hash, window_size, l2_pass_count,
                    total_count, rolling_l2_pass_rate, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(generator_key) DO UPDATE SET
                    window_size = excluded.window_size,
                    l2_pass_count = excluded.l2_pass_count,
                    total_count = excluded.total_count,
                    rolling_l2_pass_rate = excluded.rolling_l2_pass_rate,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    payload["generator_key"],
                    payload["agent_id"],
                    payload["agent_version_hash"],
                    payload["prompt_template_hash"],
                    payload["window_size"],
                    payload["l2_pass_count"],
                    payload["total_count"],
                    payload["rolling_l2_pass_rate"],
                    payload["status"],
                    utc_now(),
                ),
            )

    def generator_health_by_key(self, generator_key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT generator_key, agent_id, agent_version_hash,
                       prompt_template_hash, window_size, l2_pass_count,
                       total_count, rolling_l2_pass_rate, status, updated_at
                FROM generator_health
                WHERE generator_key = ?
                """,
                (generator_key,),
            ).fetchone()
        return None if row is None else dict(row)

    def insert_candidate(self, candidate: CandidateRecord) -> None:
        now = utc_now()
        novelty_profile_json = (
            None
            if candidate.novelty_profile is None
            else _json(candidate.novelty_profile.model_dump())
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO candidates(
                    candidate_id, hypothesis_id, concept_name, wildness_level,
                    candidate_status, replication_status, replication_scope,
                    adversarial_status, datasets_passed_json, report_path,
                    metrics_json, novelty_profile_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    candidate.hypothesis_id,
                    candidate.concept_name,
                    candidate.wildness_level,
                    candidate.candidate_status,
                    candidate.replication_status,
                    candidate.replication_scope,
                    candidate.adversarial_status,
                    _json(candidate.datasets_passed_json),
                    candidate.report_path,
                    _json(candidate.metrics_json),
                    novelty_profile_json,
                    now,
                    now,
                ),
            )

    def candidate_banner_fields(self, candidate_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT candidate_id, hypothesis_id, concept_name, wildness_level,
                       candidate_status, replication_status, replication_scope,
                       adversarial_status, datasets_passed_json, report_path,
                       metrics_json
                FROM candidates
                WHERE candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["datasets_passed_json"] = json.loads(str(payload["datasets_passed_json"]))
        payload["metrics_json"] = json.loads(str(payload["metrics_json"]))
        return payload

    def enqueue_replication(
        self,
        *,
        queue_id: str,
        candidate_id: str,
        hypothesis_id: str,
        model_family: str,
        priority: int,
        reason: str,
        status: str = "queued",
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO replication_queue(
                    queue_id, candidate_id, hypothesis_id, model_family,
                    status, priority, reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(queue_id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    hypothesis_id = excluded.hypothesis_id,
                    model_family = excluded.model_family,
                    status = excluded.status,
                    priority = excluded.priority,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (
                    queue_id,
                    candidate_id,
                    hypothesis_id,
                    model_family,
                    status,
                    priority,
                    reason,
                    now,
                    now,
                ),
            )

    def replication_queue(self, *, status: str | None = None) -> list[ReplicationQueueRecord]:
        if status is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "status = ?"
            values = (status,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT queue_id, candidate_id, hypothesis_id, model_family,
                       status, priority, reason
                FROM replication_queue
                WHERE {where_clause}
                ORDER BY priority, created_at, rowid
                """,
                values,
            ).fetchall()
        return [
            ReplicationQueueRecord(
                queue_id=str(row["queue_id"]),
                candidate_id=str(row["candidate_id"]),
                hypothesis_id=str(row["hypothesis_id"]),
                model_family=str(row["model_family"]),
                status=str(row["status"]),
                priority=int(row["priority"]),
                reason=str(row["reason"]),
            )
            for row in rows
        ]

    def record_replication_report(
        self,
        report: ReplicationReport,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        implementation = report.independent_implementation
        reference_checks_json = {
            "checks": [
                check.model_dump(mode="json")
                for check in report.reference_checks
            ]
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO replication_reports(
                    report_id, candidate_id, hypothesis_id, replication_status,
                    replication_scope, model_family, independent_code_path,
                    parser_id, fixture_set_id, reviewer_id, reference_checks_json,
                    route_on_failure, blocks_stable_candidate, metadata_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    hypothesis_id = excluded.hypothesis_id,
                    replication_status = excluded.replication_status,
                    replication_scope = excluded.replication_scope,
                    model_family = excluded.model_family,
                    independent_code_path = excluded.independent_code_path,
                    parser_id = excluded.parser_id,
                    fixture_set_id = excluded.fixture_set_id,
                    reviewer_id = excluded.reviewer_id,
                    reference_checks_json = excluded.reference_checks_json,
                    route_on_failure = excluded.route_on_failure,
                    blocks_stable_candidate = excluded.blocks_stable_candidate,
                    metadata_json = excluded.metadata_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    report.report_id,
                    report.candidate_id,
                    report.hypothesis_id,
                    report.replication_status,
                    report.replication_scope,
                    report.model_family,
                    implementation.generated_code_path,
                    implementation.parser_id,
                    implementation.fixture_set_id,
                    implementation.reviewer_id,
                    _json(reference_checks_json),
                    report.route_on_failure,
                    1 if report.blocks_stable_candidate else 0,
                    _json(report.metadata_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def replication_reports_by_candidate(
        self,
        candidate_id: str,
    ) -> list[ReplicationReportRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT report_id, candidate_id, hypothesis_id, replication_status,
                       replication_scope, model_family, independent_code_path,
                       parser_id, fixture_set_id, reviewer_id, reference_checks_json,
                       route_on_failure, blocks_stable_candidate, metadata_json
                FROM replication_reports
                WHERE candidate_id = ?
                ORDER BY created_at, rowid
                """,
                (candidate_id,),
            ).fetchall()
        return [
            ReplicationReportRecord(
                report_id=str(row["report_id"]),
                candidate_id=str(row["candidate_id"]),
                hypothesis_id=str(row["hypothesis_id"]),
                replication_status=str(row["replication_status"]),
                replication_scope=str(row["replication_scope"]),
                model_family=str(row["model_family"]),
                independent_code_path=str(row["independent_code_path"]),
                parser_id=str(row["parser_id"]),
                fixture_set_id=str(row["fixture_set_id"]),
                reviewer_id=str(row["reviewer_id"]),
                reference_checks_json=_dict_json(row["reference_checks_json"]),
                route_on_failure=str(row["route_on_failure"]),
                blocks_stable_candidate=bool(row["blocks_stable_candidate"]),
                metadata_json=_dict_json(row["metadata_json"]),
            )
            for row in rows
        ]

    def enqueue_adversarial(
        self,
        *,
        queue_id: str,
        candidate_id: str,
        hypothesis_id: str,
        priority: int,
        reason: str,
        status: str = "queued",
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO adversarial_queue(
                    queue_id, candidate_id, hypothesis_id, status,
                    priority, reason, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(queue_id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    hypothesis_id = excluded.hypothesis_id,
                    status = excluded.status,
                    priority = excluded.priority,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (
                    queue_id,
                    candidate_id,
                    hypothesis_id,
                    status,
                    priority,
                    reason,
                    now,
                    now,
                ),
            )

    def adversarial_queue(self, *, status: str | None = None) -> list[AdversarialQueueRecord]:
        if status is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "status = ?"
            values = (status,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT queue_id, candidate_id, hypothesis_id, status, priority, reason
                FROM adversarial_queue
                WHERE {where_clause}
                ORDER BY priority, created_at, rowid
                """,
                values,
            ).fetchall()
        return [
            AdversarialQueueRecord(
                queue_id=str(row["queue_id"]),
                candidate_id=str(row["candidate_id"]),
                hypothesis_id=str(row["hypothesis_id"]),
                status=str(row["status"]),
                priority=int(row["priority"]),
                reason=str(row["reason"]),
            )
            for row in rows
        ]

    def record_adversarial_report(
        self,
        report: AdversarialValidationReport,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        attempts_json = {
            "attempts": [attempt.model_dump(mode="json") for attempt in report.attempts]
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO adversarial_reports(
                    report_id, candidate_id, hypothesis_id, adversarial_status,
                    replication_status, replication_scope, distinct_attempt_count,
                    required_type_count, preregistered_count, budget_exhausted,
                    attempts_json, negative_evidence_json, dataset_statuses_json,
                    external_status, metadata_json, agent_id, agent_version_hash,
                    prompt_template_id, prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    candidate_id = excluded.candidate_id,
                    hypothesis_id = excluded.hypothesis_id,
                    adversarial_status = excluded.adversarial_status,
                    replication_status = excluded.replication_status,
                    replication_scope = excluded.replication_scope,
                    distinct_attempt_count = excluded.distinct_attempt_count,
                    required_type_count = excluded.required_type_count,
                    preregistered_count = excluded.preregistered_count,
                    budget_exhausted = excluded.budget_exhausted,
                    attempts_json = excluded.attempts_json,
                    negative_evidence_json = excluded.negative_evidence_json,
                    dataset_statuses_json = excluded.dataset_statuses_json,
                    external_status = excluded.external_status,
                    metadata_json = excluded.metadata_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    report.report_id,
                    report.candidate_id,
                    report.hypothesis_id,
                    report.adversarial_status,
                    report.replication_status,
                    report.replication_scope,
                    report.distinct_attempt_count,
                    report.required_type_count,
                    report.preregistered_count,
                    1 if report.budget_exhausted else 0,
                    _json(attempts_json),
                    _json(report.negative_evidence_json),
                    _json(report.dataset_statuses_json),
                    report.external_status,
                    _json(report.metadata_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def adversarial_reports_by_candidate(
        self,
        candidate_id: str,
    ) -> list[AdversarialReportRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT report_id, candidate_id, hypothesis_id, adversarial_status,
                       replication_status, replication_scope, distinct_attempt_count,
                       required_type_count, preregistered_count, budget_exhausted,
                       attempts_json, negative_evidence_json, dataset_statuses_json,
                       external_status, metadata_json
                FROM adversarial_reports
                WHERE candidate_id = ?
                ORDER BY created_at, rowid
                """,
                (candidate_id,),
            ).fetchall()
        return [
            AdversarialReportRecord(
                report_id=str(row["report_id"]),
                candidate_id=str(row["candidate_id"]),
                hypothesis_id=str(row["hypothesis_id"]),
                adversarial_status=str(row["adversarial_status"]),
                replication_status=str(row["replication_status"]),
                replication_scope=str(row["replication_scope"]),
                distinct_attempt_count=int(row["distinct_attempt_count"]),
                required_type_count=int(row["required_type_count"]),
                preregistered_count=int(row["preregistered_count"]),
                budget_exhausted=bool(row["budget_exhausted"]),
                attempts_json=_dict_json(row["attempts_json"]),
                negative_evidence_json=_dict_json(row["negative_evidence_json"]),
                dataset_statuses_json=_dict_json(row["dataset_statuses_json"]),
                external_status=str(row["external_status"]),
                metadata_json=_dict_json(row["metadata_json"]),
            )
            for row in rows
        ]

    def register_adversarial_candidate_report(
        self,
        report: AdversarialValidationReport,
        *,
        report_path: str,
        provenance: ArtifactProvenance,
        title: str | None = None,
    ) -> None:
        self.record_adversarial_report(report, provenance=provenance)
        self.register_report(
            report_id=report.report_id,
            hypothesis_id=report.hypothesis_id,
            candidate_id=report.candidate_id,
            report_path=report_path,
            external_status=report.external_status,
            title=title or "Adversarial candidate report",
            provenance=provenance,
            metadata={
                "adversarial_status": report.adversarial_status,
                "replication_status": report.replication_status,
                "replication_scope": report.replication_scope,
                "external_status": report.external_status,
                "distinct_attempt_count": report.distinct_attempt_count,
                "required_type_count": report.required_type_count,
                "preregistered_count": report.preregistered_count,
                "budget_exhausted": report.budget_exhausted,
                "negative_evidence_json": report.negative_evidence_json,
                "dataset_statuses_json": report.dataset_statuses_json,
            },
        )

    def register_stable_candidate(
        self,
        entry: StableCandidateRegistryEntry,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO stable_candidate_registry(
                    candidate_id, hypothesis_id, candidate_status, replication_status,
                    replication_scope, adversarial_status, datasets_passed_json,
                    report_path, external_status, registry_json, agent_id,
                    agent_version_hash, prompt_template_id, prompt_template_hash,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    hypothesis_id = excluded.hypothesis_id,
                    candidate_status = excluded.candidate_status,
                    replication_status = excluded.replication_status,
                    replication_scope = excluded.replication_scope,
                    adversarial_status = excluded.adversarial_status,
                    datasets_passed_json = excluded.datasets_passed_json,
                    report_path = excluded.report_path,
                    external_status = excluded.external_status,
                    registry_json = excluded.registry_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    entry.candidate_id,
                    entry.hypothesis_id,
                    entry.candidate_status,
                    entry.replication_status,
                    entry.replication_scope,
                    entry.adversarial_status,
                    _json(entry.datasets_passed_json),
                    entry.report_path,
                    entry.external_status,
                    _json(entry.registry_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    now,
                    now,
                ),
            )

    def stable_candidate_by_id(
        self,
        candidate_id: str,
    ) -> StableCandidateRegistryRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT candidate_id, hypothesis_id, candidate_status, replication_status,
                       replication_scope, adversarial_status, datasets_passed_json,
                       report_path, external_status, registry_json
                FROM stable_candidate_registry
                WHERE candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        return StableCandidateRegistryRecord(
            candidate_id=str(row["candidate_id"]),
            hypothesis_id=str(row["hypothesis_id"]),
            candidate_status=str(row["candidate_status"]),
            replication_status=str(row["replication_status"]),
            replication_scope=str(row["replication_scope"]),
            adversarial_status=str(row["adversarial_status"]),
            datasets_passed_json=_dict_json(row["datasets_passed_json"]),
            report_path=_optional_str(row["report_path"]),
            external_status=str(row["external_status"]),
            registry_json=_dict_json(row["registry_json"]),
        )

    def register_report(
        self,
        *,
        report_id: str,
        report_path: str,
        external_status: str,
        provenance: ArtifactProvenance,
        hypothesis_id: str | None = None,
        candidate_id: str | None = None,
        title: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO reports(
                    report_id, hypothesis_id, candidate_id, report_path,
                    external_status, title, metadata_json, agent_id,
                    agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    hypothesis_id,
                    candidate_id,
                    report_path,
                    external_status,
                    title,
                    _json(metadata or {}),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def report_by_id(self, report_id: str) -> ReportRecord | None:
        reports = self._reports_where("report_id = ?", (report_id,))
        return reports[0] if reports else None

    def record_external_transition_proposal(
        self,
        proposal: ExternalTransitionProposal,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        decided_at = None if proposal.decision == "pending" else utc_now()
        evidence_json = {
            "evidence": [record.model_dump(mode="json") for record in proposal.evidence]
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_external_transitions(
                    proposal_id, report_id, hypothesis_id, candidate_id,
                    current_external_status, target_external_status, confidence,
                    evidence_json, reason, decision, decision_reason, rerun_required,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at, decided_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    report_id = excluded.report_id,
                    hypothesis_id = excluded.hypothesis_id,
                    candidate_id = excluded.candidate_id,
                    current_external_status = excluded.current_external_status,
                    target_external_status = excluded.target_external_status,
                    confidence = excluded.confidence,
                    evidence_json = excluded.evidence_json,
                    reason = excluded.reason,
                    decision = excluded.decision,
                    decision_reason = excluded.decision_reason,
                    rerun_required = excluded.rerun_required,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash,
                    decided_at = excluded.decided_at
                """,
                (
                    proposal.proposal_id,
                    proposal.report_id,
                    proposal.hypothesis_id,
                    proposal.candidate_id,
                    proposal.current_external_status,
                    proposal.target_external_status,
                    proposal.confidence,
                    _json(evidence_json),
                    proposal.reason,
                    proposal.decision,
                    proposal.decision_reason,
                    1 if proposal.rerun_required else 0,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                    decided_at,
                ),
            )

    def external_transition_proposals(
        self,
        *,
        decision: str | None = None,
    ) -> list[ExternalTransitionRecord]:
        if decision is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "decision = ?"
            values = (decision,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT proposal_id, report_id, hypothesis_id, candidate_id,
                       current_external_status, target_external_status, confidence,
                       evidence_json, reason, decision, decision_reason, rerun_required
                FROM pending_external_transitions
                WHERE {where_clause}
                ORDER BY created_at, rowid
                """,
                values,
            ).fetchall()
        return [_external_transition_record(row) for row in rows]

    def decide_external_transition(
        self,
        proposal_id: str,
        *,
        decision: str,
        decision_reason: str,
    ) -> ExternalTransitionRecord:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("external transition decision must be accepted or rejected")
        now = utc_now()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT proposal_id, report_id, candidate_id, target_external_status
                FROM pending_external_transitions
                WHERE proposal_id = ?
                """,
                (proposal_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown external transition proposal: {proposal_id}")
            rerun_required = (
                decision == "accepted"
                and str(row["target_external_status"]) != "unchecked"
            )
            connection.execute(
                """
                UPDATE pending_external_transitions
                SET decision = ?, decision_reason = ?, rerun_required = ?, decided_at = ?
                WHERE proposal_id = ?
                """,
                (decision, decision_reason, 1 if rerun_required else 0, now, proposal_id),
            )
            if decision == "accepted":
                target_external_status = str(row["target_external_status"])
                connection.execute(
                    "UPDATE reports SET external_status = ? WHERE report_id = ?",
                    (target_external_status, str(row["report_id"])),
                )
                candidate_id = _optional_str(row["candidate_id"])
                if candidate_id is not None:
                    connection.execute(
                        """
                        UPDATE stable_candidate_registry
                        SET external_status = ?
                        WHERE candidate_id = ?
                        """,
                        (target_external_status, candidate_id),
                    )
        records = self.external_transition_proposals()
        for record in records:
            if record.proposal_id == proposal_id:
                return record
        raise KeyError(f"external transition proposal disappeared: {proposal_id}")

    def record_external_rerun_request(
        self,
        request: ExternalRerunRequest,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO external_rerun_queue(
                    rerun_id, proposal_id, report_id, hypothesis_id, candidate_id,
                    target_external_status, reason, evidence_ids_json, status,
                    metadata_json, agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rerun_id) DO UPDATE SET
                    proposal_id = excluded.proposal_id,
                    report_id = excluded.report_id,
                    hypothesis_id = excluded.hypothesis_id,
                    candidate_id = excluded.candidate_id,
                    target_external_status = excluded.target_external_status,
                    reason = excluded.reason,
                    evidence_ids_json = excluded.evidence_ids_json,
                    status = excluded.status,
                    metadata_json = excluded.metadata_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    request.rerun_id,
                    request.proposal_id,
                    request.report_id,
                    request.hypothesis_id,
                    request.candidate_id,
                    request.target_external_status,
                    request.reason,
                    _json({"evidence_ids": list(request.evidence_ids)}),
                    request.status,
                    _json(request.metadata_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    now,
                    now,
                ),
            )

    def external_rerun_requests(
        self,
        *,
        status: str | None = None,
    ) -> list[ExternalRerunRecord]:
        if status is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "status = ?"
            values = (status,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT rerun_id, proposal_id, report_id, hypothesis_id, candidate_id,
                       target_external_status, reason, evidence_ids_json, status,
                       metadata_json
                FROM external_rerun_queue
                WHERE {where_clause}
                ORDER BY created_at, rowid
                """,
                values,
            ).fetchall()
        return [_external_rerun_record(row) for row in rows]

    def upsert_report_index_entry(
        self,
        entry: ReportIndexEntry,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO report_search_index(
                    report_id, hypothesis_id, candidate_id, report_path,
                    external_status, title, search_text, metadata_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    hypothesis_id = excluded.hypothesis_id,
                    candidate_id = excluded.candidate_id,
                    report_path = excluded.report_path,
                    external_status = excluded.external_status,
                    title = excluded.title,
                    search_text = excluded.search_text,
                    metadata_json = excluded.metadata_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    entry.report_id,
                    entry.hypothesis_id,
                    entry.candidate_id,
                    entry.report_path,
                    entry.external_status,
                    entry.title,
                    entry.search_text,
                    _json(entry.metadata_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    now,
                ),
            )

    def search_report_index(self, query: str) -> list[ReportIndexRecord]:
        terms = tuple(term.casefold() for term in query.split() if term)
        if not terms:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT report_id, hypothesis_id, candidate_id, report_path,
                       external_status, title, search_text, metadata_json
                FROM report_search_index
                ORDER BY report_id
                """
            ).fetchall()
        records = [_report_index_record(row) for row in rows]
        return [
            record
            for record in records
            if all(term in record.search_text.casefold() for term in terms)
        ]

    def record_dataset_backlog_item(
        self,
        item: DatasetBacklogItem,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO dataset_backlog(
                    backlog_id, dataset_id, reason, source_kind, source_ref,
                    status, priority, metadata_json, agent_id, agent_version_hash,
                    prompt_template_id, prompt_template_hash, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(backlog_id) DO UPDATE SET
                    dataset_id = excluded.dataset_id,
                    reason = excluded.reason,
                    source_kind = excluded.source_kind,
                    source_ref = excluded.source_ref,
                    status = excluded.status,
                    priority = excluded.priority,
                    metadata_json = excluded.metadata_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    item.backlog_id,
                    item.dataset_id,
                    item.reason,
                    item.source_kind,
                    item.source_ref,
                    item.status,
                    item.priority,
                    _json(item.metadata_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    now,
                    now,
                ),
            )

    def dataset_backlog(self, *, status: str | None = None) -> list[DatasetBacklogRecord]:
        if status is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "status = ?"
            values = (status,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT backlog_id, dataset_id, reason, source_kind, source_ref,
                       status, priority, metadata_json
                FROM dataset_backlog
                WHERE {where_clause}
                ORDER BY priority, created_at, rowid
                """,
                values,
            ).fetchall()
        return [_dataset_backlog_record(row) for row in rows]

    def record_operator_digest(
        self,
        digest: OperatorDigest,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO operator_digests(
                    digest_id, digest_type, content, agent_id,
                    agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(digest_id) DO UPDATE SET
                    digest_type = excluded.digest_type,
                    content = excluded.content,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    digest.digest_id,
                    digest.digest_type,
                    digest.content,
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def operator_digests(
        self,
        *,
        digest_type: str | None = None,
    ) -> list[OperatorDigestRecord]:
        if digest_type is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "digest_type = ?"
            values = (digest_type,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT digest_id, digest_type, content
                FROM operator_digests
                WHERE {where_clause}
                ORDER BY created_at, rowid
                """,
                values,
            ).fetchall()
        return [
            OperatorDigestRecord(
                digest_id=str(row["digest_id"]),
                digest_type=str(row["digest_type"]),
                content=str(row["content"]),
            )
            for row in rows
        ]

    def record_maintenance_job(
        self,
        result: MaintenanceJobResult,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO maintenance_jobs(
                    job_id, job_type, status, summary, preserved_audit_records,
                    removed_paths_json, artifacts_json, agent_id, agent_version_hash,
                    prompt_template_id, prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    job_type = excluded.job_type,
                    status = excluded.status,
                    summary = excluded.summary,
                    preserved_audit_records = excluded.preserved_audit_records,
                    removed_paths_json = excluded.removed_paths_json,
                    artifacts_json = excluded.artifacts_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    result.job_id,
                    result.job_type,
                    result.status,
                    result.summary,
                    result.preserved_audit_records,
                    _json({"paths": list(result.removed_paths)}),
                    _json(result.artifacts_json),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def maintenance_jobs(
        self,
        *,
        status: str | None = None,
    ) -> list[MaintenanceJobRecord]:
        if status is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "status = ?"
            values = (status,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT job_id, job_type, status, summary, preserved_audit_records,
                       removed_paths_json, artifacts_json
                FROM maintenance_jobs
                WHERE {where_clause}
                ORDER BY created_at, rowid
                """,
                values,
            ).fetchall()
        return [_maintenance_job_record(row) for row in rows]

    def record_scale_out_profile(
        self,
        profile: ScaleOutProfile,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO scale_out_profiles(
                    profile_id, enabled, worker_count, profile_json,
                    agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    worker_count = excluded.worker_count,
                    profile_json = excluded.profile_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    profile.profile_id,
                    1 if profile.enabled else 0,
                    profile.worker_count,
                    _json(profile.model_dump(mode="json")),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def scale_out_profiles(self) -> list[ScaleOutProfileRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT profile_id, enabled, worker_count, profile_json
                FROM scale_out_profiles
                ORDER BY created_at, rowid
                """
            ).fetchall()
        return [_scale_out_profile_record(row) for row in rows]

    def record_release_readiness_report(
        self,
        report: ReleaseReadinessReport,
        *,
        provenance: ArtifactProvenance,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO release_readiness_reports(
                    report_id, status, completed_phase_count, required_phase_count,
                    report_json, agent_id, agent_version_hash, prompt_template_id,
                    prompt_template_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    status = excluded.status,
                    completed_phase_count = excluded.completed_phase_count,
                    required_phase_count = excluded.required_phase_count,
                    report_json = excluded.report_json,
                    agent_id = excluded.agent_id,
                    agent_version_hash = excluded.agent_version_hash,
                    prompt_template_id = excluded.prompt_template_id,
                    prompt_template_hash = excluded.prompt_template_hash
                """,
                (
                    report.report_id,
                    report.status,
                    report.completed_phase_count,
                    report.required_phase_count,
                    _json(report.model_dump(mode="json")),
                    provenance.agent_id,
                    provenance.agent_version_hash,
                    provenance.prompt_template_id,
                    provenance.prompt_template_hash,
                    utc_now(),
                ),
            )

    def release_readiness_reports(
        self,
        *,
        status: str | None = None,
    ) -> list[ReleaseReadinessRecord]:
        if status is None:
            where_clause = "1 = 1"
            values: tuple[str, ...] = ()
        else:
            where_clause = "status = ?"
            values = (status,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT report_id, status, completed_phase_count,
                       required_phase_count, report_json, agent_id,
                       agent_version_hash, prompt_template_id,
                       prompt_template_hash
                FROM release_readiness_reports
                WHERE {where_clause}
                ORDER BY created_at, rowid
                """,
                values,
            ).fetchall()
        return [_release_readiness_record(row) for row in rows]

    def reports_by_hypothesis(self, hypothesis_id: str) -> list[ReportRecord]:
        return self._reports_where("hypothesis_id = ?", (hypothesis_id,))

    def reports_by_candidate(self, candidate_id: str) -> list[ReportRecord]:
        return self._reports_where("candidate_id = ?", (candidate_id,))

    def reports_by_external_status(self, external_status: str) -> list[ReportRecord]:
        return self._reports_where("external_status = ?", (external_status,))

    def _reports_where(self, where_clause: str, values: Iterable[str]) -> list[ReportRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT report_id, hypothesis_id, candidate_id, report_path,
                       external_status, title, metadata_json
                FROM reports
                WHERE {where_clause}
                ORDER BY created_at, rowid
                """,
                tuple(values),
            ).fetchall()
        return [
            ReportRecord(
                report_id=str(row["report_id"]),
                hypothesis_id=_optional_str(row["hypothesis_id"]),
                candidate_id=_optional_str(row["candidate_id"]),
                report_path=str(row["report_path"]),
                external_status=str(row["external_status"]),
                title=_optional_str(row["title"]),
                metadata_json=_dict_json(row["metadata_json"]),
            )
            for row in rows
        ]


def prompt_template_path(prompt_dir: Path, template_id: str) -> Path:
    if template_id not in PROMPT_TEMPLATE_IDS:
        raise ValueError(f"unknown prompt template id: {template_id}")
    return prompt_dir / f"{template_id}.md"


def prompt_template_hash(prompt_dir: Path, template_id: str) -> str:
    return hashlib.sha256(prompt_template_path(prompt_dir, template_id).read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json(value: JsonValue | Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _dict_json(value: object) -> dict[str, Any]:
    payload = json.loads(str(value))
    if not isinstance(payload, dict):
        raise ValueError("stored JSON payload must decode to an object")
    return payload


def _external_transition_record(row: sqlite3.Row) -> ExternalTransitionRecord:
    return ExternalTransitionRecord(
        proposal_id=str(row["proposal_id"]),
        report_id=str(row["report_id"]),
        hypothesis_id=_optional_str(row["hypothesis_id"]),
        candidate_id=_optional_str(row["candidate_id"]),
        current_external_status=str(row["current_external_status"]),
        target_external_status=str(row["target_external_status"]),
        confidence=float(row["confidence"]),
        evidence_json=_dict_json(row["evidence_json"]),
        reason=str(row["reason"]),
        decision=str(row["decision"]),
        decision_reason=_optional_str(row["decision_reason"]),
        rerun_required=bool(row["rerun_required"]),
    )


def _external_rerun_record(row: sqlite3.Row) -> ExternalRerunRecord:
    return ExternalRerunRecord(
        rerun_id=str(row["rerun_id"]),
        proposal_id=str(row["proposal_id"]),
        report_id=str(row["report_id"]),
        hypothesis_id=_optional_str(row["hypothesis_id"]),
        candidate_id=_optional_str(row["candidate_id"]),
        target_external_status=str(row["target_external_status"]),
        reason=str(row["reason"]),
        evidence_ids_json=_dict_json(row["evidence_ids_json"]),
        status=str(row["status"]),
        metadata_json=_dict_json(row["metadata_json"]),
    )


def _report_index_record(row: sqlite3.Row) -> ReportIndexRecord:
    return ReportIndexRecord(
        report_id=str(row["report_id"]),
        hypothesis_id=_optional_str(row["hypothesis_id"]),
        candidate_id=_optional_str(row["candidate_id"]),
        report_path=str(row["report_path"]),
        external_status=str(row["external_status"]),
        title=_optional_str(row["title"]),
        search_text=str(row["search_text"]),
        metadata_json=_dict_json(row["metadata_json"]),
    )


def _dataset_backlog_record(row: sqlite3.Row) -> DatasetBacklogRecord:
    return DatasetBacklogRecord(
        backlog_id=str(row["backlog_id"]),
        dataset_id=str(row["dataset_id"]),
        reason=str(row["reason"]),
        source_kind=str(row["source_kind"]),
        source_ref=str(row["source_ref"]),
        status=str(row["status"]),
        priority=int(row["priority"]),
        metadata_json=_dict_json(row["metadata_json"]),
    )


def _maintenance_job_record(row: sqlite3.Row) -> MaintenanceJobRecord:
    return MaintenanceJobRecord(
        job_id=str(row["job_id"]),
        job_type=str(row["job_type"]),
        status=str(row["status"]),
        summary=str(row["summary"]),
        preserved_audit_records=int(row["preserved_audit_records"]),
        removed_paths_json=_dict_json(row["removed_paths_json"]),
        artifacts_json=_dict_json(row["artifacts_json"]),
    )


def _scale_out_profile_record(row: sqlite3.Row) -> ScaleOutProfileRecord:
    return ScaleOutProfileRecord(
        profile_id=str(row["profile_id"]),
        enabled=bool(row["enabled"]),
        worker_count=int(row["worker_count"]),
        profile_json=_dict_json(row["profile_json"]),
    )


def _release_readiness_record(row: sqlite3.Row) -> ReleaseReadinessRecord:
    return ReleaseReadinessRecord(
        report_id=str(row["report_id"]),
        status=str(row["status"]),
        completed_phase_count=int(row["completed_phase_count"]),
        required_phase_count=int(row["required_phase_count"]),
        report_json=_dict_json(row["report_json"]),
        agent_id=str(row["agent_id"]),
        agent_version_hash=str(row["agent_version_hash"]),
        prompt_template_id=str(row["prompt_template_id"]),
        prompt_template_hash=str(row["prompt_template_hash"]),
    )
