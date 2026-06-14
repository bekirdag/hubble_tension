CREATE TABLE IF NOT EXISTS release_readiness_reports (
    report_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    completed_phase_count INTEGER NOT NULL,
    required_phase_count INTEGER NOT NULL,
    report_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_release_readiness_reports_status
    ON release_readiness_reports(status, created_at);
