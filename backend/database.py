import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = Path(__file__).resolve().parent / "migrations"
DEFAULT_DATABASE_PATH = ROOT / "data" / "reelpick.db"
DEFAULT_USER_ID = "demo-user"


SEEDED_MOVIES = [
    ("palm-springs", "Palm Springs", 2020, "tt9484998", 1, "Comedy · Sci-fi"),
    ("knives-out", "Knives Out", 2019, "tt8946378", 2, "Mystery · Comedy"),
    ("nice-guys", "The Nice Guys", 2016, "tt3799694", 3, "Comedy · Crime"),
    ("game-night", "Game Night", 2018, "tt2704998", 4, "Comedy · Mystery"),
    ("about-time", "About Time", 2013, "tt2194499", 5, "Romance · Sci-fi"),
    (
        "wilderpeople",
        "Hunt for the Wilderpeople",
        2016,
        "tt4698684",
        6,
        "Adventure · Comedy",
    ),
    (
        "everything-everywhere",
        "Everything Everywhere All at Once",
        2022,
        "tt6710474",
        7,
        "Action · Fantasy",
    ),
    ("past-lives", "Past Lives", 2023, "tt13238346", 8, "Drama · Romance"),
    (
        "safety-not-guaranteed",
        "Safety Not Guaranteed",
        2012,
        "tt1862079",
        3,
        "Comedy · Sci-fi",
    ),
    ("the-menu", "The Menu", 2022, "tt9764362", 2, "Thriller · Comedy"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def stable_payload_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class Database:
    def __init__(self, path: Optional[Path] = None) -> None:
        configured = os.getenv("REELPICK_DB_PATH", "").strip()
        if path is not None:
            self.path = path
        elif configured:
            self.path = Path(configured)
        elif Path("/data").is_dir():
            self.path = Path("/data/reelpick.db")
        else:
            self.path = DEFAULT_DATABASE_PATH
        self._write_lock = threading.RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            for migration_path in sorted(MIGRATIONS.glob("*.sql")):
                version = int(migration_path.stem.split("_", 1)[0])
                applied = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?",
                    (version,),
                ).fetchone()
                if applied:
                    continue
                connection.executescript(migration_path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, utc_now()),
                )
            self._seed(connection)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def write_connection(self) -> Iterator[sqlite3.Connection]:
        with self._write_lock:
            with self.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                yield connection

    def _seed(self, connection: sqlite3.Connection) -> None:
        now = utc_now()
        connection.execute(
            """
            INSERT INTO users(user_id, description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (
                DEFAULT_USER_ID,
                "Usually watches with friends and likes witty, inventive movies.",
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO user_memory_state(
                user_id, memory_version, last_processed_feedback_revision,
                readable_summary, updated_at
            ) VALUES (?, 0, 0, '', ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (DEFAULT_USER_ID, now),
        )
        for movie_id, title, year, imdb_id, poster, genre in SEEDED_MOVIES:
            connection.execute(
                """
                INSERT INTO movies(
                    movie_id, title, year, imdb_id, imdb_url, factual_metadata,
                    metadata_provenance, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(movie_id) DO NOTHING
                """,
                (
                    movie_id,
                    title,
                    year,
                    imdb_id,
                    f"https://www.imdb.com/title/{imdb_id}/",
                    json.dumps({"genre": genre, "poster_sprite": poster}),
                    json.dumps({"source": "seeded_demo_catalogue"}),
                    now,
                ),
            )
        self._seed_feedback(connection, now)

    def _seed_feedback(self, connection: sqlite3.Connection, now: str) -> None:
        seeds = [
            ("everything-everywhere", "viewing_status", "watched"),
            ("everything-everywhere", "watched_rating", "liked"),
            ("knives-out", "viewing_status", "watched"),
            ("knives-out", "watched_rating", "liked"),
            ("nice-guys", "viewing_status", "watched"),
            ("nice-guys", "watched_rating", "liked"),
            ("game-night", "viewing_status", "watched"),
            ("game-night", "watched_rating", "disliked"),
            ("about-time", "watchlist", "saved"),
        ]
        for movie_id, dimension, value in seeds:
            feedback_id = f"seed_{movie_id}_{dimension}"
            payload = {
                "movie_id": movie_id,
                "dimension": dimension,
                "value": value,
                "context": "personal",
            }
            connection.execute(
                """
                INSERT INTO feedback_events(
                    feedback_id, user_id, movie_id, dimension, value,
                    source_surface, context, operation, idempotency_key,
                    payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, 'seed', 'personal', 'create', ?, ?, ?)
                ON CONFLICT(feedback_id) DO NOTHING
                """,
                (
                    feedback_id,
                    DEFAULT_USER_ID,
                    movie_id,
                    dimension,
                    value,
                    feedback_id,
                    stable_payload_hash(payload),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO feedback_current(
                    user_id, movie_id, dimension, context, context_id,
                    feedback_id, value, updated_at
                ) VALUES (?, ?, ?, 'personal', '', ?, ?, ?)
                ON CONFLICT(user_id, movie_id, dimension, context, context_id)
                DO NOTHING
                """,
                (DEFAULT_USER_ID, movie_id, dimension, feedback_id, value, now),
            )

    def fetch_one(
        self,
        query: str,
        parameters: Sequence[Any] = (),
    ) -> Optional[Dict[str, Any]]:
        with self.connection() as connection:
            row = connection.execute(query, parameters).fetchone()
        return dict(row) if row else None

    def fetch_all(
        self,
        query: str,
        parameters: Sequence[Any] = (),
    ) -> List[Dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]
