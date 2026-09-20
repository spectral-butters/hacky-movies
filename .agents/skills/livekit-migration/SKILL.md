---
name: livekit-migration
description: Migrate an existing LiveKit Agents Python project to SLNG hosted speech infrastructure for STT/TTS via livekit-plugins-slng, with optional SLNG Context Router support through LiveKit's OpenAI-compatible plugin. Use when the user asks to "move my LiveKit agent to slng", "use slng for STT/TTS in LiveKit", "swap Deepgram/Cartesia for slng", "add the slng livekit plugin", "use SLNG LLM router in LiveKit", or "migrate livekit to slng".
license: MIT
compatibility: Requires a LiveKit Agents Python project, internet access, and a SLNG_API_KEY for runtime verification. Works with uv, Poetry, pip, or other Python dependency managers when detected.
---

# Migrate a LiveKit Agent to SLNG

Move an existing LiveKit Agents Python project onto SLNG hosted speech infrastructure by replacing
the speech-to-text and text-to-speech stages with `slng.STT` and `slng.TTS` from
`livekit-plugins-slng`. If the user explicitly selected SLNG LLM and SLNG has provisioned the
customer's org/router configuration, point the project's LLM at the SLNG OpenAI-compatible LLM
Router through LiveKit's OpenAI plugin.

This is a pipeline migration, not an agent rewrite. Preserve prompts, tools, VAD, turn detection,
room wiring, dispatch behavior, and business logic. Preserve the user's current LLM unless the user
or generated stack explicitly asks for provisioned SLNG Context Router.

> Scope: `livekit-plugins-slng` exposes `slng.STT` and `slng.TTS`. It does not provide an LLM class.
> If SLNG LLM is selected, use LiveKit's OpenAI-compatible LLM support with a custom `base_url`.
> Use the agent-facing model `slng/auto`; provider/catalog model ids belong in SLNG org config.
> Never add or reference `slng.LLM`.

Use these references only when needed:

- [`references/project-discovery.md`](references/project-discovery.md) - project layout, package manager, env, and pipeline detection
- [`references/pipeline-reference.md`](references/pipeline-reference.md) - plugin constructors, model examples, regions, and starter before/after
- [`references/verification.md`](references/verification.md) - checks, live-turn verification, rollback, and troubleshooting
- [`../setup-api-key`](../setup-api-key/SKILL.md) - obtain and validate an SLNG API key

## Operating Principles

- Adapt to the project in front of you. Do not assume `src/agent.py`, `uv`, `.env.local`, `ruff`, or
  pytest unless discovery confirms them.
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

- The LiveKit agent entrypoint, for example `src/agent.py`, `agent.py`, `main.py`, or a configured
  script in `pyproject.toml`, Dockerfile, Procfile, or deployment config.
- The dependency manager: `uv`, Poetry, pip, pip-tools, or another project-specific flow.
- The env loading strategy: `.env.local`, `.env`, shell env, container env, or deployment secrets.
- Current STT, TTS, LLM, VAD, turn detection, and noise cancellation wiring.
- Where STT and TTS are constructed: `AgentSession(...)`, a factory function, an agent class, or
  another module.
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

The SLNG LiveKit plugin and the SLNG Context Router both use `SLNG_API_KEY`. If the project already has
`VOICEAI_API_KEY` and `SLNG_API_KEY` is missing, treat `VOICEAI_API_KEY` as the same SLNG credential
only after validation, then configure `SLNG_API_KEY` for the LiveKit runtime.

Check presence without printing the value:

```bash
[ -n "$SLNG_API_KEY" ] && echo "SLNG_API_KEY is set" || echo "SLNG_API_KEY is NOT set"
```

Validate the key with `voiceai whoami` (`GET /v1/me`) or the `setup-api-key` skill's current
recommended method. A `200` response means the key is usable; `401` means it is missing, malformed,
revoked, or for the wrong workspace.

Store the key using the project's discovered env convention. For the official starter this is often
`.env.local`; other projects may use `.env`, shell env, deployment secrets, or container config.
Confirm any local env file is ignored by git before writing to it.

