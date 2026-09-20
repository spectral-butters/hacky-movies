import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote_plus

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import demo, onboarding
from backend.database import DEFAULT_USER_ID, Database
from backend.devin_client import (
    DevinAPIError,
    DevinClient,
    DevinConfigurationError,
    DevinSessionTimeout,
)
from backend.memory import PreferenceAnalysisWorker
from backend.details import details_for_many
from backend.posters import poster_urls_for
from backend.trailers import is_stale, trailer_urls_for
from backend.speech import (
    SpeechAPIError,
    SpeechConfigurationError,
    transcribe,
)
from backend.nebius_client import NebiusClient
from backend.repository import (
    DEFAULT_RECOMMENDATION_PROVIDER,
    RECOMMENDATION_PROVIDERS,
    ConflictError,
    NotFoundError,
    ReelPickRepository,
)


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_VALUES = {
    "recommendation_interest": {"interested", "not_interested"},
    "viewing_status": {"watched", "unwatched", "unknown"},
    "watched_rating": {"liked", "disliked", "neutral"},
    "watchlist": {"saved", "not_saved"},
    "group_vote": {"like", "dislike", "abstain"},
}
REASON_CODES = {
    "not_in_mood",
    "story",
    "cast",
    "pacing",
    "humour",
    "violence_or_horror",
    "other",
    "characters",
    "atmosphere",
    "visuals",
    "emotion",
    "action",
    "confusing",
}


class RecommendationContext(BaseModel):
    mode: Literal["personal", "round1", "round2"] = "personal"
    liked: List[str] = Field(default_factory=list, max_length=100)
    disliked: List[str] = Field(default_factory=list, max_length=100)
    watched: List[str] = Field(default_factory=list, max_length=100)
    excluded: List[str] = Field(default_factory=list, max_length=100)


class RecommendationRequest(BaseModel):
    prompt: str = Field(min_length=2, max_length=500)
    count: int = Field(default=5, ge=1, le=5)
    session_id: Optional[str] = None
    event_id: Optional[str] = None
    mode: Literal["personal", "event_nomination"] = "personal"
    context: Optional[RecommendationContext] = None


class MovieRecommendation(BaseModel):
    id: str
    title: str
    year: int
    genre: str
    provider: str
    watch_url: str
    hook: str
    poster: int
    poster_url: Optional[str]
    imdb_id: Optional[str]
    imdb_url: Optional[str]
    match_score: int
    recommendation_type: Literal[
        "strong_match",
        "broader_match",
        "discovery_pick",
    ]
    preference_connections: List[str]
    possible_mismatch: Optional[str]
    in_watchlist: bool
    clip_url: Optional[str] = None
    plot: Optional[str] = None
    director: List[str] = Field(default_factory=list)
    cast: List[str] = Field(default_factory=list)
    runtime_minutes: Optional[int] = None
    rating: Optional[float] = None


class RecommendationResponse(BaseModel):
    session_id: str
    batch_id: Optional[str]
    devin_session_id: Optional[str]
    requested_count: int
    returned_count: int
    memory_version_used: int
    shortfall_reason: Optional[str]
    interpreted_request: Dict[str, Any]
    movies: List[MovieRecommendation]


class FeedbackRequest(BaseModel):
    movie_id: str
    dimension: Literal[
        "recommendation_interest",
        "viewing_status",
        "watched_rating",
        "watchlist",
        "group_vote",
    ]
    value: str
    source_surface: str = Field(min_length=1, max_length=80)
    context: Literal["personal", "session", "event"] = "personal"
    session_id: Optional[str] = None
    event_id: Optional[str] = None
    reason_code: Optional[str] = None
    reason_text: Optional[str] = Field(default=None, max_length=500)
    superseded_feedback_id: Optional[str] = None


class UndoRequest(BaseModel):
    feedback_id: str


class UserDescriptionRequest(BaseModel):
    description: str = Field(max_length=2000)


class ExplicitMemoryRequest(BaseModel):
    dimension: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=160)
    direction: Literal["prefer", "avoid"]
    strength: Literal["soft_preference", "explicit_restriction"] = "soft_preference"
    context_scope: Literal["general", "session", "event"] = "general"
    context_id: Optional[str] = None
    evidence_summary: str = Field(min_length=1, max_length=500)


class CorrectMemoryRequest(ExplicitMemoryRequest):
    pass


class EventRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    event_date: Optional[str] = None
    prompt: str = Field(min_length=2, max_length=500)


class JoinEventRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class ProviderRequest(BaseModel):
    provider: Literal["devin", "nebius"]


class NominationRequest(BaseModel):
    movie_ids: List[str] = Field(min_length=1, max_length=2)


class VoteRequest(BaseModel):
    votes: Dict[str, Literal["like", "dislike", "abstain"]] = Field(
        default_factory=dict
    )
    finished: bool = False


class RoundRequest(BaseModel):
    status: Literal["round1", "round2", "final", "completed"]


class OnboardingGenresRequest(BaseModel):
    genres: List[str] = Field(default_factory=list, max_length=20)


class OnboardingFinishRequest(BaseModel):
    status: Literal["complete", "skipped"] = "complete"


class WinnerRequest(BaseModel):
    movie_id: str = Field(min_length=1, max_length=200)


database = Database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database.initialize()
    app.state.repository = ReelPickRepository(app.state.database)
    catalogue = seed_catalogues(app.state.repository)
    backfill = asyncio.create_task(
        asyncio.to_thread(warm_catalogues, app.state.repository, catalogue)
    )
    yield
    backfill.cancel()


app = FastAPI(title="ReelPick API", version="0.3.0", lifespan=lifespan)
app.state.database = database
app.state.repository = ReelPickRepository(database)


def get_repository(request: Request) -> ReelPickRepository:
    return request.app.state.repository


def get_demo_mode(x_reelpick_demo: Optional[str] = Header(default=None)) -> bool:
    return demo.resolve_demo_mode(x_reelpick_demo)


