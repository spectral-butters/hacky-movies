# SLNG Pipecat Pipeline Reference

Service constructors, models, regions, and the exact wire-up for migrating a Pipecat bot's STT/TTS
to the SLNG plugin, with optional SLNG Context Router wiring. Treat this as a reference, not as the
migration workflow. The workflow lives in [`../SKILL.md`](../SKILL.md).

> `pipecat-slng` exposes `SlngSTTService`, `SlngTTSService`, and `SlngHttpTTSService` only. There is
> no `SlngLLMService`. If provisioned SLNG Context Router was selected, use Pipecat's
> `OpenAILLMService`.

## Install and import

Use the package manager discovered in the project. Requires Python 3.11+ and `pipecat-ai>=1.3.0`.

```bash
uv add pipecat-slng
# or:
poetry add pipecat-slng
# or add pipecat-slng to requirements.txt and install with the project's pip flow
```

```python
from pipecat_slng import SlngSTTService, SlngTTSService
# non-streaming HTTP TTS, only when batch synthesis fits better:
from pipecat_slng import SlngHttpTTSService
```

The services take `api_key` explicitly. Pass `api_key=os.getenv("SLNG_API_KEY")` at the call site.
Never inline the key.

## STT - `SlngSTTService`

Streams over `wss://api.slng.ai/v1/bridges/unmute/stt/{model}`.

```python
SlngSTTService(
    api_key=os.getenv("SLNG_API_KEY"),
    model="slng/deepgram/nova:3-en",   # default; slng/provider/model:variant-language
    language=Language.EN,              # default
    region_override=None,              # e.g. "eu-north-1"
    world_part_override=None,          # e.g. "eu"; region_override wins if both set
    # base_url="api.slng.ai", encoding="linear16", sample_rate=None,
    # enable_vad=True, enable_partials=True, settings=None also available
)
```

Transcripts with confidence below 0.5 are dropped automatically.

## TTS - `SlngTTSService` (streaming WebSocket)

Streams over `wss://api.slng.ai/v1/bridges/unmute/tts/{model}`. Recommended for conversational
agents: low latency with mid-utterance interruption support.

```python
SlngTTSService(
    api_key=os.getenv("SLNG_API_KEY"),
    model="slng/deepgram/aura:2-en",   # default; slng/provider/model:variant-language
    voice="aura-2-thalia-en",          # voice id for the chosen model
    language=Language.EN,
    speed=None,                        # unsupported on some models (e.g. Rime, Sarvam)
    region_override=None,
    world_part_override=None,
    # base_url="api.slng.ai", encoding="linear16", sample_rate=None, settings=None also available
)
```

Changing voice, speed, or language at runtime reconnects the WebSocket. It is a brief, visible
reconnect, not a silent update.

## HTTP TTS - `SlngHttpTTSService` (non-streaming)

Batch synthesis fallback. Only text and voice are configurable; encoding, sample rate, language, and
speed use server defaults. Auto-detects WAV (decoded to PCM) and plain PCM responses; compressed
formats yield errors.

```python
SlngHttpTTSService(
    api_key=os.getenv("SLNG_API_KEY"),
    model="slng/deepgram/aura:2-en",
    voice="aura-2-thalia-en",
)
```

## Model Examples

