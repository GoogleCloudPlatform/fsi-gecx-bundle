# Credit Support Agent Operations

## Runtime contract

- ADK is locked to `2.4.0` in `pyproject.toml`, `requirements.txt`, and `uv.lock`.
- Live response scheduling is applied in `agent/tooling.py`.
- `VOICE_AGENT_SESSION_RESUMPTION_ENABLED` controls Gemini Live connection
  resumption independently from durable ADK session storage.
- `VOICE_SESSION_PERSISTENCE_ENABLED` controls ADK `DatabaseSessionService`;
  local development falls back to the in-memory service when `DATABASE_URL` is
  absent.
- Durable sessions retain at most `VOICE_SESSION_MAX_EVENTS` (default 120) when
  hydrated and expire after `VOICE_SESSION_TTL_SECONDS` (default 12 hours).
- The agent fails closed before a consequential tool when the banking reset
  generation cannot be verified or has changed.

## Pre-deployment checks

```bash
uv sync --frozen
uv run pytest -q
uv run ruff check agent tests voice_agent.py
```

Also run the banking-service tests for knowledge guidance, reset integration,
and migrations, build the banking UI, and inspect `terraform plan` for:

- one Cloud SQL IAM user for `voice-agent-sa`
- Cloud SQL client and instance-user grants for that service account
- the credit-support-agent `DATABASE_URL` changing to its own async user
- no replacement of the Cloud SQL instance or unrelated Cloud Run services

Deploy the database migration and banking service before the agent revision so
the reset epoch table and voice-context field exist first.

## Evo rehearsal

Run each audio path once, then run the all-disputed fraud path three consecutive
times before a demo:

1. all flagged charges disputed, replacement accepted, Wallet accepted
2. all charges recognized (no replacement)
3. partial dispute
4. Wallet declined and Wallet ambiguous (no Wallet tool call)
5. interruption before confirmation (no mutation)
6. transient tool failure (bounded retry or safe escalation)
7. presenter reset during a pending confirmation (old session must be rejected)
8. remote Knowledge Catalog and forced local fallback

For each run, confirm one mutation call, no spoken success before its structured
result, the expected UI event, terminal outcome, guidance source/topics/version,
and reset generation in structured logs. Qualify preview avatar separately; the
audio path is the release gate.

## Rollback

First route traffic to the prior Cloud Run revision. The database additions are
backward compatible and can remain in place. If a source rollback is required,
restore `google-adk==2.3.0` and its lock file, disable
`VOICE_AGENT_SESSION_RESUMPTION_ENABLED`, and deploy the prior agent image. No
banking or UI rollback is required because MCP and data-channel payloads remain
compatible.
