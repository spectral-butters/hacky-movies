from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import demo
from backend.database import Database
from backend.main import app
from backend.repository import ReelPickRepository


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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_server_default_applies_when_the_client_sends_no_header(client, monkeypatch):
    monkeypatch.setenv("REELPICK_DEMO", "1")

    assert client.get("/api/bootstrap").json()["demo_mode"] is True


def test_an_explicit_header_overrides_the_server_default(client, monkeypatch):
    monkeypatch.setenv("REELPICK_DEMO", "1")

    off = client.get("/api/bootstrap", headers={"X-ReelPick-Demo": "0"})

    assert off.json()["demo_mode"] is False


def test_demo_recommendations_need_no_api_key(client, monkeypatch):
    monkeypatch.setenv("REELPICK_DEMO", "1")
    monkeypatch.setattr(demo, "demo_latency_seconds", lambda: 0.0)

    response = client.post(
        "/api/recommendations",
        json={"prompt": "tense and twisty", "count": 5, "mode": "personal"},
    )

    payload = response.json()
    assert response.status_code == 200, payload
    assert payload["returned_count"] == 5
    assert all(movie["clip_url"].startswith("/demo/clips/") for movie in payload["movies"])


def test_duplicate_nominations_are_collapsed(client, monkeypatch):
    monkeypatch.setenv("REELPICK_DEMO", "1")
    monkeypatch.setattr(demo, "demo_latency_seconds", lambda: 0.0)
    host = {"X-ReelPick-User": "host"}
    guest = {"X-ReelPick-User": "guest"}

    event = client.post(
        "/api/events", json={"name": "Dup Night", "prompt": "Something tense"}, headers=host
    ).json()
    code = event["invite_code"]
    client.post(f"/api/events/{code}/join", json={"display_name": "Guest"}, headers=guest)
    client.post(f"/api/events/{code}/round", json={"status": "round1"}, headers=host)
    nominations = client.post(
        "/api/recommendations",
        json={
            "prompt": "Something tense",
            "count": 5,
            "mode": "event_nomination",
            "event_id": event["event_id"],
        },
        headers=host,
    ).json()
    picks = [movie["id"] for movie in nominations["movies"][:2]]
    client.post(f"/api/events/{code}/nominations", json={"movie_ids": picks}, headers=host)
    client.post(f"/api/events/{code}/nominations", json={"movie_ids": picks}, headers=guest)
    client.post(f"/api/events/{code}/round", json={"status": "round2"}, headers=host)

    state = client.get(f"/api/events/{code}/state", headers=host).json()

    assert state["nominated_movie_ids"] == picks


def test_every_demo_clip_exists_on_disk() -> None:
    entries = demo.load_catalogue()["movies"]

    missing = [entry["file"] for entry in entries if not demo.clip_path(entry["file"])]

    assert missing == []


def test_demo_catalogue_ids_are_well_formed_and_unique() -> None:
    ids = [entry["imdb_id"] for entry in demo.load_catalogue()["movies"]]

    assert all(demo_id is None or demo_id.startswith("tt") for demo_id in ids)
    assert len([i for i in ids if i]) == len({i for i in ids if i})


def test_demo_refill_ignores_lifetime_ratings(monkeypatch) -> None:
    monkeypatch.setattr(demo, "demo_latency_seconds", lambda: 0.0)
    catalogue = demo.load_catalogue()["movies"]
    shown = [f"{entry['title']} ({entry['year']})" for entry in catalogue[:5]]

    result = demo.recommend(
        prompt="anything",
        count=2,
        context={
            "liked": [f"{entry['title']} ({entry['year']})" for entry in catalogue[5:]],
            "disliked": [],
            "watched": [f"{entry['title']} ({entry['year']})" for entry in catalogue],
            "excluded": shown,
        },
    )

    titles = [movie["title"] for movie in result["recommendations"]]
    assert len(titles) == 2
    assert not set(titles) & {entry["title"] for entry in catalogue[:5]}
