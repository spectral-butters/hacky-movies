ALTER TABLE movie_events ADD COLUMN winner_movie_id TEXT;

CREATE TABLE IF NOT EXISTS event_nominations (
    event_id TEXT NOT NULL REFERENCES movie_events(event_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    movie_id TEXT NOT NULL REFERENCES movies(movie_id),
    created_at TEXT NOT NULL,
    PRIMARY KEY(event_id, user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS event_votes (
    event_id TEXT NOT NULL REFERENCES movie_events(event_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    movie_id TEXT NOT NULL REFERENCES movies(movie_id),
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(event_id, user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS event_stage_progress (
    event_id TEXT NOT NULL REFERENCES movie_events(event_id),
    user_id TEXT NOT NULL REFERENCES users(user_id),
    stage TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    PRIMARY KEY(event_id, user_id, stage)
);

CREATE INDEX IF NOT EXISTS idx_nominations_event ON event_nominations(event_id);
CREATE INDEX IF NOT EXISTS idx_votes_event ON event_votes(event_id);
