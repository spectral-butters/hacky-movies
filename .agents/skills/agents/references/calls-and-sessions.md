# Calls and Sessions

How to put an agent on a real phone call or in a browser session, and how to handle async tool execution.

Base: `https://api.agents.slng.ai`.

## Dispatch outbound call

`POST /v1/agents/{agent_id}/calls` places a real phone call to a number.

### cURL

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/calls \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+14155551234",
    "arguments": {
      "patient_name": "Maria",
      "practice_name": "Greenfield Family Medicine"
    }
  }'
```

### Python

```python
call = client.agents.calls.create(
    agent_id=agent_id,
    phone_number="+14155551234",
    arguments={"patient_name": "Maria"},
)
print(call.id, call.status)
```

### TypeScript

```typescript
const call = await client.agents.calls.create(agentId, {
  phoneNumber: "+14155551234",
  arguments: { patient_name: "Maria" },
});
```

**Constraints on `arguments`:** max 32 keys, key ≤ 64 chars, value ≤ 1024 chars, total payload ≤ 8192 chars.

The agent must be connected to a configured telephony number (see slng dashboard → Telephony) before outbound calls work.

## List calls

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/calls \
  -H "Authorization: Bearer $VOICEAI_API_KEY"
```

```python
calls = client.agents.calls.list(agent_id)
```

```typescript
const calls = await client.agents.calls.list(agentId);
```

## Get a specific call

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/calls/$CALL_ID \
  -H "Authorization: Bearer $VOICEAI_API_KEY"
```

```python
call = client.agents.calls.get(agent_id, call_id)
print(call.status, call.duration_seconds, call.transcript)
```

Response includes `status` (`queued`, `ringing`, `in_progress`, `completed`, `failed`), `duration_seconds`, `transcript`, `tool_calls`, and `recording_url` if recording is enabled.

## Create web (browser) session

`POST /v1/agents/{agent_id}/web-sessions` returns a LiveKit token your browser frontend uses to connect to the agent over WebRTC. No phone number needed.

### cURL

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/web-sessions \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {"customer_name": "Maria"}
  }'
```

Response:

```json
{
  "call_id": "550e8400-e29b-41d4-a716-446655440000",
  "room_name": "room_...",
  "livekit_url": "wss://livekit.slng.ai",
  "livekit_token": "eyJhbGciOi...",
  "max_session_seconds": 1800,
  "message": "Web session created successfully"
}
```

### Python

```python
session = client.agents.web_sessions.create(
    agent_id=agent_id,
    arguments={"customer_name": "Maria"},
)
# return session.livekit_url + session.livekit_token to the browser
```

### TypeScript (server-side)

```typescript
const session = await client.agents.webSessions.create(agentId, {
  arguments: { customer_name: "Maria" },
});
// Send session.livekit_url, session.livekit_token, session.room_name to the browser
```

### Browser (LiveKit JS)

```typescript
import { Room } from "livekit-client";

const room = new Room();
await room.connect(session.livekit_url, session.livekit_token);
// LiveKit handles mic capture and audio playback
```

**Never expose `VOICEAI_API_KEY` to the browser.** Always mint the session token from your backend.

## Submit tool execution

`POST /v1/agents/{agent_id}/calls/{call_id}/tool-executions` appends a tool execution record to a call. This endpoint is primarily used by SLNG-managed agent runtimes to report contextual and system tool activity back to the Agents API — most integrations will not call it directly.

Required body fields: `tool_name`, `tool_kind` (`webhook` | `template` | `human_transfer` | `built_in`), `invocation_source` (`system` | `contextual`), `started_at`, `finished_at`, `duration_ms`, `outcome` (`succeeded` | `failed` | `timed_out` | `skipped` | `cancelled`).

```bash
curl https://api.agents.slng.ai/v1/agents/$AGENT_ID/calls/$CALL_ID/tool-executions \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "book_appointment",
    "tool_kind": "webhook",
    "invocation_source": "contextual",
    "started_at": "2026-05-20T14:00:00Z",
    "finished_at": "2026-05-20T14:00:02Z",
    "duration_ms": 1850,
    "outcome": "succeeded"
  }'
```

Returns `204 No Content` on success.

## Call lifecycle events

Configure a System webhook on your agent to receive these events:

- `call_start` — call connected, before the agent speaks
- `first_user_message` — after the first transcribed line from the caller
- `tool_succeeded` / `tool_failed` — fires per LLM tool invocation
- `call_end` — call hung up; includes `call_end_reason`

See the [`agent-prompt`](../../agent-prompt/SKILL.md) skill for the System webhook JSON schema and supported `source.type` values.
