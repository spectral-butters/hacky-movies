from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import onboarding
from backend.database import Database
from backend.main import app
from backend.repository import ReelPickRepository


SURVEY_USER = "survey-user"


@pytest.fixture
def repository(tmp_path: Path) -> ReelPickRepository:
    database = Database(tmp_path / "reelpick.db")
    database.initialize()
    return ReelPickRepository(database)


@pytest.fixture
def client(repository, monkeypatch):
    for name in ("DEVIN_API_KEY", "DEVIN_ORG_ID", "NEBIUS_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("backend.main.attach_posters", lambda repo, movies: None)
    monkeypatch.setattr("backend.main.attach_details", lambda repo, movies: None)
    monkeypatch.setattr("backend.main.attach_trailers", lambda repo, movies: None)
    app.state.database = repository.database
    app.state.repository = repository
    app.dependency_overrides.clear()
    with TestClient(app, headers={"X-ReelPick-User": SURVEY_USER}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def react(client, movie_id, rating, index):
    for dimension, value in (("viewing_status", "watched"), ("watched_rating", rating)):
        response = client.post(
            "/api/feedback",
            json={
                "movie_id": movie_id,
                "dimension": dimension,
                "value": value,
                "source_surface": "onboarding",
                "context": "personal",
            },
            headers={"Idempotency-Key": f"onboarding-{movie_id}-{dimension}-{index}"},
        )
        assert response.status_code == 201, response.text


def test_first_round_is_the_broad_calibration_set(client) -> None:
    payload = client.get("/api/onboarding").json()

    assert payload["status"] == "pending"
    assert [movie["title"] for movie in payload["movies"]] == [
        "The Hangover",
        "Gone Girl",
        "Interstellar",
        "The Lord of the Rings: The Fellowship of the Ring",
        "Get Out",
    ]


def test_genres_are_clamped_and_unknown_values_dropped(client) -> None:
    response = client.put(
        "/api/onboarding/genres",
        json={"genres": ["comedy", "horror", "nonsense", "drama", "scifi", "romance"]},
    )

    assert response.json()["genres"] == ["comedy", "horror", "drama", "scifi"]


def test_rounds_never_repeat_a_rated_movie_and_exhaust_the_pool(client) -> None:
    client.put("/api/onboarding/genres", json={"genres": ["comedy", "thriller"]})
    seen = []
    for round_index in range(10):
        payload = client.get("/api/onboarding").json()
        movies = payload["movies"]
        if not movies:
            assert payload["exhausted"] is True
            break
        titles = [movie["title"] for movie in movies]
        assert not set(titles) & set(seen), f"round {round_index} repeated {titles}"
        seen += titles
        for position, movie in enumerate(movies):
            react(client, movie["id"], "disliked" if position == 2 else "liked", round_index)
    assert len(seen) == len(onboarding.CATALOGUE)


def test_enough_signal_requires_likes_and_a_dislike(client) -> None:
    payload = client.get("/api/onboarding").json()
    for position, movie in enumerate(payload["movies"]):
        react(client, movie["id"], "liked", position)

    progress = client.get("/api/onboarding").json()["progress"]
    assert progress["rated"] == 5
    assert progress["likes"] == 5
    assert progress["dislikes"] == 0
    assert progress["enough"] is False


def test_watchlist_action_is_not_counted_as_a_rating(client) -> None:
    movie = client.get("/api/onboarding").json()["movies"][0]
    client.post(
        "/api/feedback",
        json={
            "movie_id": movie["id"],
            "dimension": "watchlist",
            "value": "saved",
            "source_surface": "onboarding",
            "context": "personal",
        },
        headers={"Idempotency-Key": "watchlist-only"},
    )

    progress = client.get("/api/onboarding").json()["progress"]
    assert progress["reacted"] == 1
    assert progress["rated"] == 0


def test_finish_is_reported_by_bootstrap(client) -> None:
    client.post("/api/onboarding/finish", json={"status": "skipped"})

    assert client.get("/api/bootstrap").json()["onboarding"]["status"] == "skipped"


def test_catalogue_reuses_the_seeded_movie_row(client, repository) -> None:
    client.get("/api/onboarding")

    ids = onboarding.catalogue_movie_ids(repository.database)

    assert ids["Knives Out"] == "knives-out"
    assert ids["Everything Everywhere All at Once"] == "everything-everywhere"


def test_movies_already_rated_outside_the_survey_are_not_asked_again(
    client, repository
) -> None:
    client.get("/api/onboarding")
    demo = onboarding.progress(repository.database, "demo-user")

    assert "Knives Out" in demo["reacted_titles"]
    assert demo["likes"] >= 1

    asked = set()
    for _ in range(8):
        movies = client.get(
            "/api/onboarding", headers={"X-ReelPick-User": "demo-user"}
        ).json()["movies"]
        if not movies:
            break
        titles = [movie["title"] for movie in movies]
        asked.update(titles)
        for position, movie in enumerate(movies):
            react(client, movie["id"], "liked", position)
    assert "Knives Out" not in asked
