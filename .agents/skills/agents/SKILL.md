---
name: agents
description: Create, manage, and dispatch slng.ai voice agents. Use when the user wants to create a voice agent, list or update existing agents, manage agent versions, dispatch an outbound phone call from an agent, start a web (browser) voice session, or inspect the org-level resources agents use — the shared Tools library, MCP servers, Vault secrets, client models, or SIP trunks — or work with the slng Agent Infra / Voice Agents API.
license: MIT
compatibility: Requires internet access and a slng.ai API key (VOICEAI_API_KEY).
---

# slng Voice Agents

Manage voice agents and place real phone calls through slng's Voice Agents API. The agents API lives on a different base than the unified TTS/STT API.

**Base URL:** `https://api.agents.slng.ai`
**Auth:** `Authorization: Bearer $VOICEAI_API_KEY`

> **Setup:** [`setup-api-key`](../setup-api-key/SKILL.md) configures `VOICEAI_API_KEY`. Install paths are in [`references/installation.md`](references/installation.md). To craft the agent's `system_prompt` and `greeting`, use the [`agent-prompt`](../agent-prompt/SKILL.md) skill.

## Quick Start: Create an agent and dispatch a call

### cURL

```bash
# 1. Create
AGENT_ID=$(curl -sS https://api.agents.slng.ai/v1/agents \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hello Agent",
    "greeting": "Hi, thanks for calling Acme. How can I help you today?",
    "system_prompt": "[Identity]\n- You are a friendly receptionist for Acme.\n[Style]\n- Warm and concise.",
    "language": "en",
    "region": "eu-central",
    "models": {
      "stt": "slng/deepgram/nova:3-en",
      "llm": "groq/openai/gpt-oss-120b",
      "tts": "slng/deepgram/aura:2-en",
      "tts_voice": "aura-2-thalia-en"
    }
  }' | jq -r .id)

# 2. Dispatch an outbound call
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/calls \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+14155551234"}'
```

### Python

```python
import os, requests

BASE = "https://api.agents.slng.ai/v1"
H = {"Authorization": f"Bearer {os.environ['VOICEAI_API_KEY']}"}

agent = requests.post(f"{BASE}/agents", headers=H, json={
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
}).json()

requests.post(f"{BASE}/agents/{agent['id']}/calls", headers=H, json={
    "phone_number": "+14155551234",
})
```

### TypeScript

```typescript
const BASE = "https://api.agents.slng.ai/v1";
const h = {
  Authorization: `Bearer ${process.env.VOICEAI_API_KEY}`,
  "Content-Type": "application/json",
};

const agent = await fetch(`${BASE}/agents`, {
  method: "POST",
  headers: h,
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
}).then((r) => r.json());

await fetch(`${BASE}/agents/${agent.id}/calls`, {
  method: "POST",
  headers: h,
  body: JSON.stringify({ phone_number: "+14155551234" }),
});
```

