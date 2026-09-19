import json
from typing import Any, Dict, List, Optional

from backend.repository import NotFoundError, ReelPickRepository


class ReelPickReadTools:
    def __init__(
        self,
        repository: ReelPickRepository,
        *,
        user_id: str,
        session_id: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        self.repository = repository
        self.user_id = user_id
        self.session_id = session_id
        self.event_id = event_id
        self.calls = 0
        self.max_calls = 12

    def search_movie_catalogue(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        self._count_call()
        normalized = query.casefold().strip()
        bounded_limit = max(1, min(limit, 50))
        filters = filters or {}
        results = []
        for movie in self.repository.list_movies():
            searchable = " ".join(
                [
                    movie["title"],
                    json.dumps(movie["factual_metadata"]),
                    json.dumps(movie["ai_attributes"]),
                ]
            ).casefold()
            if normalized and normalized not in searchable:
                continue
            if filters.get("year") and movie["year"] != int(filters["year"]):
                continue
            results.append(movie)
            if len(results) >= bounded_limit:
                break
        return results

    def get_movie_profiles(self, movie_ids: List[str]) -> List[Dict[str, Any]]:
        self._count_call()
        profiles = []
        for movie_id in list(dict.fromkeys(movie_ids))[:50]:
            try:
                profiles.append(self.repository.get_movie(movie_id))
            except NotFoundError:
                continue
        return profiles

    def get_user_preference_memory(
        self,
        scope: str = "general",
    ) -> Dict[str, Any]:
        self._count_call()
        memory = self.repository.get_memory(self.user_id)
        memory["entries"] = [
            entry
            for entry in memory["entries"]
            if scope == "all" or entry["context_scope"] == scope
        ][:100]
        return memory

    def get_relevant_feedback(
        self,
        movie_ids: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        self._count_call()
        movie_filter = set(movie_ids or [])
        dimension_filter = set(dimensions or [])
        results = []
        for feedback in self.repository.get_current_feedback(self.user_id):
            if movie_filter and feedback["movie_id"] not in movie_filter:
                continue
            if dimension_filter and feedback["dimension"] not in dimension_filter:
                continue
            results.append(feedback)
            if len(results) >= max(1, min(limit, 100)):
                break
        return results

    def get_session_state(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        self._count_call()
        requested_session_id = session_id or self.session_id
        if not requested_session_id:
            raise NotFoundError("No recommendation session is in scope.")
        session = self.repository.get_recommendation_session(
            requested_session_id,
            self.user_id,
        )
        session["refill"] = self.repository.recommendation_refill_state(
            requested_session_id,
            self.user_id,
        )
        return session

    def get_feedback_event(self, feedback_id: str) -> Dict[str, Any]:
        self._count_call()
        feedback = self.repository.database.fetch_one(
            """
            SELECT * FROM feedback_events
            WHERE feedback_id = ? AND user_id = ?
            """,
            (feedback_id, self.user_id),
        )
        if not feedback:
            raise NotFoundError("Feedback not found.")
        return feedback

    def get_current_movie_feedback(self, movie_id: str) -> List[Dict[str, Any]]:
        self._count_call()
        return [
            feedback
            for feedback in self.repository.get_current_feedback(self.user_id)
            if feedback["movie_id"] == movie_id
        ]

    def _count_call(self) -> None:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError("ReelPick AI tool-call limit exceeded.")