def get_user_id(x_reelpick_user: str = Header(default=DEFAULT_USER_ID)) -> str:
    user_id = x_reelpick_user.strip()
    if not user_id or len(user_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid ReelPick user ID.")
    return user_id


def build_recommender(provider: str):
    if provider == "nebius":
        return NebiusClient.from_env()
    return DevinClient.from_env()


def get_devin_client(
    demo_mode: bool = Depends(get_demo_mode),
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
):
    if demo_mode:
        return None
    try:
        return build_recommender(repository.get_recommendation_provider(user_id))
    except DevinConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def process_analysis_job(
    database: Database,
    job_id: str,
    demo_mode: bool = False,
) -> None:
    if demo_mode:
        return
    job = database.fetch_one(
        "SELECT user_id FROM analysis_jobs WHERE job_id = ?",
        (job_id,),
    )
    repository = ReelPickRepository(database)
    provider = (
        repository.get_recommendation_provider(job["user_id"])
        if job
        else DEFAULT_RECOMMENDATION_PROVIDER
    )
    try:
        client = build_recommender(provider)
    except DevinConfigurationError:
        return
    worker = PreferenceAnalysisWorker(database, client)
    for attempt in range(3):
        worker.process_job(job_id)
        job = database.fetch_one(
            "SELECT status, next_attempt_at FROM analysis_jobs WHERE job_id = ?",
            (job_id,),
        )
        if not job or job["status"] != "retry":
            return
        if attempt < 2:
            time.sleep(2 ** attempt)


def attach_posters(
    repository: ReelPickRepository,
    stored_movies: List[Dict[str, Any]],
) -> None:
    missing = [
        movie
        for movie in stored_movies
        if movie.get("imdb_id") and not movie.get("poster_url")
    ]
    if not missing:
        return
    found = poster_urls_for(movie["imdb_id"] for movie in missing)
    for movie in missing:
        poster_url = found.get(movie["imdb_id"])
        if not poster_url:
            continue
        movie["poster_url"] = poster_url
        repository.set_poster_url(movie["movie_id"], poster_url)


def attach_details(
    repository: ReelPickRepository,
    stored_movies: List[Dict[str, Any]],
) -> None:
    missing = [
        movie
        for movie in stored_movies
        if movie.get("imdb_id") and not (movie.get("factual_metadata") or {}).get("plot")
    ]
    if not missing:
        return
    found = details_for_many(movie["imdb_id"] for movie in missing)
    for movie in missing:
        details = found.get(movie["imdb_id"])
        if not details:
            continue
        factual = {**(movie.get("factual_metadata") or {}), **details}
        movie["factual_metadata"] = factual
        repository.set_factual_metadata(movie["movie_id"], factual)


def attach_trailers(
    repository: ReelPickRepository,
    stored_movies: List[Dict[str, Any]],
) -> None:
    missing = [
        movie
        for movie in stored_movies
        if movie.get("imdb_id") and is_stale(movie.get("short_video_url"))
    ]
    if not missing:
        return
    found = trailer_urls_for(movie["imdb_id"] for movie in missing)
    for movie in missing:
        trailer_url = found.get(movie["imdb_id"])
        if not trailer_url:
            continue
        movie["short_video_url"] = trailer_url
        repository.set_short_video_url(movie["movie_id"], trailer_url)


def seed_catalogues(repository: ReelPickRepository) -> List[Dict[str, Any]]:
    """Store the fixed survey and demo movies so their artwork can be warmed.

    Demo mode must not need the network, so both catalogues are enriched at
    startup rather than on the request that first shows them.
    """
    stored = [
        repository.upsert_recommendation_movie(onboarding.as_recommendation(entry))
        for entry in onboarding.CATALOGUE
    ]
    try:
        demo_entries = demo.load_catalogue()["movies"]
    except demo.DemoCatalogueError:
        return stored
    for entry in demo_entries:
        stored.append(
            repository.upsert_recommendation_movie(
                {
                    "title": entry["title"],
                    "year": entry["year"],
                    "imdb_id": entry.get("imdb_id"),
                    "imdb_url": (
                        f"https://www.imdb.com/title/{entry['imdb_id']}/"
                        if entry.get("imdb_id")
                        else None
                    ),
                    "reason": entry.get("reason", ""),
                    "match_score": entry.get("match_score", 0),
                    "recommendation_type": entry.get(
                        "recommendation_type", "strong_match"
                    ),
                    "preference_connections": [],
                    "possible_mismatch": None,
                }
            )
        )
    return stored


def backfill_posters(repository: ReelPickRepository) -> None:
    attach_posters(repository, repository.movies_without_poster())


def warm_catalogues(repository: ReelPickRepository, catalogue: List[Dict[str, Any]]) -> None:
    attach_details(repository, catalogue)
    backfill_posters(repository)


def stored_as_raw(
    stored_movie: Dict[str, Any],
    *,
    demo_mode: bool,
) -> Dict[str, Any]:
    attributes = stored_movie.get("ai_attributes") or {}
    return {
        "title": stored_movie["title"],
        "year": stored_movie["year"],
        "imdb_id": stored_movie.get("imdb_id"),
        "imdb_url": stored_movie.get("imdb_url"),
        "reason": attributes.get("reason") or "Part of tonight's shared line-up.",
        "match_score": attributes.get("match_score") or 0,
        "recommendation_type": attributes.get("recommendation_type") or "strong_match",
        "preference_connections": attributes.get("preference_connections") or [],
        "possible_mismatch": attributes.get("possible_mismatch"),
        "clip_url": demo.clip_url_for(stored_movie["title"]) if demo_mode else None,
    }


def build_shared_movies(
    repository: ReelPickRepository,
    movie_ids: List[str],
    *,
    demo_mode: bool,
) -> List["MovieRecommendation"]:
    stored_movies = []
    for movie_id in movie_ids:
        try:
            stored_movies.append(repository.get_movie(movie_id))
        except NotFoundError:
            continue
    return [
        normalize_movie(stored_as_raw(movie, demo_mode=demo_mode), movie, index)
        for index, movie in enumerate(stored_movies)
    ]


def normalize_movie(
    raw_movie: Dict[str, Any],
    stored_movie: Dict[str, Any],
    index: int,
) -> MovieRecommendation:
    title = str(raw_movie.get("title", "")).strip()
    try:
        year = int(raw_movie.get("year", 0))
    except (TypeError, ValueError) as error:
        raise DevinAPIError(f"Invalid year returned for {title or 'movie'}.") from error
    if not title or year < 1888 or year > 2100:
        raise DevinAPIError("The recommendation service returned an invalid movie title or year.")

    imdb_id = raw_movie.get("imdb_id")
    imdb_url = raw_movie.get("imdb_url")
    if imdb_id is not None:
        imdb_id = str(imdb_id).strip()
        expected_url = f"https://www.imdb.com/title/{imdb_id}/"
        if not re.fullmatch(r"tt\d{7,10}", imdb_id) or imdb_url != expected_url:
            raise DevinAPIError(f"Invalid IMDb identity returned for {title}.")
    elif imdb_url is not None:
        raise DevinAPIError(f"IMDb ID and URL must both be null for {title}.")

    factual = stored_movie.get("factual_metadata", {})
    genre = str(raw_movie.get("genre") or factual.get("genre") or "Movie")
    poster = int(factual.get("poster_sprite", (index % 8) + 1))
    destination = imdb_url or (
        f"https://www.justwatch.com/us/search?q={quote_plus(title)}"
    )
    recommendation_type = raw_movie.get("recommendation_type")
    if recommendation_type not in {
        "strong_match",
        "broader_match",
        "discovery_pick",
    }:
        raise DevinAPIError(f"Invalid recommendation type returned for {title}.")

    return MovieRecommendation(
        id=stored_movie["movie_id"],
        title=title,
        year=year,
        genre=genre,
        provider="IMDb" if imdb_url else "JustWatch",
        watch_url=destination,
        hook=str(raw_movie.get("reason", "")).strip(),
        poster=poster,
        poster_url=stored_movie.get("poster_url") or None,
        imdb_id=imdb_id,
        imdb_url=imdb_url,
        match_score=int(raw_movie.get("match_score", 0)),
        recommendation_type=recommendation_type,
        preference_connections=[
            str(item) for item in raw_movie.get("preference_connections", [])
        ],
        possible_mismatch=raw_movie.get("possible_mismatch"),
        in_watchlist=bool(raw_movie.get("in_watchlist")),
        clip_url=raw_movie.get("clip_url") or stored_movie.get("short_video_url") or None,
        plot=factual.get("plot"),
        director=[str(name) for name in factual.get("director", [])],
        cast=[str(name) for name in factual.get("cast", [])],
        runtime_minutes=factual.get("runtime_minutes"),
        rating=factual.get("rating"),
    )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)) -> Dict[str, str]:
    payload = await audio.read()
    try:
        text = await asyncio.to_thread(transcribe, payload, audio.content_type)
    except SpeechConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except SpeechAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"text": text}


