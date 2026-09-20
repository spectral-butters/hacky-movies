# Verifying the Migration

Run these after applying the migration. They are ordered cheapest-first: static checks, then focused
wiring tests, then a live boot. A live spoken turn is the acceptance gate.

## 1. Git safety checks

The tree should contain only the intended pipeline edits, with no whitespace or conflict errors:

```bash
git diff --check
git status --short
```

Review that the changed files match the discovered project shape, for example the entrypoint,
dependency file, tests, and optional env/config docs.

## 2. No-secret check

The diff must not contain a literal API key:

```bash
git diff | grep -nE 'api_key|SLNG_API_KEY'
```

Acceptable matches are references such as `SLNG_API_KEY`, `os.getenv("SLNG_API_KEY")`, or docs telling
the user to set the variable. If any line contains a quoted key value, remove it and rotate the key.
When SLNG LLM is selected, the Context Router must also read `SLNG_API_KEY`; do not introduce a separate
literal key.

## 3. Unit Test

Prefer a test that imports the project's own service factory or bot builder and asserts the
configured STT and TTS are `SlngSTTService` and `SlngTTSService`. If provisioned SLNG Context Router was
selected, assert the LLM is Pipecat's `OpenAILLMService` configured with the selected regional
`base_url`, `model="slng/auto"`, environment-backed API key, and required `X-Slng-Agent-Id` /
`X-Slng-Session-Id` headers. This catches future edits to the actual bot.

If the project has no factory, add one only when it keeps the edit small and makes the pipeline easier
to test. Do not refactor unrelated business logic just to add a test.

Fallback test for projects where the pipeline cannot be imported cleanly:

```python
# tests/test_slng_pipeline.py
import os

import pytest
from pipecat_slng import SlngSTTService, SlngTTSService


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    # A dummy value is fine for a config assertion.
    monkeypatch.setenv("SLNG_API_KEY", "test-key")


def test_stt_is_slng_nova_3():
    stt = SlngSTTService(api_key=os.getenv("SLNG_API_KEY"), model="slng/deepgram/nova:3-en")
    assert isinstance(stt, SlngSTTService)


def test_tts_is_slng_aura_2():
    tts = SlngTTSService(
        api_key=os.getenv("SLNG_API_KEY"),
        model="slng/deepgram/aura:2-en",
        voice="aura-2-thalia-en",
    )
    assert isinstance(tts, SlngTTSService)
```

Only assert model ids through public or stable project-level configuration. Avoid private fields
unless there is no better option and the test is clearly marked as version sensitive.

Run tests with the discovered package manager:

```bash
uv run pytest
# or:
poetry run pytest
# or:
python -m pytest
```

## 4. Live-turn check - the real acceptance gate

A passing unit test and clean lint only prove the code is wired to the right strings. They pass even
when the bot is broken at runtime (missing org/router config, invalid key, provider rejecting the
request, or unstable agent/session identifiers preventing router behavior).
**Only a live spoken turn that completes STT -> LLM -> TTS proves the migration works.** This step needs
a real `SLNG_API_KEY` in the project's runtime environment, validated against `/v1/agents`, plus
whatever credentials the project's transport requires (Daily room/API key, telephony number, ...).

Use the discovered entrypoint and transport. For a SmallWebRTC bot:

```bash
uv run bot.py
# then open http://localhost:7860/client in a browser with a mic
```

For a Daily transport, run the bot (some projects use a `-t daily` flag) and join the printed Daily
room URL from a mic-enabled client. For telephony transports, call the configured number.

**Verify each stage independently**. STT can transcribe while TTS fails, or vice-versa. Confirm you
see the user transcript in the logs *and* hear the spoken reply. If one stage fails at runtime, see
the Troubleshooting table below and handle it as the subset case. Check first-token latency in
the [slng dashboard](https://app.slng.ai).

## 5. Lint and Format

Run the project's existing commands. Examples:

```bash
uv run ruff format
uv run ruff check
```

## Acceptance checklist

- [ ] `git status` was clean before the migration started (clean rollback point).
- [ ] `from pipecat_slng import SlngSTTService, SlngTTSService` imports successfully.
- [ ] STT and TTS are `SlngSTTService` / `SlngTTSService` wired to the intended models, in the same
      `Pipeline([...])` positions as before.
- [ ] The LLM was left on its current provider, unless SLNG LLM was selected.
- [ ] If SLNG LLM was selected, SLNG org/router configuration is provisioned.
- [ ] If SLNG LLM was selected, the LLM uses Pipecat's `OpenAILLMService`, the selected regional
      Context Router base URL, `model="slng/auto"`, required `X-Slng-Agent-Id` / `X-Slng-Session-Id`
      headers, and no `SlngLLMService` reference.
- [ ] No API key literal appears in the diff.
- [ ] Project tests pass, including any STT/TTS assertions added for this migration.
- [ ] `SLNG_API_KEY` is available to the runtime and validates against `/v1/me` (e.g. `voiceai whoami`).
- [ ] A **live turn** completes: user transcript appears in logs **and** the spoken reply is heard (each stage verified independently).
- [ ] Any stage left on its original provider is reported to the user with how to finish it.
- [ ] The original entrypoint and deployment command still work.

## Rollback

Because the migration started from a clean tree:

```bash
git restore .             # before committing: discard all migration edits
git revert <sha>          # after committing: reverse the migration commit
```

If the project did not have git and the user chose a manual backup, restore from that backup instead.

## Troubleshooting

These issues often surface only during a live turn:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `401` on `wss://api.slng.ai/v1/bridges/unmute/...` | Missing or invalid `SLNG_API_KEY` in the runtime environment | Validate the key and ensure the same env is loaded by the bot process |
| api_key error when the service is constructed | No key resolved at the call site | Configure `SLNG_API_KEY` before launch and pass `api_key=os.getenv("SLNG_API_KEY")` |
| No transcripts despite audible speech | Wrong STT model id, region without that model, or low-confidence audio (transcripts under 0.5 confidence are dropped) | Confirm the model id and region in the current SLNG docs; test with clear audio |
| Brief audio gap after changing voice/speed/language | Expected behavior: runtime setting changes reconnect the TTS WebSocket | No fix needed; avoid mid-utterance setting changes if the gap matters |
| `speed` rejected or ignored | Model does not support speed (e.g. Rime, Sarvam) | Drop the `speed` argument for that model |
| HTTP TTS returns an error for the audio format | `SlngHttpTTSService` handles WAV and plain PCM only; compressed formats error | Use server defaults, or switch to streaming `SlngTTSService` |
| STT works but TTS fails, or vice versa | One model, voice, provider route, or region is unavailable | Keep the working stage on SLNG, revert the failing stage to its original provider, and report the partial migration |
| Provider-specific 400 during TTS/STT | Gateway or model-specific incompatibility | Confirm the current SLNG docs, retry with another supported model only as a temporary unblock, and report the issue |
