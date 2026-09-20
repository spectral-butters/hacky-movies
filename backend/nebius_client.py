import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import (
    RecommenderAPIError,
    RecommenderConfigurationError,
    RecommenderTimeout,
)
from .net import default_ssl_context
from .prompting import (
    DEFAULT_MEMORY_PROMPT_PATH,
    DEFAULT_PROMPT_PATH,
    PromptBuilder,
)

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_MODEL = "Qwen/Qwen3.5-397B-A17B"
SYSTEM_PROMPT = (
    "You are ReelPick's movie recommendation engine. "
    "Follow the instructions in the user message exactly and answer with a "
    "single JSON object that matches the requested schema. "
    "Never add prose, markdown fences or commentary around the JSON."
)


class NebiusClient(PromptBuilder):
    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        prompt_path: Path = DEFAULT_PROMPT_PATH,
        memory_prompt_path: Path = DEFAULT_MEMORY_PROMPT_PATH,
        request_timeout: float = 180.0,
        temperature: float = 0.6,
        max_tokens: int = 4096,
        thinking: bool = False,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.prompt_path = prompt_path
        self.memory_prompt_path = memory_prompt_path
        self.request_timeout = request_timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking = thinking

    @classmethod
    def from_env(cls) -> "NebiusClient":
        api_key = os.getenv("NEBIUS_API_KEY", "").strip()
        if not api_key:
            raise RecommenderConfigurationError("NEBIUS_API_KEY is not configured.")
        return cls(
            api_key,
            model=os.getenv("NEBIUS_MODEL", DEFAULT_MODEL),
            base_url=os.getenv("NEBIUS_API_BASE_URL", DEFAULT_BASE_URL),
            prompt_path=Path(os.getenv("MOVIE_SEARCH_PROMPT_PATH", str(DEFAULT_PROMPT_PATH))),
            memory_prompt_path=Path(
                os.getenv(
                    "PREFERENCE_ANALYSIS_PROMPT_PATH",
                    str(DEFAULT_MEMORY_PROMPT_PATH),
                )
            ),
            request_timeout=float(os.getenv("NEBIUS_REQUEST_TIMEOUT_SECONDS", "180")),
            temperature=float(os.getenv("NEBIUS_TEMPERATURE", "0.6")),
            max_tokens=int(os.getenv("NEBIUS_MAX_TOKENS", "4096")),
            thinking=os.getenv("NEBIUS_THINKING", "off").strip().lower()
            in {"1", "on", "true", "yes"},
        )

    def recommend(
        self,
        *,
        prompt: str,
        count: int,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = self._complete(
            prompt=self._build_prompt(prompt=prompt, count=count, context=context),
            schema=self._output_schema(count),
            schema_name="movie_recommendations",
        )
        recommendations = payload.get("recommendations")
        if not isinstance(recommendations, list):
            raise RecommenderAPIError(
                "The recommendation service finished without movie recommendations."
            )
        return {
            "session_id": None,
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
            raise RecommenderConfigurationError(
                f"Preference analysis prompt could not be read at {self.memory_prompt_path}."
            ) from error
        prompt = template.replace(
            "{{minimum_distinct_movies}}",
            str(minimum_distinct_movies),
        ).replace(
            "{{analysis_input}}",
            json.dumps(analysis_input, ensure_ascii=False, indent=2),
        )
        payload = self._complete(
            prompt=prompt,
            schema=self._memory_output_schema(),
            schema_name="preference_analysis",
        )
        return {"session_id": None, **payload}

    def _complete(
        self,
        *,
        prompt: str,
        schema: Dict[str, Any],
        schema_name: str,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        if not self.thinking:
            body["chat_template_kwargs"] = {"thinking": False, "enable_thinking": False}

        try:
            response = self._post(body)
        except RecommenderAPIError as error:
            if not _is_unsupported_field(error):
                raise
            body.pop("chat_template_kwargs", None)
            body["response_format"] = {"type": "json_object"}
            response = self._post(body)

        content = _message_content(response)
        parsed = self._parse_json_value(content)
        if not isinstance(parsed, dict):
            raise RecommenderAPIError(
                "The recommendation service returned an unreadable answer."
            )
        return parsed

    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(
                request, timeout=self.request_timeout, context=default_ssl_context()
            ) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RecommenderAPIError(
                f"The recommendation service returned HTTP {error.code}: {detail[:500]}"
            ) from error
        except TimeoutError as error:
            raise RecommenderTimeout(
                "The recommendation service took too long to answer."
            ) from error
        except (URLError, OSError) as error:
            raise RecommenderAPIError(
                f"Could not reach the recommendation service: {error}"
            ) from error
        except ValueError as error:
            raise RecommenderAPIError(
                "The recommendation service returned invalid JSON."
            ) from error

    def _parse_json_value(self, value: Any) -> Optional[Any]:
        if isinstance(value, (dict, list)):
            return value
        if not isinstance(value, str):
            return None
        text = value.strip()
        if text.startswith("```"):
            text = text.split("```")[1] if "```" in text[3:] else text.strip("`")
            text = text.removeprefix("json").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None


def _message_content(response: Dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RecommenderAPIError("The recommendation service returned no answer.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise RecommenderAPIError("The recommendation service returned an empty answer.")
    return content


def _is_unsupported_field(error: Exception) -> bool:
    text = str(error).lower()
    return "http 400" in text and (
        "chat_template_kwargs" in text
        or "json_schema" in text
        or "response_format" in text
        or "extra" in text
    )