## 4. Install and Probe Required Plugins

Install `livekit-plugins-slng` with the detected package manager:

```bash
uv add livekit-plugins-slng
```

Equivalent examples:

```bash
poetry add livekit-plugins-slng
python -m pip install livekit-plugins-slng
```

Then probe the import using the matching runner:

```bash
uv run python -c "from livekit.plugins import slng; assert slng.STT and slng.TTS"
```

If the import fails, stop before editing code. Report the exact failure and point the user at the
current SLNG LiveKit plugin docs to confirm the package and import surface.

If SLNG LLM was selected, first confirm SLNG org/router configuration has been provisioned for this
customer. If it has not, stop and report that SLNG must configure the customer's provider/model/API-key
settings before LLM migration can be verified.

Then ensure the project has LiveKit's OpenAI plugin and probe its import.
Use the package manager and import style already used by the project; common examples are:

```bash
uv add livekit-plugins-openai
uv run python -c "from livekit.plugins import openai; assert openai.LLM"
```

Do not use `livekit-plugins-slng` for LLM wiring.

## 5. Plan the Speech Swap

Default to a faithful migration:

- Keep the current STT provider/model through SLNG when a clear mapping exists.
- Keep the current TTS provider/model and voice through SLNG when a clear mapping exists.
- Keep the current language and sample-rate choices unless SLNG requires a different representation.
- Leave the LLM and non-speech LiveKit components unchanged unless SLNG LLM was selected.
- If SLNG LLM was selected, replace only the LLM constructor with LiveKit's OpenAI-compatible LLM
  pointed at the selected regional SLNG Context Router base URL, `model="slng/auto"`, and required
  `X-Slng-Agent-Id` / `X-Slng-Session-Id` headers from stable project identifiers.
- Use automatic region selection unless the user needs a pinned region for latency or residency.

Ask the user only when the current project does not contain enough information to choose safely. If a
model or voice is unavailable through SLNG, migrate the stage that works and leave the other stage on
its current provider so the agent still boots. Report the partial migration clearly.

## 6. Apply Minimal, Idempotent Edits

Add the import once:

```python
from livekit.plugins import slng
```

Replace only STT and TTS constructors with `slng.STT(...)` and `slng.TTS(...)`. If SLNG LLM was
selected, replace only the current LLM constructor with LiveKit OpenAI-compatible LLM configuration.
Preserve the rest of the session and agent configuration.

Do not inline secrets. Usually no explicit `api_key` argument is needed because the plugin reads
`SLNG_API_KEY`. If the call site must be explicit, use `os.environ["SLNG_API_KEY"]`, never a literal.
Use the same env var for the Context Router. For Context Router, use `model="slng/auto"` and add
`X-Slng-Agent-Id` and `X-Slng-Session-Id` as headers using stable identifiers already present in the
agent/session/room context. Do not generate random IDs per request, and do not expose provider/catalog
model ids in code.

Before inserting anything, check whether the project already contains:

- `livekit-plugins-slng` in dependencies
- `from livekit.plugins import slng`
- `slng.STT(...)` or `slng.TTS(...)`
- a LiveKit OpenAI plugin dependency/import, if SLNG LLM was selected
- a prior SLNG pipeline test

Run the project's existing formatter and lint commands if present. Do not introduce new tooling just
for this migration unless the user asks.

## 7. Verify the Migration

Use the cheapest checks first, then require a live spoken turn for acceptance:

1. `git diff --check`
2. Secret scan of the diff for literal keys
3. Existing project tests, plus a focused STT/TTS and optional LLM wiring assertion when practical
4. Entrypoint boot or download/preload command, if the project has one
5. Live spoken turn that completes STT -> LLM -> TTS

Green tests are not enough. A bad key, unavailable model, or provider gateway issue may only appear
when the agent handles real audio. Verification details and troubleshooting are in
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
feat(voice): route LiveKit STT/TTS through slng
```
