import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "movie_search.txt"


class DevinConfigurationError(RuntimeError):
    pass


class DevinAPIError(RuntimeError):
    pass


class DevinSessionTimeout(TimeoutError):
    pass


class DevinClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.devin.ai/v1",
        prompt_path: Path = DEFAULT_PROMPT_PATH,
        poll_interval: float = 2.0,
        session_timeout: float = 150.0,
        request_timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.prompt_path = prompt_path
        self.poll_interval = poll_interval
        self.session_timeout = session_timeout
        self.request_timeout = request_timeout

    @classmethod
    def from_env(cls) -> "DevinClient":
        api_key = os.getenv("DEVIN_API_KEY", "").strip()
        if not api_key:
            raise DevinConfigurationError("DEVIN_API_KEY is not configured.")

        return cls(
            api_key,
            base_url=os.getenv("DEVIN_API_BASE_URL", "https://api.devin.ai/v1"),
            prompt_path=Path(os.getenv("MOVIE_SEARCH_PROMPT_PATH", str(DEFAULT_PROMPT_PATH))),
            poll_interval=float(os.getenv("DEVIN_POLL_INTERVAL_SECONDS", "2")),
            session_timeout=float(os.getenv("DEVIN_SESSION_TIMEOUT_SECONDS", "150")),
            request_timeout=float(os.getenv("DEVIN_REQUEST_TIMEOUT_SECONDS", "30")),
        )

    def recommend(
        self,
        *,
        prompt: str,
        count: int,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        session = self._request_json(
            "POST",
            "/sessions",
            {
                "prompt": self._build_prompt(prompt=prompt, count=count, context=context),
                "title": "ReelPick movie search",
                "unlisted": True,
                "max_acu_limit": 1,
                "knowledge_ids": [],
                "secret_ids": [],
                "tags": ["reelpick", "movie-recommendation"],
                "structured_output_schema": self._output_schema(count),
            },
        )
        session_id = session.get("session_id")
        if not session_id:
            raise DevinAPIError("Devin did not return a session ID.")

        deadline = time.monotonic() + self.session_timeout
        while time.monotonic() < deadline:
            details = self._request_json("GET", f"/sessions/{session_id}")
            status = details.get("status_enum") or details.get("status")
            if status == "finished":
                return {
                    "session_id": session_id,
                    "movies": self._extract_movies(details),
                }
            if status in {"blocked", "expired"}:
                raise DevinAPIError(f"Devin session {status} before returning recommendations.")
            time.sleep(self.poll_interval)

        raise DevinSessionTimeout("Devin took too long to return movie recommendations.")

    def _build_prompt(self, *, prompt: str, count: int, context: Dict[str, Any]) -> str:
        try:
            master_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise DevinConfigurationError(
                f"Movie search prompt could not be read at {self.prompt_path}."
            ) from error

        request_context = {
            "viewer_request": prompt,
            "recommendation_count": count,
            "mode": context.get("mode", "personal"),
            "liked_movies": context.get("liked", []),
            "disliked_movies": context.get("disliked", []),
            "watched_movies": context.get("watched", []),
            "exclude_movies": context.get("excluded", []),
        }
        return (
            f"{master_prompt}\n\n"
            "REELPICK REQUEST CONTEXT\n"
            f"{json.dumps(request_context, ensure_ascii=False, indent=2)}\n\n"
            "Return only the structured output requested by the API. "
            "Do not ask follow-up questions and do not create or modify files."
        )

    def _output_schema(self, count: int) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["movies"],
            "properties": {
                "movies": {
                    "type": "array",
                    "minItems": count,
                    "maxItems": count,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "title",
                            "year",
                            "genre",
                            "provider",
                            "watch_url",
                            "hook",
                        ],
                        "properties": {
                            "title": {"type": "string"},
                            "year": {"type": "integer"},
                            "genre": {"type": "string"},
                            "provider": {"type": "string"},
                            "watch_url": {"type": "string"},
                            "hook": {"type": "string"},
                        },
                    },
                }
            },
        }

    def _extract_movies(self, details: Dict[str, Any]) -> List[Dict[str, Any]]:
        structured_output = details.get("structured_output")
        parsed = self._parse_json_value(structured_output)
        if isinstance(parsed, dict) and isinstance(parsed.get("movies"), list):
            return parsed["movies"]

        for message in reversed(details.get("messages") or []):
            if message.get("origin") not in {None, "devin"} and message.get("type") != "devin_message":
                continue
            parsed = self._parse_json_value(message.get("message"))
            if isinstance(parsed, dict) and isinstance(parsed.get("movies"), list):
                return parsed["movies"]

        raise DevinAPIError("Devin finished without a valid movie recommendation payload.")

    def _parse_json_value(self, value: Any) -> Optional[Any]:
        if isinstance(value, (dict, list)):
            return value
        if not isinstance(value, str):
            return None

        candidates = [value]
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", value, re.DOTALL)
        if fenced:
            candidates.insert(0, fenced.group(1))
        embedded = re.search(r"(\{.*\})", value, re.DOTALL)
        if embedded:
            candidates.append(embedded.group(1))

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise DevinAPIError(
                f"Devin API returned HTTP {error.code}: {detail[:500]}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise DevinAPIError(f"Could not reach the Devin API: {error}") from error
        except json.JSONDecodeError as error:
            raise DevinAPIError("Devin API returned invalid JSON.") from error
