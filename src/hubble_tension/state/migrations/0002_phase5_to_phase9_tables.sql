CREATE TABLE IF NOT EXISTS fiction_sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    license_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    disabled_reason TEXT,
    consecutive_failed_ab_cycles INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS motif_ab_cycles (
    cycle_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES fiction_sources(source_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generator_health (
    generator_key TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    window_size INTEGER NOT NULL,
    l2_pass_count INTEGER NOT NULL,
    total_count INTEGER NOT NULL,
    rolling_l2_pass_rate REAL NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_motif_ab_cycles_source ON motif_ab_cycles(source_id);
CREATE INDEX IF NOT EXISTS idx_generator_health_status ON generator_health(status);
