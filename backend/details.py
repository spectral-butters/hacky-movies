import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional

from .imdb import graphql

IMDB_ID_PATTERN = re.compile(r"tt\d{7,10}")
MAX_PARALLEL_LOOKUPS = 5
MAX_CAST = 4
MAX_GENRES = 3
DETAILS_QUERY = """
query Details($id: ID!) {
  title(id: $id) {
    runtime { seconds }
    plot { plotText { plainText } }
    ratingsSummary { aggregateRating }
    titleGenres { genres { genre { text } } }
    principalCredits(filter: { categories: ["director", "cast"] }) {
      category { text }
      credits { name { nameText { text } } }
    }
  }
}
"""


def details_for(imdb_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not imdb_id or not IMDB_ID_PATTERN.fullmatch(imdb_id):
        return None
    data = graphql(DETAILS_QUERY, {"id": imdb_id})
    title = (data or {}).get("title")
    if not title:
        return None

    genres = [
        str(item["genre"]["text"])
        for item in ((title.get("titleGenres") or {}).get("genres") or [])
        if (item.get("genre") or {}).get("text")
    ]
    credits = _credits_by_category(title.get("principalCredits") or [])
    seconds = (title.get("runtime") or {}).get("seconds")
    plot = ((title.get("plot") or {}).get("plotText") or {}).get("plainText")
    rating = (title.get("ratingsSummary") or {}).get("aggregateRating")

    details: Dict[str, Any] = {}
    if genres:
        details["genres"] = genres
        details["genre"] = " · ".join(genres[:2])
    if credits.get("director"):
        details["director"] = credits["director"][:2]
    if credits.get("cast"):
        details["cast"] = credits["cast"][:MAX_CAST]
    if isinstance(seconds, int) and seconds > 0:
        details["runtime_minutes"] = round(seconds / 60)
    if plot:
        details["plot"] = str(plot).strip()
    if isinstance(rating, (int, float)):
        details["rating"] = float(rating)
    return details or None


def details_for_many(
    imdb_ids: Iterable[Optional[str]],
) -> Dict[str, Dict[str, Any]]:
    unique = [
        imdb_id
        for imdb_id in dict.fromkeys(imdb_ids)
        if imdb_id and IMDB_ID_PATTERN.fullmatch(imdb_id)
    ]
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_LOOKUPS, len(unique))) as pool:
        found = pool.map(details_for, unique)
    return {
        imdb_id: details for imdb_id, details in zip(unique, found) if details
    }


def _credits_by_category(groups: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for group in groups:
        label = str((group.get("category") or {}).get("text", "")).casefold()
        names = [
            str(credit["name"]["nameText"]["text"])
            for credit in group.get("credits") or []
            if ((credit.get("name") or {}).get("nameText") or {}).get("text")
        ]
        if not names:
            continue
        if "director" in label:
            result.setdefault("director", []).extend(names)
        elif "star" in label or "cast" in label:
            result.setdefault("cast", []).extend(names)
    return result
