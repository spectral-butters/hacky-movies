# ReelPick

Dependency-free hackathon MVP for an AI-powered movie recommendation app.

## Flows

- **Personal:** natural-language prompt → five short-form recommendations → hold-and-drag reactions → liked results → final movie → where to watch.
- **Movie night:** create event → invite lobby → private nominations → host closes Round 1 → group voting → host picks a finalist → winner.
- **Library:** burger menu → account, liked/disliked preferences, watchlist, and prior movie nights.

All data, AI responses, media, account details, and provider handoffs are mocked for the demo. Preference and watchlist edits persist in local storage.

## Run locally

```sh
python3 -m http.server 4173
```

Open `http://localhost:4173`.

## Interaction notes

- In recommendation feeds, swipe vertically to move through movies.
- Press and hold a movie for 150 ms, then drag toward a colored quadrant and release to react.
- Tap the movie to pause or resume its animated mock clip.
