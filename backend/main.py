import asyncio
import re
from pathlib import Path
from typing import Dict, List, Literal
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.devin_client import (
    DevinAPIError,
    DevinClient,
    DevinConfigurationError,
    DevinSessionTimeout,
)


ROOT = Path(__file__).resolve().parents[1]


class RecommendationContext(BaseModel):
    mode: Literal["personal", "round1", "round2"] = "personal"
    liked: List[str] = Field(default_factory=list, max_length=100)
    disliked: List[str] = Field(default_factory=list, max_length=100)
    watched: List[str] = Field(default_factory=list, max_length=100)
    excluded: List[str] = Field(default_factory=list, max_length=100)


class RecommendationRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=500)
    count: int = Field(default=5, ge=1, le=10)
    context: RecommendationContext = Field(default_factory=RecommendationContext)


class MovieRecommendation(BaseModel):
    id: str
    title: str
    year: int
    genre: str
    provider: str
    watch_url: str
    hook: str
    poster: int


class RecommendationResponse(BaseModel):
    session_id: str
    movies: List[MovieRecommendation]


def get_devin_client() -> DevinClient:
    try:
        return DevinClient.from_env()
    except DevinConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def normalize_movies(raw_movies: List[Dict[str, object]]) -> List[MovieRecommendation]:
    normalized: List[MovieRecommendation] = []
    used_ids = set()

    for index, raw_movie in enumerate(raw_movies):
        title = str(raw_movie.get("title", "")).strip()
        if not title:
            raise DevinAPIError("Devin returned a recommendation without a title.")
        try:
            year = int(raw_movie.get("year", 0))
        except (TypeError, ValueError) as error:
            raise DevinAPIError(f"Invalid year returned for {title}.") from error
        if year < 1888 or year > 2100:
            raise DevinAPIError(f"Invalid year returned for {title}.")

        movie_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        movie_id = f"{movie_id}-{year}"
        if movie_id in used_ids:
            movie_id = f"{movie_id}-{index + 1}"
        used_ids.add(movie_id)

        watch_url = str(raw_movie.get("watch_url", "")).strip()
        if not watch_url.startswith(("https://", "http://")):
            watch_url = f"https://www.justwatch.com/us/search?q={quote_plus(title)}"

        normalized.append(
            MovieRecommendation(
                id=movie_id,
                title=title,
                year=year,
                genre=str(raw_movie.get("genre", "")).strip() or "Movie",
                provider=str(raw_movie.get("provider", "")).strip() or "JustWatch",
                watch_url=watch_url,
                hook=str(raw_movie.get("hook", "")).strip(),
                poster=(index % 8) + 1,
            )
        )

    return normalized


app = FastAPI(title="ReelPick API", version="0.2.0")


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def recommendations(
    request: RecommendationRequest,
    client: DevinClient = Depends(get_devin_client),
) -> RecommendationResponse:
    try:
        result = await asyncio.to_thread(
            client.recommend,
            prompt=request.prompt.strip(),
            count=request.count,
            context=request.context.model_dump(),
        )
        movies = normalize_movies(result["movies"])
        if len(movies) != request.count:
            raise DevinAPIError(
                f"Devin returned {len(movies)} movies; expected {request.count}."
            )
        return RecommendationResponse(session_id=result["session_id"], movies=movies)
    except DevinConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except DevinSessionTimeout as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except DevinAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(ROOT / "app.js", media_type="application/javascript")


@app.get("/styles.css")
def frontend_styles() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css")


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
