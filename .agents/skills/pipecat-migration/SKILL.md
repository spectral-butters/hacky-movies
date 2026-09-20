---
name: pipecat-migration
description: Migrate an existing Pipecat Python project to SLNG hosted speech infrastructure for STT/TTS via pipecat-slng, with optional SLNG Context Router support through Pipecat's OpenAI-compatible service. Use when the user asks to "move my Pipecat bot to slng", "use slng for STT/TTS in Pipecat", "swap Deepgram/Cartesia for slng in pipecat", "add the slng pipecat plugin", "use SLNG LLM router in Pipecat", or "migrate pipecat to slng".
license: MIT
compatibility: Requires a Pipecat (pipecat-ai >= 1.3.0) Python 3.11+ project, internet access, and a SLNG_API_KEY for runtime verification. Works with uv, Poetry, pip, or other Python dependency managers when detected.
---

# Migrate a Pipecat Bot to SLNG

Move an existing Pipecat Python project onto SLNG hosted speech infrastructure by replacing the
speech-to-text and text-to-speech services with `SlngSTTService` and `SlngTTSService` from
`pipecat-slng`. If the user explicitly selected SLNG LLM and SLNG has provisioned the customer's
org/router configuration, point the project's LLM at the SLNG OpenAI-compatible Context Router through
Pipecat's `OpenAILLMService`.

This is a pipeline migration, not a bot rewrite. Preserve the transport (Daily, SmallWebRTC,
Twilio/telephony, FastAPI WebSocket), VAD, turn-taking, context aggregators, prompts, tools, and
business logic. Preserve the user's current LLM unless the user or generated stack explicitly asks
for provisioned SLNG Context Router.

> Scope: `pipecat-slng` exposes `SlngSTTService`, `SlngTTSService`, and `SlngHttpTTSService`. It
> does not provide an LLM service. If SLNG LLM is selected, use Pipecat's `OpenAILLMService` with a
> custom `base_url`. Use the agent-facing model `slng/auto`; provider/catalog model ids belong in
> SLNG org config. Never add or reference an `SlngLLMService`.

Use these references only when needed:

- [`references/project-discovery.md`](references/project-discovery.md) - project layout, package manager, env, and pipeline detection
- [`references/pipeline-reference.md`](references/pipeline-reference.md) - service constructors, model examples, regions, and starter before/after
- [`references/verification.md`](references/verification.md) - checks, live-turn verification, rollback, and troubleshooting
- [`../setup-api-key`](../setup-api-key/SKILL.md) - obtain and validate an SLNG API key

## Operating Principles

- Adapt to the project in front of you. Do not assume `bot.py`, `uv`, `.env`, `ruff`, or pytest
  unless discovery confirms them.
- Ask only for choices that cannot be inferred safely, such as an ambiguous model, voice, language, or
  data residency requirement. Do not ask the user to choose an LLM provider/catalog model id for
  router code; SLNG provisions that in org config.
- Keep edits minimal and idempotent. Running the migration twice should not duplicate imports,
  dependencies, tests, or constructor arguments.
- Stop before code edits if the required plugin cannot be installed and imported. Do not guess alternate
  package names or import paths.
- Never print, paste, log, or commit API keys.

## 1. Discover the Existing Project

Before editing, inspect enough local context to identify:

- The Pipecat entrypoint, for example `bot.py`, `main.py`, `examples/bot.py`, a configured script
  in `pyproject.toml`, Dockerfile, Procfile, or a Pipecat Cloud deployment config such as
  `pcc-deploy.toml`.
- The dependency manager: `uv`, Poetry, pip, pip-tools, or another project-specific flow.
- The env loading strategy: `.env`, `.env.local`, shell env, container env, or deployment secrets.
- Current STT, TTS, LLM, VAD, transport, and turn-taking wiring.
- Where the services are constructed and where `Pipeline([...])` assembles them: a
  `bot(runner_args)` function used by the Pipecat development runner, a `run_bot()` function, a
  factory, or separate modules.
- Where the LLM is constructed, only if SLNG LLM was selected.
- Existing tests and quality commands, if any.

Report the discovered STT, TTS, and LLM providers before changing anything, including whether the LLM
will stay unchanged or move to the provisioned SLNG Context Router. Use
[`references/project-discovery.md`](references/project-discovery.md) for command examples.

## 2. Establish a Rollback Point

Prefer a clean git tree before mutating files:

```bash
git status --short
git diff --check
```

If there are uncommitted changes, stop and ask the user to commit or stash them before continuing.
If the project is not a git repo, ask whether to initialize git, create a manual backup, or proceed
without automatic rollback. Do not run `git init` without user confirmation.

## 3. Validate Credentials Without Exposing Them

The SLNG Pipecat plugin and the SLNG Context Router both use `SLNG_API_KEY`. If the project already has
`VOICEAI_API_KEY` and `SLNG_API_KEY` is missing, treat `VOICEAI_API_KEY` as the same SLNG credential
only after validation, then configure `SLNG_API_KEY` for the Pipecat runtime.

Check presence without printing the value:

```bash
[ -n "$SLNG_API_KEY" ] && echo "SLNG_API_KEY is set" || echo "SLNG_API_KEY is NOT set"
```

Validate the key with `voiceai whoami` (`GET /v1/me`) or the `setup-api-key` skill's current
recommended method. A `200` response means the key is usable; `401` means it is missing, malformed,
revoked, or for the wrong workspace.

Store the key using the project's discovered env convention. Many Pipecat projects load `.env` via
`load_dotenv()`; others use shell env, deployment secrets, or container config. Confirm any local
env file is ignored by git before writing to it.

