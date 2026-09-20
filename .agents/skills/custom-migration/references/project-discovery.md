# Custom Project Discovery

Use this reference before editing a custom Python, JavaScript, or TypeScript voice project. The goal
is to adapt to the real provider seams instead of assuming a framework shape.

## Identify Runtime and Entrypoints

Search for package managers, runtimes, and common entrypoints:

```bash
rg --files | rg '(^|/)(pyproject\.toml|requirements.*\.txt|poetry\.lock|uv\.lock|package\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb|deno\.json|Dockerfile|Procfile)$'
rg --files | rg '(^|/)(main|app|server|worker|index|agent)\.(py|js|mjs|cjs|ts|tsx)$'
```

Read scripts in `package.json`, `pyproject.toml`, Dockerfile, Procfile, deployment YAML, or process
manager config before choosing install, test, or boot commands.

## Detect Env Loading

Search for env access and dotenv conventions:

```bash
rg -n "SLNG_API_KEY|VOICEAI_API_KEY|process\.env|os\.environ|getenv|load_dotenv|dotenv|env_file" .
```

Use `SLNG_API_KEY` for new SLNG wiring. If `VOICEAI_API_KEY` already exists, validate it before
mapping it to `SLNG_API_KEY`. Do not write local secret files unless they are ignored by git and match
the project's existing convention.

## Detect Provider Boundaries

Search for speech and model providers:

```bash
rg -n "stt|transcri|speech.?to.?text|deepgram|assembly|whisper|soniox|recogniz|audio" .
rg -n "tts|text.?to.?speech|synth|speak|voice|cartesia|elevenlabs|rime|murf|aura" .
rg -n "llm|chat.completions|openai|anthropic|bedrock|azure|generate|completion" .
```

Classify each selected stage before editing:

- **Clear seam**: one wrapper/service/function owns provider calls. Replace here.
- **Inline seam**: route/job/websocket handler calls provider directly. Prefer adding one small SLNG
  adapter and replacing the inline call.
- **No seam**: provider logic is mixed through business logic or browser code. Stop and report the
  adapter boundary to create first.

## Detect Streaming vs Batch

Preserve the existing contract:

- STT batch: file/buffer in, transcript result out.
- STT streaming: audio frames/chunks in, partial/final transcript events out.
- TTS batch: text in, audio buffer/file/URL out.
- TTS streaming: text or chunks in, audio chunks out.
- LLM streaming: token/SSE/iterator behavior must keep the current app contract.

Before editing, summarize:

```text
Runtime/package manager: ...
Entrypoint/boot command: ...
Env/runtime secrets: ...
STT seam: ... (batch/streaming, will migrate or stay unchanged)
TTS seam: ... (batch/streaming, will migrate or stay unchanged)
LLM seam: ... (will migrate to SLNG router or stay unchanged)
Test/check commands: ...
Real workflow to verify: ...
```
