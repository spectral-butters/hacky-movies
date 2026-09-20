# Installation

The agents API lives at `https://api.agents.slng.ai` (separate base from the unified TTS/STT API). All requests use `VOICEAI_API_KEY`. See [`setup-api-key`](../../setup-api-key/SKILL.md).

## CLI

The `voiceai` CLI focuses on TTS/STT. Agent management is best done through the dashboard or the API directly. To install the CLI for related TTS/STT work:

```bash
# Homebrew (macOS / Linux)
brew install slng-ai/tap/voiceai

# Install script
curl -fsSL https://docs.slng.ai/install.sh | sh

# npm (cross-platform)
npm install -g voiceai-cli
```

For agent operations, use the SDK or `curl` examples below.

## Python

```bash
pip install voiceai-sdk
```

```python
import os
from voiceai import VoiceAI

client = VoiceAI(api_key=os.environ["VOICEAI_API_KEY"])

agent = client.agents.create(
    name="Hello Agent",
    greeting="Hi, thanks for calling Acme. How can I help you today?",
    system_prompt="[Identity]\n- You are a friendly receptionist for Acme.",
    language="en",
    region="eu-central",
    models={
        "stt": "slng/deepgram/nova:3-en",
        "llm": "groq/openai/gpt-oss-120b",
        "tts": "slng/deepgram/aura:2-en",
        "tts_voice": "aura-2-thalia-en",
    },
)
print(agent.id)
```

Plain `requests`:

```python
import os, requests

r = requests.post(
    "https://api.agents.slng.ai/v1/agents",
    headers={"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"},
    json={
        "name": "Hello Agent",
        "greeting": "Hi, thanks for calling Acme. How can I help you today?",
        "system_prompt": "[Identity]\n- You are a friendly receptionist for Acme.",
        "language": "en",
        "region": "eu-central",
        "models": {
            "stt": "slng/deepgram/nova:3-en",
            "llm": "groq/openai/gpt-oss-120b",
            "tts": "slng/deepgram/aura:2-en",
            "tts_voice": "aura-2-thalia-en",
        },
    },
)
print(r.json()["id"])
```

## TypeScript

```bash
npm install voiceai-sdk
```

```typescript
import { VoiceAI } from "voiceai-sdk";

const client = new VoiceAI({ apiKey: process.env.VOICEAI_API_KEY! });

const agent = await client.agents.create({
  name: "Hello Agent",
  greeting: "Hi, thanks for calling Acme. How can I help you today?",
  systemPrompt: "[Identity]\n- You are a friendly receptionist for Acme.",
  language: "en",
  region: "eu-central",
  models: {
    stt: "slng/deepgram/nova:3-en",
    llm: "groq/openai/gpt-oss-120b",
    tts: "slng/deepgram/aura:2-en",
    tts_voice: "aura-2-thalia-en",
  },
});
console.log(agent.id);
```

Plain `fetch`:

```typescript
const r = await fetch("https://api.agents.slng.ai/v1/agents", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.VOICEAI_API_KEY}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    name: "Hello Agent",
    greeting: "Hi, thanks for calling Acme. How can I help you today?",
    system_prompt: "[Identity]\n- You are a friendly receptionist for Acme.",
    language: "en",
    region: "eu-central",
    models: {
      stt: "slng/deepgram/nova:3-en",
      llm: "groq/openai/gpt-oss-120b",
      tts: "slng/deepgram/aura:2-en",
      tts_voice: "aura-2-thalia-en",
    },
  }),
});
console.log((await r.json()).id);
```

## cURL

```bash
curl https://api.agents.slng.ai/v1/agents \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hello Agent",
    "greeting": "Hi, thanks for calling Acme. How can I help you today?",
    "system_prompt": "[Identity]\n- You are a friendly receptionist for Acme.",
    "language": "en",
    "region": "eu-central",
    "models": {
      "stt": "slng/deepgram/nova:3-en",
      "llm": "groq/openai/gpt-oss-120b",
      "tts": "slng/deepgram/aura:2-en",
      "tts_voice": "aura-2-thalia-en"
    }
  }'
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `VOICEAI_API_KEY` | Bearer token. Required. |
| `VOICEAI_BASE_URL` | Optional override of the unified API base (not used for agents API). |
