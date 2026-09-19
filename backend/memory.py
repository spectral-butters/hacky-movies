import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.database import Database, new_id, utc_now
from backend.devin_client import DevinAPIError, DevinClient, DevinSessionTimeout


class PreferenceAnalysisWorker:
    _locks_guard = threading.Lock()
    _user_locks: Dict[str, threading.Lock] = {}

    def __init__(
        self,
        database: Database,
        client: DevinClient,
        *,
        minimum_distinct_movies: Optional[int] = None,
        max_attempts: int = 3,
    ) -> None:
        self.database = database
        self.client = client
        self.minimum_distinct_movies = minimum_distinct_movies or int(
            os.getenv("PREFERENCE_MIN_DISTINCT_MOVIES", "3")
        )
        self.max_attempts = max_attempts

    def process_job(self, job_id: str) -> None:
        job = self.database.fetch_one(
            "SELECT * FROM analysis_jobs WHERE job_id = ?",
            (job_id,),
        )
        if not job or job["status"] == "completed":
            return
        lock = self._lock_for_user(job["user_id"])
        with lock:
            self._process_serialized(job_id)

    def _process_serialized(self, job_id: str) -> None:
        for stale_retry in range(2):
            snapshot = self._load_snapshot(job_id)
            if not snapshot:
                return
            try:
                result = self.client.analyze_preference(
                    analysis_input=snapshot["analysis_input"],
                    minimum_distinct_movies=self.minimum_distinct_movies,
                )
                applied = self._apply_result(snapshot, result)
                if applied:
                    return
                if stale_retry == 0:
                    continue
                raise DevinAPIError("Preference memory changed during analysis.")
            except (DevinAPIError, DevinSessionTimeout, ValueError) as error:
                self._record_failure(job_id, str(error))
                return

    def _load_snapshot(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.database.write_connection() as connection:
            job = connection.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job or job["status"] == "completed":
                return None
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'running', attempt_count = attempt_count + 1,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (utc_now(), job_id),
            )
            feedback = connection.execute(
                "SELECT * FROM feedback_events WHERE feedback_id = ?",
                (job["feedback_id"],),
            ).fetchone()
            movie = connection.execute(
                "SELECT * FROM movies WHERE movie_id = ?",
                (feedback["movie_id"],),
            ).fetchone()
            memory_state = connection.execute(
                "SELECT * FROM user_memory_state WHERE user_id = ?",
                (job["user_id"],),
            ).fetchone()
            current_feedback = connection.execute(
                """
                SELECT fe.*, m.title, m.year
                FROM feedback_current fc
                JOIN feedback_events fe ON fe.feedback_id = fc.feedback_id
                JOIN movies m ON m.movie_id = fc.movie_id
                WHERE fc.user_id = ?
                ORDER BY fc.updated_at DESC
                LIMIT 100
                """,
                (job["user_id"],),
            ).fetchall()
            memory_entries = connection.execute(
                """
                SELECT * FROM preference_memory_entries
                WHERE user_id = ?
                ORDER BY updated_at DESC
                LIMIT 100
                """,
                (job["user_id"],),
            ).fetchall()

        return {
            "job": dict(job),
            "memory_version": memory_state["memory_version"],
            "analysis_input": {
                "feedback_event": dict(feedback),
                "movie_profile": self._decode_movie(dict(movie)),
                "active_feedback": [dict(row) for row in current_feedback],
                "preference_memory": [
                    self._decode_memory(dict(row)) for row in memory_entries
                ],
            },
        }

    def _apply_result(
        self,
        snapshot: Dict[str, Any],
        result: Dict[str, Any],
    ) -> bool:
        operations = result.get("operations")
        if not isinstance(operations, list):
            raise ValueError("Preference analysis returned invalid operations.")
        job = snapshot["job"]
        now = utc_now()
        with self.database.write_connection() as connection:
            memory_state = connection.execute(
                "SELECT * FROM user_memory_state WHERE user_id = ?",
                (job["user_id"],),
            ).fetchone()
            if memory_state["memory_version"] != snapshot["memory_version"]:
                connection.execute(
                    "UPDATE analysis_jobs SET status = 'pending', updated_at = ? WHERE job_id = ?",
                    (now, job["job_id"]),
                )
                return False

            valid_feedback = {
                row["feedback_id"]: row
                for row in connection.execute(
                    "SELECT * FROM feedback_events WHERE user_id = ?",
                    (job["user_id"],),
                ).fetchall()
            }
            changed = False
            next_version = memory_state["memory_version"] + 1
            for operation in operations:
                changed = (
                    self._apply_operation(
                        connection,
                        user_id=job["user_id"],
                        operation=operation,
                        valid_feedback=valid_feedback,
                        version=next_version,
                        now=now,
                    )
                    or changed
                )

            revision = connection.execute(
                "SELECT COUNT(*) AS count FROM feedback_events WHERE user_id = ?",
                (job["user_id"],),
            ).fetchone()["count"]
            if changed:
                connection.execute(
                    """
                    UPDATE user_memory_state
                    SET memory_version = ?, last_processed_feedback_revision = ?,
                        readable_summary = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        next_version,
                        revision,
                        self._build_summary(connection, job["user_id"]),
                        now,
                        job["user_id"],
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE user_memory_state
                    SET last_processed_feedback_revision = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (revision, now, job["user_id"]),
                )
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = 'completed', last_error = NULL,
                    model_version = 'devin-v3',
                    prompt_version = 'preference-analysis-v1',
                    tool_outcomes = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (
                    json.dumps(
                        [
                            {
                                "name": "structured_preference_analysis",
                                "outcome": "success",
                                "operation_count": len(operations),
                            }
                        ]
                    ),
                    now,
                    job["job_id"],
                ),
            )
        return True

    def _apply_operation(
        self,
        connection: Any,
        *,
        user_id: str,
        operation: Dict[str, Any],
        valid_feedback: Dict[str, Any],
        version: int,
        now: str,
    ) -> bool:
        operation_name = operation.get("operation")
        if operation_name == "no_change":
            return False
        support = self._validated_ids(
            operation.get("supporting_feedback_ids"), valid_feedback
        )
        contradictions = self._validated_ids(
            operation.get("contradicting_feedback_ids"), valid_feedback
        )
        if not support:
            return False
        context_scope = operation.get("context_scope")
        if context_scope not in {"general", "session", "event"}:
            return False
        support_rows = [valid_feedback[item] for item in support]
        session_only = [
            row for row in support_rows if row["reason_code"] == "not_in_mood"
        ]
        context_id = operation.get("context_id")
        if session_only:
            context_scope = "session"
            context_id = session_only[0]["session_id"]
        if context_scope == "general":
            distinct_movies = {valid_feedback[item]["movie_id"] for item in support}
            explicit_reason = any(
                row["reason_text"] and row["reason_code"] != "not_in_mood"
                for row in support_rows
            )
            if (
                len(distinct_movies) < self.minimum_distinct_movies
                and not explicit_reason
            ):
                return False
        if operation_name == "add":
            rejected = connection.execute(
                """
                SELECT 1 FROM preference_memory_entries
                WHERE user_id = ? AND dimension = ? AND lower(target) = lower(?)
                  AND status = 'user_rejected'
                  AND supporting_feedback_ids = ?
                """,
                (
                    user_id,
                    operation.get("dimension", ""),
                    operation.get("target", ""),
                    json.dumps(support),
                ),
            ).fetchone()
            if rejected:
                return False
            connection.execute(
                """
                INSERT INTO preference_memory_entries(
                    entry_id, user_id, dimension, target, direction, source,
                    strength, confidence, context_scope, context_id,
                    supporting_feedback_ids, contradicting_feedback_ids,
                    evidence_summary, status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'inferred', 'soft_preference', ?, ?, ?,
                          ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    new_id("memory"),
                    user_id,
                    operation.get("dimension", "movie"),
                    operation.get("target", ""),
                    operation.get("direction", "prefer"),
                    operation.get("confidence", "tentative"),
                    context_scope,
                    context_id,
                    json.dumps(support),
                    json.dumps(contradictions),
                    operation.get("evidence_summary", ""),
                    version,
                    now,
                    now,
                ),
            )
            return True
        entry_id = operation.get("entry_id")
        entry = connection.execute(
            """
            SELECT * FROM preference_memory_entries
            WHERE entry_id = ? AND user_id = ?
            """,
            (entry_id, user_id),
        ).fetchone()
        if not entry:
            return False
        if entry["source"] == "explicit":
            return False
        if operation_name == "retract":
            connection.execute(
                """
                UPDATE preference_memory_entries
                SET status = 'retracted', contradicting_feedback_ids = ?,
                    version = ?, updated_at = ?
                WHERE entry_id = ?
                """,
                (json.dumps(contradictions), version, now, entry_id),
            )
            return True
        if operation_name == "revise":
            connection.execute(
                """
                UPDATE preference_memory_entries
                SET dimension = ?, target = ?, direction = ?,
                    strength = 'soft_preference', confidence = ?,
                    context_scope = ?, context_id = ?,
                    supporting_feedback_ids = ?, contradicting_feedback_ids = ?,
                    evidence_summary = ?, version = ?, updated_at = ?
                WHERE entry_id = ?
                """,
                (
                    operation.get("dimension", entry["dimension"]),
                    operation.get("target", entry["target"]),
                    operation.get("direction", entry["direction"]),
                    operation.get("confidence", entry["confidence"]),
                    context_scope,
                    context_id,
                    json.dumps(support),
                    json.dumps(contradictions),
                    operation.get("evidence_summary", entry["evidence_summary"]),
                    version,
                    now,
                    entry_id,
                ),
            )
            return True
        return False

    def _record_failure(self, job_id: str, error: str) -> None:
        with self.database.write_connection() as connection:
            job = connection.execute(
                "SELECT * FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if not job:
                return
            attempts = job["attempt_count"]
            status = "failed" if attempts >= self.max_attempts else "retry"
            delay = min(60, 2 ** max(0, attempts - 1))
            next_attempt = (
                datetime.now(timezone.utc) + timedelta(seconds=delay)
            ).isoformat()
            connection.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, next_attempt_at = ?, last_error = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (status, next_attempt, error[:1000], utc_now(), job_id),
            )

    @classmethod
    def _lock_for_user(cls, user_id: str) -> threading.Lock:
        with cls._locks_guard:
            if user_id not in cls._user_locks:
                cls._user_locks[user_id] = threading.Lock()
            return cls._user_locks[user_id]

    @staticmethod
    def _validated_ids(
        values: Any,
        valid_feedback: Dict[str, Any],
    ) -> List[str]:
        if not isinstance(values, list):
            return []
        return list(
            dict.fromkeys(
                value
                for value in values
                if isinstance(value, str) and value in valid_feedback
            )
        )

    @staticmethod
    def _decode_movie(movie: Dict[str, Any]) -> Dict[str, Any]:
        movie["factual_metadata"] = json.loads(movie["factual_metadata"])
        movie["ai_attributes"] = json.loads(movie["ai_attributes"])
        movie["metadata_provenance"] = json.loads(movie["metadata_provenance"])
        return movie

    @staticmethod
    def _decode_memory(entry: Dict[str, Any]) -> Dict[str, Any]:
        entry["supporting_feedback_ids"] = json.loads(
            entry["supporting_feedback_ids"]
        )
        entry["contradicting_feedback_ids"] = json.loads(
            entry["contradicting_feedback_ids"]
        )
        return entry

    @staticmethod
    def _build_summary(connection: Any, user_id: str) -> str:
        rows = connection.execute(
            """
            SELECT direction, target FROM preference_memory_entries
            WHERE user_id = ? AND status = 'active' AND context_scope = 'general'
            ORDER BY updated_at DESC LIMIT 12
            """,
            (user_id,),
        ).fetchall()
        prefers = [row["target"] for row in rows if row["direction"] == "prefer"]
        avoids = [row["target"] for row in rows if row["direction"] == "avoid"]
        parts = []
        if prefers:
            parts.append(f"Prefers {', '.join(prefers)}")
        if avoids:
            parts.append(f"Avoids {', '.join(avoids)}")
        return ". ".join(parts) + ("." if parts else "")
