---
name: setup-api-key
description: Configure and validate a slng.ai Voice AI API key. Use when getting started with slng, when an API call returns 401, or when the user asks to "set up VOICEAI_API_KEY", "configure slng credentials", or "get a voiceai key".
license: MIT
---

# Setup slng API Key

Configure `VOICEAI_API_KEY` so the CLI, SDKs, and direct REST calls can authenticate against `https://api.slng.ai`.

## Handling rules

- If `$VOICEAI_API_KEY` is already set, use it silently. Do not ask the user to paste or confirm it.
- Never echo the key back in responses, logs, error messages, or shell history.
- Prefer `read -s VOICEAI_API_KEY && export VOICEAI_API_KEY` (terminal does not echo, key stays out of the conversation transcript) over asking the user to paste in chat. Only fall back to in-chat paste if the environment cannot be set before the session.
- After saving to `.env`, confirm `.env` is in `.gitignore` before continuing.

## Workflow

> **Fastest path (CLI installed):** `voiceai login` prompts for the key, saves it to a credential
> profile, and verifies it against `/v1/me` in one step (`--profile <name>` for a named profile,
> `--no-verify` to skip the probe). Use it instead of steps 2–4 when the CLI is available and the key
> can live in the CLI config. The manual steps below still apply for `.env` / shell-rc / CI setups.

### 1. Check if a key is already configured

```bash
echo "$VOICEAI_API_KEY"
```

Also check a project `.env`:

```bash
grep -E '^VOICEAI_API_KEY=' .env 2>/dev/null
```

If a key is set, validate it (see step 3) and stop. Do not prompt the user.

### 2. If missing, obtain a key

Direct the user to the dashboard:

> Open https://app.slng.ai/api-keys, create a new key, and copy it now. The key is shown only once.

Ask the user to paste the key.

### 3. Validate the key

If the CLI is installed (v0.1.9 or later), use the built-in `whoami` command. It hits `GET /v1/me` under the hood — no TTS/STT credits consumed — and prints a masked key plus the authenticated workspace on success:

```bash
voiceai whoami
# → ✔ Signed in as slng_cu_...DFTF · [SLNG] Nicolas's Workspace (hobby) · key "cli" · profile: default
```

For scripting:

```bash
voiceai whoami --json
# → {"ok":true,"status":200,"profile":"default","masked_key":"slng_cu_...DFTF","account":{"name":null,"email":null,"org_id":"8b7580a9-a6d1-4ae0-9a09-4457afebe0d2","org_name":"[SLNG] Nicolas's Workspace","api_key_label":"cli","tier":"hobby"}}
```

Exit code is `0` on success, `1` on 401.

If `voiceai` is not on PATH (or you're on an older CLI), fall back to raw curl against the same endpoint:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $VOICEAI_API_KEY" \
  https://api.slng.ai/v1/me
```

- `200` — key is good.
- `401` — key is invalid. Ask the user to re-check and paste again. Allow one retry, then stop.

Override the base URL for staging with `VOICEAI_BASE_URL` (CLI) or by editing the curl host.

### 4. Persist the key

Ask the user where to save it:

**Project `.env`** (recommended for repos):

```bash
echo 'VOICEAI_API_KEY=...' >> .env
```

Make sure `.env` is in `.gitignore`.

**Shell rc** (for global use):

```bash
# zsh
echo 'export VOICEAI_API_KEY="..."' >> ~/.zshrc

# bash
echo 'export VOICEAI_API_KEY="..."' >> ~/.bashrc
```

Then `source ~/.zshrc` or open a new terminal.

**voiceai CLI config** (third option, used only by the CLI):

```bash
voiceai config set apiKey "slng_cu_..."
```

Stored at `~/.config/voiceai/config.json`. Note: env vars override anything in this file.

To wipe local CLI state (config file, cached keys, legacy `~/.config/slng/` directory), run:

```bash
voiceai config reset --force
```

Useful when reconfiguring against a different workspace or before uninstalling — `brew uninstall` does not remove the config directory.

## Environment variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `VOICEAI_API_KEY` | Bearer token sent as `Authorization: Bearer <key>` | Yes |
| `VOICEAI_BASE_URL` | Override the unified base URL (default `https://api.slng.ai`). Used by TTS/STT and by `voiceai whoami` (`/v1/me`) | No |
| `VOICEAI_AGENTS_BASE_URL` | Override the agents API base URL (default `https://api.agents.slng.ai`). Used by the agents skill | No |

## Security

- Never commit keys to git. Always gitignore `.env`.
- Treat the key like a password. Rotate it from the dashboard if leaked.

## Common errors

- **401 Unauthorized** — key missing, malformed, or revoked. Re-check the dashboard.
- **403 Forbidden** — key is valid but lacks permission for that endpoint. Check the workspace it belongs to.
- **429 Too Many Requests** — rate limit. Back off and retry.
