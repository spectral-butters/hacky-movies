import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
CLIP_DIR = Path(os.getenv("REELPICK_DEMO_CLIP_DIR", str(ROOT / "demo")))
CATALOGUE_PATH = Path(
    os.getenv("REELPICK_DEMO_CATALOGUE", str(CLIP_DIR / "catalogue.json"))
)
CLIP_ROUTE = "/demo/clips"
TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}
YEAR_SUFFIX = re.compile(r"\s+\(\d{4}\)$")


class DemoCatalogueError(RuntimeError):
    pass


def demo_default() -> bool:
    return os.getenv("REELPICK_DEMO", "").strip().lower() in TRUTHY


def demo_latency_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("REELPICK_DEMO_LATENCY_SECONDS", "2")))
    except ValueError:
        return 2.0


def resolve_demo_mode(header_value: Optional[str]) -> bool:
    token = (header_value or "").strip().lower()
    if token in TRUTHY:
        return True
    if token in FALSY:
        return False
    return demo_default()


def load_catalogue() -> Dict[str, Any]:
    try:
        payload = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DemoCatalogueError(
            f"Demo catalogue could not be read at {CATALOGUE_PATH}."
        ) from error
    entries = payload.get("movies")
    if not isinstance(entries, list) or not entries:
        raise DemoCatalogueError("Demo catalogue contains no movies.")
    return payload


def clip_path(filename: str) -> Optional[Path]:
    candidate = (CLIP_DIR / filename).resolve()
    if CLIP_DIR.resolve() not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def recommend(
    *,
    prompt: str,
    count: int,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """The demo reel is a fixed eight-clip loop.

    Only titles already shown in this session are withheld. Lifetime ratings are
    ignored on purpose: the catalogue is too small to survive them, and a demo
    that degrades with account history is worse than useless on stage.
    """
    catalogue = load_catalogue()
    time.sleep(demo_latency_seconds())
    seen = _seen_titles(context.get("excluded", []))
    picks: List[Dict[str, Any]] = []
    for entry in catalogue["movies"]:
        if len(picks) == count:
            break
        if str(entry["title"]).casefold() in seen:
            continue
        if not clip_path(entry["file"]):
            continue
        picks.append(_as_recommendation(entry))
    return {
        "session_id": f"demo-{uuid.uuid4()}",
        "interpreted_request": catalogue.get("interpreted_request", {}),
        "recommendations": picks,
    }


def _seen_titles(labels: Iterable[str]) -> set:
    return {YEAR_SUFFIX.sub("", str(label)).casefold() for label in labels}


def _as_recommendation(entry: Dict[str, Any]) -> Dict[str, Any]:
    imdb_id = entry.get("imdb_id")
    return {
        "title": entry["title"],
        "year": entry["year"],
        "imdb_id": imdb_id,
        "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None,
        "reason": entry["reason"],
        "match_score": entry.get("match_score", 80),
        "recommendation_type": entry.get("recommendation_type", "strong_match"),
        "preference_connections": entry.get("preference_connections", []),
        "possible_mismatch": entry.get("possible_mismatch"),
        "genre": entry.get("genre", "Movie"),
        "clip_url": f"{CLIP_ROUTE}/{quote(entry['file'])}",
    }
