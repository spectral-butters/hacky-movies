import json

from fastapi.testclient import TestClient

from backend.devin_client import DevinClient
from backend.main import app, get_devin_client


class FakeDevinClient:
    def __init__(self) -> None:
        self.request = None

    def recommend(self, *, prompt, count, context):
        self.request = {"prompt": prompt, "count": count, "context": context}
        return {
            "session_id": "devin-test-session",
            "movies": [
                {
                    "title": "Galaxy Quest",
                    "year": 1999,
                    "genre": "Comedy · Sci-fi",
                    "provider": "JustWatch",
                    "watch_url": "",
                    "hook": "Actors from a cancelled space show face the real thing.",
                }
            ],
        }


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_recommendations_use_devin_and_normalize_movies() -> None:
    fake_client = FakeDevinClient()
    app.dependency_overrides[get_devin_client] = lambda: fake_client
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/recommendations",
                json={
                    "prompt": "Funny science fiction",
                    "count": 1,
                    "context": {
                        "mode": "personal",
                        "liked": ["Palm Springs"],
                        "disliked": [],
                        "watched": [],
                        "excluded": ["The Matrix"],
                    },
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "devin-test-session"
    assert payload["movies"][0] == {
        "id": "galaxy-quest-1999",
        "title": "Galaxy Quest",
        "year": 1999,
        "genre": "Comedy · Sci-fi",
        "provider": "JustWatch",
        "watch_url": "https://www.justwatch.com/us/search?q=Galaxy+Quest",
        "hook": "Actors from a cancelled space show face the real thing.",
        "poster": 1,
    }
    assert fake_client.request["prompt"] == "Funny science fiction"
    assert fake_client.request["context"]["liked"] == ["Palm Springs"]


def test_missing_api_key_returns_service_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("DEVIN_API_KEY", raising=False)
    monkeypatch.delenv("DEVIN_ORG_ID", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/recommendations",
            json={"prompt": "A smart thriller", "count": 1},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "DEVIN_API_KEY is not configured."


def test_missing_org_id_returns_service_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("DEVIN_API_KEY", "test-key")
    monkeypatch.delenv("DEVIN_ORG_ID", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/recommendations",
            json={"prompt": "A smart thriller", "count": 1},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "DEVIN_ORG_ID is not configured."


def test_devin_client_builds_context_prompt_and_reads_structured_output(tmp_path) -> None:
    prompt_path = tmp_path / "master.txt"
    prompt_path.write_text("MASTER MOVIE PROMPT", encoding="utf-8")
    client = DevinClient("test-key", "org-test", prompt_path=prompt_path)

    prompt = client._build_prompt(
        prompt="Warm comedy",
        count=3,
        context={"mode": "round1", "liked": ["About Time"], "excluded": ["Palm Springs"]},
    )
    payload = client._extract_movies(
        {"structured_output": json.dumps({"movies": [{"title": "Galaxy Quest"}]})}
    )

    assert prompt.startswith("MASTER MOVIE PROMPT")
    assert '"viewer_request": "Warm comedy"' in prompt
    assert '"mode": "round1"' in prompt
    assert payload == [{"title": "Galaxy Quest"}]


def test_devin_client_falls_back_to_json_message() -> None:
    client = DevinClient("test-key", "org-test")
    payload = client._extract_movies(
        {
            "structured_output": None,
            "messages": [
                {
                    "origin": "devin",
                    "type": "devin_message",
                    "message": '```json\n{"movies":[{"title":"Arrival"}]}\n```',
                }
            ],
        }
    )

    assert payload == [{"title": "Arrival"}]


def test_devin_client_accepts_structured_output_while_waiting_for_user(
    monkeypatch,
) -> None:
    client = DevinClient("test-key", "org-test", poll_interval=0)
    responses = iter(
        [
            {"session_id": "devin-test"},
            {
                "status": "running",
                "status_detail": "waiting_for_user",
                "structured_output": {"movies": [{"title": "Arrival"}]},
            },
            {"session_id": "devin-test", "is_archived": True},
        ]
    )
    monkeypatch.setattr(client, "_request_json", lambda *args, **kwargs: next(responses))

    result = client.recommend(prompt="Thoughtful sci-fi", count=1, context={})

    assert result == {
        "session_id": "devin-test",
        "movies": [{"title": "Arrival"}],
    }
