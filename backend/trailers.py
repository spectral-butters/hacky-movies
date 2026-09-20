import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from .imdb import get_json, graphql

SUGGESTION_URL = "https://v3.sg.media-imdb.com/suggestion/x/{imdb_id}.json?includeVideos=1"
IMDB_ID_PATTERN = re.compile(r"tt\d{7,10}")
VIDEO_ID_PATTERN = re.compile(r"vi\d{6,12}")
PLAYBACK_QUERY = (
    "query Playback($id: ID!) { video(id: $id) { contentType { displayName "
    "{ value } } playbackURLs { mimeType url videoDefinition } } }"
)
DEFINITION_ORDER = ("DEF_480p", "DEF_SD", "DEF_720p", "DEF_1080p")
REQUEST_TIMEOUT = 8.0
MAX_PARALLEL_LOOKUPS = 5
REFRESH_MARGIN_SECONDS = 1800


def signed_url_expiry(url: Optional[str]) -> Optional[int]:
    if not url:
        return None
    try:
        values = parse_qs(urlparse(url).query).get("Expires")
        return int(values[0]) if values else None
    except (ValueError, TypeError):
        return None


def is_stale(url: Optional[str]) -> bool:
    expiry = signed_url_expiry(url)
    if expiry is None:
        return True
    return expiry - REFRESH_MARGIN_SECONDS <= time.time()


def trailer_url_for(imdb_id: Optional[str]) -> Optional[str]:
    video_id = _best_video_id(imdb_id)
    if not video_id:
        return None
    return _playback_url(video_id)


def trailer_urls_for(imdb_ids: Iterable[Optional[str]]) -> Dict[str, str]:
    unique = [
        imdb_id
        for imdb_id in dict.fromkeys(imdb_ids)
        if imdb_id and IMDB_ID_PATTERN.fullmatch(imdb_id)
    ]
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_LOOKUPS, len(unique))) as pool:
        found = pool.map(trailer_url_for, unique)
    return {imdb_id: url for imdb_id, url in zip(unique, found) if url}


def _best_video_id(imdb_id: Optional[str]) -> Optional[str]:
    if not imdb_id or not IMDB_ID_PATTERN.fullmatch(imdb_id):
        return None
    payload = get_json(
        SUGGESTION_URL.format(imdb_id=imdb_id),
        headers={"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"},
    )
    if not payload:
        return None
    for entry in payload.get("d") or []:
        if entry.get("id") != imdb_id:
            continue
        videos = [
            video
            for video in entry.get("v") or []
            if VIDEO_ID_PATTERN.fullmatch(str(video.get("id", "")))
        ]
        if not videos:
            return None
        trailers = [
            video
            for video in videos
            if "trailer" in str(video.get("l", "")).casefold()
        ]
        return str((trailers or videos)[0]["id"])
    return None


def definition_order() -> List[str]:
    preferred = os.getenv("REELPICK_TRAILER_DEFINITION", "").strip()
    if not preferred:
        return list(DEFINITION_ORDER)
    return [preferred] + [item for item in DEFINITION_ORDER if item != preferred]


def _playback_url(video_id: str) -> Optional[str]:
    video = (graphql(PLAYBACK_QUERY, {"id": video_id}) or {}).get("video") or {}
    sources: List[Dict[str, str]] = [
        source
        for source in video.get("playbackURLs") or []
        if source.get("mimeType") == "video/mp4" and _is_imdb_video(source.get("url"))
    ]
    if not sources:
        return None
    by_definition = {source.get("videoDefinition"): source["url"] for source in sources}
    for definition in definition_order():
        if definition in by_definition:
            return by_definition[definition]
    return sources[0]["url"]


def _is_imdb_video(url: Optional[str]) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == "imdb-video.media-imdb.com"