## Endpoints at a glance

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/agents` | Create agent |
| `GET` | `/v1/agents` | List agents |
| `GET` | `/v1/agents/{id}` | Get agent |
| `PATCH` | `/v1/agents/{id}` | Update agent (partial) |
| `PUT` | `/v1/agents/{id}` | Replace agent |
| `DELETE` | `/v1/agents/{id}` | Delete agent |
| `POST` | `/v1/agents/{id}/duplicate` | Duplicate agent |
| `POST` | `/v1/agents/import` | Create an agent from a config document |
| `GET` | `/v1/agents/{id}/config` | Download an agent's config JSON |
| `GET` | `/v1/agents/{id}/versions` | List an agent's saved versions |
| `GET` | `/v1/agents/{id}/versions/{n}` | Get one version (add `/config` to download it) |
| `POST` | `/v1/agents/{id}/versions/{n}/restore/preview` · `/restore/accept` | Preview then restore a version |
| `GET` | `/v1/agents/{id}/sip-trunk-options` | List SIP trunk options available to the agent |
| `POST` | `/v1/agents/{id}/calls` | Dispatch outbound call |
| `GET` | `/v1/agents/{id}/calls` | List calls for agent |
| `GET` | `/v1/agents/{id}/calls/{call_id}` | Get specific call |
| `GET` | `/v1/agents/{id}/calls/export` | Export an agent's calls as CSV |
| `POST` | `/v1/agents/{id}/web-sessions` | Create browser voice session |
| `POST` | `/v1/agents/{id}/calls/{call_id}/tool-executions` | Append a tool execution record to a call (used by SLNG-managed runtimes) |

Org-level resources agents draw on — the shared **Tools** library, **MCP servers**, the **Vault**
(secrets), **client models**, and **SIP trunks** — live under `/v1/agents/tools`,
`/v1/agents/mcp-servers`, `/v1/agents/secrets`, `/v1/agents/client-models`. See
[`references/org-resources.md`](references/org-resources.md).

See [`references/managing-agents.md`](references/managing-agents.md) and [`references/calls-and-sessions.md`](references/calls-and-sessions.md) for full examples in all four paths.

## Agent config shape

Minimum (all required):

```json
{
  "name": "Hello Agent",
  "greeting": "Hi, thanks for calling Acme. How can I help you today?",
  "system_prompt": "...",
  "language": "en",
  "region": "eu-central",
  "models": {
    "stt": "slng/deepgram/nova:3-en",
    "llm": "groq/openai/gpt-oss-120b",
    "tts": "slng/deepgram/aura:2-en",
    "tts_voice": "aura-2-thalia-en"
  }
}
```

`region` must be one of `us-east`, `eu-central`, `ap-south`. `models` may also include `stt_kwargs`, `llm_kwargs`, `tts_kwargs` objects to pass provider-specific overrides.

## Available LLMs

The agents API currently accepts these LLM model IDs. Use one of these verbatim — other Groq/Bedrock routes are not provisioned.

| Model | ID | When to pick |
|---|---|---|
| GPT OSS 120b | `groq/openai/gpt-oss-120b` | Default. Fastest, best for short turns. |
| Nemotron Super | `bedrock-mantle/nvidia.nemotron-super-3-120b` | Higher quality for complex prompts / tool use. |
| Nemotron Nano | `bedrock-mantle/nvidia.nemotron-nano-3-30b` | Lowest latency, simple flows. |

Optional fields:

- `tools` — webhook tools the agent can call. See the [`agent-prompt`](../agent-prompt/SKILL.md) skill for the schema and LLM-vs-system webhook guidance.
- `template_defaults` — fallback values for `{{variable}}` placeholders in `greeting` / `system_prompt`.
- `enable_interruptions` — boolean, defaults to `true`.

## Dispatching a call

Outbound calls require a phone number in E.164 format. Pass `arguments` to fill template variables:

```json
{
  "phone_number": "+14155551234",
  "arguments": {
    "customer_name": "Maria",
    "package_name": "Weekend Getaway"
  }
}
```

Constraints on `arguments`: max 32 keys, key ≤ 64 chars, value ≤ 1024 chars, combined payload ≤ 8192 chars.

## Web (browser) sessions

For embedding an agent in a website (no phone), create a web session and pass the returned LiveKit token to the browser:

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/web-sessions \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"customer_name": "Maria"}}'
```

Response includes `call_id`, `room_name`, `livekit_url`, `livekit_token`, `max_session_seconds`, and `message`. The browser then connects with the standard LiveKit client using `livekit_url` and `livekit_token`.

## Error handling

| Status | Meaning |
|--------|---------|
| `400` | Bad request — usually invalid `system_prompt` or `models` config |
| `401` | Invalid API key |
| `404` | Agent or call not found |
| `409` | Conflict (e.g. duplicate name) |
| `422` | Validation error — error body lists invalid fields |
| `429` | Rate limit |

## See also

- [`references/installation.md`](references/installation.md)
- [`references/managing-agents.md`](references/managing-agents.md)
- [`references/calls-and-sessions.md`](references/calls-and-sessions.md)
- [`agent-prompt`](../agent-prompt/SKILL.md) — generate the `greeting`, `system_prompt`, template variables, and tools to feed into agent creation
