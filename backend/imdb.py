import json
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .net import default_ssl_context

GRAPHQL_URL = "https://api.graphql.imdb.com/"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 8.0


def get_json(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes] = None,
) -> Optional[Dict[str, Any]]:
    request = Request(
        url,
        data=body,
        headers={"User-Agent": BROWSER_USER_AGENT, **(headers or {})},
    )
    try:
        with urlopen(
            request, timeout=REQUEST_TIMEOUT, context=default_ssl_context()
        ) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def graphql(query: str, variables: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """IMDb's GraphQL endpoint answers 403 without a browser Origin and Referer."""
    payload = get_json(
        GRAPHQL_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.imdb.com",
            "Referer": "https://www.imdb.com/",
        },
        body=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
    )
    return (payload or {}).get("data")
