# ReelPick

Hackathon MVP for an AI-powered movie recommendation app. The responsive frontend is served by a FastAPI backend that uses the Devin API to generate real movie recommendations.

## Flows

- **Personal:** natural-language prompt → five short-form recommendations → hold-and-drag reactions → liked results → final movie → where to watch.
- **Movie night:** create event → invite lobby → private nominations → host closes Round 1 → group voting → host picks a finalist → winner.
- **Library:** burger menu → account, liked/disliked preferences, watchlist, and prior movie nights.

Recommendation titles and metadata come from Devin. Short-form media, account details, event collaboration, and provider availability remain mocked for the demo. Preference and watchlist edits persist in local storage.

## Configure

Create a Devin service-user API key in [Settings → Service users](https://app.devin.ai/settings/devin-api?tab=service-users#org-service-users-list), then expose it to the backend:

```sh
export DEVIN_API_KEY="cog_..."
```

The master recommendation prompt lives in `prompts/movie_search.txt`. It can be replaced without changing the API contract. Optional runtime settings:

```sh
export DEVIN_API_BASE_URL="https://api.devin.ai/v1"
export DEVIN_SESSION_TIMEOUT_SECONDS="150"
export MOVIE_SEARCH_PROMPT_PATH="prompts/movie_search.txt"
```

## Run locally

```sh
python3 -m venv .venv
.venv/bin/pip install '.[dev]'
.venv/bin/uvicorn backend.main:app --reload --port 4173
```

Open `http://localhost:4173`.

## Check

```sh
.venv/bin/pytest
node --check app.js
git diff --check
```

## Interaction notes

- In recommendation feeds, swipe vertically to move through movies.
- Press and hold a movie for 150 ms, then drag toward a colored quadrant and release to react.
- Tap the movie to pause or resume its animated mock clip.
