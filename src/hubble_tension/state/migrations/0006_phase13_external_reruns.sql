CREATE TABLE IF NOT EXISTS external_rerun_queue (
    rerun_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES pending_external_transitions(proposal_id) ON DELETE CASCADE,
    report_id TEXT NOT NULL,
    hypothesis_id TEXT,
    candidate_id TEXT,
    target_external_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_external_rerun_queue_status
    ON external_rerun_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_external_rerun_queue_report
    ON external_rerun_queue(report_id, status);
