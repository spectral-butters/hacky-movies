import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import onboarding
from backend.database import SEEDED_MOVIES, Database
from backend.devin_client import DevinAPIError, DevinClient
from backend.main import app, get_devin_client
from backend.memory import PreferenceAnalysisWorker
from backend.repository import ConflictError, NotFoundError, ReelPickRepository
from backend.tools import ReelPickReadTools


RECOMMENDATIONS = [
    ("Galaxy Quest", 1999, "tt0177789"),
    ("Hot Fuzz", 2007, "tt0425112"),
    ("The Death of Stalin", 2017, "tt4686844"),
    ("What We Do in the Shadows", 2014, "tt3416742"),
    ("Best in Show", 2000, "tt0218839"),
]


class FakeDevinClient:
    def __init__(self, returned_count=None) -> None:
        self.request = None
        self.returned_count = returned_count

    def recommend(self, *, prompt, count, context):
        self.request = {"prompt": prompt, "count": count, "context": context}
        size = count if self.returned_count is None else self.returned_count
        movies = []
        for index, (title, year, imdb_id) in enumerate(RECOMMENDATIONS[:size]):
            movies.append(
                {
                    "title": title,
                    "year": year,
                    "imdb_id": imdb_id,
                    "imdb_url": f"https://www.imdb.com/title/{imdb_id}/",
                    "match_score": 94 - index * 4,
                    "recommendation_type": (
                        "strong_match"
                        if index < 3
                        else "broader_match"
                        if index == 3
                        else "discovery_pick"
                    ),
                    "reason": "Matches the requested witty, inventive comedy tone.",
                    "preference_connections": ["Witty comedy"],
                    "possible_mismatch": None,
                    "in_watchlist": False,
                }
            )
        return {
            "session_id": "devin-test-session",
            "interpreted_request": {
                "summary": "Witty comedies",
                "hard_constraints": ["Comedy"],
                "soft_preferences": ["Inventive"],
            },
            "recommendations": movies,
        }


class FakeMemoryClient:
    def __init__(self, operations=None, error=None, delay=0) -> None:
        self.operations = operations or []
        self.error = error
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def analyze_preference(self, *, analysis_input, minimum_distinct_movies):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.error:
                raise self.error
            return {
                "session_id": "memory-session",
                "operations": self.operations,
                "summary": "done",
            }
        finally:
            with self._lock:
                self.active -= 1


@pytest.fixture
def repository(tmp_path: Path) -> ReelPickRepository:
    database = Database(tmp_path / "reelpick.db")
    database.initialize()
    return ReelPickRepository(database)


