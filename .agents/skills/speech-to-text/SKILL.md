---
name: speech-to-text
description: Transcribe audio to text using the slng.ai Voice AI API. Use when transcribing audio files, building live captions, processing meeting recordings, or working with Deepgram Nova, Sarvam Saaras, Soniox, or Reson8 STT via slng.
license: MIT
compatibility: Requires internet access and a slng.ai API key (VOICEAI_API_KEY).
---

# slng Speech-to-Text

Transcribe audio (file or live stream) through slng's unified STT API. One protocol reaches every provider (Deepgram, Sarvam, Soniox, Reson8). File transcription uses HTTP; live audio uses WebSocket.

> **Setup:** [`setup-api-key`](../setup-api-key/SKILL.md) configures `VOICEAI_API_KEY`. Install paths are in [`references/installation.md`](references/installation.md).

## Quick Start

### CLI

```bash
# Transcribe a file
voiceai stt audio.wav --model slng/deepgram/nova:3-en

# Live microphone
voiceai stt --stream
```

### Python

```python
import os, requests

with open("audio.wav", "rb") as f:
    r = requests.post(
        "https://api.slng.ai/v1/stt/slng/deepgram/nova:3-en",
        headers={"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"},
        files={"audio": f},
    )

print(r.json()["transcript"])
```

### TypeScript

```typescript
import { readFileSync } from "fs";

const form = new FormData();
form.append("audio", new Blob([readFileSync("audio.wav")]), "audio.wav");

const r = await fetch("https://api.slng.ai/v1/stt/slng/deepgram/nova:3-en", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.VOICEAI_API_KEY}` },
  body: form,
});
console.log((await r.json()).transcript);
```

### cURL

```bash
curl https://api.slng.ai/v1/stt/slng/deepgram/nova:3-en \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -F "audio=@audio.wav"
```

## Models

Unified endpoint shape: `POST /v1/stt/{provider}/{model}:{variant}` for files, `WSS /v1/stt/{provider}/{model}:{variant}` for streaming.

| Model ID | Languages | Best for |
|----------|-----------|----------|
| `slng/deepgram/nova:3-en` | English | Default. High accuracy, fast |
| `slng/deepgram/nova:3-es` | Spanish | |
| `slng/deepgram/nova:3-multi` | Auto-detect | Multi-language |
| `slng/deepgram/nova:3-hi` · `-te` · `-kn` · `-mr` · `-id` | Indic + Indonesian | Language-specific Nova 3 |
| `deepgram/nova:3-medical` | English (medical) | Healthcare terminology |
| `slng/speechmatics/realtime:v2` | Multilingual | Real-time |
| `sarvam/saaras:v3` | Indic languages | Hindi, Tamil, Telugu, etc. |
| `gradium/stt:default` | Multilingual | |
| `soniox/speech-ai:rt-v5` | Multilingual | Real-time, ultra-low latency |
| `reson8/reson8stt:v1` | Multilingual | Real-time, telephony-tuned |

List current deployments:

```bash
voiceai models --stt
```

## Streaming (WebSocket)

For live mic input or low-latency captions, use the WebSocket endpoint. See [`references/streaming.md`](references/streaming.md) for the full protocol and examples in all 4 paths.

Quick CLI:

```bash
voiceai stt --stream                                  # mic
arecord -f S16_LE -r 16000 -c 1 | voiceai stt --stream --source stdin
```

## File transcription

For pre-recorded audio, the HTTP endpoint is simplest. Supports common formats (WAV, MP3, FLAC, OGG, WebM, M4A). See [`references/file-transcription.md`](references/file-transcription.md).

## Response shape

File transcription returns JSON:

```json
{
  "transcript": "Hello from slng.",
  "words": [
    {"word": "Hello", "start": 0.02, "end": 0.31, "confidence": 0.99},
    {"word": "from",  "start": 0.32, "end": 0.55, "confidence": 0.98},
    {"word": "slng",  "start": 0.56, "end": 1.10, "confidence": 0.96}
  ],
  "language": "en"
}
```

Streaming returns a series of events: `ready`, `partial_transcript`, `final_transcript`, `error`.

## Audio formats

- **File**: WAV, MP3, FLAC, OGG, WebM, M4A, AAC
- **Streaming**: raw PCM `linear16` at 16 kHz, mono, sent in 4096-byte chunks

## Error handling

| Status | Meaning | Fix |
|--------|---------|-----|
| `401` | Invalid API key | Check `VOICEAI_API_KEY` |
| `400` | Bad audio format or missing field | Verify `Content-Type`, file encoding |
| `413` | File too large | Chunk or use streaming |
| `429` | Rate limit | Back off |

## See also

- [`references/installation.md`](references/installation.md)
- [`references/streaming.md`](references/streaming.md)
- [`references/file-transcription.md`](references/file-transcription.md)
