# Streaming TTS

For long passages or real-time playback, stream over WebSocket instead of waiting for a one-shot HTTP response.

WebSocket URL: `wss://api.slng.ai/v1/tts/{provider}/{model}:{variant}/ws`

## Protocol

1. Connect with `Authorization: Bearer <key>` header.
2. Send a text frame with the synthesis request:

   ```json
   { "type": "synthesize", "text": "Your text here", "model": "aura-2-luna-en" }
   ```

3. Receive binary audio frames (PCM or MP3 chunks depending on model) and JSON status events:

   ```json
   {"type":"audio","audio_base64":"..."}
   {"type":"final","is_final":true}
   ```

4. Close the socket when done (or send `{"type":"close"}`).

## CLI

```bash
# Pipe streamed audio directly to a player
voiceai tts "long passage..." --stream | ffplay -nodisp -autoexit -

# Save streamed audio to a file
voiceai tts "long passage..." --stream --out long.mp3
```

## Python

```python
import asyncio, json, os, base64, websockets

URL = "wss://api.slng.ai/v1/tts/slng/deepgram/aura:2/ws"

async def stream_tts(text: str, out_path: str):
    headers = {"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"}
    async with websockets.connect(URL, extra_headers=headers) as ws:
        await ws.send(json.dumps({
            "type": "synthesize",
            "text": text,
            "model": "aura-2-luna-en",
        }))
        with open(out_path, "wb") as f:
            async for message in ws:
                if isinstance(message, bytes):
                    f.write(message)
                else:
                    event = json.loads(message)
                    if event.get("audio_base64"):
                        f.write(base64.b64decode(event["audio_base64"]))
                    if event.get("is_final"):
                        break

asyncio.run(stream_tts("Stream me line by line...", "out.mp3"))
```

With the SDK:

```python
from voiceai import VoiceAI

client = VoiceAI()
with client.tts.stream(model="slng/deepgram/aura:2-en", text="...", voice="aura-2-luna-en") as stream, \
     open("out.mp3", "wb") as f:
    for chunk in stream:
        f.write(chunk)
```

## TypeScript

```typescript
import WebSocket from "ws";
import { writeFileSync, appendFileSync } from "fs";

const ws = new WebSocket("wss://api.slng.ai/v1/tts/slng/deepgram/aura:2/ws", {
  headers: { Authorization: `Bearer ${process.env.VOICEAI_API_KEY}` },
});

writeFileSync("out.mp3", "");

ws.on("open", () => {
  ws.send(JSON.stringify({
    type: "synthesize",
    text: "Stream me line by line...",
    model: "aura-2-luna-en",
  }));
});

ws.on("message", (data, isBinary) => {
  if (isBinary) {
    appendFileSync("out.mp3", data as Buffer);
    return;
  }
  const event = JSON.parse(data.toString());
  if (event.audio_base64) appendFileSync("out.mp3", Buffer.from(event.audio_base64, "base64"));
  if (event.is_final) ws.close();
});
```

With the SDK:

```typescript
import { VoiceAI } from "voiceai-sdk";
import { createWriteStream } from "fs";

const client = new VoiceAI();
const stream = await client.tts.stream({
  model: "slng/deepgram/aura:2-en",
  text: "...",
  voice: "aura-2-luna-en",
});
const out = createWriteStream("out.mp3");
for await (const chunk of stream) out.write(chunk);
out.end();
```

## wscat

Quick smoke test:

```bash
npx wscat -c wss://api.slng.ai/v1/tts/slng/deepgram/aura:2/ws \
  -H "Authorization: Bearer $VOICEAI_API_KEY"

# then paste:
{"type":"synthesize","text":"hello","model":"aura-2-luna-en"}
```

## When to use streaming vs HTTP

- **HTTP (`/v1/tts/...`)** — short clips, you only need the final file. Simpler.
- **WebSocket (`.../ws`)** — long text, low time-to-first-audio, or models that only support streaming (Cartesia Sonic, Kugel, Murf, Soniox).