@pytest.fixture
def client(repository, monkeypatch):
    monkeypatch.delenv("DEVIN_API_KEY", raising=False)
    monkeypatch.delenv("DEVIN_ORG_ID", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setattr("backend.main.attach_posters", lambda repo, movies: None)
    monkeypatch.setattr("backend.main.attach_details", lambda repo, movies: None)
    monkeypatch.setattr("backend.main.attach_trailers", lambda repo, movies: None)
    app.state.database = repository.database
    app.state.repository = repository
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def submit(
    repository,
    *,
    movie_id,
    dimension,
    value,
    key,
    context="personal",
    context_id="",
    session_id=None,
    event_id=None,
    reason_code=None,
    reason_text=None,
):
    return repository.submit_feedback(
        user_id="demo-user",
        movie_id=movie_id,
        dimension=dimension,
        value=value,
        source_surface="test",
        context=context,
        context_id=context_id,
        idempotency_key=key,
        session_id=session_id,
        event_id=event_id,
        reason_code=reason_code,
        reason_text=reason_text,
    )


def test_health_and_bootstrap_are_persistent(client) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    payload = client.get("/api/bootstrap").json()

    catalogue = {movie["movie_id"] for movie in payload["movies"]}
    assert {movie_id for movie_id, *_ in SEEDED_MOVIES} <= catalogue
    assert {
        (entry["title"], entry["year"]) for entry in onboarding.CATALOGUE
    } <= {(movie["title"], movie["year"]) for movie in payload["movies"]}
    assert {item["movie_id"] for item in payload["feedback"] if item["value"] == "saved"} == {
        "about-time"
    }


def test_join_page_uses_root_relative_assets(client) -> None:
    response = client.get("/join/ABC123")

    assert response.status_code == 200
    assert 'href="/styles.css"' in response.text
    assert 'src="/app.js"' in response.text
    assert client.get("/styles.css").headers["content-type"].startswith("text/css")
    assert client.get("/app.js").headers["content-type"].startswith(
        "application/javascript"
    )


def test_recommendations_use_authoritative_backend_context(client) -> None:
    fake_client = FakeDevinClient()
    app.dependency_overrides[get_devin_client] = lambda: fake_client
    response = client.post(
        "/api/recommendations",
        json={
            "prompt": "Funny science fiction",
            "count": 1,
            "context": {
                "liked": ["INJECTED FRONTEND VALUE"],
                "disliked": [],
                "watched": [],
                "excluded": [],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["devin_session_id"] == "devin-test-session"
    assert payload["requested_count"] == 5
    assert fake_client.request["count"] == 5
    assert payload["movies"][0]["id"] == "galaxy-quest-1999"
    assert payload["movies"][0]["imdb_url"] == "https://www.imdb.com/title/tt0177789/"
    assert "INJECTED FRONTEND VALUE" not in fake_client.request["context"]["liked"]
    assert "Knives Out (2019)" in fake_client.request["context"]["liked"]


def test_recommendation_shortfall_is_controlled(client) -> None:
    app.dependency_overrides[get_devin_client] = lambda: FakeDevinClient(
        returned_count=1
    )
    response = client.post(
        "/api/recommendations",
        json={"prompt": "Funny movies", "count": 5},
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 1
    assert response.json()["shortfall_reason"] == (
        "Only 1 verified, eligible recommendations remained."
    )


def test_missing_api_configuration_returns_service_unavailable(client) -> None:
    response = client.post(
        "/api/recommendations",
        json={"prompt": "A smart thriller", "count": 1},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "DEVIN_API_KEY is not configured."


def test_master_prompt_binds_every_authoritative_variable(tmp_path) -> None:
    prompt_path = tmp_path / "master.txt"
    prompt_path.write_text(
        "{{current_request}}|{{user_description}}|{{liked_movies}}|"
        "{{disliked_movies}}|{{already_watched_movies}}|{{watchlist_movies}}|"
        "{{preference_memory}}|{{excluded_movies}}",
        encoding="utf-8",
    )
    client = DevinClient("test-key", "org-test", prompt_path=prompt_path)
    prompt = client._build_prompt(
        prompt="Warm comedy",
        count=3,
        context={
            "user_description": "Watches with friends",
            "liked": ["About Time"],
            "disliked": ["Tenet"],
            "watched": ["Arrival"],
            "watchlist": ["Past Lives"],
            "memory_entries": [{"target": "dry humour"}],
            "excluded": ["Palm Springs"],
            "mode": "round1",
        },
    )

    assert "{{" not in prompt
    for value in (
        "Warm comedy",
        "Watches with friends",
        "About Time",
        "Tenet",
        "Arrival",
        "Past Lives",
        "dry humour",
        "Palm Springs",
    ):
        assert value in prompt
    assert client._output_schema(3)["properties"]["recommendations"]["minItems"] == 0


def test_devin_accepts_structured_output_before_terminal_status(monkeypatch) -> None:
    client = DevinClient("test-key", "org-test", poll_interval=0)
    payload = FakeDevinClient().recommend(prompt="x", count=1, context={})
    responses = iter(
        [
            {"session_id": "devin-test"},
            {
                "status": "running",
                "status_detail": "waiting_for_user",
                "structured_output": {
                    "interpreted_request": payload["interpreted_request"],
                    "recommendations": payload["recommendations"],
                },
            },
            {"session_id": "devin-test", "is_archived": True},
        ]
    )
    monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

    result = client.recommend(prompt="Thoughtful sci-fi", count=1, context={})

    assert result["session_id"] == "devin-test"
    assert result["recommendations"][0]["title"] == "Galaxy Quest"


def test_feed_interest_does_not_mark_movie_watched_or_liked(repository) -> None:
    session_id = repository.create_recommendation_session(
        user_id="demo-user",
        prompt="Comedy",
        mode="personal",
        event_id=None,
        memory_version=0,
    )
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="recommendation_interest",
        value="interested",
        key="interest-1",
        context="session",
        context_id=session_id,
        session_id=session_id,
    )

    current = repository.get_current_feedback("demo-user")
    palm = [item for item in current if item["movie_id"] == "palm-springs"]
    assert {(item["dimension"], item["value"]) for item in palm} == {
        ("recommendation_interest", "interested")
    }
    assert repository.get_analysis_job_for_feedback(feedback["feedback_id"])


@pytest.mark.parametrize("rating", ["liked", "disliked", "neutral"])
def test_watched_rating_is_separate_and_removes_watchlist(repository, rating) -> None:
    submit(
        repository,
        movie_id="about-time",
        dimension="viewing_status",
        value="watched",
        key=f"watched-{rating}",
    )
    submit(
        repository,
        movie_id="about-time",
        dimension="watched_rating",
        value=rating,
        key=f"rating-{rating}",
    )

    current = repository.get_current_feedback("demo-user")
    about_time = [item for item in current if item["movie_id"] == "about-time"]
    states = {(item["dimension"], item["value"]) for item in about_time}
    assert ("viewing_status", "watched") in states
    assert ("watched_rating", rating) in states
    assert ("watchlist", "saved") not in states


def test_idempotency_and_undo_do_not_overwrite_newer_actions(repository) -> None:
    original, created = submit(
        repository,
        movie_id="palm-springs",
        dimension="watchlist",
        value="saved",
        key="same-key",
    )
    duplicate, duplicate_created = submit(
        repository,
        movie_id="palm-springs",
        dimension="watchlist",
        value="saved",
        key="same-key",
    )
    assert created is True
    assert duplicate_created is False
    assert duplicate["feedback_id"] == original["feedback_id"]
    with pytest.raises(ConflictError):
        submit(
            repository,
            movie_id="palm-springs",
            dimension="watchlist",
            value="not_saved",
            key="same-key",
        )

    newer, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="watchlist",
        value="not_saved",
        key="newer-key",
    )
    with pytest.raises(ConflictError):
        repository.undo_feedback(
            user_id="demo-user",
            feedback_id=original["feedback_id"],
            idempotency_key="undo-stale",
        )
    undo, _ = repository.undo_feedback(
        user_id="demo-user",
        feedback_id=newer["feedback_id"],
        idempotency_key="undo-current",
    )
    assert undo["operation"] == "undo"
    current = repository.get_current_feedback("demo-user")
    assert any(
        item["movie_id"] == "palm-springs"
        and item["dimension"] == "watchlist"
        and item["value"] == "saved"
        for item in current
    )


def test_refill_count_uses_retained_unwatched_shortlist(repository) -> None:
    session_id = repository.create_recommendation_session(
        user_id="demo-user",
        prompt="Comedy",
        mode="personal",
        event_id=None,
        memory_version=0,
    )
    batch_movies = [
        "palm-springs",
        "about-time",
        "wilderpeople",
        "safety-not-guaranteed",
        "the-menu",
    ]
    repository.save_recommendation_batch(
        session_id=session_id,
        requested_count=5,
        movie_ids=batch_movies,
        retained_ids=[],
        exclusions=[],
        interpreted_request={},
        model_version="test",
        prompt_version="test",
    )
    for index, movie_id in enumerate(batch_movies[:2]):
        submit(
            repository,
            movie_id=movie_id,
            dimension="recommendation_interest",
            value="interested",
            key=f"retain-{index}",
            context="session",
            context_id=session_id,
            session_id=session_id,
        )

    assert repository.recommendation_refill_state(session_id, "demo-user")[
        "requested_count"
    ] == 3
    submit(
        repository,
        movie_id="palm-springs",
        dimension="viewing_status",
        value="watched",
        key="watched-retained",
    )
    assert repository.recommendation_refill_state(session_id, "demo-user")[
        "requested_count"
    ] == 4


def test_group_votes_do_not_change_general_taste(repository) -> None:
    event = repository.create_event(
        host_user_id="demo-user",
        name="Friday",
        event_date=None,
        prompt="Comedy",
        invite_base_url="https://example.com",
    )
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="group_vote",
        value="like",
        key="group-vote",
        context="event",
        context_id=event["event_id"],
        event_id=event["event_id"],
    )

    assert repository.get_analysis_job_for_feedback(feedback["feedback_id"]) is None
    assert repository.get_memory("demo-user")["entries"] == []


def test_event_link_and_join_are_persistent(repository) -> None:
    event = repository.create_event(
        host_user_id="demo-user",
        name="Friday",
        event_date="2026-09-25",
        prompt="Comedy",
        invite_base_url="https://reelpick.example",
    )
    repository.join_event(
        invite_code=event["invite_code"],
        user_id="guest-user",
        display_name="Guest",
    )
    reloaded = ReelPickRepository(Database(repository.database.path)).get_event(
        event["invite_code"]
    )

    assert event["invite_url"].endswith(f"/join/{event['invite_code']}")
    assert {participant["display_name"] for participant in reloaded["participants"]} == {
        "Alex",
        "Guest",
    }


def test_conservative_inference_requires_three_movies(repository) -> None:
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="watched_rating",
        value="disliked",
        key="weak-signal",
    )
    job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    fake = FakeMemoryClient(
        [
            memory_operation(
                feedback["feedback_id"],
                target="time-loop movies",
            )
        ]
    )
    PreferenceAnalysisWorker(repository.database, fake).process_job(job["job_id"])

    assert repository.get_memory("demo-user")["entries"] == []


def test_explicit_actor_reason_can_create_specific_memory(repository) -> None:
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="watched_rating",
        value="disliked",
        key="actor-reason",
        reason_code="cast",
        reason_text="I do not enjoy Andy Samberg.",
    )
    job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    fake = FakeMemoryClient(
        [
            memory_operation(
                feedback["feedback_id"],
                dimension="actor",
                target="Andy Samberg",
                direction="avoid",
            )
        ]
    )
    PreferenceAnalysisWorker(repository.database, fake).process_job(job["job_id"])

    entry = repository.get_memory("demo-user")["entries"][0]
    assert entry["dimension"] == "actor"
    assert entry["target"] == "Andy Samberg"
    assert entry["source"] == "inferred"


def test_not_in_mood_reason_is_forced_to_session_scope(repository) -> None:
    session_id = repository.create_recommendation_session(
        user_id="demo-user",
        prompt="Comedy",
        mode="personal",
        event_id=None,
        memory_version=0,
    )
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="recommendation_interest",
        value="not_interested",
        key="not-tonight",
        context="session",
        context_id=session_id,
        session_id=session_id,
        reason_code="not_in_mood",
        reason_text="Not tonight.",
    )
    job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    fake = FakeMemoryClient(
        [memory_operation(feedback["feedback_id"], target="comedies")]
    )
    PreferenceAnalysisWorker(repository.database, fake).process_job(job["job_id"])

    entry = repository.get_memory("demo-user")["entries"][0]
    assert entry["context_scope"] == "session"
    assert entry["context_id"] == session_id


