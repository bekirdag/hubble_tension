CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    local_path TEXT,
    category TEXT,
    source_file TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_extractions (
    extraction_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    method_json TEXT NOT NULL DEFAULT '{}',
    datasets_json TEXT NOT NULL DEFAULT '{}',
    priors_json TEXT NOT NULL DEFAULT '{}',
    results_json TEXT NOT NULL DEFAULT '{}',
    no_go_lessons_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concept_seeds (
    seed_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_ref TEXT,
    concept_text TEXT NOT NULL,
    wildness_level TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prior_art_checks (
    check_id TEXT PRIMARY KEY,
    hypothesis_id TEXT,
    concept_seed_id TEXT REFERENCES concept_seeds(seed_id),
    prior_art_json TEXT NOT NULL DEFAULT '{}',
    verdict TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assumption_sets (
    assumption_set_id TEXT PRIMARY KEY,
    hypothesis_id TEXT,
    assumptions_json TEXT NOT NULL,
    diff_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    parent_hypothesis_id TEXT REFERENCES hypotheses(hypothesis_id),
    root_seed_id TEXT REFERENCES concept_seeds(seed_id),
    concept_seed_id TEXT REFERENCES concept_seeds(seed_id),
    is_root_seed INTEGER NOT NULL DEFAULT 0 CHECK (is_root_seed IN (0, 1)),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'screening_only_local_prior',
    assumption_set_id TEXT REFERENCES assumption_sets(assumption_set_id),
    hypothesis_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (is_root_seed = 1 OR parent_hypothesis_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS formal_models (
    model_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    equations_json TEXT NOT NULL,
    model_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS implementations (
    implementation_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    model_id TEXT REFERENCES formal_models(model_id),
    path TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_url TEXT,
    local_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS constraints (
    constraint_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES datasets(dataset_id),
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    observable TEXT NOT NULL,
    severity TEXT NOT NULL,
    definition_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_state (
    state_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    attempt_id TEXT REFERENCES attempts(attempt_id),
    status TEXT NOT NULL,
    state_path TEXT,
    log_path TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tuning_events (
    tuning_event_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    branch_id TEXT,
    decision TEXT NOT NULL,
    event_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hypothesis_edges (
    edge_id TEXT PRIMARY KEY,
    source_hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    target_hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    edge_type TEXT NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lab_notes (
    note_id TEXT PRIMARY KEY,
    hypothesis_id TEXT REFERENCES hypotheses(hypothesis_id),
    note_type TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lab_head_decisions (
    decision_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    rationale TEXT NOT NULL,
    uncertainty TEXT NOT NULL,
    observation_json TEXT NOT NULL DEFAULT '{}',
    actions_json TEXT NOT NULL DEFAULT '{}',
    next_step TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_log (
    event_id TEXT PRIMARY KEY,
    attempt_id TEXT,
    branch_id TEXT,
    test_id TEXT,
    event_type TEXT NOT NULL,
    reason TEXT,
    status TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    runtime_state_key TEXT REFERENCES runtime_state(state_key),
    attempt_id TEXT,
    run_id TEXT,
    reason TEXT NOT NULL,
    state_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    concept_name TEXT NOT NULL,
    wildness_level TEXT NOT NULL,
    candidate_status TEXT NOT NULL,
    replication_status TEXT NOT NULL,
    replication_scope TEXT NOT NULL DEFAULT 'not_recorded',
    adversarial_status TEXT NOT NULL,
    datasets_passed_json TEXT NOT NULL DEFAULT '{}',
    report_path TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    novelty_profile_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    hypothesis_id TEXT,
    candidate_id TEXT,
    report_path TEXT NOT NULL,
    external_status TEXT NOT NULL,
    title TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_digests (
    digest_id TEXT PRIMARY KEY,
    digest_type TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metric_packets (
    metric_packet_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    packet_json TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version_hash TEXT NOT NULL,
    prompt_template_id TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_log_attempt ON event_log(attempt_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_recorded_at ON checkpoints(recorded_at);
CREATE INDEX IF NOT EXISTS idx_lab_notes_hypothesis ON lab_notes(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_reports_hypothesis ON reports(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_reports_candidate ON reports(candidate_id);
CREATE INDEX IF NOT EXISTS idx_reports_external_status ON reports(external_status);
CREATE INDEX IF NOT EXISTS idx_candidates_hypothesis ON candidates(hypothesis_id);
