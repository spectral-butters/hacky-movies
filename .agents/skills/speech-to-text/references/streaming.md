# Streaming STT (WebSocket)

For live mic input, real-time captions, or sub-200ms latency, use the WebSocket endpoint.

WebSocket URL: `wss://api.slng.ai/v1/stt/{provider}/{model}:{variant}`

## Protocol

1. Connect with `Authorization: Bearer <key>` header.
2. Send an init JSON frame:

   ```json
   {
     "type": "init",
     "config": {
       "language": "en",
       "sample_rate": 16000,
       "encoding": "linear16",
       "channels": 1
     }
   }
   ```

3. Receive `{"type": "ready", "session_id": "..."}`.
4. Stream binary audio frames — raw PCM linear16, 16 kHz mono, ~4096 bytes per frame.
5. Receive events:
   - `{"type":"partial_transcript","transcript":"..."}` — interim text
   - `{"type":"final_transcript","transcript":"..."}` — committed segment
   - `{"type":"error","message":"..."}`
6. Send `{"type":"close"}` (or `{"type":"stop"}`) when done.

## CLI

```bash
# Live microphone
voiceai stt --stream

# Pipe pre-encoded raw PCM
arecord -f S16_LE -r 16000 -c 1 | voiceai stt --stream --source stdin

# Pick a model
voiceai stt --stream --model slng/deepgram/nova:3-en
```

## Python

```python
import asyncio, json, os, websockets

URL = "wss://api.slng.ai/v1/stt/slng/deepgram/nova:3-en"

async def transcribe(path: str):
    headers = {"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"}
    async with websockets.connect(URL, extra_headers=headers) as ws:
        await ws.send(json.dumps({
            "type": "init",
            "config": {"language": "en", "sample_rate": 16000, "encoding": "linear16"},
        }))
        # wait for ready
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"

        async def receiver():
            async for raw in ws:
                event = json.loads(raw)
                if event["type"] == "partial_transcript":
                    print(f"... {event['transcript']}", end="\r")
                elif event["type"] == "final_transcript":
                    print(f"\n[final] {event['transcript']}")
                elif event["type"] == "error":
                    print(f"error: {event['message']}")
                    return

        recv_task = asyncio.create_task(receiver())

        with open(path, "rb") as f:
            while chunk := f.read(4096):
                await ws.send(chunk)

        await ws.send(json.dumps({"type": "close"}))
        await recv_task

asyncio.run(transcribe("audio.raw"))
```

With the SDK:

```python
from voiceai import VoiceAI

client = VoiceAI()
async with client.stt.stream(model="slng/deepgram/nova:3-en", encoding="linear16", sample_rate=16000) as session:
    async for chunk in iter_mic():
        await session.send(chunk)
    async for event in session.events():
        if event.type == "final_transcript":
            print(event.transcript)
```

## TypeScript

```typescript
import WebSocket from "ws";
import { readFileSync } from "fs";

const URL = "wss://api.slng.ai/v1/stt/slng/deepgram/nova:3-en";
const ws = new WebSocket(URL, {
  headers: { Authorization: `Bearer ${process.env.VOICEAI_API_KEY}` },
});

ws.on("open", () => {
  ws.send(JSON.stringify({
    type: "init",
    config: { language: "en", sample_rate: 16000, encoding: "linear16" },
  }));
});

ws.on("message", (raw) => {
  const event = JSON.parse(raw.toString());
  if (event.type === "ready") {
    const audio = readFileSync("audio.raw");
    for (let i = 0; i < audio.length; i += 4096) ws.send(audio.subarray(i, i + 4096));
    ws.send(JSON.stringify({ type: "close" }));
  } else if (event.type === "final_transcript") {
    console.log("[final]", event.transcript);
  }
});
```

With the SDK:

```typescript
import { VoiceAI } from "voiceai-sdk";

const client = new VoiceAI();
const session = await client.stt.stream({
  model: "slng/deepgram/nova:3-en",
  encoding: "linear16",
  sampleRate: 16000,
});

session.on("final_transcript", (e) => console.log(e.transcript));
for await (const chunk of mic()) session.send(chunk);
await session.close();
```

## wscat

```bash
npx wscat -c wss://api.slng.ai/v1/stt/slng/deepgram/nova:3-en \
  -H "Authorization: Bearer $VOICEAI_API_KEY"

# then paste:
{"type":"init","config":{"language":"en","sample_rate":16000,"encoding":"linear16"}}
```

(wscat won't let you send binary audio, but it's useful for confirming the init handshake.)

## Capturing mic audio

Raw PCM linear16 mono at 16 kHz is the universal input. Common ways to produce it:

```bash
# Linux (ALSA)
arecord -f S16_LE -r 16000 -c 1 -t raw

# macOS (sox / ffmpeg)
ffmpeg -f avfoundation -i ":0" -ac 1 -ar 16000 -f s16le -

# From an existing MP3
ffmpeg -i in.mp3 -ac 1 -ar 16000 -f s16le -
```