def test_contradictory_evidence_can_retract_inferred_memory(repository) -> None:
    first, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="watched_rating",
        value="disliked",
        key="first-actor",
        reason_code="cast",
        reason_text="I dislike this actor.",
    )
    first_job = repository.get_analysis_job_for_feedback(first["feedback_id"])
    add_client = FakeMemoryClient(
        [
            memory_operation(
                first["feedback_id"],
                dimension="actor",
                target="Andy Samberg",
                direction="avoid",
            )
        ]
    )
    worker = PreferenceAnalysisWorker(repository.database, add_client)
    worker.process_job(first_job["job_id"])
    entry = repository.get_memory("demo-user")["entries"][0]

    second, _ = submit(
        repository,
        movie_id="nice-guys",
        dimension="watched_rating",
        value="liked",
        key="contradiction",
        reason_code="cast",
        reason_text="I like this cast.",
    )
    second_job = repository.get_analysis_job_for_feedback(second["feedback_id"])
    retract_client = FakeMemoryClient(
        [
            {
                **memory_operation(second["feedback_id"]),
                "operation": "retract",
                "entry_id": entry["entry_id"],
                "contradicting_feedback_ids": [second["feedback_id"]],
            }
        ]
    )
    PreferenceAnalysisWorker(repository.database, retract_client).process_job(
        second_job["job_id"]
    )

    stored = repository.database.fetch_one(
        "SELECT status FROM preference_memory_entries WHERE entry_id = ?",
        (entry["entry_id"],),
    )
    assert stored["status"] == "retracted"


