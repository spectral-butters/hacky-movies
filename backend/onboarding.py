import json
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from .database import Database

GENRES = [
    ("comedy", "Comedy"),
    ("thriller", "Thriller & mystery"),
    ("action", "Action & adventure"),
    ("scifi", "Science fiction"),
    ("fantasy", "Fantasy"),
    ("drama", "Drama"),
    ("romance", "Romance"),
    ("horror", "Horror"),
    ("animation", "Animation"),
    ("documentary", "Documentary"),
    ("surprise", "Surprise me"),
]
GENRE_KEYS = {key for key, _ in GENRES}
MAX_GENRES = 4

CATALOGUE: List[Dict[str, Any]] = [
    {"title": "Borat", "year": 2006, "imdb_id": "tt0443453", "bucket": "comedy", "genres": ["comedy"], "label": "Comedy · Satire"},
    {"title": "The Hangover", "year": 2009, "imdb_id": "tt1119646", "bucket": "comedy", "genres": ["comedy"], "label": "Comedy"},
    {"title": "Superbad", "year": 2007, "imdb_id": "tt0829482", "bucket": "comedy", "genres": ["comedy"], "label": "Comedy · Coming of age"},
    {"title": "The Grand Budapest Hotel", "year": 2014, "imdb_id": "tt2278388", "bucket": "comedy", "genres": ["comedy", "drama"], "label": "Comedy · Drama"},
    {"title": "Bridesmaids", "year": 2011, "imdb_id": "tt1478338", "bucket": "comedy", "genres": ["comedy", "romance"], "label": "Comedy · Romance"},
    {"title": "Gone Girl", "year": 2014, "imdb_id": "tt2267998", "bucket": "thriller", "genres": ["thriller", "drama"], "label": "Thriller · Mystery"},
    {"title": "Prisoners", "year": 2013, "imdb_id": "tt1392214", "bucket": "thriller", "genres": ["thriller", "drama"], "label": "Thriller · Drama"},
    {"title": "Knives Out", "year": 2019, "imdb_id": "tt8946378", "bucket": "thriller", "genres": ["thriller", "comedy"], "label": "Mystery · Comedy"},
    {"title": "John Wick", "year": 2014, "imdb_id": "tt2911666", "bucket": "thriller", "genres": ["action", "thriller"], "label": "Action · Thriller"},
    {"title": "The Departed", "year": 2006, "imdb_id": "tt0407887", "bucket": "thriller", "genres": ["thriller", "drama"], "label": "Crime · Drama"},
    {"title": "Interstellar", "year": 2014, "imdb_id": "tt0816692", "bucket": "scifi", "genres": ["scifi", "drama"], "label": "Sci-fi · Drama"},
    {"title": "The Matrix", "year": 1999, "imdb_id": "tt0133093", "bucket": "scifi", "genres": ["scifi", "action"], "label": "Sci-fi · Action"},
    {"title": "Dune", "year": 2021, "imdb_id": "tt1160419", "bucket": "scifi", "genres": ["scifi", "fantasy"], "label": "Sci-fi · Epic"},
    {"title": "The Lord of the Rings: The Fellowship of the Ring", "year": 2001, "imdb_id": "tt0120737", "bucket": "scifi", "genres": ["fantasy", "action"], "label": "Fantasy · Adventure"},
    {"title": "Everything Everywhere All at Once", "year": 2022, "imdb_id": "tt6710474", "bucket": "scifi", "genres": ["scifi", "comedy", "action"], "label": "Sci-fi · Comedy"},
    {"title": "The Shawshank Redemption", "year": 1994, "imdb_id": "tt0111161", "bucket": "drama", "genres": ["drama"], "label": "Drama"},
    {"title": "La La Land", "year": 2016, "imdb_id": "tt3783958", "bucket": "drama", "genres": ["romance", "drama"], "label": "Romance · Musical"},
    {"title": "The Wolf of Wall Street", "year": 2013, "imdb_id": "tt0993846", "bucket": "drama", "genres": ["drama", "comedy"], "label": "Drama · Comedy"},
    {"title": "Parasite", "year": 2019, "imdb_id": "tt6751668", "bucket": "drama", "genres": ["thriller", "drama"], "label": "Drama · Thriller"},
    {"title": "The Notebook", "year": 2004, "imdb_id": "tt0332280", "bucket": "drama", "genres": ["romance", "drama"], "label": "Romance"},
    {"title": "The Conjuring", "year": 2013, "imdb_id": "tt1457767", "bucket": "horror", "genres": ["horror"], "label": "Horror · Supernatural"},
    {"title": "Get Out", "year": 2017, "imdb_id": "tt5052448", "bucket": "horror", "genres": ["horror", "thriller"], "label": "Horror · Thriller"},
    {"title": "Hereditary", "year": 2018, "imdb_id": "tt7784604", "bucket": "horror", "genres": ["horror", "drama"], "label": "Horror · Drama"},
    {"title": "A Quiet Place", "year": 2018, "imdb_id": "tt6644200", "bucket": "horror", "genres": ["horror", "scifi"], "label": "Horror · Survival"},
    {"title": "Scream", "year": 1996, "imdb_id": "tt0117571", "bucket": "horror", "genres": ["horror", "comedy"], "label": "Horror · Slasher"},
]

