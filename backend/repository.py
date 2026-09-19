import json
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple

from backend.database import (
    DEFAULT_USER_ID,
    Database,
    new_id,
    stable_payload_hash,
    utc_now,
)


class ConflictError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


class ReelPickRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_user(self, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
        now = utc_now()
        with self.database.write_connection() as connection:
            connection.execute(
                """
                INSERT INTO users(user_id, description, created_at, updated_at)
                VALUES (?, '', ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO user_memory_state(
                    user_id, memory_version, last_processed_feedback_revision,
                    readable_summary, updated_at
                ) VALUES (?, 0, 0, '', ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, now),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row)

    def update_user_description(self, user_id: str, description: str) -> None:
        self.ensure_user(user_id)
        with self.database.write_connection() as connection:
            connection.execute(
                "UPDATE users SET description = ?, updated_at = ? WHERE user_id = ?",
                (description.strip(), utc_now(), user_id),
            )

    def get_movie(self, movie_id: str) -> Dict[str, Any]:
        row = self.database.fetch_one(
            "SELECT * FROM movies WHERE movie_id = ?",
            (movie_id,),
        )
        if not row:
            raise NotFoundError("Movie not found.")
        return self._decode_movie(row)

    def list_movies(self) -> List[Dict[str, Any]]:
        return [
            self._decode_movie(row)
            for row in self.database.fetch_all(
                "SELECT * FROM movies ORDER BY title, year"
            )
        ]

    def upsert_recommendation_movie(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        title = str(movie["title"]).strip()
        year = int(movie["year"])
        existing = self.database.fetch_one(
            "SELECT * FROM movies WHERE lower(title) = lower(?) AND year = ?",
            (title, year),
        )
        movie_id = (
            existing["movie_id"]
            if existing
            else f"{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}-{year}"
        )
        imdb_id = movie.get("imdb_id")
        imdb_url = movie.get("imdb_url")
        attributes = {
            "match_score": movie.get("match_score"),
            "recommendation_type": movie.get("recommendation_type"),
            "reason": movie.get("reason"),
            "preference_connections": movie.get("preference_connections", []),
            "possible_mismatch": movie.get("possible_mismatch"),
        }
        provenance = {
            "source": "devin_recommendation",
            "imdb_verified_by_model": bool(imdb_id and imdb_url),
        }
        now = utc_now()
        with self.database.write_connection() as connection:
            connection.execute(
                """
                INSERT INTO movies(
                    movie_id, title, year, imdb_id, imdb_url, factual_metadata,
                    ai_attributes, metadata_provenance, last_updated
                ) VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?)
                ON CONFLICT(movie_id) DO UPDATE SET
                    title = excluded.title,
                    year = excluded.year,
                    imdb_id = COALESCE(excluded.imdb_id, movies.imdb_id),
                    imdb_url = COALESCE(excluded.imdb_url, movies.imdb_url),
                    ai_attributes = excluded.ai_attributes,
                    metadata_provenance = excluded.metadata_provenance,
                    movie_profile_version = movies.movie_profile_version + 1,
                    last_updated = excluded.last_updated
                """,
                (
                    movie_id,
                    title,
                    year,
                    imdb_id,
                    imdb_url,
                    json.dumps(attributes),
                    json.dumps(provenance),
                    now,
                ),
            )
        return self.get_movie(movie_id)

    def get_user_context(self, user_id: str) -> Dict[str, Any]:
        user = self.ensure_user(user_id)
        rows = self.database.fetch_all(
            """
            SELECT fc.dimension, fc.value, m.movie_id, m.title, m.year
            FROM feedback_current fc
            JOIN movies m ON m.movie_id = fc.movie_id
            WHERE fc.user_id = ? AND fc.context = 'personal'
            ORDER BY fc.updated_at DESC
            """,
            (user_id,),
        )
        liked = []
        disliked = []
        watched = []
        watchlist = []
        for row in rows:
            label = f"{row['title']} ({row['year']})"
            if row["dimension"] == "watched_rating" and row["value"] == "liked":
                liked.append(label)
            if row["dimension"] == "watched_rating" and row["value"] == "disliked":
                disliked.append(label)
            if row["dimension"] == "viewing_status" and row["value"] == "watched":
                watched.append(label)
            if row["dimension"] == "watchlist" and row["value"] == "saved":
                watchlist.append(label)
        memory = self.get_memory(user_id)
        return {
            "user_description": user["description"],
            "liked": self._dedupe(liked),
            "disliked": self._dedupe(disliked),
            "watched": self._dedupe(watched),
            "watchlist": self._dedupe(watchlist),
            "memory_version": memory["version"],
            "memory_entries": memory["entries"],
        }

    def create_recommendation_session(
        self,
        *,
        user_id: str,
        prompt: str,
        mode: str,
        event_id: Optional[str],
        memory_version: int,
    ) -> str:
        self.ensure_user(user_id)
        session_id = new_id("session")
        now = utc_now()
        with self.database.write_connection() as connection:
            connection.execute(
                """
                INSERT INTO recommendation_sessions(
                    session_id, user_id, original_prompt, current_prompt,
                    event_id, mode, status, memory_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    prompt,
                    prompt,
                    event_id,
                    mode,
                    memory_version,
                    now,
                    now,
                ),
            )
        return session_id

    def get_recommendation_session(
        self,
        session_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        row = self.database.fetch_one(
            """
            SELECT * FROM recommendation_sessions
            WHERE session_id = ? AND user_id = ?
            """,
            (session_id, user_id),
        )
        if not row:
            raise NotFoundError("Recommendation session not found.")
        row["parsed_intent"] = json.loads(row["parsed_intent"])
        return row

    def recommendation_refill_state(
        self,
        session_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        self.get_recommendation_session(session_id, user_id)
        recommended_rows = self.database.fetch_all(
            """
            SELECT ordered_movie_ids
            FROM recommendation_batches
            WHERE session_id = ?
            ORDER BY created_at
            """,
            (session_id,),
        )
        recommended_ids = []
        for row in recommended_rows:
            recommended_ids.extend(json.loads(row["ordered_movie_ids"]))

        retained_rows = self.database.fetch_all(
            """
            SELECT fc.movie_id
            FROM feedback_current fc
            WHERE fc.user_id = ?
              AND fc.context = 'session'
              AND fc.context_id = ?
              AND fc.dimension = 'recommendation_interest'
              AND fc.value = 'interested'
              AND NOT EXISTS (
                  SELECT 1 FROM feedback_current watched
                  WHERE watched.user_id = fc.user_id
                    AND watched.movie_id = fc.movie_id
                    AND watched.context = 'personal'
                    AND watched.dimension = 'viewing_status'
                    AND watched.value = 'watched'
              )
            """,
            (user_id, session_id),
        )
        retained_ids = [row["movie_id"] for row in retained_rows]
        return {
            "recommended_ids": self._dedupe(recommended_ids),
            "retained_ids": self._dedupe(retained_ids),
            "requested_count": max(0, 5 - len(set(retained_ids))),
        }

    def save_recommendation_batch(
        self,
        *,
        session_id: str,
        requested_count: int,
        movie_ids: List[str],
        retained_ids: List[str],
        exclusions: List[str],
        interpreted_request: Dict[str, Any],
        model_version: str,
        prompt_version: str,
    ) -> str:
        batch_id = new_id("batch")
        with self.database.write_connection() as connection:
            connection.execute(
                """
                INSERT INTO recommendation_batches(
                    batch_id, session_id, requested_count, ordered_movie_ids,
                    retained_shortlist, exclusions, ranking_reasons,
                    model_version, prompt_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    session_id,
                    requested_count,
                    json.dumps(movie_ids),
                    json.dumps(retained_ids),
                    json.dumps(exclusions),
                    json.dumps(interpreted_request),
                    model_version,
                    prompt_version,
                    utc_now(),
                ),
            )
        return batch_id

    def submit_feedback(
        self,
        *,
        user_id: str,
        movie_id: str,
        dimension: str,
        value: str,
        source_surface: str,
        context: str,
        context_id: str,
        idempotency_key: str,
        session_id: Optional[str] = None,
        event_id: Optional[str] = None,
        reason_code: Optional[str] = None,
        reason_text: Optional[str] = None,
        operation: str = "create",
        superseded_feedback_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], bool]:
        self.ensure_user(user_id)
        self.get_movie(movie_id)
        payload = {
            "movie_id": movie_id,
            "dimension": dimension,
            "value": value,
            "source_surface": source_surface,
            "context": context,
            "context_id": context_id,
            "session_id": session_id,
            "event_id": event_id,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "operation": operation,
            "superseded_feedback_id": superseded_feedback_id,
        }
        payload_hash = stable_payload_hash(payload)
        now = utc_now()
        with self.database.write_connection() as connection:
            duplicate = connection.execute(
                """
                SELECT * FROM feedback_events
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
            if duplicate:
                if duplicate["payload_hash"] != payload_hash:
                    raise ConflictError(
                        "Idempotency key was already used with a different payload."
                    )
                return dict(duplicate), False

            current = connection.execute(
                """
                SELECT feedback_id FROM feedback_current
                WHERE user_id = ? AND movie_id = ? AND dimension = ?
                  AND context = ? AND context_id = ?
                """,
                (user_id, movie_id, dimension, context, context_id),
            ).fetchone()
            if operation == "create" and current:
                operation = "replace"
                superseded_feedback_id = current["feedback_id"]

            feedback_id = new_id("feedback")
            connection.execute(
                """
                INSERT INTO feedback_events(
                    feedback_id, user_id, movie_id, session_id, event_id,
                    dimension, value, source_surface, reason_code, reason_text,
                    context, operation, superseded_feedback_id, idempotency_key,
                    payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    user_id,
                    movie_id,
                    session_id,
                    event_id,
                    dimension,
                    value,
                    source_surface,
                    reason_code,
                    reason_text,
                    context,
                    operation,
                    superseded_feedback_id,
                    idempotency_key,
                    payload_hash,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO feedback_current(
                    user_id, movie_id, dimension, context, context_id,
                    feedback_id, value, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, movie_id, dimension, context, context_id)
                DO UPDATE SET
                    feedback_id = excluded.feedback_id,
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    movie_id,
                    dimension,
                    context,
                    context_id,
                    feedback_id,
                    value,
                    now,
                ),
            )
            if dimension == "viewing_status" and value == "watched":
                self._remove_watchlist_in_transaction(
                    connection,
                    user_id=user_id,
                    movie_id=movie_id,
                    source_surface=source_surface,
                    idempotency_key=f"{idempotency_key}:watched-watchlist",
                    now=now,
                )
            if self._should_analyze(dimension, value, context):
                connection.execute(
                    """
                    INSERT INTO analysis_jobs(
                        job_id, user_id, feedback_id, status, next_attempt_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                    ON CONFLICT(feedback_id) DO NOTHING
                    """,
                    (new_id("job"), user_id, feedback_id, now, now, now),
                )
            row = connection.execute(
                "SELECT * FROM feedback_events WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        return dict(row), True

    def undo_feedback(
        self,
        *,
        user_id: str,
        feedback_id: str,
        idempotency_key: str,
    ) -> Tuple[Dict[str, Any], bool]:
        original = self.database.fetch_one(
            """
            SELECT * FROM feedback_events
            WHERE feedback_id = ? AND user_id = ?
            """,
            (feedback_id, user_id),
        )
        if not original:
            raise NotFoundError("Feedback not found.")
        current = self.database.fetch_one(
            """
            SELECT * FROM feedback_current
            WHERE user_id = ? AND movie_id = ? AND dimension = ?
              AND context = ? AND context_id = ?
            """,
            (
                user_id,
                original["movie_id"],
                original["dimension"],
                original["context"],
                self._context_id(original),
            ),
        )
        if not current or current["feedback_id"] != feedback_id:
            raise ConflictError("Newer feedback exists and cannot be undone implicitly.")

        payload = {"undo_feedback_id": feedback_id}
        payload_hash = stable_payload_hash(payload)
        now = utc_now()
        with self.database.write_connection() as connection:
            duplicate = connection.execute(
                """
                SELECT * FROM feedback_events
                WHERE user_id = ? AND idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
            if duplicate:
                if duplicate["payload_hash"] != payload_hash:
                    raise ConflictError(
                        "Idempotency key was already used with a different payload."
                    )
                return dict(duplicate), False
            undo_id = new_id("feedback")
            connection.execute(
                """
                INSERT INTO feedback_events(
                    feedback_id, user_id, movie_id, session_id, event_id,
                    dimension, value, source_surface, reason_code, reason_text,
                    context, operation, superseded_feedback_id, idempotency_key,
                    payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'undo', ?, ?, ?, 'undo', ?, ?, ?, ?)
                """,
                (
                    undo_id,
                    user_id,
                    original["movie_id"],
                    original["session_id"],
                    original["event_id"],
                    original["dimension"],
                    original["value"],
                    original["reason_code"],
                    original["reason_text"],
                    original["context"],
                    feedback_id,
                    idempotency_key,
                    payload_hash,
                    now,
                ),
            )
            previous = None
            if original["superseded_feedback_id"]:
                previous = connection.execute(
                    "SELECT * FROM feedback_events WHERE feedback_id = ?",
                    (original["superseded_feedback_id"],),
                ).fetchone()
            if previous:
                connection.execute(
                    """
                    UPDATE feedback_current
                    SET feedback_id = ?, value = ?, updated_at = ?
                    WHERE user_id = ? AND movie_id = ? AND dimension = ?
                      AND context = ? AND context_id = ?
                    """,
                    (
                        previous["feedback_id"],
                        previous["value"],
                        now,
                        user_id,
                        original["movie_id"],
                        original["dimension"],
                        original["context"],
                        self._context_id(original),
                    ),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM feedback_current
                    WHERE user_id = ? AND movie_id = ? AND dimension = ?
                      AND context = ? AND context_id = ?
                    """,
                    (
                        user_id,
                        original["movie_id"],
                        original["dimension"],
                        original["context"],
                        self._context_id(original),
                    ),
                )
            connection.execute(
                """
                UPDATE preference_memory_entries
                SET status = 'retracted', updated_at = ?
                WHERE user_id = ? AND status = 'active'
                  AND supporting_feedback_ids LIKE ?
                """,
                (now, user_id, f"%{feedback_id}%"),
            )
            row = connection.execute(
                "SELECT * FROM feedback_events WHERE feedback_id = ?",
                (undo_id,),
            ).fetchone()
        return dict(row), True

    def get_current_feedback(self, user_id: str) -> List[Dict[str, Any]]:
        return self.database.fetch_all(
            """
            SELECT fc.*, m.title, m.year
            FROM feedback_current fc
            JOIN movies m ON m.movie_id = fc.movie_id
            WHERE fc.user_id = ?
            ORDER BY fc.updated_at DESC
            """,
            (user_id,),
        )

    def get_analysis_job_for_feedback(
        self,
        feedback_id: str,
    ) -> Optional[Dict[str, Any]]:
        return self.database.fetch_one(
            "SELECT * FROM analysis_jobs WHERE feedback_id = ?",
            (feedback_id,),
        )

    def list_pending_analysis_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.database.fetch_all(
            """
            SELECT * FROM analysis_jobs
            WHERE status IN ('pending', 'retry')
              AND next_attempt_at <= ?
            ORDER BY created_at
            LIMIT ?
            """,
            (utc_now(), limit),
        )

    def get_memory(self, user_id: str) -> Dict[str, Any]:
        self.ensure_user(user_id)
        state = self.database.fetch_one(
            "SELECT * FROM user_memory_state WHERE user_id = ?",
            (user_id,),
        )
        entries = self.database.fetch_all(
            """
            SELECT * FROM preference_memory_entries
            WHERE user_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            """,
            (user_id,),
        )
        for entry in entries:
            entry["supporting_feedback_ids"] = json.loads(
                entry["supporting_feedback_ids"]
            )
            entry["contradicting_feedback_ids"] = json.loads(
                entry["contradicting_feedback_ids"]
            )
        return {
            "version": state["memory_version"],
            "summary": state["readable_summary"],
            "entries": entries,
        }

    def add_explicit_memory(
        self,
        *,
        user_id: str,
        dimension: str,
        target: str,
        direction: str,
        strength: str,
        context_scope: str,
        context_id: Optional[str],
        evidence_summary: str,
    ) -> Dict[str, Any]:
        self.ensure_user(user_id)
        now = utc_now()
        with self.database.write_connection() as connection:
            state = connection.execute(
                "SELECT memory_version FROM user_memory_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            version = state["memory_version"] + 1
            entry_id = new_id("memory")
            connection.execute(
                """
                INSERT INTO preference_memory_entries(
                    entry_id, user_id, dimension, target, direction, source,
                    strength, confidence, context_scope, context_id,
                    evidence_summary, status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'explicit', ?, 'user_confirmed', ?, ?,
                          ?, 'active', ?, ?, ?)
                """,
                (
                    entry_id,
                    user_id,
                    dimension,
                    target,
                    direction,
                    strength,
                    context_scope,
                    context_id,
                    evidence_summary,
                    version,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE user_memory_state
                SET memory_version = ?, readable_summary = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    version,
                    self._memory_summary(connection, user_id),
                    now,
                    user_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM preference_memory_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
        return dict(row)

    def update_memory_status(
        self,
        *,
        user_id: str,
        entry_id: str,
        status: str,
        confirmation: bool = False,
    ) -> Dict[str, Any]:
        now = utc_now()
        with self.database.write_connection() as connection:
            entry = connection.execute(
                """
                SELECT * FROM preference_memory_entries
                WHERE entry_id = ? AND user_id = ?
                """,
                (entry_id, user_id),
            ).fetchone()
            if not entry:
                raise NotFoundError("Memory entry not found.")
            state = connection.execute(
                "SELECT memory_version FROM user_memory_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            version = state["memory_version"] + 1
            confidence = "user_confirmed" if confirmation else entry["confidence"]
            connection.execute(
                """
                UPDATE preference_memory_entries
                SET status = ?, confidence = ?, version = ?, updated_at = ?
                WHERE entry_id = ?
                """,
                (status, confidence, version, now, entry_id),
            )
            connection.execute(
                """
                UPDATE user_memory_state
                SET memory_version = ?, readable_summary = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    version,
                    self._memory_summary(connection, user_id),
                    now,
                    user_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM preference_memory_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
        return dict(row)

    def correct_memory(
        self,
        *,
        user_id: str,
        entry_id: str,
        dimension: str,
        target: str,
        direction: str,
        strength: str,
        context_scope: str,
        context_id: Optional[str],
        evidence_summary: str,
    ) -> Dict[str, Any]:
        now = utc_now()
        with self.database.write_connection() as connection:
            entry = connection.execute(
                """
                SELECT * FROM preference_memory_entries
                WHERE entry_id = ? AND user_id = ?
                """,
                (entry_id, user_id),
            ).fetchone()
            if not entry:
                raise NotFoundError("Memory entry not found.")
            state = connection.execute(
                "SELECT memory_version FROM user_memory_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            version = state["memory_version"] + 1
            connection.execute(
                """
                UPDATE preference_memory_entries
                SET dimension = ?, target = ?, direction = ?, source = 'explicit',
                    strength = ?, confidence = 'user_confirmed',
                    context_scope = ?, context_id = ?, evidence_summary = ?,
                    status = 'active', version = ?, updated_at = ?
                WHERE entry_id = ?
                """,
                (
                    dimension,
                    target,
                    direction,
                    strength,
                    context_scope,
                    context_id,
                    evidence_summary,
                    version,
                    now,
                    entry_id,
                ),
            )
            connection.execute(
                """
                UPDATE user_memory_state
                SET memory_version = ?, readable_summary = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    version,
                    self._memory_summary(connection, user_id),
                    now,
                    user_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM preference_memory_entries WHERE entry_id = ?",
                (entry_id,),
            ).fetchone()
        return dict(row)

    def rebuild_memory(self, user_id: str) -> List[str]:
        now = utc_now()
        with self.database.write_connection() as connection:
            state = connection.execute(
                "SELECT memory_version FROM user_memory_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not state:
                raise NotFoundError("User memory state not found.")
            version = state["memory_version"] + 1
            connection.execute(
                """
                UPDATE preference_memory_entries
                SET status = 'retracted', version = ?, updated_at = ?
                WHERE user_id = ? AND source = 'inferred' AND status = 'active'
                """,
                (version, now, user_id),
            )
            feedback_rows = connection.execute(
                """
                SELECT fe.feedback_id
                FROM feedback_current fc
                JOIN feedback_events fe ON fe.feedback_id = fc.feedback_id
                WHERE fc.user_id = ?
                  AND (
                    (fc.dimension = 'watched_rating'
                     AND fc.value IN ('liked', 'disliked'))
                    OR
                    (fc.dimension = 'recommendation_interest'
                     AND fc.value IN ('interested', 'not_interested'))
                  )
                  AND NOT (
                    fc.context = 'event' AND fc.dimension = 'group_vote'
                  )
                """,
                (user_id,),
            ).fetchall()
            job_ids = []
            for row in feedback_rows:
                existing = connection.execute(
                    "SELECT job_id FROM analysis_jobs WHERE feedback_id = ?",
                    (row["feedback_id"],),
                ).fetchone()
                if existing:
                    job_id = existing["job_id"]
                    connection.execute(
                        """
                        UPDATE analysis_jobs
                        SET status = 'pending', attempt_count = 0,
                            next_attempt_at = ?, last_error = NULL, updated_at = ?
                        WHERE job_id = ?
                        """,
                        (now, now, job_id),
                    )
                else:
                    job_id = new_id("job")
                    connection.execute(
                        """
                        INSERT INTO analysis_jobs(
                            job_id, user_id, feedback_id, status,
                            next_attempt_at, created_at, updated_at
                        ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                        """,
                        (
                            job_id,
                            user_id,
                            row["feedback_id"],
                            now,
                            now,
                            now,
                        ),
                    )
                job_ids.append(job_id)
            connection.execute(
                """
                UPDATE user_memory_state
                SET memory_version = ?, readable_summary = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    version,
                    self._memory_summary(connection, user_id),
                    now,
                    user_id,
                ),
            )
        return job_ids

    def create_event(
        self,
        *,
        host_user_id: str,
        name: str,
        event_date: Optional[str],
        prompt: str,
        invite_base_url: str,
    ) -> Dict[str, Any]:
        self.ensure_user(host_user_id)
        event_id = new_id("event")
        code = self._new_invite_code()
        now = utc_now()
        with self.database.write_connection() as connection:
            connection.execute(
                """
                INSERT INTO movie_events(
                    event_id, invite_code, host_user_id, name, event_date,
                    prompt, status, invite_base_url, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'inviting', ?, ?, ?)
                """,
                (
                    event_id,
                    code,
                    host_user_id,
                    name,
                    event_date,
                    prompt,
                    invite_base_url.rstrip("/"),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO event_participants(
                    event_id, user_id, display_name, role, joined_at
                ) VALUES (?, ?, 'Alex', 'host', ?)
                """,
                (event_id, host_user_id, now),
            )
        return self.get_event(code)

    def get_event(self, invite_code: str) -> Dict[str, Any]:
        event = self.database.fetch_one(
            "SELECT * FROM movie_events WHERE invite_code = ?",
            (invite_code.upper(),),
        )
        if not event:
            raise NotFoundError("Movie night not found.")
        participants = self.database.fetch_all(
            """
            SELECT user_id, display_name, role, joined_at
            FROM event_participants
            WHERE event_id = ?
            ORDER BY joined_at
            """,
            (event["event_id"],),
        )
        event["participants"] = participants
        event["invite_url"] = (
            f"{event['invite_base_url'].rstrip('/')}/join/{event['invite_code']}"
        )
        return event

    def join_event(
        self,
        *,
        invite_code: str,
        user_id: str,
        display_name: str,
    ) -> Dict[str, Any]:
        event = self.get_event(invite_code)
        self.ensure_user(user_id)
        with self.database.write_connection() as connection:
            connection.execute(
                """
                INSERT INTO event_participants(
                    event_id, user_id, display_name, role, joined_at
                ) VALUES (?, ?, ?, 'participant', ?)
                ON CONFLICT(event_id, user_id) DO UPDATE SET
                    display_name = excluded.display_name
                """,
                (event["event_id"], user_id, display_name.strip(), utc_now()),
            )
        return self.get_event(invite_code)

    def bootstrap(self, user_id: str) -> Dict[str, Any]:
        user = self.ensure_user(user_id)
        return {
            "user": user,
            "movies": self.list_movies(),
            "feedback": self.get_current_feedback(user_id),
            "memory": self.get_memory(user_id),
        }

    def _remove_watchlist_in_transaction(
        self,
        connection: Any,
        *,
        user_id: str,
        movie_id: str,
        source_surface: str,
        idempotency_key: str,
        now: str,
    ) -> None:
        current = connection.execute(
            """
            SELECT feedback_id, value FROM feedback_current
            WHERE user_id = ? AND movie_id = ? AND dimension = 'watchlist'
              AND context = 'personal' AND context_id = ''
            """,
            (user_id, movie_id),
        ).fetchone()
        if not current or current["value"] != "saved":
            return
        feedback_id = new_id("feedback")
        payload = {
            "movie_id": movie_id,
            "dimension": "watchlist",
            "value": "not_saved",
            "context": "personal",
        }
        connection.execute(
            """
            INSERT INTO feedback_events(
                feedback_id, user_id, movie_id, dimension, value,
                source_surface, context, operation, superseded_feedback_id,
                idempotency_key, payload_hash, created_at
            ) VALUES (?, ?, ?, 'watchlist', 'not_saved', ?, 'personal',
                      'replace', ?, ?, ?, ?)
            """,
            (
                feedback_id,
                user_id,
                movie_id,
                source_surface,
                current["feedback_id"],
                idempotency_key,
                stable_payload_hash(payload),
                now,
            ),
        )
        connection.execute(
            """
            UPDATE feedback_current
            SET feedback_id = ?, value = 'not_saved', updated_at = ?
            WHERE user_id = ? AND movie_id = ? AND dimension = 'watchlist'
              AND context = 'personal' AND context_id = ''
            """,
            (feedback_id, now, user_id, movie_id),
        )

    def _memory_summary(self, connection: Any, user_id: str) -> str:
        rows = connection.execute(
            """
            SELECT direction, target FROM preference_memory_entries
            WHERE user_id = ? AND status = 'active' AND context_scope = 'general'
            ORDER BY updated_at DESC LIMIT 12
            """,
            (user_id,),
        ).fetchall()
        if not rows:
            return ""
        prefers = [row["target"] for row in rows if row["direction"] == "prefer"]
        avoids = [row["target"] for row in rows if row["direction"] == "avoid"]
        parts = []
        if prefers:
            parts.append(f"Prefers {', '.join(prefers)}")
        if avoids:
            parts.append(f"Avoids {', '.join(avoids)}")
        return ". ".join(parts) + "."

    def _new_invite_code(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if not self.database.fetch_one(
                "SELECT 1 FROM movie_events WHERE invite_code = ?",
                (code,),
            ):
                return code

    @staticmethod
    def _decode_movie(row: Dict[str, Any]) -> Dict[str, Any]:
        decoded = dict(row)
        decoded["factual_metadata"] = json.loads(decoded["factual_metadata"])
        decoded["ai_attributes"] = json.loads(decoded["ai_attributes"])
        decoded["metadata_provenance"] = json.loads(decoded["metadata_provenance"])
        return decoded

    @staticmethod
    def _should_analyze(dimension: str, value: str, context: str) -> bool:
        if context == "event" and dimension == "group_vote":
            return False
        return (
            dimension == "watched_rating" and value in {"liked", "disliked"}
        ) or (
            dimension == "recommendation_interest"
            and value in {"interested", "not_interested"}
        )

    @staticmethod
    def _context_id(event: Dict[str, Any]) -> str:
        if event["context"] == "session":
            return event.get("session_id") or ""
        if event["context"] == "event":
            return event.get("event_id") or ""
        return ""

    @staticmethod
    def _dedupe(values: List[str]) -> List[str]:
        return list(dict.fromkeys(values))
