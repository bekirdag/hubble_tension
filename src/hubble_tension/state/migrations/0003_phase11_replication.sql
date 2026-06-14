CREATE TABLE IF NOT EXISTS replication_queue (
    queue_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    model_family TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replication_reports (
    report_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    replication_status TEXT NOT NULL,
    replication_scope TEXT NOT NULL,
    model_family TEXT NOT NULL,
    independent_code_path TEXT NOT NULL,
    parser_id TEXT NOT NULL,
    fixture_set_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    reference_checks_json TEXT NOT NULL DEFAULT '{}',
    route_on_failure TEXT NOT NULL,
    blocks_stable_candidate INTEGER NOT NULL CHECK (blocks_stable_candidate IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_replication_queue_status
    ON replication_queue(status, priority);
CREATE INDEX IF NOT EXISTS idx_replication_queue_candidate
    ON replication_queue(candidate_id);
CREATE INDEX IF NOT EXISTS idx_replication_reports_candidate
    ON replication_reports(candidate_id);
CREATE INDEX IF NOT EXISTS idx_replication_reports_status
    ON replication_reports(replication_status, replication_scope);
