CREATE TABLE IF NOT EXISTS pending_external_transitions (
    proposal_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    hypothesis_id TEXT,
    candidate_id TEXT,
    current_external_status TEXT NOT NULL,
    target_external_status TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL,
    decision TEXT NOT NULL,
    decision_reason TEXT,
    rerun_required INTEGER NOT NULL CHECK (rerun_required IN (0, 1)),
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS report_search_index (
    report_id TEXT PRIMARY KEY,
    hypothesis_id TEXT,
    candidate_id TEXT,
    report_path TEXT NOT NULL,
    external_status TEXT NOT NULL,
    title TEXT,
    search_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_backlog (
    backlog_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS maintenance_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT NOT NULL,
    preserved_audit_records INTEGER NOT NULL,
    removed_paths_json TEXT NOT NULL DEFAULT '{}',
    artifacts_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scale_out_profiles (
    profile_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    worker_count INTEGER NOT NULL,
    profile_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_external_transitions_report
    ON pending_external_transitions(report_id, decision);
CREATE INDEX IF NOT EXISTS idx_report_search_index_external_status
    ON report_search_index(external_status);
CREATE INDEX IF NOT EXISTS idx_dataset_backlog_status
    ON dataset_backlog(status, priority);
CREATE INDEX IF NOT EXISTS idx_maintenance_jobs_status
    ON maintenance_jobs(status);
