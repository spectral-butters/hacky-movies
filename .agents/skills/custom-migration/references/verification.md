# Verifying a Custom Migration

Run these after applying the migration. They are ordered cheapest-first: static checks, focused
adapter tests, project checks, then a real workflow.

## 1. Git and Secret Checks

The tree should contain only intended provider-seam edits:

```bash
git diff --check
git status --short
```

The diff must not contain literal keys:

```bash
git diff | grep -nE 'api_key|apiKey|SLNG_API_KEY|VOICEAI_API_KEY'
```

Acceptable matches are env variable references such as `SLNG_API_KEY`,
`os.environ["SLNG_API_KEY"]`, or `process.env.SLNG_API_KEY`. If any line contains a quoted key value,
remove it and rotate the key.

## 2. Focused Tests

Prefer updating existing provider tests over adding disconnected tests. Good focused assertions:

- STT adapter calls `voiceai-sdk` with the selected model and preserves transcript shape.
- TTS adapter calls `voiceai-sdk` with selected model/voice and preserves audio return shape.
- LLM adapter uses the selected router base URL, `model="slng/auto"`, `SLNG_API_KEY`, and required
  `X-Slng-Agent-Id` / `X-Slng-Session-Id` headers.
- Streaming adapters preserve partial/final transcript or audio chunk event contracts.

Use mocks for SDK calls unless the project already has integration-test infrastructure. Do not assert
private SDK fields.

## 3. Project Checks

Run only commands the project already uses, for example:

```bash
python -m pytest
python -m ruff check
npm test
npm run lint
npm run typecheck
npm run build
```

Do not add new tooling just for the migration.

## 4. Real Workflow

Run the smallest workflow that proves the selected stages work end to end:

- STT: upload/stream real audio and confirm transcript output.
- TTS: synthesize real text and confirm playable audio.
- LLM: send a real prompt and confirm the response path still matches the app contract.
- Voice pipeline: complete one spoken turn if the app supports it.

If one selected stage fails at runtime, revert only that stage to its original provider when possible,
keep working SLNG stages, and report the partial migration.

## Acceptance Checklist

- [ ] Clean rollback point was established before edits.
- [ ] `voiceai-sdk` imports successfully when STT/TTS are selected.
- [ ] OpenAI-compatible client imports successfully when SLNG LLM is selected.
- [ ] SLNG org/router configuration is provisioned before Context Router migration is verified.
- [ ] Selected stages use `SLNG_API_KEY` without literal key values.
- [ ] Context Router uses `slng/auto` and stable agent/session headers, with no provider/catalog model ids
      in customer code.
- [ ] No fake framework wrappers were added.
- [ ] The diff is limited to dependency files, env docs/config, one adapter seam, provider call sites,
      and focused tests.
- [ ] Existing tests/checks pass or failures are reported.
- [ ] Real workflow for selected stages succeeds.

## Rollback

Because the migration started from a clean tree:

```bash
git restore .             # before committing: discard all migration edits
git revert <sha>          # after committing: reverse the migration commit
```
