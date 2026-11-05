CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    git_sha TEXT,
    dataset_version TEXT NOT NULL,
    dataset_fingerprint TEXT NOT NULL,
    comparison_key TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    decision TEXT NOT NULL,
    approved_at TEXT,
    run_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS compatible_runs
    ON evaluation_runs (comparison_key, approved_at DESC);

CREATE TABLE IF NOT EXISTS evaluation_cases (
    run_id TEXT NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    repetition INTEGER NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    answer TEXT,
    error TEXT,
    PRIMARY KEY (run_id, case_id, repetition)
);

CREATE TABLE IF NOT EXISTS metric_results (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    repetition INTEGER NOT NULL,
    framework TEXT NOT NULL,
    metric TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL CHECK (score >= -1 AND score <= 1),
    reason TEXT,
    latency_ms REAL NOT NULL,
    cached INTEGER NOT NULL,
    PRIMARY KEY (run_id, case_id, repetition, framework, metric),
    FOREIGN KEY (run_id, case_id, repetition)
        REFERENCES evaluation_cases(run_id, case_id, repetition) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS safety_results (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    repetition INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    marker_seen INTEGER NOT NULL,
    leaked INTEGER NOT NULL,
    false_refusal INTEGER NOT NULL,
    fixture_exposed INTEGER NOT NULL,
    PRIMARY KEY (run_id, case_id, repetition),
    FOREIGN KEY (run_id, case_id, repetition)
        REFERENCES evaluation_cases(run_id, case_id, repetition) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS regression_results (
    run_id TEXT NOT NULL REFERENCES evaluation_runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    baseline_run_id TEXT NOT NULL,
    baseline_score REAL NOT NULL,
    current_score REAL NOT NULL,
    deterioration REAL NOT NULL,
    PRIMARY KEY (run_id, case_id, metric)
);

CREATE TABLE IF NOT EXISTS performance_results (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    repetition INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    retrieval_ms REAL NOT NULL,
    generation_ms REAL NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_usd REAL,
    PRIMARY KEY (run_id, case_id, repetition),
    FOREIGN KEY (run_id, case_id, repetition)
        REFERENCES evaluation_cases(run_id, case_id, repetition) ON DELETE CASCADE
);
