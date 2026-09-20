# Pipecat Project Discovery

Use this reference before editing a user's Pipecat project. The goal is to adapt to the project's
real shape instead of assuming the quickstart layout.

## Identify the Project

Look for Pipecat dependencies and entrypoints:

```bash
rg -n "pipecat-ai|pipecat\.pipeline|Pipeline\(|PipelineWorker|WorkerRunner|PipelineTask|PipelineRunner" .
rg --files | rg '(^|/)(bot|main|app|server)\.py$|pyproject\.toml|Dockerfile|Procfile|pcc-deploy\.toml|requirements.*\.txt|poetry\.lock|uv\.lock'
```

Common entrypoints include:

- `bot.py`
- `main.py`
- `examples/bot.py`
- a script referenced by `pyproject.toml`
- a command in `Dockerfile`, `Procfile`, `pcc-deploy.toml` (Pipecat Cloud), deployment YAML, or
  process manager config

Bots built on the Pipecat development runner define `async def bot(runner_args: RunnerArguments)`
and create their transport with `create_transport(runner_args, transport_params)`. Older or custom
bots may build the transport and run `PipelineWorker` / `WorkerRunner` (pre-1.0: `PipelineTask` /
`PipelineRunner`) directly in `main()`.

Confirm the entrypoint before using commands like `uv run bot.py`.

## Detect the Dependency Manager

Use the tool already present in the project:

| Signal | Preferred install command |
|--------|---------------------------|
| `uv.lock` or existing `uv` commands | `uv add pipecat-slng` |
| `poetry.lock` | `poetry add pipecat-slng` |
| `requirements.txt` | add `pipecat-slng` to requirements, then install with the project's pip flow |
| `pyproject.toml` only | inspect the build backend and existing docs before choosing |

Use the matching runner for import probes and tests, for example `uv run python`, `poetry run python`,
or `python`.

## Detect Env Loading

Search for dotenv and env references:

```bash
rg -n "load_dotenv|SLNG_API_KEY|VOICEAI_API_KEY|os\.environ|getenv|dotenv" .
```

The SLNG Pipecat services take `api_key` explicitly; wire `os.getenv("SLNG_API_KEY")` at the call
site. The SLNG Context Router uses the same variable when SLNG LLM is selected. Some SLNG projects may
already have `VOICEAI_API_KEY` for the CLI or REST skills. If `VOICEAI_API_KEY` is present and
validated, configure `SLNG_API_KEY` to the same value for the Pipecat runtime instead of asking for
a second key.

Store secrets where the project already expects runtime secrets:

- `.env` when the project loads `.env` (the common Pipecat pattern, often via `load_dotenv()`)
- `.env.local` when the project loads it explicitly
- deployment secrets for hosted environments (including Pipecat Cloud secret sets)
- shell env for one-off local verification

Confirm local secret files are ignored by git before writing them.

## Detect the Pipeline

Read the entrypoint and imported modules to locate each stage:

- STT: `stt = ...`, `DeepgramSTTService`, `WhisperSTTService`, or another `*STTService`
- TTS: `tts = ...`, `CartesiaTTSService`, `ElevenLabsTTSService`, or another `*TTSService`
- LLM: `llm = ...`, `OpenAILLMService`, `AnthropicLLMService`, or custom model clients.
  Preserve this unless the user explicitly selected SLNG LLM.
- Transport: `DailyTransport`, `SmallWebRTCTransport`, or a websocket/telephony transport with a
  Twilio/Telnyx serializer. Stays unchanged.
- VAD and turn-taking: `SileroVADAnalyzer` via `vad_analyzer=...`. In Pipecat 1.x it lives on
  `LLMUserAggregatorParams` (along with `user_turn_strategies`); pre-1.0 projects configure it on
  `TransportParams`. Stays unchanged either way. Do not confuse it with the SLNG STT service's own
  `enable_vad` parameter.
- Context aggregators: in Pipecat 1.x, `LLMContext` with
  `user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)`; pre-1.0 projects use
  `OpenAILLMContext` with `llm.create_context_aggregator(context)`. Placement in `Pipeline([...])`
  stays unchanged.

Service construction and pipeline assembly are usually close together, for example:

```python
pipeline = Pipeline(
    [
        transport.input(),
        stt,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ]
)
```

Other projects use factories or separate modules. Replace the service constructors where they are
actually built, not the pipeline list.

Before editing, summarize what you found:

```text
Entrypoint: ...
Dependency manager: ...
Env file/runtime secrets: ...
STT: ...
TTS: ...
LLM: ... (will stay unchanged)
Transport/VAD/aggregators: ... (will stay unchanged)
```

If provisioned SLNG Context Router was selected, report:

```text
LLM: ... (will migrate to SLNG Context Router via Pipecat OpenAILLMService)
LLM router base URL: ...
LLM router model: slng/auto
Router org config: provisioned / not confirmed
Router headers: stable agent id ..., stable session id ...
```