def test_rejected_inference_does_not_reappear_from_same_evidence(repository) -> None:
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="watched_rating",
        value="disliked",
        key="reject-me",
        reason_code="cast",
        reason_text="I dislike this actor.",
    )
    job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    operation = memory_operation(
        feedback["feedback_id"],
        dimension="actor",
        target="Andy Samberg",
        direction="avoid",
    )
    fake = FakeMemoryClient([operation])
    worker = PreferenceAnalysisWorker(repository.database, fake)
    worker.process_job(job["job_id"])
    entry = repository.get_memory("demo-user")["entries"][0]
    repository.update_memory_status(
        user_id="demo-user",
        entry_id=entry["entry_id"],
        status="user_rejected",
    )
    rebuilt_jobs = repository.rebuild_memory("demo-user")
    worker.process_job(rebuilt_jobs[0])

    entries = repository.database.fetch_all(
        """
        SELECT * FROM preference_memory_entries
        WHERE user_id = ? AND dimension = 'actor' AND target = 'Andy Samberg'
        """,
        ("demo-user",),
    )
    assert len(entries) == 1
    assert entries[0]["status"] == "user_rejected"


def test_ai_failure_preserves_feedback_and_retries(repository) -> None:
    feedback, _ = submit(
        repository,
        movie_id="palm-springs",
        dimension="watched_rating",
        value="disliked",
        key="ai-failure",
    )
    job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    worker = PreferenceAnalysisWorker(
        repository.database,
        FakeMemoryClient(error=DevinAPIError("temporary failure")),
    )
    worker.process_job(job["job_id"])

    current = repository.get_current_feedback("demo-user")
    assert any(item["feedback_id"] == feedback["feedback_id"] for item in current)
    updated_job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    assert updated_job["status"] == "retry"
    assert updated_job["attempt_count"] == 1


