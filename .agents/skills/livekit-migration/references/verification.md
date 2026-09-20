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

Acceptable matches are references such as `SLNG_API_KEY`, `os.environ["SLNG_API_KEY"]`, or docs telling
the user to set the variable. If any line contains a quoted key value, remove it and rotate the key.
When SLNG LLM is selected, the Context Router must also read `SLNG_API_KEY`; do not introduce a separate
literal key.

## 3. Unit Test

Prefer a test that imports the project's own pipeline factory or session builder and asserts the
configured STT and TTS are `slng.STT` and `slng.TTS`. If provisioned SLNG Context Router was selected,
assert the LLM is the LiveKit OpenAI-compatible LLM configured with the selected regional `base_url`,
`model="slng/auto"`, environment-backed API key, and required `X-Slng-Agent-Id` /
`X-Slng-Session-Id` headers. This catches future edits to the actual agent.

If the project has no factory, add one only when it keeps the edit small and makes the pipeline easier
to test. Do not refactor unrelated business logic just to add a test.

Fallback test for projects where the pipeline cannot be imported cleanly:

```python
# tests/test_slng_pipeline.py
import pytest
from livekit.plugins import slng


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    # The plugin reads SLNG_API_KEY; a dummy value is fine for a config assertion.
    monkeypatch.setenv("SLNG_API_KEY", "test-key")


def test_stt_is_slng_nova_3():
    stt = slng.STT(model="deepgram/nova:3", language="en")
    assert isinstance(stt, slng.STT)


def test_tts_is_slng_sonic_3():
    tts = slng.TTS(model="cartesia/sonic:3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc")
    assert isinstance(tts, slng.TTS)
```

Only assert model ids through public or stable project-level configuration. Avoid private fields such
as `_model` or `_opts` unless there is no better option and the test is clearly marked as version
sensitive.

Run tests with the discovered package manager:

```bash
uv run pytest
# or:
poetry run pytest
# or:
python -m pytest
```

## 4. Live-turn check - the real acceptance gate

A passing unit test and clean `ruff` only prove the code is wired to the right strings. They pass even
when the agent is broken at runtime (missing org/router config, invalid key, provider rejecting the
request, or unstable agent/session identifiers preventing router behavior).
**Only a live spoken turn that completes STT -> LLM -> TTS proves the migration works.** This step needs
a real `SLNG_API_KEY` in the project's runtime environment, validated against `/v1/agents`, and LiveKit
credentials.

Use the discovered entrypoint. For the official starter:

```bash
uv run python src/agent.py download-files
uv run python src/agent.py console
```

For LiveKit Cloud observability, use `dev` instead. If the entrypoint uses `agent_name=` (explicit
dispatch), the worker will not auto-join rooms. Dispatch it and join with a mic client:

```bash
uv run python src/agent.py dev
# in another shell:
lk dispatch create --new-room --agent-name <agent_name>
# then join that room from a mic-enabled client (e.g. https://agents-playground.livekit.io)
```

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
- [ ] `from livekit.plugins import slng` imports successfully.
- [ ] STT and TTS are `slng.STT` / `slng.TTS` wired to the intended models.
- [ ] The LLM was left on its current provider, unless SLNG LLM was selected.
- [ ] If SLNG LLM was selected, SLNG org/router configuration is provisioned.
- [ ] If SLNG LLM was selected, the LLM uses LiveKit's OpenAI-compatible plugin, the selected regional
      Context Router base URL, `model="slng/auto"`, required `X-Slng-Agent-Id` / `X-Slng-Session-Id`
      headers, and no `slng.LLM` reference.
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
| `401` on an SLNG websocket or `STT/TTS fallback exhausted` | Missing or invalid `SLNG_API_KEY` in the runtime environment | Validate the key and ensure the same env is loaded by the worker process |
| `ValueError: api_key is required` | No key resolved when the component is constructed | Configure `SLNG_API_KEY` before launch or pass `api_key=os.environ["SLNG_API_KEY"]` |
| No transcription and empty LiveKit Cloud agent panel | Worker did not run a healthy turn, or explicit-dispatch agent was never dispatched | Fix credentials first, then dispatch the named agent and join the room with a mic client |
| STT works but TTS fails, or vice versa | One model, voice, provider route, or region is unavailable | Keep the working stage on SLNG, revert the failing stage to its original provider, and report the partial migration |
| Provider-specific 400 during TTS/STT | Gateway or model-specific incompatibility | Confirm the current SLNG docs, retry with another supported model only as a temporary unblock, and report the issue |
