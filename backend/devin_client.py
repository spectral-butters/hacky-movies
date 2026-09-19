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
DEFAULT_MEMORY_PROMPT_PATH = ROOT / "prompts" / "preference_analysis.txt"


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
        org_id: str,
        *,
        base_url: str = "https://api.devin.ai/v3",
        prompt_path: Path = DEFAULT_PROMPT_PATH,
        memory_prompt_path: Path = DEFAULT_MEMORY_PROMPT_PATH,
        poll_interval: float = 2.0,
        session_timeout: float = 150.0,
        request_timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.org_id = org_id
        self.base_url = base_url.rstrip("/")
        self.prompt_path = prompt_path
        self.memory_prompt_path = memory_prompt_path
        self.poll_interval = poll_interval
        self.session_timeout = session_timeout
        self.request_timeout = request_timeout

    @classmethod
    def from_env(cls) -> "DevinClient":
        api_key = os.getenv("DEVIN_API_KEY", "").strip()
        if not api_key:
            raise DevinConfigurationError("DEVIN_API_KEY is not configured.")
        org_id = os.getenv("DEVIN_ORG_ID", "").strip()
        if not org_id:
            raise DevinConfigurationError("DEVIN_ORG_ID is not configured.")

        return cls(
            api_key,
            org_id,
            base_url=os.getenv("DEVIN_API_BASE_URL", "https://api.devin.ai/v3"),
            prompt_path=Path(os.getenv("MOVIE_SEARCH_PROMPT_PATH", str(DEFAULT_PROMPT_PATH))),
            memory_prompt_path=Path(
                os.getenv(
                    "PREFERENCE_ANALYSIS_PROMPT_PATH",
                    str(DEFAULT_MEMORY_PROMPT_PATH),
                )
            ),
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
        session_id, payload = self._run_structured_session(
            prompt=self._build_prompt(prompt=prompt, count=count, context=context),
            title="ReelPick movie search",
            tags=["reelpick", "movie-recommendation"],
            schema=self._output_schema(count),
        )
        recommendations = payload.get("recommendations")
        if not isinstance(recommendations, list):
            raise DevinAPIError("Devin finished without movie recommendations.")
        return {
            "session_id": session_id,
            "interpreted_request": payload.get("interpreted_request", {}),
            "recommendations": recommendations,
        }

    def analyze_preference(
        self,
        *,
        analysis_input: Dict[str, Any],
        minimum_distinct_movies: int,
    ) -> Dict[str, Any]:
        try:
            template = self.memory_prompt_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise DevinConfigurationError(
                f"Preference analysis prompt could not be read at {self.memory_prompt_path}."
            ) from error
        prompt = template.replace(
            "{{minimum_distinct_movies}}",
            str(minimum_distinct_movies),
        ).replace(
            "{{analysis_input}}",
            json.dumps(analysis_input, ensure_ascii=False, indent=2),
        )
        session_id, payload = self._run_structured_session(
            prompt=prompt,
            title="ReelPick preference analysis",
            tags=["reelpick", "preference-analysis"],
            schema=self._memory_output_schema(),
        )
        return {"session_id": session_id, **payload}

    def _run_structured_session(
        self,
        *,
        prompt: str,
        title: str,
        tags: List[str],
        schema: Dict[str, Any],
    ) -> Any:
        session = self._request_json(
            "POST",
            self._sessions_path(),
            {
                "prompt": prompt,
                "title": title,
                "max_acu_limit": 1,
                "knowledge_ids": [],
                "repos": [],
                "resumable": False,
                "secret_ids": [],
                "tags": tags,
                "structured_output_required": True,
                "structured_output_schema": schema,
            },
        )
        session_id = session.get("session_id")
        if not session_id:
            raise DevinAPIError("Devin did not return a session ID.")

        deadline = time.monotonic() + self.session_timeout
        while time.monotonic() < deadline:
            details = self._request_json("GET", f"{self._sessions_path()}/{session_id}")
            status = details.get("status")
            status_detail = details.get("status_detail")
            if details.get("structured_output") is not None or status_detail == "finished":
                payload = self._extract_payload(details)
                try:
                    self._request_json(
                        "POST",
                        f"{self._sessions_path()}/{session_id}/archive",
                    )
                except DevinAPIError:
                    pass
                return session_id, payload
            if status in {"error", "suspended"}:
                reason = status_detail or status
                raise DevinAPIError(
                    f"Devin session stopped with status {reason} before returning output."
                )
            if status_detail in {"waiting_for_user", "waiting_for_approval"}:
                raise DevinAPIError(
                    f"Devin session is {status_detail.replace('_', ' ')} instead of returning output."
                )
            time.sleep(self.poll_interval)

        raise DevinSessionTimeout("Devin took too long to return structured output.")

    def _sessions_path(self) -> str:
        return f"/organizations/{self.org_id}/sessions"

    def _build_prompt(self, *, prompt: str, count: int, context: Dict[str, Any]) -> str:
        try:
            master_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise DevinConfigurationError(
                f"Movie search prompt could not be read at {self.prompt_path}."
            ) from error

        replacements = {
            "{{current_request}}": json.dumps(prompt, ensure_ascii=False),
            "{{user_description}}": json.dumps(
                context.get("user_description", ""), ensure_ascii=False
            ),
            "{{liked_movies}}": json.dumps(
                context.get("liked", []), ensure_ascii=False, indent=2
            ),
            "{{disliked_movies}}": json.dumps(
                context.get("disliked", []), ensure_ascii=False, indent=2
            ),
            "{{already_watched_movies}}": json.dumps(
                context.get("watched", []), ensure_ascii=False, indent=2
            ),
            "{{watchlist_movies}}": json.dumps(
                context.get("watchlist", []), ensure_ascii=False, indent=2
            ),
            "{{preference_memory}}": json.dumps(
                context.get("memory_entries", []), ensure_ascii=False, indent=2
            ),
            "{{excluded_movies}}": json.dumps(
                context.get("excluded", []), ensure_ascii=False, indent=2
            ),
        }
        rendered_prompt = master_prompt
        for placeholder, value in replacements.items():
            rendered_prompt = rendered_prompt.replace(placeholder, value)
        return (
            f"{rendered_prompt}\n\n"
            f"For this API request, return exactly {count} recommendations. "
            "This overrides fixed counts above only for refill requests. "
            "If no additional verified, eligible movies exist, return fewer rather "
            "than inventing candidates. "
            f"The recommendation mode is {json.dumps(context.get('mode', 'personal'))}. "
            "Return only the structured output requested by the API. "
            "Do not ask follow-up questions and do not create or modify files."
        )

    def _output_schema(self, count: int) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["interpreted_request", "recommendations"],
            "properties": {
                "interpreted_request": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["summary", "hard_constraints", "soft_preferences"],
                    "properties": {
                        "summary": {"type": "string"},
                        "hard_constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "soft_preferences": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                "recommendations": {
                    "type": "array",
                    "minItems": 0,
                    "maxItems": count,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "title",
                            "year",
                            "imdb_id",
                            "imdb_url",
                            "match_score",
                            "recommendation_type",
                            "reason",
                            "preference_connections",
                            "possible_mismatch",
                            "in_watchlist",
                        ],
                        "properties": {
                            "title": {"type": "string"},
                            "year": {"type": "integer"},
                            "imdb_id": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "imdb_url": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "match_score": {
                                "type": "integer",
                                "minimum": 70,
                                "maximum": 100,
                            },
                            "recommendation_type": {
                                "type": "string",
                                "enum": [
                                    "strong_match",
                                    "broader_match",
                                    "discovery_pick",
                                ],
                            },
                            "reason": {"type": "string"},
                            "preference_connections": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "possible_mismatch": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "in_watchlist": {"type": "boolean"},
                        },
                    },
                }
            },
        }

    def _memory_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["operations", "summary"],
            "properties": {
                "operations": {
                    "type": "array",
                    "maxItems": 8,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "operation",
                            "entry_id",
                            "dimension",
                            "target",
                            "direction",
                            "strength",
                            "confidence",
                            "context_scope",
                            "context_id",
                            "supporting_feedback_ids",
                            "contradicting_feedback_ids",
                            "evidence_summary",
                        ],
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["add", "revise", "retract", "no_change"],
                            },
                            "entry_id": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "dimension": {"type": "string"},
                            "target": {"type": "string"},
                            "direction": {
                                "type": "string",
                                "enum": ["prefer", "avoid"],
                            },
                            "strength": {
                                "type": "string",
                                "enum": ["soft_preference", "explicit_restriction"],
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["tentative", "supported"],
                            },
                            "context_scope": {
                                "type": "string",
                                "enum": ["general", "session", "event"],
                            },
                            "context_id": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "supporting_feedback_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "contradicting_feedback_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "evidence_summary": {"type": "string"},
                        },
                    },
                },
                "summary": {"type": "string"},
            },
        }

    def _extract_movies(self, details: Dict[str, Any]) -> List[Dict[str, Any]]:
        parsed = self._extract_payload(details)
        if isinstance(parsed.get("recommendations"), list):
            return parsed["recommendations"]
        if isinstance(parsed.get("movies"), list):
            return parsed["movies"]

        raise DevinAPIError("Devin finished without a valid movie recommendation payload.")

    def _extract_payload(self, details: Dict[str, Any]) -> Dict[str, Any]:
        structured_output = details.get("structured_output")
        parsed = self._parse_json_value(structured_output)
        if isinstance(parsed, dict):
            return parsed

        for message in reversed(details.get("messages") or []):
            if message.get("origin") not in {None, "devin"} and message.get("type") != "devin_message":
                continue
            parsed = self._parse_json_value(message.get("message"))
            if isinstance(parsed, dict):
                return parsed

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
