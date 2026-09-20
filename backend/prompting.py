import json
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import RecommenderConfigurationError

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "movie_search.txt"
DEFAULT_MEMORY_PROMPT_PATH = ROOT / "prompts" / "preference_analysis.txt"


class PromptBuilder:
    prompt_path: Path = DEFAULT_PROMPT_PATH
    memory_prompt_path: Path = DEFAULT_MEMORY_PROMPT_PATH

    def _build_prompt(self, *, prompt: str, count: int, context: Dict[str, Any]) -> str:
        try:
            master_prompt = self.prompt_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise RecommenderConfigurationError(
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
