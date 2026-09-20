---
name: custom-migration
description: Migrate a custom Python, JavaScript, or TypeScript voice project to SLNG hosted STT/TTS via voiceai-sdk, with optional SLNG Context Router support through OpenAI-compatible client wiring. Use when the user asks to replace custom STT, TTS, or LLM providers with SLNG, integrate SLNG into a non-LiveKit project, use SLNG SDKs in an existing voice pipeline, or make an audit-friendly SLNG migration.
license: MIT
compatibility: Requires an existing Python, JavaScript, or TypeScript project with clear STT, TTS, or LLM provider boundaries, internet access, and SLNG_API_KEY for runtime verification.
---

# Migrate a Custom Voice Project to SLNG

Move an existing custom project onto SLNG hosted models by replacing selected provider boundaries:
STT and TTS use `voiceai-sdk`; LLM uses the provisioned SLNG OpenAI-compatible Context Router only when
selected.

This is not a framework rewrite. Preserve routing, prompts, tools, storage, transports, UI, queues,
telephony, session state, and business logic. Only replace STT/TTS/LLM call sites that are already
clear provider seams, or add one small SLNG adapter module if that makes the diff easier to audit.

> Do not invent generic `VoiceAgent`, `STT`, `TTS`, `LLM`, or `Intelligence` abstractions unless the
> project already has those concepts.

Use these references only when needed:

- [`references/project-discovery.md`](references/project-discovery.md) - language/runtime, package manager, env, and provider boundary discovery
- [`references/sdk-and-router-reference.md`](references/sdk-and-router-reference.md) - Python/JS SDK and Context Router wiring patterns
- [`references/verification.md`](references/verification.md) - checks, live workflow verification, rollback, and troubleshooting
- [`../setup-api-key`](../setup-api-key/SKILL.md) - obtain and validate an SLNG API key

## Operating Principles

- Discover first. Do not assume Python vs JavaScript, sync vs async, streaming vs batch, or any file
  path such as `agent.py`, `src/index.ts`, `.env.local`, or `uv`.
- Keep edits minimal and idempotent. Running the migration twice should not duplicate dependencies,
  imports, env wiring, adapter functions, tests, or constructor arguments.
- Replace only selected stages. If the user selected STT/TTS only, preserve the LLM. If the user
  selected SLNG LLM, migrate the LLM through OpenAI-compatible wiring only after SLNG org/router
  configuration has been provisioned.
- Stop before code edits if there is no sensible provider boundary. Report the smallest adapter seam
  to create instead of scattering SDK calls through business logic.
- Never print, paste, log, or commit API keys.

## 1. Discover the Project

Before editing, identify:

- Language and runtime: Python, JavaScript, TypeScript, Node, Bun, Deno, browser, server, worker, or
  mixed.
- Package manager and runner: pip, uv, Poetry, npm, pnpm, yarn, bun, or project-specific scripts.
- Env loading: `.env`, deployment secrets, shell env, container env, or framework config.
- Current STT, TTS, and LLM providers, including whether each call path is streaming or batch.
- The smallest provider seams: SDK wrapper, service class, route handler, job worker, websocket
  handler, audio pipeline, or direct API call.
- Existing tests, lint/typecheck commands, and the smallest real workflow that exercises the changed
  stages.

Report the discovered boundaries before changing anything. Use
[`references/project-discovery.md`](references/project-discovery.md) for search patterns.

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

Use `SLNG_API_KEY` for every selected SLNG stage. If the project already has `VOICEAI_API_KEY` and
`SLNG_API_KEY` is missing, treat `VOICEAI_API_KEY` as the same SLNG credential only after validation,
then configure `SLNG_API_KEY` for runtime.

Check presence without printing the value:

```bash
[ -n "$SLNG_API_KEY" ] && echo "SLNG_API_KEY is set" || echo "SLNG_API_KEY is NOT set"
```

Store secrets using the project's existing env convention and confirm local secret files are ignored
by git before writing to them.

## 4. Install and Probe Dependencies

For STT/TTS, install `voiceai-sdk` with the detected package manager:

```bash
python -m pip install voiceai-sdk
npm install voiceai-sdk
```

Use the matching import probe:

```bash
python -c "from voiceai import Slng, AsyncSlng; assert Slng and AsyncSlng"
node -e "import('voiceai-sdk').then(m => { if (!m.default) process.exit(1) })"
```

If SLNG LLM was selected, first confirm SLNG org/router configuration has been provisioned for this
customer. If it has not, stop and report that SLNG must configure the customer's provider/model/API-key
settings before LLM migration can be verified.

Then use an existing OpenAI-compatible client if present. Otherwise install the standard OpenAI SDK
for the project language and probe it. Do not invent an SLNG LLM SDK class.

## 5. Plan the Stage Swap

Default to a faithful migration:

- STT: keep current audio format, sample rate, language behavior, partial/final transcript contract,
  and streaming or batch mode when possible.
- TTS: keep current text input, voice, language, streaming or batch mode, and audio output contract
  when possible.
- LLM: preserve the existing LLM unless SLNG LLM was selected; then point an OpenAI-compatible client
  at the selected regional SLNG router with `model="slng/auto"` and required
  `X-Slng-Agent-Id` / `X-Slng-Session-Id` headers from stable project identifiers.
- Add one small adapter module only when it makes the diff easier to review.
- If a selected model or mode is unsupported, migrate the stages that work and leave the failing stage
  unchanged. Report the partial migration clearly.

## 6. Apply Minimal, Idempotent Edits

Use `voiceai-sdk` at the existing provider seam or in one new adapter module. Do not add a new agent
framework or rename project concepts.

Use `os.environ["SLNG_API_KEY"]` in Python and `process.env.SLNG_API_KEY` in server-side JavaScript.
For browser code, do not expose the key; route through an existing backend or stop and report that a
server-side boundary is required.

For Context Router, use `slng/auto` as the only code-level model. Do not place provider/catalog model ids
in customer code; those belong in SLNG org configuration. Add `X-Slng-Agent-Id` and
`X-Slng-Session-Id` as headers using stable app identifiers. Do not generate random IDs per request.

Before inserting anything, check whether the project already has:

- `voiceai-sdk` in dependencies
- an SLNG client or adapter
- OpenAI SDK/client wiring for LLM
- existing provider tests that should be updated instead of duplicated

Run the project's existing formatter, lint, and typecheck commands if present. Do not introduce new
tooling just for this migration unless the user asks.

## 7. Verify the Migration

Use the cheapest checks first, then require a real workflow for acceptance:

1. `git diff --check`
2. Secret scan of the diff for literal keys
3. Existing tests plus focused STT/TTS/LLM adapter assertions when practical
4. Typecheck/lint/build commands already used by the project
5. Real workflow that exercises changed stages end to end

Green unit tests are not enough. Invalid credentials, unsupported audio formats, streaming contract
mismatches, and model availability issues often appear only in the real workflow. Verification
details are in [`references/verification.md`](references/verification.md).

## 8. Report the Result

Finish with:

- Runtime, package manager, and entrypoint detected
- STT before and after, or unchanged with reason
- TTS before and after, including voice if known, or unchanged with reason
- LLM before and after, or unchanged with reason
- Files changed and why the diff is audit-friendly
- Checks run and any checks not run
- Real workflow result
- Rollback command based on the user's git state

Suggested commit message once verified:

```text
feat(voice): route custom voice pipeline through slng
```
