# File Transcription (HTTP)

For pre-recorded audio, the HTTP endpoint is simpler than WebSocket streaming. One POST with the audio file in, one JSON response out.

Endpoint: `POST https://api.slng.ai/v1/stt/{provider}/{model}:{variant}`
Content type: `multipart/form-data` with field `audio`.

## CLI

```bash
voiceai stt audio.wav --model slng/deepgram/nova:3-en
voiceai stt long.mp3  --model slng/deepgram/nova:3-es
```

CLI prints the transcript to stdout; pipe to `jq` or a file as needed.

## Python

```python
import os
from voiceai import VoiceAI

client = VoiceAI(api_key=os.environ["VOICEAI_API_KEY"])

with open("audio.wav", "rb") as f:
    result = client.stt.transcribe(
        model="slng/deepgram/nova:3-en",
        audio=f,
        language="en",        # optional
        diarize=True,         # optional
    )

print(result.transcript)
for word in result.words:
    print(f"{word.start:5.2f}s  {word.word}")
```

Plain `requests`:

```python
import os, requests

with open("audio.wav", "rb") as f:
    r = requests.post(
        "https://api.slng.ai/v1/stt/slng/deepgram/nova:3-en",
        headers={"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"},
        files={"audio": f},
        data={"language": "en"},   # form fields go alongside the file
    )

r.raise_for_status()
data = r.json()
print(data["transcript"])
```

## TypeScript

```typescript
import { VoiceAI } from "voiceai-sdk";
import { createReadStream } from "fs";

const client = new VoiceAI({ apiKey: process.env.VOICEAI_API_KEY! });

const result = await client.stt.transcribe({
  model: "slng/deepgram/nova:3-en",
  audio: createReadStream("audio.wav"),
  language: "en",
});

console.log(result.transcript);
```

Plain `fetch`:

```typescript
import { readFileSync } from "fs";

const form = new FormData();
form.append("audio", new Blob([readFileSync("audio.wav")]), "audio.wav");
form.append("language", "en");

const r = await fetch("https://api.slng.ai/v1/stt/slng/deepgram/nova:3-en", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.VOICEAI_API_KEY}` },
  body: form,
});
console.log(await r.json());
```

## cURL

```bash
curl https://api.slng.ai/v1/stt/slng/deepgram/nova:3-en \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -F "audio=@audio.wav" \
  -F "language=en"
```

## Common options

| Field | Type | Purpose |
|-------|------|---------|
| `audio` | file | Required. The audio to transcribe. |
| `language` | string | ISO 639-1 hint. Omit for auto-detect on multilingual models. |
| `diarize` | boolean | Label each word with a speaker id. |
| `punctuate` | boolean | Include punctuation. Default `true`. |
| `smart_format` | boolean | Numbers/dates as digits, not words. |
| `keywords` | string[] | Bias the model toward specific words (names, jargon). |

Exact options vary per provider. The error response will list valid fields if you send something unsupported.

## Response shape

```json
{
  "transcript": "Hello from slng.",
  "language": "en",
  "duration_seconds": 1.4,
  "words": [
    {"word": "Hello", "start": 0.02, "end": 0.31, "confidence": 0.99, "speaker": "0"},
    {"word": "from",  "start": 0.32, "end": 0.55, "confidence": 0.98, "speaker": "0"},
    {"word": "slng",  "start": 0.56, "end": 1.10, "confidence": 0.96, "speaker": "0"}
  ]
}
```

## Supported formats

WAV, MP3, FLAC, OGG, WebM, M4A, AAC. Most models accept up to ~200 MB / 4 hours. For longer audio, chunk client-side or switch to the streaming endpoint.
