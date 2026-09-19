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
    Header,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.database import DEFAULT_USER_ID, Database
from backend.devin_client import (
    DevinAPIError,
    DevinClient,
    DevinConfigurationError,
    DevinSessionTimeout,
)
from backend.memory import PreferenceAnalysisWorker
from backend.repository import (
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


database = Database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database.initialize()
    app.state.repository = ReelPickRepository(app.state.database)
    yield


app = FastAPI(title="ReelPick API", version="0.3.0", lifespan=lifespan)
app.state.database = database
app.state.repository = ReelPickRepository(database)


def get_repository(request: Request) -> ReelPickRepository:
    return request.app.state.repository


def get_devin_client() -> DevinClient:
    try:
        return DevinClient.from_env()
    except DevinConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def get_user_id(x_reelpick_user: str = Header(default=DEFAULT_USER_ID)) -> str:
    user_id = x_reelpick_user.strip()
    if not user_id or len(user_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid ReelPick user ID.")
    return user_id


def process_analysis_job(database: Database, job_id: str) -> None:
    try:
        client = DevinClient.from_env()
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
        raise DevinAPIError("Devin returned an invalid movie title or year.")

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
    genre = str(factual.get("genre", "Movie"))
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
        imdb_id=imdb_id,
        imdb_url=imdb_url,
        match_score=int(raw_movie.get("match_score", 0)),
        recommendation_type=recommendation_type,
        preference_connections=[
            str(item) for item in raw_movie.get("preference_connections", [])
        ],
        possible_mismatch=raw_movie.get("possible_mismatch"),
        in_watchlist=bool(raw_movie.get("in_watchlist")),
    )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/bootstrap")
def bootstrap(
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Dict[str, Any]:
    return repository.bootstrap(user_id)


@app.put("/api/user/description", status_code=204)
def update_user_description(
    request: UserDescriptionRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
) -> Response:
    repository.update_user_description(user_id, request.description)
    return Response(status_code=204)


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def recommendations(
    request: RecommendationRequest,
    user_id: str = Depends(get_user_id),
    repository: ReelPickRepository = Depends(get_repository),
    client: DevinClient = Depends(get_devin_client),
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

        result = await asyncio.to_thread(
            client.recommend,
            prompt=prompt,
            count=requested_count,
            context=context,
        )
        raw_movies = result["recommendations"]
        if len(raw_movies) > requested_count:
            raise DevinAPIError(
                f"Devin returned {len(raw_movies)} movies; maximum is {requested_count}."
            )
        names = [(str(movie.get("title", "")).casefold(), movie.get("year")) for movie in raw_movies]
        if len(names) != len(set(names)):
            raise DevinAPIError("Devin returned duplicate movies.")
        forbidden_titles = {
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
                "Devin returned excluded movies: "
                + ", ".join(str(title) for title in returned_forbidden)
            )
        for raw_movie in raw_movies:
            reason = str(raw_movie.get("reason", "")).strip()
            if not reason or len(reason.split()) >= 25:
                raise DevinAPIError(
                    f"Recommendation reason for {raw_movie.get('title')} must be under 25 words."
                )

        normalized = []
        movie_ids = []
        for index, raw_movie in enumerate(raw_movies):
            stored = repository.upsert_recommendation_movie(raw_movie)
            movie = normalize_movie(raw_movie, stored, index)
            normalized.append(movie)
            movie_ids.append(movie.id)

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


@app.get("/")
def frontend() -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/join/{invite_code}")
def join_frontend(invite_code: str) -> FileResponse:
    return FileResponse(ROOT / "index.html")


@app.get("/app.js")
def frontend_script() -> FileResponse:
    return FileResponse(ROOT / "app.js", media_type="application/javascript")


@app.get("/styles.css")
def frontend_styles() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css")


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
