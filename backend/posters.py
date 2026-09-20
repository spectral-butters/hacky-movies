import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .net import default_ssl_context

SUGGESTION_URL = "https://v3.sg.media-imdb.com/suggestion/x/{imdb_id}.json?includeVideos=0"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
IMDB_ID_PATTERN = re.compile(r"tt\d{7,10}")
POSTER_WIDTH = 400
REQUEST_TIMEOUT = 8.0
MAX_PARALLEL_LOOKUPS = 5


def poster_url_for(imdb_id: Optional[str]) -> Optional[str]:
    if not imdb_id or not IMDB_ID_PATTERN.fullmatch(imdb_id):
        return None
    request = Request(
        SUGGESTION_URL.format(imdb_id=imdb_id),
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(
            request, timeout=REQUEST_TIMEOUT, context=default_ssl_context()
        ) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None

    for entry in payload.get("d") or []:
        if entry.get("id") != imdb_id:
            continue
        image_url = (entry.get("i") or {}).get("imageUrl")
        if image_url:
            return _sized(image_url)
    return None


def poster_urls_for(imdb_ids: Iterable[Optional[str]]) -> Dict[str, str]:
    unique = [
        imdb_id
        for imdb_id in dict.fromkeys(imdb_ids)
        if imdb_id and IMDB_ID_PATTERN.fullmatch(imdb_id)
    ]
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_LOOKUPS, len(unique))) as pool:
        found = pool.map(poster_url_for, unique)
    return {
        imdb_id: url for imdb_id, url in zip(unique, found) if url
    }


def _sized(image_url: str) -> str:
    base = image_url.split("._V1_")[0]
    return f"{base}._V1_QL75_UX{POSTER_WIDTH}_.jpg"
