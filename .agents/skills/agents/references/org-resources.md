# Org resources: Tools, MCP servers, Vault, client models, SIP trunks

Voice agents draw on a set of organisation-level resources that are shared across every agent, not
defined per agent. They live under the agents API base (`https://api.agents.slng.ai`) and each has a
read-only inspector in the `voiceai` CLI. All requests use `Authorization: Bearer $VOICEAI_API_KEY`.

The CLI subcommands below are the fastest way to see what your org already has; the REST paths are
for programmatic access. Full request/response schemas live at https://docs.slng.ai.

## Tools library

Reusable tools (webhook, template, human-transfer, built-in) that agents call mid-conversation. A
tool is defined once and attached to many agents.

```bash
voiceai tool list                          # every tool your agents can call
voiceai tool get api_request               # one tool, all properties (--json carries arg_schema)
voiceai tool run check_order --confirm-side-effects   # execute one tool for real
```

| Method | Path | Purpose |
|--------|------|---------|
| `POST` / `GET` | `/v1/agents/tools` | Create / list tools |
| `GET` / `PATCH` / `DELETE` | `/v1/agents/tools/{tool_id}` | Get / update / delete a tool |
| `POST` | `/v1/agents/tools/{tool_id}/duplicate` · `/publish` · `/run` · `/introspect` | Copy, publish, execute, or introspect a tool |
| `GET` | `/v1/agents/tools/{tool_id}/versions` · `/versions/{n}` | Tool version history |

Attaching a tool to an agent is done through the agent's `tools` array — see the
[`agent-prompt`](../../agent-prompt/SKILL.md) skill for the webhook/system tool schema.

## MCP servers

Model Context Protocol servers that expose tools to your agents.

```bash
voiceai mcp list                 # every MCP server available to your org
voiceai mcp get firecrawl-mcp    # one server, all properties
voiceai mcp tools firecrawl-mcp  # the tools that server exposes
voiceai mcp run firecrawl-mcp    # connect now and report what it exposes
```

| Method | Path | Purpose |
|--------|------|---------|
| `POST` / `GET` | `/v1/agents/mcp-servers` | Register / list MCP servers |
| `GET` / `PATCH` / `DELETE` | `/v1/agents/mcp-servers/{server_id}` | Get / update / delete |
| `POST` | `/v1/agents/mcp-servers/{server_id}/connect` | Connect and enumerate its tools |

## Vault (secrets & variables)

Named secrets/variables that tools and webhooks reference at call time, so credentials never live in
an agent config. Values are write-only through the API; reads return metadata, not the secret.

```bash
voiceai secret list                              # every vault entry
voiceai secret get STRIPE_KEY                     # metadata for one entry (exit 0 if present)
voiceai secret create STRIPE_KEY                  # prompts for the value
voiceai secret create --secrets-file .env.local   # one entry per KEY=VALUE line
```

| Method | Path | Purpose |
|--------|------|---------|
| `POST` / `GET` | `/v1/agents/secrets` | Create / list vault entries |
| `GET` / `PATCH` / `DELETE` | `/v1/agents/secrets/{name}` | Get metadata / update / delete |
| `PATCH` | `/v1/agents/secrets/{name}/description` | Update the description |
| `GET` | `/v1/agents/secrets/{name}/references` | List what references this entry |

## Client models

Bring-your-own / custom model registrations an org can attach to agents.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` / `GET` | `/v1/agents/client-models` | Register / list client models |
| `GET` / `PUT` / `DELETE` | `/v1/agents/client-models/{client_model_id}` | Get / replace / delete |

## SIP trunks

Inbound and outbound SIP trunks for telephony. Inbound and outbound trunks are separate objects — the
same name can exist on both sides, so direction is part of a trunk's identity.

```bash
voiceai trunks list                        # every trunk, both directions
voiceai trunks list --direction outbound   # only outbound
voiceai trunks get nicotestslng            # one trunk, and what each agent says about it
```

Per-agent trunk options are read via `GET /v1/agents/{id}/sip-trunk-options`.

## Pushing a compiled agent package

For agents authored with the Unmute toolchain, the CLI can push a compiled package directly:

```bash
voiceai agents push <dir>   # push an unmute-compiled agent package
```