Unlike plugins that read the key implicitly, the SLNG Pipecat services take `api_key` explicitly.
Wire `api_key=os.getenv("SLNG_API_KEY")` at the call site, never a literal.

## 4. Install and Probe Required Plugins

Install `pipecat-slng` with the detected package manager:

```bash
uv add pipecat-slng
```

Equivalent examples:

```bash
poetry add pipecat-slng
python -m pip install pipecat-slng
```

Then probe the import using the matching runner:

```bash
uv run python -c "from pipecat_slng import SlngSTTService, SlngTTSService"
```

If the import fails, stop before editing code. Report the exact failure and point the user at the
current SLNG Pipecat plugin docs to confirm the package and import surface. The plugin requires
Python 3.11+ and `pipecat-ai>=1.3.0`; report a version conflict instead of forcing an upgrade.

If SLNG LLM was selected, first confirm SLNG org/router configuration has been provisioned for this
customer. If it has not, stop and report that SLNG must configure the customer's provider/model/API-key
settings before LLM migration can be verified.

Then ensure the project has Pipecat's OpenAI service available and probe its import. Most projects
already have it; otherwise install the extra the project's docs recommend (commonly
`pipecat-ai[openai]`):

```bash
uv run python -c "from pipecat.services.openai.llm import OpenAILLMService"
```

Do not use `pipecat-slng` for LLM wiring.

## 5. Plan the Speech Swap

Default to a faithful migration:

- Keep the current STT provider/model through SLNG when a clear mapping exists.
- Keep the current TTS provider/model and voice through SLNG when a clear mapping exists.
- Keep streaming `SlngTTSService` for conversational bots. Use `SlngHttpTTSService` only for batch
  synthesis flows; it accepts only text and voice, with server defaults for everything else.
- Keep the current language, sample-rate, and encoding choices unless SLNG requires a different
  representation. Note that `speed` is unavailable on some models (for example Rime and Sarvam).
- Leave the LLM, transport, VAD, context aggregators, and other Pipecat processors unchanged unless
  SLNG LLM was selected.
- If SLNG LLM was selected, replace only the LLM constructor with Pipecat's `OpenAILLMService`
  pointed at the selected regional SLNG Context Router base URL, `model="slng/auto"`, and required
  `X-Slng-Agent-Id` / `X-Slng-Session-Id` headers from stable project identifiers.
- Use automatic region selection unless the user needs a pinned region for latency or residency
  (`region_override`, or `world_part_override` for a coarser zone).

Before concluding that a provider, model, or voice is unavailable through SLNG, check the current
SLNG docs model pages or the dashboard. The example tables in
[`references/pipeline-reference.md`](references/pipeline-reference.md) are not exhaustive; SLNG
routes more providers (for example Cartesia) than any static list shows. When still ambiguous,
attempt the faithful mapping and let live-turn verification decide, rather than substituting a
different provider silently.

Ask the user only when the current project does not contain enough information to choose safely. If a
model or voice is confirmed unavailable, migrate the stage that works and leave the other stage on
its current provider so the bot still boots. Report the partial migration clearly.

## 6. Apply Minimal, Idempotent Edits

Add the import once:

```python
from pipecat_slng import SlngSTTService, SlngTTSService
```

Replace only the STT and TTS service constructors that feed `Pipeline([...])` with
`SlngSTTService(...)` and `SlngTTSService(...)`, keeping the pipeline order intact. If SLNG LLM was
selected, replace only the current LLM constructor with Pipecat's OpenAI-compatible LLM
configuration. Preserve the rest of the pipeline, transport, and bot configuration.

Do not inline secrets. Pass `api_key=os.getenv("SLNG_API_KEY")`, never a literal. Use the same env
var for the Context Router. For Context Router, use the `slng/auto` model (via
`settings=OpenAILLMService.Settings(model="slng/auto")` in current Pipecat) and add
`X-Slng-Agent-Id` and `X-Slng-Session-Id` as `default_headers` using stable identifiers already
present in the bot/session context. Do not generate random IDs per request, and do not expose provider/catalog model ids in
code.

Before inserting anything, check whether the project already contains:

- `pipecat-slng` in dependencies
- `from pipecat_slng import ...`
- `SlngSTTService(...)`, `SlngTTSService(...)`, or `SlngHttpTTSService(...)`
- an `OpenAILLMService` already pointed at an SLNG router base URL, if SLNG LLM was selected
- a prior SLNG pipeline test

Run the project's existing formatter and lint commands if present. Do not introduce new tooling just
for this migration unless the user asks.

## 7. Verify the Migration

Use the cheapest checks first, then require a live spoken turn for acceptance:

1. `git diff --check`
2. Secret scan of the diff for literal keys
3. Existing project tests, plus a focused STT/TTS and optional LLM wiring assertion when practical
4. Entrypoint boot, if the project has one
5. Live spoken turn through the bot's real transport that completes STT -> LLM -> TTS

Green tests are not enough. A bad key, unavailable model, or provider gateway issue may only appear
when the bot handles real audio. Verification details and troubleshooting are in
[`references/verification.md`](references/verification.md).

## 8. Report the Result

Finish with:

- Entrypoint and package manager detected
- STT before and after
- TTS before and after, including voice if known
- LLM before and after, or LLM provider left unchanged
- Region behavior, auto or pinned
- Tests/checks run and any checks not run
- Whether a live spoken turn succeeded
- Any stage left on its original provider and how to finish it
- Rollback command based on the user's git state

Suggested commit message once verified:

```text
feat(voice): route Pipecat STT/TTS through slng
```
