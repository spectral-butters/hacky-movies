# SLNG LiveKit Pipeline Reference

Models, voices, regions, and the exact wire-up for migrating a LiveKit agent's STT/TTS to the
SLNG plugin, with optional SLNG Context Router wiring. Treat this as a reference, not as the migration workflow. The workflow lives in
[`../SKILL.md`](../SKILL.md).

> `livekit-plugins-slng` exposes `slng.STT` and `slng.TTS` only. There is no `slng.LLM` and no
> `Intelligence` class. If provisioned SLNG Context Router was selected, use LiveKit's
> OpenAI-compatible plugin.

## Install and import

Use the package manager discovered in the project:

```bash
uv add livekit-plugins-slng
# or:
poetry add livekit-plugins-slng
# or add livekit-plugins-slng to requirements.txt and install with the project's pip flow
```

```python
from livekit.plugins import slng
```

The plugin reads `SLNG_API_KEY` from the environment automatically. Pass `api_key=os.environ["SLNG_API_KEY"]`
explicitly if you want it visible at the call site. Never inline the key.

## STT - `slng.STT`

```python
slng.STT(
    model="deepgram/nova:3",     # default; provider/model:variant
    language="en",               # default
    region_override=None,        # e.g. "eu-north-1", or a priority list
    # api_key, slng_base_url="api.slng.ai", sample_rate, encoding,
    # enable_partial_transcripts, enable_diarization, vad_threshold, ... also available
)
```

## TTS - `slng.TTS`

```python
slng.TTS(
    model="deepgram/aura:2",     # default; provider/model:variant
    voice="default",             # voice id for the chosen model
    language="en",
    region_override=None,
    speed=1.0,
    # api_key, slng_base_url="api.slng.ai", sample_rate, ... also available
)
```

## Model Examples

Models use a `provider/model:variant` id. The `slng/`-prefixed ids are SLNG-hosted; the others route a
provider through SLNG. This list is an example catalog and can change. Confirm exact ids in the
current SLNG docs or dashboard when the mapping is not obvious from the project.

**STT (`slng.STT`)**

| Model id | Provider | Notes |
|----------|----------|-------|
| `slng/deepgram/nova:3-en` | Deepgram | SLNG-hosted Nova 3, lowest latency. `-multi` variant for auto language |
| `deepgram/nova:3` | Deepgram | Provider-routed Nova 3 |
| `soniox/speech-ai:rt-v5` | Soniox | Real-time, diarisation, 60+ languages |
| `reson8/reson8stt:v1` | Reson8 | 9 European locales, telephony-tuned |
| `sarvam/saaras:v3` | Sarvam AI | Indian + European languages (24 locales) |

**TTS (`slng.TTS`)** - each model has its own voice ids.

| Model id | Provider | Notes |
|----------|----------|-------|
| `slng/deepgram/aura:2-en` | Deepgram | SLNG-hosted Aura 2, pairs natively with Nova 3 STT |
| `slng/fish/tts:s2.1-pro` | Fish Audio | SLNG-hosted, high quality |
| `cartesia/sonic:3` | Cartesia | Sonic 3, WebSocket streaming, voice cloning, 40+ languages |
| `murf/murftts:falcon` | Murf | Studio quality, 16 locales |
| `kugelaudio/kugel:2` | KugelAudio | Studio quality |
| `soniox/tts-rt:v1` | Soniox | Real-time, 50+ languages |
| `sarvam/bulbul:v3` | Sarvam AI | 11 Indian-language locales |

## Optional LLM - SLNG Context Router

Only migrate the LLM when the user or generated stack explicitly selected SLNG Context Router and SLNG
has provisioned org/router configuration for the customer. Otherwise keep the project's existing LLM
unchanged.

The SLNG Context Router is OpenAI-compatible at `/v1/chat/completions`, so use LiveKit's OpenAI plugin
with a custom `base_url`. Do not add `slng.LLM`.

```python
import os
from livekit.plugins import openai

llm = openai.LLM(
    model="slng/auto",
    api_key=os.environ["SLNG_API_KEY"],
    base_url="https://us.context-router.slng.ai/v1",
    extra_headers={
        "X-Slng-Agent-Id": agent_id,
        "X-Slng-Session-Id": session_id,
    },
)
```

Use stable project identifiers for `agent_id` and `session_id`, such as the configured LiveKit agent
name and room/session id. Do not generate random IDs per request. These headers are required for
agent-context routing, tracing, caching, and token-savings behavior.

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

Like-for-like examples from the standard starter:

| Before (LiveKit Inference) | After (slng) |
|----------------------------|--------------|
| `deepgram/nova-3` | `deepgram/nova:3` |
| `cartesia/sonic-3` (voice `<id>`) | `cartesia/sonic:3` (same voice id) |

## Regions

Pin a region with `region_override` (string or priority list). If unset, the closest region is
auto-selected. Available regions include `us-east-1`, `eu-north-1`, `ap-south-1`, `ap-southeast-2`,
`asia-south1`, `asia-southeast2`, `australia-southeast1`. Not every model is deployed in every region.

```python
slng.STT(model="deepgram/nova:3", region_override="eu-north-1")
```

## Starter Layout Example

In the standard `agent-starter-python` layout:

- **STT and TTS** are often on `AgentSession(stt=..., tts=...)`. These are what SLNG replaces.
- **LLM** is often on the `Agent` subclass (`Agent.__init__(llm=...)`). It stays unchanged unless
  provisioned SLNG Context Router was selected, in which case configure LiveKit's OpenAI-compatible LLM
  there.
- **VAD** (`silero`), **turn detection** (`MultilingualModel`), and any **noise cancellation** plugin
  (e.g. `ai_coustics`) stay as they are unless the user opts to remove them.

## Before / after - standard starter

**Before** (LiveKit Inference):

```python
from livekit.agents import inference
# ... in AgentSession(...):
stt=inference.STT(model="deepgram/nova-3", language="multi"),
tts=inference.TTS(model="cartesia/sonic-3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
```

**After** (slng). Add the import once at the top of the file:

```python
from livekit.plugins import slng
```

In `AgentSession(...)`, replace STT and TTS (leave `vad`, `turn_detection`, and
`preemptive_generation` as they are, and leave the LLM on the `Agent` unless provisioned SLNG LLM
Router was selected):

```python
stt=slng.STT(model="deepgram/nova:3", language="multi"),
tts=slng.TTS(model="cartesia/sonic:3", voice="9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
```

Add `region_override="eu-north-1"` (or your region) to either call for data residency.

If provisioned SLNG Context Router was selected, update the existing LLM constructor separately:

```python
from livekit.plugins import openai

# ... wherever the current LLM is constructed:
llm=openai.LLM(
    model="slng/auto",
    api_key=os.environ["SLNG_API_KEY"],
    base_url="https://eu.context-router.slng.ai/v1",
    extra_headers={
        "X-Slng-Agent-Id": agent_id,
        "X-Slng-Session-Id": session_id,
    },
)
```

Keep the project's existing entrypoint. In the official starter that is usually `src/agent.py`, and
the Dockerfile may run `uv run src/agent.py start`, but other projects differ.