The model id goes in the bridge URL path. `slng/`-prefixed ids such as `slng/deepgram/nova:3-en`
are SLNG-hosted; ids like `cartesia/sonic:3` route a provider through SLNG. The tables below are
examples, not the catalog. **Never declare a provider unsupported from these tables alone.** SLNG
routes more providers than any static list shows. Confirm availability with the voiceai CLI when
installed (`voiceai models --tts`, `voiceai models --stt`, `voiceai voices --model <id>`), or in the
current SLNG docs model pages or the [dashboard](https://app.slng.ai). A REST catalog endpoint
is not available yet.

When availability is still ambiguous, prefer a faithful attempt over a silent substitution: keep the
project's current provider/model routed through SLNG and let the live-turn verification prove it.
Only fall back to a known SLNG-hosted model (for example `slng/deepgram/aura:2-en`) if the bridge
rejects the model id, and report the substitution.

**STT (`SlngSTTService`)**

| Model id | Provider | Notes |
|----------|----------|-------|
| `slng/deepgram/nova:3-en` | Deepgram | Default. Nova 3, lowest latency |
| `slng/sarvam/saaras:v3-en` | Sarvam AI | Indian + European languages |

**TTS (`SlngTTSService` / `SlngHttpTTSService`)** - each model has its own voice ids.

| Model id | Provider | Notes |
|----------|----------|-------|
| `slng/deepgram/aura:2-en` | Deepgram | Default. Aura 2, pairs natively with Nova 3 STT |
| `slng/fish/tts:s2.1-pro` | Fish Audio | SLNG-hosted, high quality |
| `cartesia/sonic:3` | Cartesia | Sonic 3, WebSocket streaming, voice cloning - existing Cartesia voice ids carry over |
| `slng/inworld/max:1.5` | Inworld | SLNG-hosted TTS 1.5 Max |
| `slng/sarvam/bulbul:v3-...` | Sarvam AI | Indian-language locales. No `speed` |

## Optional LLM - SLNG Context Router

Only migrate the LLM when the user or generated stack explicitly selected SLNG Context Router and SLNG
has provisioned org/router configuration for the customer. Otherwise keep the project's existing LLM
unchanged.

The SLNG Context Router is OpenAI-compatible at `/v1/chat/completions`, so use Pipecat's
`OpenAILLMService` with a custom `base_url`. Do not add an `SlngLLMService`.

```python
import os
from pipecat.services.openai.llm import OpenAILLMService

llm = OpenAILLMService(
    api_key=os.environ["SLNG_API_KEY"],
    base_url="https://us.context-router.slng.ai/v1",
    default_headers={
        "X-Slng-Agent-Id": agent_id,
        "X-Slng-Session-Id": session_id,
    },
    settings=OpenAILLMService.Settings(model="slng/auto"),
)
```

Match the constructor style the project already uses: current Pipecat passes the model through
`settings=OpenAILLMService.Settings(...)`; older projects pass `model="slng/auto"` directly, which
still works but is deprecated.

Use stable project identifiers for `agent_id` and `session_id`, such as the configured bot name and
the transport room/session id. Do not generate random IDs per request. These headers are required
for agent-context routing, tracing, caching, and token-savings behavior.

Regional base URLs:

| Selection | Router base URL |
|-----------|-----------------|
| India | `https://india.context-router.slng.ai/v1` |
| United States | `https://us.context-router.slng.ai/v1` |
| Europe | `https://eu.context-router.slng.ai/v1` |
| Indonesia | `https://indonesia.context-router.slng.ai/v1` |

The public agent-facing model is `slng/auto`. Do not place provider/catalog model ids in customer
code; SLNG configures provider models, customer provider API keys, routing policy, cache behavior,
and other router parameters in org configuration. If that org configuration is not ready, stop before
LLM edits and report that SLNG must provision it before verification.

## Regions

Pin a region with `region_override`, or a coarser geographic zone with `world_part_override`.
`region_override` takes priority when both are set. If neither is set, the closest region is
auto-selected. Available regions include `us-east-1`, `eu-north-1`, `ap-southeast-2`; world parts
are `na`, `eu`, `ap`. Not every model is deployed in every region.

```python
SlngSTTService(api_key=os.getenv("SLNG_API_KEY"), model="slng/deepgram/nova:3-en", region_override="eu-north-1")
```

The WebSocket services send region selection as connection headers; `SlngHttpTTSService` sends it as
query parameters. The constructor arguments are the same either way.

## Typical Bot Layout

In a typical Pipecat bot:

- **STT and TTS** are constructed as services (`stt = ...`, `tts = ...`) and placed in
  `Pipeline([...])`. These are what SLNG replaces.
- **LLM** is its own service in the same pipeline (`OpenAILLMService`, `AnthropicLLMService`, ...).
  It stays unchanged unless provisioned SLNG Context Router was selected, in which case configure
  `OpenAILLMService` with the router base URL there.
- **Transport** (`DailyTransport`, `SmallWebRTCTransport`, websocket/telephony), **VAD**
  (`SileroVADAnalyzer` on `LLMUserAggregatorParams` in 1.x, on `TransportParams` in older projects),
  and **context aggregators** (`LLMContext` + `LLMContextAggregatorPair` in 1.x, `OpenAILLMContext`
  + `create_context_aggregator` pre-1.0) stay as they are unless the user opts to change them.

## Before / after - typical bot

**Before** (direct providers):

```python
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService

stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
tts = CartesiaTTSService(
    api_key=os.getenv("CARTESIA_API_KEY"),
    voice_id="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
)
```

**After** (slng). Add the import once at the top of the file:

```python
from pipecat_slng import SlngSTTService, SlngTTSService
```

Replace only the service constructors (leave the `Pipeline([...])` list, transport, VAD, context
aggregators, and the LLM as they are unless provisioned SLNG Context Router was selected):

```python
stt = SlngSTTService(
    api_key=os.getenv("SLNG_API_KEY"),
    model="slng/deepgram/nova:3-en",
)
tts = SlngTTSService(
    api_key=os.getenv("SLNG_API_KEY"),
    model="cartesia/sonic:3",
    voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",  # same Cartesia voice id as before
)
```

This keeps the bot on the same Cartesia model and voice, now routed through SLNG. Confirm the exact
model id in the current SLNG docs; switch to another model (for example `slng/deepgram/aura:2-en`
with an Aura voice) only if the user asks or the model is confirmed unavailable.

Add `region_override="eu-north-1"` (or your region) to either call for data residency.

If provisioned SLNG Context Router was selected, update the existing LLM constructor separately:

```python
from pipecat.services.openai.llm import OpenAILLMService

llm = OpenAILLMService(
    api_key=os.environ["SLNG_API_KEY"],
    base_url="https://eu.context-router.slng.ai/v1",
    default_headers={
        "X-Slng-Agent-Id": agent_id,
        "X-Slng-Session-Id": session_id,
    },
    settings=OpenAILLMService.Settings(model="slng/auto"),
)
```

Keep the project's existing entrypoint. In many Pipecat projects that is `bot.py` run with
`uv run bot.py`, but other projects differ.