CALIBRATION = [
    "The Hangover",
    "Interstellar",
    "Gone Girl",
    "The Lord of the Rings: The Fellowship of the Ring",
    "Get Out",
]
ROUND_SIZE = 5
WILDCARD_PER_ROUND = 1
MIN_RATED = 8
MIN_LIKES = 2
MIN_DISLIKES = 1
TARGET_REACTIONS = 15


def movie_id_for(entry: Dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", entry["title"].lower()).strip("-")
    return f"{slug}-{entry['year']}"


def catalogue_movie_ids(database: Database) -> Dict[str, str]:
    rows = database.fetch_all("SELECT movie_id, title, year FROM movies")
    existing = {
        (str(row["title"]).casefold(), int(row["year"])): row["movie_id"] for row in rows
    }
    return {
        entry["title"]: existing.get(
            (entry["title"].casefold(), entry["year"]), movie_id_for(entry)
        )
        for entry in CATALOGUE
    }


def as_recommendation(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": entry["title"],
        "year": entry["year"],
        "imdb_id": entry["imdb_id"],
        "imdb_url": f"https://www.imdb.com/title/{entry['imdb_id']}/",
        "genre": entry["label"],
        "reason": "A calibration pick for your taste profile.",
        "match_score": 0,
        "recommendation_type": "discovery_pick",
        "preference_connections": [],
        "possible_mismatch": None,
    }


def normalize_genres(values: Sequence[str]) -> List[str]:
    seen: List[str] = []
    for value in values:
        key = str(value).strip().lower()
        if key in GENRE_KEYS and key not in seen:
            seen.append(key)
    return seen[:MAX_GENRES]


def progress(database: Database, user_id: str) -> Dict[str, Any]:
    by_title = catalogue_movie_ids(database)
    title_by_id = {movie_id: title for title, movie_id in by_title.items()}
    ids = list(title_by_id)
    placeholders = ",".join("?" for _ in ids)
    rows = database.fetch_all(
        f"""
        SELECT movie_id, dimension, value
        FROM feedback_current
        WHERE user_id = ?
          AND context = 'personal'
          AND movie_id IN ({placeholders})
        """,
        (user_id, *ids),
    )
    reacted: Set[str] = set()
    likes = 0
    dislikes = 0
    for row in rows:
        title = title_by_id.get(row["movie_id"])
        if not title:
            continue
        reacted.add(title)
        if row["dimension"] != "watched_rating":
            continue
        if row["value"] == "liked":
            likes += 1
        elif row["value"] == "disliked":
            dislikes += 1
    rated = likes + dislikes
    return {
        "reacted_titles": sorted(reacted),
        "reacted": len(reacted),
        "rated": rated,
        "likes": likes,
        "dislikes": dislikes,
        "enough": rated >= MIN_RATED and likes >= MIN_LIKES and dislikes >= MIN_DISLIKES,
        "target": TARGET_REACTIONS,
        "pool": len(CATALOGUE),
    }


def next_round(
    reacted_titles: Sequence[str],
    genres: Sequence[str],
) -> List[Dict[str, Any]]:
    done = set(reacted_titles)
    remaining = [entry for entry in CATALOGUE if entry["title"] not in done]
    if not remaining:
        return []

    calibration = [entry for entry in remaining if entry["title"] in CALIBRATION]
    if len(calibration) == len(CALIBRATION):
        return calibration

    wanted = set(genres) - {"surprise"}
    preferred = [entry for entry in remaining if wanted & set(entry["genres"])]
    wildcards = [entry for entry in remaining if entry not in preferred]
    if not wanted:
        preferred, wildcards = remaining, []

    picks = _spread(preferred, ROUND_SIZE - WILDCARD_PER_ROUND if wildcards else ROUND_SIZE)
    picks += _spread([entry for entry in wildcards if entry not in picks], ROUND_SIZE - len(picks))
    if len(picks) < ROUND_SIZE:
        picks += [
            entry
            for entry in remaining
            if entry not in picks
        ][: ROUND_SIZE - len(picks)]
    return picks[:ROUND_SIZE]


def _spread(entries: Sequence[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        buckets.setdefault(entry["bucket"], []).append(entry)
    picks: List[Dict[str, Any]] = []
    while len(picks) < limit and any(buckets.values()):
        for bucket in list(buckets):
            if len(picks) == limit:
                break
            if buckets[bucket]:
                picks.append(buckets[bucket].pop(0))
    return picks


def read_state(database: Database, user_id: str) -> Dict[str, Any]:
    row = database.fetch_one(
        "SELECT onboarding_status, onboarding_genres FROM users WHERE user_id = ?",
        (user_id,),
    )
    if not row:
        return {"status": "pending", "genres": []}
    try:
        genres = json.loads(row["onboarding_genres"] or "[]")
    except ValueError:
        genres = []
    return {
        "status": row["onboarding_status"] or "pending",
        "genres": genres if isinstance(genres, list) else [],
    }


def write_state(
    database: Database,
    user_id: str,
    *,
    status: Optional[str] = None,
    genres: Optional[Sequence[str]] = None,
) -> None:
    assignments = []
    values: List[Any] = []
    if status is not None:
        assignments.append("onboarding_status = ?")
        values.append(status)
    if genres is not None:
        assignments.append("onboarding_genres = ?")
        values.append(json.dumps(list(genres)))
    if not assignments:
        return
    values.append(user_id)
    with database.write_connection() as connection:
        connection.execute(
            f"UPDATE users SET {', '.join(assignments)} WHERE user_id = ?",
            tuple(values),
        )