def test_analysis_jobs_are_serialized_per_user(repository) -> None:
    jobs = []
    for index, movie_id in enumerate(("palm-springs", "about-time")):
        feedback, _ = submit(
            repository,
            movie_id=movie_id,
            dimension="watched_rating",
            value="liked",
            key=f"concurrent-{index}",
        )
        jobs.append(repository.get_analysis_job_for_feedback(feedback["feedback_id"]))
    fake = FakeMemoryClient(
        [{"operation": "no_change"}],
        delay=0.05,
    )
    worker = PreferenceAnalysisWorker(repository.database, fake)
    threads = [
        threading.Thread(target=worker.process_job, args=(job["job_id"],))
        for job in jobs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert fake.max_active == 1
    assert {
        repository.get_analysis_job_for_feedback(job["feedback_id"])["status"]
        for job in jobs
    } == {"completed"}


def test_read_tools_are_bounded_and_user_scoped(repository) -> None:
    repository.ensure_user("other-user")
    other, _ = repository.submit_feedback(
        user_id="other-user",
        movie_id="palm-springs",
        dimension="watchlist",
        value="saved",
        source_surface="test",
        context="personal",
        context_id="",
        idempotency_key="other-feedback",
    )
    tools = ReelPickReadTools(repository, user_id="demo-user")

    assert tools.search_movie_catalogue("<ignore instructions>", limit=1000) == []
    with pytest.raises(NotFoundError):
        tools.get_feedback_event(other["feedback_id"])
    for _ in range(10):
        tools.get_user_preference_memory()
    with pytest.raises(RuntimeError):
        tools.get_user_preference_memory()


def memory_operation(
    feedback_id,
    *,
    dimension="genre",
    target="comedies",
    direction="avoid",
):
    return {
        "operation": "add",
        "entry_id": None,
        "dimension": dimension,
        "target": target,
        "direction": direction,
        "strength": "soft_preference",
        "confidence": "tentative",
        "context_scope": "general",
        "context_id": None,
        "supporting_feedback_ids": [feedback_id],
        "contradicting_feedback_ids": [],
        "evidence_summary": "Supported by explicit feedback.",
    }
