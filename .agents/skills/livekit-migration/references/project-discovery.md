# LiveKit Project Discovery

Use this reference before editing a user's LiveKit Agents project. The goal is to adapt to the
project's real shape instead of assuming the official starter.

## Identify the Project

Look for LiveKit Agents dependencies and entrypoints:

```bash
rg -n "livekit-agents|livekit.agents|AgentSession|JobContext|WorkerOptions" .
rg --files | rg '(^|/)(agent|main|app|worker)\.py$|pyproject\.toml|Dockerfile|Procfile|requirements.*\.txt|poetry\.lock|uv\.lock'
```

Common entrypoints include:

- `src/agent.py`
- `agent.py`
- `main.py`
- `app.py`
- a script referenced by `pyproject.toml`
- a command in `Dockerfile`, `Procfile`, deployment YAML, or process manager config

Confirm the entrypoint before using commands like `python src/agent.py console`.

## Detect the Dependency Manager

Use the tool already present in the project:

| Signal | Preferred install command |
|--------|---------------------------|
| `uv.lock` or existing `uv` commands | `uv add livekit-plugins-slng` |
| `poetry.lock` | `poetry add livekit-plugins-slng` |
| `requirements.txt` | add `livekit-plugins-slng` to requirements, then install with the project's pip flow |
| `pyproject.toml` only | inspect the build backend and existing docs before choosing |

Use the matching runner for import probes and tests, for example `uv run python`, `poetry run python`,
or `python`.

## Detect Env Loading

Search for dotenv and env references:

```bash
rg -n "load_dotenv|SLNG_API_KEY|VOICEAI_API_KEY|os\.environ|getenv|dotenv" .
```

The SLNG LiveKit plugin reads `SLNG_API_KEY` by default. The SLNG Context Router uses the same variable
when SLNG LLM is selected. Some SLNG projects may already have `VOICEAI_API_KEY` for the CLI or REST
skills. If `VOICEAI_API_KEY` is present and validated, configure `SLNG_API_KEY` to the same value for
the LiveKit runtime instead of asking for a second key.

Store secrets where the project already expects runtime secrets:

- `.env.local` for the official starter when it calls `load_dotenv(".env.local")`
- `.env` when the project loads `.env`
- deployment secrets for hosted environments
- shell env for one-off local verification

Confirm local secret files are ignored by git before writing them.

## Detect the Pipeline

Read the entrypoint and imported modules to locate each stage:

- STT: `stt=...`, `STT(...)`, `transcription`, or speech recognizer config
- TTS: `tts=...`, `TTS(...)`, voice config, or synthesizer config
- LLM: `llm=...`, `LLM(...)`, `openai`, `anthropic`, `inference.LLM`, or custom model clients.
  Preserve this unless the user explicitly selected SLNG LLM.
- VAD and turn detection: `vad=...`, `silero`, `turn_detection`, `MultilingualModel`
- dispatch behavior: `agent_name=`, `WorkerOptions`, explicit dispatch docs

In the official starter, STT and TTS are often on `AgentSession(...)`, while the LLM may live on an
`Agent` subclass. Other projects may use factories or dependency injection. Replace the constructors
where they are actually built.

Before editing, summarize what you found:

```text
Entrypoint: ...
Dependency manager: ...
Env file/runtime secrets: ...
STT: ...
TTS: ...
LLM: ... (will stay unchanged)
VAD/turn detection: ... (will stay unchanged)
```

If provisioned SLNG Context Router was selected, report:

```text
LLM: ... (will migrate to SLNG Context Router via LiveKit OpenAI-compatible plugin)
LLM router base URL: ...
LLM router model: slng/auto
Router org config: provisioned / not confirmed
Router headers: stable agent id ..., stable session id ...
```
