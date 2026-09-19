CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS movies (
    movie_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    year INTEGER NOT NULL,
    imdb_id TEXT,
    imdb_url TEXT,
    poster_url TEXT,
    short_video_url TEXT,
    factual_metadata TEXT NOT NULL DEFAULT '{}',
    ai_attributes TEXT NOT NULL DEFAULT '{}',
    metadata_provenance TEXT NOT NULL DEFAULT '{}',
    attribute_schema_version INTEGER NOT NULL DEFAULT 1,
    movie_profile_version INTEGER NOT NULL DEFAULT 1,
    last_updated TEXT NOT NULL,
    UNIQUE(title, year)
);

CREATE TABLE IF NOT EXISTS recommendation_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    original_prompt TEXT NOT NULL,
    current_prompt TEXT NOT NULL,
    parsed_intent TEXT NOT NULL DEFAULT '{}',
    event_id TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    memory_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_batches (
    batch_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES recommendation_sessions(session_id),
    requested_count INTEGER NOT NULL,
    ordered_movie_ids TEXT NOT NULL,
    retained_shortlist TEXT NOT NULL DEFAULT '[]',
    exclusions TEXT NOT NULL DEFAULT '[]',
    ranking_reasons TEXT NOT NULL DEFAULT '{}',
    model_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_events (
    feedback_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    movie_id TEXT NOT NULL REFERENCES movies(movie_id),
    session_id TEXT REFERENCES recommendation_sessions(session_id),
    event_id TEXT,
    dimension TEXT NOT NULL,
    value TEXT NOT NULL,
    source_surface TEXT NOT NULL,
    reason_code TEXT,
    reason_text TEXT,
    context TEXT NOT NULL,
    operation TEXT NOT NULL,
    superseded_feedback_id TEXT REFERENCES feedback_events(feedback_id),
    idempotency_key TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS feedback_current (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    movie_id TEXT NOT NULL REFERENCES movies(movie_id),
    dimension TEXT NOT NULL,
    context TEXT NOT NULL,
    context_id TEXT NOT NULL DEFAULT '',
    feedback_id TEXT NOT NULL REFERENCES feedback_events(feedback_id),
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id, movie_id, dimension, context, context_id)
);

CREATE TABLE IF NOT EXISTS preference_memory_entries (
    entry_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    dimension TEXT NOT NULL,
    target TEXT NOT NULL,
    direction TEXT NOT NULL,
    source TEXT NOT NULL,
    strength TEXT NOT NULL,
    confidence TEXT NOT NULL,
    context_scope TEXT NOT NULL,
    context_id TEXT,
    supporting_feedback_ids TEXT NOT NULL DEFAULT '[]',
    contradicting_feedback_ids TEXT NOT NULL DEFAULT '[]',
    evidence_summary TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_memory_state (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id),
    memory_version INTEGER NOT NULL DEFAULT 0,
    last_processed_feedback_revision INTEGER NOT NULL DEFAULT 0,
    readable_summary TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    feedback_id TEXT NOT NULL REFERENCES feedback_events(feedback_id),
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    model_version TEXT,
    prompt_version TEXT,
    tool_outcomes TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(feedback_id)
);

CREATE TABLE IF NOT EXISTS movie_events (
    event_id TEXT PRIMARY KEY,
    invite_code TEXT NOT NULL UNIQUE,
    host_user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL,
    event_date TEXT,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,
    invite_base_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_participants (
    event_id TEXT NOT NULL REFERENCES movie_events(event_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY(event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_user_movie
    ON feedback_events(user_id, movie_id, created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_session
    ON feedback_events(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_user_status
    ON preference_memory_entries(user_id, status, context_scope);
CREATE INDEX IF NOT EXISTS idx_jobs_status
    ON analysis_jobs(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_batches_session
    ON recommendation_batches(session_id, created_at);
