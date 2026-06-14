CREATE TABLE IF NOT EXISTS adversarial_queue (
    queue_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS adversarial_reports (
    report_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    adversarial_status TEXT NOT NULL,
    replication_status TEXT NOT NULL,
    replication_scope TEXT NOT NULL,
    distinct_attempt_count INTEGER NOT NULL,
    required_type_count INTEGER NOT NULL,
    preregistered_count INTEGER NOT NULL,
    budget_exhausted INTEGER NOT NULL CHECK (budget_exhausted IN (0, 1)),
    attempts_json TEXT NOT NULL DEFAULT '{}',
    negative_evidence_json TEXT NOT NULL DEFAULT '{}',
    dataset_statuses_json TEXT NOT NULL DEFAULT '{}',
    external_status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stable_candidate_registry (
    candidate_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    candidate_status TEXT NOT NULL,
    replication_status TEXT NOT NULL,
    replication_scope TEXT NOT NULL,
    adversarial_status TEXT NOT NULL,
    datasets_passed_json TEXT NOT NULL DEFAULT '{}',
    report_path TEXT,
    external_status TEXT NOT NULL,
    registry_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_adversarial_queue_status
    ON adversarial_queue(status, priority);
CREATE INDEX IF NOT EXISTS idx_adversarial_queue_candidate
    ON adversarial_queue(candidate_id);
CREATE INDEX IF NOT EXISTS idx_adversarial_reports_candidate
    ON adversarial_reports(candidate_id);
CREATE INDEX IF NOT EXISTS idx_adversarial_reports_status
    ON adversarial_reports(adversarial_status, replication_status);
CREATE INDEX IF NOT EXISTS idx_stable_candidate_registry_status
    ON stable_candidate_registry(candidate_status, adversarial_status, replication_status);
