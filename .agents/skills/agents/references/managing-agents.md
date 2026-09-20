# Managing Agents

CRUD operations on the `/v1/agents` resource. Base: `https://api.agents.slng.ai`.

## Create

### cURL

```bash
curl https://api.agents.slng.ai/v1/agents \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Patient Outreach",
    "greeting": "Hi, is this {{patient_name}}?",
    "system_prompt": "[Identity]\n- You are Sarah, a patient outreach coordinator at {{practice_name}}.\n[Style]\n- Warm and caring.\n[Response Guidelines]\n- Ask one question at a time.\n[Task and Conversation Flow]\n1. Greet the patient by name and ask if they have a moment.\n2. ...\n[Guardrails]\n- Never provide medical advice.",
    "language": "en",
    "region": "eu-central",
    "models": {
      "stt": "slng/deepgram/nova:3-en",
      "llm": "groq/openai/gpt-oss-120b",
      "tts": "slng/deepgram/aura:2-en",
      "tts_voice": "aura-2-thalia-en"
    },
    "template_defaults": {
      "practice_name": "Greenfield Family Medicine"
    },
    "tools": [
      {
        "type": "webhook",
        "id": "d8f8c1d7-3cf0-4c95-bb06-f28a2a1d2b50",
        "name": "book_appointment",
        "description": "Book an appointment for the patient",
        "url": "https://your-server.example.com/webhook/book-appointment",
        "source": "contextual",
        "parameters": {
          "type": "object",
          "required": ["patient_name", "preferred_date"],
          "properties": {
            "patient_name": {"type": "string", "description": "Patient full name"},
            "preferred_date": {"type": "string", "description": "Preferred date, ISO 8601"}
          },
          "additionalProperties": false
        },
        "timeout_seconds": 10,
        "wait_for_response": true,
        "show_results_to_llm": true
      }
    ]
  }'
```

### Python

```python
from voiceai import VoiceAI

client = VoiceAI()

agent = client.agents.create(
    name="Patient Outreach",
    greeting="Hi, is this {{patient_name}}?",
    system_prompt="[Identity]\n- You are Sarah, a patient outreach coordinator...",
    language="en",
    region="eu-central",
    models={
        "stt": "slng/deepgram/nova:3-en",
        "llm": "groq/openai/gpt-oss-120b",
        "tts": "slng/deepgram/aura:2-en",
        "tts_voice": "aura-2-thalia-en",
    },
    template_defaults={"practice_name": "Greenfield Family Medicine"},
    tools=[...],
)
```

### TypeScript

```typescript
const agent = await client.agents.create({
  name: "Patient Outreach",
  greeting: "Hi, is this {{patient_name}}?",
  systemPrompt: "[Identity]\n- You are Sarah, ...",
  language: "en",
  region: "eu-central",
  models: {
    stt: "slng/deepgram/nova:3-en",
    llm: "groq/openai/gpt-oss-120b",
    tts: "slng/deepgram/aura:2-en",
    tts_voice: "aura-2-thalia-en",
  },
  templateDefaults: { practice_name: "Greenfield Family Medicine" },
  tools: [...],
});
```

## List

```bash
curl https://api.agents.slng.ai/v1/agents \
  -H "Authorization: Bearer $VOICEAI_API_KEY"
```

```python
agents = client.agents.list()
for a in agents:
    print(a.id, a.name)
```

```typescript
const agents = await client.agents.list();
agents.forEach((a) => console.log(a.id, a.name));
```

## Get

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID \
  -H "Authorization: Bearer $VOICEAI_API_KEY"
```

```python
agent = client.agents.get(agent_id)
```

```typescript
const agent = await client.agents.get(agentId);
```

## Update (partial)

`PATCH` only sends the fields you want to change.

```bash
curl -X PATCH https://api.agents.slng.ai/v1/agents/$AGENT_ID \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"greeting": "Hi! New greeting."}'
```

```python
client.agents.update(agent_id, greeting="Hi! New greeting.")
```

```typescript
await client.agents.update(agentId, { greeting: "Hi! New greeting." });
```

## Replace

`PUT` replaces the entire agent definition. You must send every required field.

```bash
curl -X PUT https://api.agents.slng.ai/v1/agents/$AGENT_ID \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @full-agent.json
```

## Delete

```bash
curl -X DELETE https://api.agents.slng.ai/v1/agents/$AGENT_ID \
  -H "Authorization: Bearer $VOICEAI_API_KEY"
```

```python
client.agents.delete(agent_id)
```

```typescript
await client.agents.delete(agentId);
```

## Duplicate

```bash
curl -X POST https://api.agents.slng.ai/v1/agents/$AGENT_ID/duplicate \
  -H "Authorization: Bearer $VOICEAI_API_KEY"
```

Returns a new agent with a fresh id and a copied configuration.

## Field reference

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | string | yes | Display name |
| `greeting` | string | yes | First spoken line. May contain `{{vars}}` |
| `system_prompt` | string | yes | Use sections like `[Identity]`, `[Style]`, etc. See [`agent-prompt`](../../agent-prompt/SKILL.md) |
| `language` | string | yes | ISO code like `"en"` |
| `region` | string | yes | One of `us-east`, `eu-central`, `ap-south` |
| `models` | object | yes | Required keys: `stt`, `llm`, `tts`, `tts_voice`. Optional: `stt_kwargs`, `llm_kwargs`, `tts_kwargs`. `llm` must be one of the IDs in [Available LLMs](../SKILL.md#available-llms) |
| `tools` | array | no | Webhook tool definitions |
| `template_defaults` | object | no | Fallback values for `{{vars}}` |
| `enable_interruptions` | boolean | no | Defaults to `true` |