@app.get("/api/bootstrap")
def bootstrap(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
    demo_mode: bool = Depends(get_demo_mode),
) -> Dict[str, Any]:
    payload = repository.bootstrap(user_id)
    payload["demo_mode"] = demo_mode
    payload["demo_available"] = demo.CATALOGUE_PATH.is_file()
    payload["onboarding"] = onboarding.read_state(repository.database, user_id)
    return payload


@app.put("/api/user/description", status_code=204)
def update_user_description(
    request: UserDescriptionRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Response:
    repository.update_user_description(user_id, request.description)
    return Response(status_code=204)


@app.get("/api/onboarding")
async def onboarding_round(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    repository.ensure_user(user_id)
    state = onboarding.read_state(repository.database, user_id)
    stats = onboarding.progress(repository.database, user_id)
    entries = onboarding.next_round(stats["reacted_titles"], state["genres"])
    movies: List[Dict[str, Any]] = []
    if entries:
        stored = [
            repository.upsert_recommendation_movie(onboarding.as_recommendation(entry))
            for entry in entries
        ]
        await asyncio.to_thread(attach_posters, repository, stored)
        for entry, movie in zip(entries, stored):
            movies.append(
                {
                    "id": movie["movie_id"],
                    "title": entry["title"],
                    "year": entry["year"],
                    "genre": entry["label"],
                    "poster": (len(movies) % 8) + 1,
                    "poster_url": movie.get("poster_url") or None,
                    "imdb_id": entry["imdb_id"],
                    "imdb_url": f"https://www.imdb.com/title/{entry['imdb_id']}/",
                    "provider": "IMDb",
                    "watch_url": f"https://www.imdb.com/title/{entry['imdb_id']}/",
                }
            )
    stats.pop("reacted_titles", None)
    return {
        "status": state["status"],
        "genres": state["genres"],
        "available_genres": [
            {"key": key, "label": label} for key, label in onboarding.GENRES
        ],
        "max_genres": onboarding.MAX_GENRES,
        "movies": movies,
        "progress": stats,
        "exhausted": not entries,
    }


@app.put("/api/onboarding/genres")
def onboarding_genres(
    request: OnboardingGenresRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    repository.ensure_user(user_id)
    genres = onboarding.normalize_genres(request.genres)
    onboarding.write_state(
        repository.database, user_id, genres=genres, status="in_progress"
    )
    return {"genres": genres}


@app.post("/api/onboarding/finish")
def onboarding_finish(
    request: OnboardingFinishRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    repository.ensure_user(user_id)
    onboarding.write_state(repository.database, user_id, status=request.status)
    return {"status": request.status}


@app.get("/api/user/provider")
def get_provider(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
    demo_mode: bool = Depends(get_demo_mode),
) -> Dict[str, Any]:
    provider = repository.get_recommendation_provider(user_id)
    return {
        "provider": provider,
        "available": list(RECOMMENDATION_PROVIDERS),
        "configured": provider_is_configured(provider),
        "demo_mode": demo_mode,
    }


@app.put("/api/user/provider")
def set_provider(
    request: ProviderRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
    demo_mode: bool = Depends(get_demo_mode),
) -> Dict[str, Any]:
    try:
        provider = repository.set_recommendation_provider(user_id, request.provider)
    except ConflictError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "provider": provider,
        "configured": provider_is_configured(provider),
        "demo_mode": demo_mode,
    }


def provider_is_configured(provider: str) -> bool:
    try:
        build_recommender(provider)
    except DevinConfigurationError:
        return False
    return True


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def recommendations(
    request: RecommendationRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
    demo_mode: bool = Depends(get_demo_mode),
    client: Optional[DevinClient] = Depends(get_devin_client),
) -> RecommendationResponse:
    try:
        context = repository.get_user_context(user_id)
        retained_ids: List[str] = []
        excluded_ids: List[str] = []
        requested_count = 5
        session_id = request.session_id
        if session_id:
            session = repository.get_recommendation_session(session_id, user_id)
            refill = repository.recommendation_refill_state(session_id, user_id)
            requested_count = refill["requested_count"]
            retained_ids = refill["retained_ids"]
            excluded_ids = refill["recommended_ids"]
            prompt = request.prompt.strip() or session["current_prompt"]
        else:
            prompt = request.prompt.strip()
            session_id = repository.create_recommendation_session(
                user_id=user_id,
                prompt=prompt,
                mode=request.mode,
                event_id=request.event_id,
                memory_version=context["memory_version"],
            )

        excluded_labels = []
        for movie_id in excluded_ids:
            try:
                movie = repository.get_movie(movie_id)
                excluded_labels.append(f"{movie['title']} ({movie['year']})")
            except NotFoundError:
                continue
        context.update(
            {
                "mode": request.mode,
                "excluded": excluded_labels,
            }
        )

        shared_ids = (
            repository.event_round1_movies(request.event_id)
            if request.mode == "event_nomination" and request.event_id
            else []
        )
        if shared_ids and not request.session_id:
            normalized = build_shared_movies(
                repository, shared_ids, demo_mode=demo_mode
            )
            batch_id = repository.save_recommendation_batch(
                session_id=session_id,
                requested_count=len(normalized),
                movie_ids=[movie.id for movie in normalized],
                retained_ids=[],
                exclusions=[],
                interpreted_request={"summary": "Shared Round 1 line-up"},
                model_version="shared-round1",
                prompt_version="shared-round1",
            )
            return RecommendationResponse(
                session_id=session_id,
                batch_id=batch_id,
                devin_session_id=None,
                requested_count=len(normalized),
                returned_count=len(normalized),
                memory_version_used=context["memory_version"],
                shortfall_reason=None,
                interpreted_request={"summary": "Shared Round 1 line-up"},
                movies=normalized,
            )

        if requested_count == 0:
            return RecommendationResponse(
                session_id=session_id,
                batch_id=None,
                devin_session_id=None,
                requested_count=0,
                returned_count=0,
                memory_version_used=context["memory_version"],
                shortfall_reason=None,
                interpreted_request={},
                movies=[],
            )

        if demo_mode:
            result = await asyncio.to_thread(
                demo.recommend,
                prompt=prompt,
                count=requested_count,
                context=context,
            )
        else:
            result = await asyncio.to_thread(
                client.recommend,
                prompt=prompt,
                count=requested_count,
                context=context,
            )
        raw_movies = result["recommendations"]
        if len(raw_movies) > requested_count:
            raise DevinAPIError(
                f"The recommendation service returned {len(raw_movies)} movies; maximum is {requested_count}."
            )
        names = [(str(movie.get("title", "")).casefold(), movie.get("year")) for movie in raw_movies]
        if len(names) != len(set(names)):
            raise DevinAPIError("The recommendation service returned duplicate movies.")
        forbidden_titles = set() if demo_mode else {
            re.sub(r"\s+\(\d{4}\)$", "", label).casefold()
            for label in (
                context["liked"]
                + context["disliked"]
                + context["watched"]
                + context["excluded"]
            )
        }
        returned_forbidden = [
            movie.get("title")
            for movie in raw_movies
            if str(movie.get("title", "")).casefold() in forbidden_titles
        ]
        if returned_forbidden:
            raise DevinAPIError(
                "The recommendation service returned excluded movies: "
                + ", ".join(str(title) for title in returned_forbidden)
            )
        for raw_movie in raw_movies:
            reason = str(raw_movie.get("reason", "")).strip()
            if not reason or len(reason.split()) >= 25:
                raise DevinAPIError(
                    f"Recommendation reason for {raw_movie.get('title')} must be under 25 words."
                )

        stored_movies = [
            repository.upsert_recommendation_movie(raw_movie) for raw_movie in raw_movies
        ]
        if not demo_mode:
            await asyncio.gather(
                asyncio.to_thread(attach_details, repository, stored_movies),
                asyncio.to_thread(attach_posters, repository, stored_movies),
                asyncio.to_thread(attach_trailers, repository, stored_movies),
            )
        normalized = []
        movie_ids = []
        for index, raw_movie in enumerate(raw_movies):
            movie = normalize_movie(raw_movie, stored_movies[index], index)
            normalized.append(movie)
            movie_ids.append(movie.id)

        if request.mode == "event_nomination" and request.event_id and not request.session_id:
            saved_ids = repository.save_event_round1_movies(request.event_id, movie_ids)
            if saved_ids != movie_ids:
                movie_ids = saved_ids
                normalized = build_shared_movies(
                    repository, movie_ids, demo_mode=demo_mode
                )
        batch_id = repository.save_recommendation_batch(
            session_id=session_id,
            requested_count=requested_count,
            movie_ids=movie_ids,
            retained_ids=retained_ids,
            exclusions=excluded_ids,
            interpreted_request=result.get("interpreted_request", {}),
            model_version="devin-v3",
            prompt_version="movie-search-v2",
        )
        shortfall_reason = None
        if len(normalized) < requested_count:
            shortfall_reason = (
                f"Only {len(normalized)} verified, eligible recommendations remained."
            )
        return RecommendationResponse(
            session_id=session_id,
            batch_id=batch_id,
            devin_session_id=result["session_id"],
            requested_count=requested_count,
            returned_count=len(normalized),
            memory_version_used=context["memory_version"],
            shortfall_reason=shortfall_reason,
            interpreted_request=result.get("interpreted_request", {}),
            movies=normalized,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except demo.DemoCatalogueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except DevinConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except DevinSessionTimeout as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except DevinAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/feedback", status_code=201)
def submit_feedback(
    request: FeedbackRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
    demo_mode: bool = Depends(get_demo_mode),
) -> Dict[str, Any]:
    validate_feedback_request(request)
    context_id = resolve_context_id(request)
    try:
        feedback, created = repository.submit_feedback(
            user_id=user_id,
            movie_id=request.movie_id,
            dimension=request.dimension,
            value=request.value,
            source_surface=request.source_surface,
            context=request.context,
            context_id=context_id,
            idempotency_key=idempotency_key,
            session_id=request.session_id,
            event_id=request.event_id,
            reason_code=request.reason_code,
            reason_text=request.reason_text,
            operation="replace" if request.superseded_feedback_id else "create",
            superseded_feedback_id=request.superseded_feedback_id,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    job = repository.get_analysis_job_for_feedback(feedback["feedback_id"])
    if created and job:
        background_tasks.add_task(
            process_analysis_job,
            repository.database,
            job["job_id"],
            demo_mode,
        )
    return {
        "feedback": feedback,
        "created": created,
        "analysis_job_id": job["job_id"] if job else None,
    }


@app.post("/api/feedback/undo", status_code=201)
def undo_feedback(
    request: UndoRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        feedback, created = repository.undo_feedback(
            user_id=user_id,
            feedback_id=request.feedback_id,
            idempotency_key=idempotency_key,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"feedback": feedback, "created": created}


@app.get("/api/feedback")
def current_feedback(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    return {"items": repository.get_current_feedback(user_id)}


@app.get("/api/memory")
def get_memory(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    return repository.get_memory(user_id)


@app.post("/api/memory/explicit", status_code=201)
def add_explicit_memory(
    request: ExplicitMemoryRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    return repository.add_explicit_memory(user_id=user_id, **request.model_dump())


@app.post("/api/memory/{entry_id}/confirm")
def confirm_memory(
    entry_id: str,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.update_memory_status(
            user_id=user_id,
            entry_id=entry_id,
            status="active",
            confirmation=True,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.delete("/api/memory/{entry_id}")
def reject_memory(
    entry_id: str,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.update_memory_status(
            user_id=user_id,
            entry_id=entry_id,
            status="user_rejected",
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.put("/api/memory/{entry_id}")
def correct_memory(
    entry_id: str,
    request: CorrectMemoryRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.correct_memory(
            user_id=user_id,
            entry_id=entry_id,
            **request.model_dump(),
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/memory/rebuild", status_code=202)
def rebuild_memory(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        job_ids = repository.rebuild_memory(user_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    for job_id in job_ids:
        background_tasks.add_task(
            process_analysis_job,
            repository.database,
            job_id,
        )
    return {"job_ids": job_ids}


@app.post("/api/events", status_code=201)
def create_event(
    request: EventRequest,
    http_request: Request,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    base_url = os.getenv("PUBLIC_BASE_URL", "").strip() or str(
        http_request.base_url
    ).rstrip("/")
    return repository.create_event(
        host_user_id=user_id,
        name=request.name,
        event_date=request.event_date,
        prompt=request.prompt,
        invite_base_url=base_url,
    )


@app.get("/api/events/{invite_code}")
def get_event(
    invite_code: str,
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.get_event(invite_code)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/events/{invite_code}/join")
def join_event(
    invite_code: str,
    request: JoinEventRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.join_event(
            invite_code=invite_code,
            user_id=user_id,
            display_name=request.display_name,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/events")
def list_events(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    return {"items": repository.list_events(user_id)}


@app.get("/api/events/{invite_code}/state")
def event_state(
    invite_code: str,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.event_state(invite_code, user_id)
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/events/{invite_code}/nominations")
def submit_nominations(
    invite_code: str,
    request: NominationRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.submit_nominations(
            invite_code=invite_code,
            user_id=user_id,
            movie_ids=request.movie_ids,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/events/{invite_code}/votes")
def submit_votes(
    invite_code: str,
    request: VoteRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.submit_votes(
            invite_code=invite_code,
            user_id=user_id,
            votes=request.votes,
            finished=request.finished,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/events/{invite_code}/round")
def advance_event(
    invite_code: str,
    request: RoundRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.advance_event(
            invite_code=invite_code,
            user_id=user_id,
            status=request.status,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/events/{invite_code}/winner")
def set_event_winner(
    invite_code: str,
    request: WinnerRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    try:
        return repository.set_event_winner(
            invite_code=invite_code,
            user_id=user_id,
            movie_id=request.movie_id,
        )
    except NotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


def validate_feedback_request(request: FeedbackRequest) -> None:
    if request.value not in FEEDBACK_VALUES[request.dimension]:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid value for {request.dimension}.",
        )
    if request.reason_code and request.reason_code not in REASON_CODES:
        raise HTTPException(status_code=422, detail="Invalid feedback reason code.")
    if request.dimension == "group_vote" and request.context != "event":
        raise HTTPException(
            status_code=422,
            detail="Group votes require event context.",
        )


def resolve_context_id(request: FeedbackRequest) -> str:
    if request.context == "session":
        if not request.session_id:
            raise HTTPException(
                status_code=422,
                detail="Session context requires session_id.",
            )
        return request.session_id
    if request.context == "event":
        if not request.event_id:
            raise HTTPException(
                status_code=422,
                detail="Event context requires event_id.",
            )
        return request.event_id
    return ""


NO_STORE = {"Cache-Control": "no-store"}


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(ROOT / "index.html", headers=NO_STORE)


@app.get("/join/{invite_code}")
def join_frontend(invite_code: str) -> FileResponse:
    return FileResponse(ROOT / "index.html", headers=NO_STORE)


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(
        ROOT / "app.js", media_type="application/javascript", headers=NO_STORE
    )


@app.get("/styles.css")
def frontend_styles() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css", headers=NO_STORE)


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")

if demo.CLIP_DIR.is_dir():
    app.mount(
        demo.CLIP_ROUTE,
        StaticFiles(directory=demo.CLIP_DIR),
        name="demo-clips",
    )
