---
name: text-to-speech
description: Convert text to speech using the slng.ai Voice AI API. Use when generating audio from text, creating voiceovers, synthesizing speech, building voice apps, or working with Deepgram Aura, Rime Arcana, Cartesia Sonic, Sarvam Bulbul, Kugel, Murf Falcon, or Soniox TTS via slng.
license: MIT
compatibility: Requires internet access and a slng.ai API key (VOICEAI_API_KEY).
---

# slng Text-to-Speech

Generate speech from text using slng's unified Voice AI API. One endpoint reaches every provider (Deepgram, Rime, Cartesia, Sarvam, Kugel, Murf, Soniox) with HTTP one-shot or WebSocket streaming.

> **Setup:** [`setup-api-key`](../setup-api-key/SKILL.md) configures `VOICEAI_API_KEY`. Installation details for each path are in [`references/installation.md`](references/installation.md).

## Quick Start

### CLI

The fastest way — pick a voice, give it text, get an MP3:

```bash
voiceai tts "Your support ticket has been resolved." \
  --voice aura-2-thalia-en \
  --out ticket-resolved.mp3
```

### Python

```python
import os, requests

r = requests.post(
    "https://api.slng.ai/v1/tts/slng/deepgram/aura:2",
    headers={"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"},
    json={
        "text": "The package you ordered is out for delivery today.",
        "model": "aura-2-luna-en",
    },
)
r.raise_for_status()
open("delivery-update.wav", "wb").write(r.content)
```

### TypeScript

```typescript
const r = await fetch("https://api.slng.ai/v1/tts/slng/deepgram/aura:2", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.VOICEAI_API_KEY}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    text: "Welcome back. You have three new messages.",
    model: "aura-2-orion-en",
  }),
});
await Bun.write("welcome.wav", await r.arrayBuffer());
```

### cURL

```bash
curl https://api.slng.ai/v1/tts/slng/deepgram/aura:2 \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"Reminder: your appointment is at three pm.","model":"aura-2-asteria-en"}' \
  --output reminder.wav
```

## Models

slng exposes TTS through a unified endpoint shape: `POST /v1/tts/{provider}/{model}:{variant}`.

| Model ID | Languages | Best for |
|----------|-----------|----------|
| `slng/deepgram/aura:2-en` | English | Default. Fast, expressive, wide voice catalog |
| `slng/fish/tts:s2.1-pro` | Multilingual | SLNG-hosted Fish Audio, high quality |
| `slng/inworld/max:1.5` | Multilingual | SLNG-hosted Inworld TTS 1.5 Max |
| `cartesia/sonic:3` | Multilingual | WebSocket streaming, ultra-low latency |
| `cartesia/sonic:3.5` | Multilingual | Latest Sonic |
| `sarvam/bulbul:v3` | Indic languages | Hindi, Tamil, Telugu, Marathi, Kannada |
| `kugelaudio/kugel:2` | Multilingual | Studio quality |
| `murf/murftts:falcon` | Multilingual | Realistic, brand-friendly voices |
| `soniox/tts-rt:v1` | Multilingual | Real-time streaming |

List currently-deployed models from the CLI:

```bash
voiceai models --tts
```

See [`references/voices-and-models.md`](references/voices-and-models.md) for the full catalog and voice-selection guidance.

## Picking a voice

The `model` field in the request body is the **voice id** (not the model id, which is in the URL path). Format for Aura 2: `aura-2-{name}-{lang}`.

```bash
# List all voices for a TTS model
voiceai voices --model slng/deepgram/aura:2-en
```

Recommended defaults:

- English feminine: `aura-2-luna-en` (warm), `aura-2-thalia-en` (clear)
- English masculine: `aura-2-orion-en`

## Streaming

For long text or real-time playback, use the WebSocket interface:

```bash
voiceai tts "long passage..." --stream | ffplay -nodisp -autoexit -
```

See [`references/streaming.md`](references/streaming.md) for the WebSocket protocol and SDK examples.

## Audio output

Default response is binary audio. The CLI writes MP3 by default; the REST API returns WAV. Format depends on the upstream model — Deepgram Aura returns WAV/MP3, Cartesia and Soniox stream raw PCM frames over WebSocket.

## Regions

Pin a region to reduce latency or meet data residency requirements:

```bash
voiceai tts "..." --region eu-north-1
```

Available regions: `ap-south-1`, `ap-southeast-2`, `asia-south1`, `asia-southeast2`, `australia-southeast1`, `eu-north-1`, `us-east-1`. Or set a world part: `ap`, `eu`, `eu-non-eu`, `me`, `na`.

## Error handling

| Status | Meaning | Fix |
|--------|---------|-----|
| `401` | Missing or invalid API key | Check `VOICEAI_API_KEY` |
| `400` | Invalid request — usually bad `model` (voice id) | The error body lists valid options |
| `404` | Endpoint path wrong | Check `provider/model:variant` casing |
| `429` | Rate limit | Back off and retry |
| `500` | Upstream provider error | Often a malformed `model` value passed through |

## See also

- [`references/installation.md`](references/installation.md) — install the CLI, Python SDK, TypeScript SDK
- [`references/streaming.md`](references/streaming.md) — WebSocket streaming across all 4 paths
- [`references/voices-and-models.md`](references/voices-and-models.md) — full voice catalog
