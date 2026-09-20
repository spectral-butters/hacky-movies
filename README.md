# ReelPick

Hackathon MVP for an AI-powered movie recommendation app. The responsive frontend is served by a FastAPI backend that uses the Devin API to generate real movie recommendations.

## Flows

- **Taste survey:** optional genre hints → five well-known calibration movies → adaptive genre rounds → liked / disliked / haven't watched / watchlist, with an occasional one-tap reason. It stops offering more rounds once there is enough signal (8 rated, 2 likes, 1 dislike) and caps at the 25-movie pool.
- **Personal:** natural-language prompt → five short-form recommendations → hold-and-drag reactions → liked results → final movie → where to watch.
- **Movie night:** create event → invite lobby → one shared Round 1 line-up → private nominations → host closes Round 1 → group voting → host picks a finalist → winner.
- **Library:** burger menu → account, liked/disliked preferences, watchlist, and prior movie nights. The home screen shows the watchlist directly.

Recommendation titles and verified IMDb identities come from Devin. SQLite persists the catalogue, recommendation sessions, append-only feedback audit, current feedback state, preference memory, analysis jobs, watchlists, and movie-night invite links. Short-form media and full multi-device round orchestration remain mocked for the demo.

## Configure

Copy `.env.example` to `.env` and fill in the keys you have. The backend loads `.env`
on startup, so nothing has to be exported by hand:

```sh
cp .env.example .env
```

```sh
RECOMMENDATION_PROVIDER=devin        # default engine for new users: devin or nebius
DEVIN_API_KEY=cog_...
DEVIN_ORG_ID=org-...
NEBIUS_API_KEY=...
SLNG_API=slng_...                    # voice input
```

Real environment variables always win over `.env`, so `DEVIN_API_KEY=... uvicorn ...`
still works for a one-off override.

### Search engines

Recommendations come from one of two engines, chosen per user under **Account → Search
engine** and stored in `users.recommendation_provider`:

- **Devin** — agent sessions with verified IMDb identities. Needs `DEVIN_API_KEY` and
  `DEVIN_ORG_ID` from [Settings → Service users](https://app.devin.ai/settings/devin-api?tab=service-users#org-service-users-list).
- **Qwen 3.5** — `Qwen/Qwen3.5-397B-A17B` on
  [Nebius Token Factory](https://tokenfactory.nebius.com), thinking off, structured JSON
  output. Needs `NEBIUS_API_KEY`.

Both engines render the same master prompt from `prompts/movie_search.txt` and return the
same schema, so switching engines changes nothing else in the app.

The master recommendation prompt can be replaced without changing the API contract.
Optional runtime settings:

```sh
DEVIN_API_BASE_URL=https://api.devin.ai/v3
DEVIN_SESSION_TIMEOUT_SECONDS=150
NEBIUS_API_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=Qwen/Qwen3.5-397B-A17B
NEBIUS_THINKING=off
NEBIUS_TEMPERATURE=0.6
NEBIUS_MAX_TOKENS=4096
MOVIE_SEARCH_PROMPT_PATH=prompts/movie_search.txt
PREFERENCE_ANALYSIS_PROMPT_PATH=prompts/preference_analysis.txt
REELPICK_DB_PATH=data/reelpick.db
PUBLIC_BASE_URL=https://your-reelpick-host.example
```

`PUBLIC_BASE_URL` is optional; when omitted, invite links use the incoming request host.

The recommendation endpoint binds the current request to authoritative server-side user description, watched ratings, recommendation interest, watchlist state, and supported preference memory. Frontend-supplied preference lists are ignored.

## Shared Round 1 line-up

Everyone in a movie night nominates from the same five movies. The first Round 1 request for an
event generates the line-up and stores it on `movie_events.round1_movie_ids`; every later request
for that event replays it without calling the recommender. Round 1 only opens when the host starts
it, so in practice the host's request defines the set, and the write is guarded so a race between
two guests still leaves one agreed line-up.

Each participant keeps their own recommendation session, so nominations and feedback stay private.

## Trailers

In live mode every recommendation carries an IMDb trailer, which autoplays in the feed the way the
bundled clips do in demo mode. `backend/trailers.py` resolves an IMDb ID to a video ID through the
suggestion API, preferring a video labelled *Trailer* over a TV spot or clip, then asks IMDb's
GraphQL endpoint for the playback URLs and picks the lightest usable MP4.

The URLs are CloudFront-signed and expire after roughly 24 hours, so they are cached on
`movies.short_video_url` and re-resolved once they fall inside a 30-minute refresh margin. Posters
and trailers are fetched concurrently, so a live search costs no more wall-clock than before.

`DEF_480p` (about 30 MB for a two-minute trailer) is the default rather than `DEF_720p` (about
60 MB), because the feed autoplays and you swipe away after a few seconds. Override it when
bandwidth is not a concern:

```sh
export REELPICK_TRAILER_DEFINITION="DEF_720p"
```

Demo mode ignores all of this and keeps playing the local files in `demo/`.

## Taste survey

New users land on the survey before their first search; anyone can retake it from **My Preferences →
Take the taste survey**. The 25-movie pool lives in `backend/onboarding.py`, grouped so each round
mixes contrasting picks rather than five near-identical titles. Posters come from IMDb and are
cached on the movie row after the first lookup.

Reactions are ordinary feedback records, so the survey feeds the same preference memory, watchlist,
and recommendation context as the rest of the app:

| Survey action | Recorded as |
| --- | --- |
| Liked | `viewing_status=watched` + `watched_rating=liked` |
| Disliked | `viewing_status=watched` + `watched_rating=disliked` |
| Haven't watched | `viewing_status=unwatched` |
| Add to watchlist | `viewing_status=unwatched` + `watchlist=saved` |

A watchlist save is an interest signal, not a like, and is never treated as one. Genre selection is
a soft starting hint: unselected genres are still offered as wildcard picks and are never excluded.

## Demo mode

Demo mode replaces the Devin call with a fixed catalogue and plays the short clips in
`demo/` instead of IMDb posters. The flow is prompt → two-second wait → five clips →
decline some → request more → like or dislike → preferences, with no AI call and no
network dependency.

Toggle it per browser from the burger menu (**Demo mode**), or make it the default for
every client:

```sh
export REELPICK_DEMO=1
```

The menu toggle sends `X-ReelPick-Demo` on every request and overrides the environment
default, so one running server can serve both the demo and the live product.

Clips live in `demo/` and are described by `demo/catalogue.json`: `file` must match a
filename in that folder, and the order of `movies` is the order the demo serves them in.
The `.mp4` files are deliberately untracked. Optional settings:

```sh
export REELPICK_DEMO_CLIP_DIR="demo"
export REELPICK_DEMO_CATALOGUE="demo/catalogue.json"
export REELPICK_DEMO_LATENCY_SECONDS="2"
```

Demo recommendations are written to SQLite like real ones, so feedback, preferences, and
the watchlist behave normally. Preference-analysis jobs are recorded but not run, keeping
the demo off the network entirely.

## Run locally

```sh
python3 -m venv .venv
.venv/bin/pip install '.[dev]'
.venv/bin/uvicorn backend.main:app --reload --port 4173
```

Open `http://localhost:4173`.

## Check

```sh
.venv/bin/pytest -q
node --check app.js
.venv/bin/python -m compileall -q backend tests
git diff --check
```

## Interaction notes

- In recommendation feeds, swipe vertically to move through movies.
- Press and hold a movie for 150 ms, then drag toward a colored quadrant and release to react.
- Tap the movie to pause or resume its animated mock clip.
- Feed likes record recommendation interest only. “Already watched” records viewing status and a separate liked, disliked, or neutral watched rating.
- Movie-night links are generated by the backend and remain valid across server restarts when the SQLite data directory is persistent.
