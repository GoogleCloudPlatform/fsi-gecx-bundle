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
- `VOICE_AGENT_USE_ACTION_PROPOSALS` defaults to `true`. It makes active-alert
  fraud triage commit the banking-owned proposal id; `false` temporarily restores
  the direct `triage_fraud_case` compatibility path.

## Pre-deployment checks

```bash
uv sync --frozen
uv run pytest -q
uv run ruff check agent tests voice_agent.py
```

Also run the banking-service tests for knowledge guidance, reset integration,
and migrations, build the banking UI, and inspect `terraform plan` for:

- one AlloyDB IAM database user for `voice-agent-sa`
- AlloyDB database-user and Service Usage Consumer grants for that service account
- the credit-support-agent `DATABASE_URL` changing to its own async user
- no replacement of the AlloyDB cluster or unrelated Cloud Run services

Deploy the database migration and banking service before the agent revision so
the reset epoch table and voice-context field exist first.

When the fraud guidance bundle changes, run the banking-service Knowledge
Catalog sync after deployment. Version 2.1 adds the
`customer_reported_fraud` topic; a missing remote topic is safe because the
runtime merges the local fallback, but the catalog should be synchronized
before promotion.

## Evo rehearsal

After deployment, run the non-mutating dependency probe and evaluate the latest
completed trajectory:

```bash
uv run python scripts/voice_canary.py \
  --project evo-genai-workspace \
  --region us-central1 \
  --customer-id <presenter-auth-provider-uid> \
  --scenario fraud-wallet
```

The command uses an authenticated Cloud Run proxy, checks model/runtime
configuration, MCP reachability, durable session storage, reset generation,
and catalog grounding, then evaluates the latest session for duplicate calls,
tool outcomes, required UI events, interruptions, duration, and terminal
outcome. Use `--readiness-only` before beginning a rehearsal and `--session-id`
to evaluate a specific completed session.

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
9. no active alert: identify one pending and one posted debit from recent
   history, confirm the exact selection, and complete customer-reported triage

For each run, confirm one mutation call, no spoken success before its structured
result, the expected UI event, terminal outcome, guidance source/topics/version,
and reset generation in structured logs. Qualify preview avatar separately; the
audio path is the release gate.

Terminal telemetry distinguishes `NORMAL_DISCONNECT`, `HANDOFF`,
`MODEL_FAILURE`, `MEDIA_FAILURE`, `TOOL_FAILURE`, `HARD_TIMEOUT`, and
`CANCELLED`. A tool failure that succeeds on a same-tool retry is resolved and
does not misclassify an otherwise normal session.

## Capacity, telemetry, and retention

- Terraform limits simultaneous control requests and sets the per-instance
  weighted session ceiling through `VOICE_AGENT_MAX_CONCURRENT_SESSIONS`.
- Terraform and the Cloud Build deploy step share the same CPU, memory,
  request-concurrency, timeout, warm-instance, scaling, and weighted-capacity
  settings. Do not deploy with ad hoc Cloud Run defaults; verify the resulting
  revision against the planned values after every capacity-related change.
- Audio consumes one capacity unit by default; preview avatar consumes four.
  Tune those weights independently with
  `VOICE_AGENT_AUDIO_SESSION_CAPACITY_UNITS` and
  `VOICE_AGENT_VIDEO_SESSION_CAPACITY_UNITS` only after measuring the target
  revision.
- Treat the checked-in defaults as conservative. Record separate audio and
  preview-avatar saturation results before raising them; avatar capacity must
  never be inferred from audio-only results.
- Inspect the admission matrix without opening a room:

  ```bash
  uv run python scripts/voice_capacity_probe.py
  ```

  A real media probe is intentionally opt-in. Run it first with four audio
  sessions and then one video session against a non-demo revision, supplying a
  direct authenticated agent start URL and LiveKit credentials through the
  environment. The command refuses more than four rooms unless its explicit
  safety bound is also raised:

  ```bash
  uv run python scripts/voice_capacity_probe.py \
    --confirm-live-load \
    --mode audio \
    --sessions 4 \
    --duration-seconds 30 \
    --customer-id <presenter-auth-provider-uid> \
    --agent-start-url http://127.0.0.1:18080/internal/comms/voice/start
  ```

  Save the JSON results with the Cloud Run revision and observe CPU, memory,
  instance count, session/tool latency, interruptions, and 429 responses. The
  release criterion is no cross-session transcript or event leakage, no task
  cleanup affecting another room, and predictable admission at the configured
  capacity boundary.
- Operational callback logs contain bounded counts and outcomes, not card
  tokens, transaction ids, message bodies, raw MCP responses, customer IDs, or
  room names. Stable hashed references retain correlation without exposing the
  underlying identifiers.
- OpenTelemetry instruments session starts/completions, duration, interruption,
  typed-turn delivery, avatar-to-audio fallback, and tool outcomes/duration
  using low-cardinality attributes. Export through the environment's
  configured OpenTelemetry provider; transcript content is never a metric
  attribute.

## Local voice UI acceptance fixture

The test-only fixture provides mock banking reads and a real LiveKit data-channel
participant. It does not call Gemini, MCP tools, or banking mutations. With a
LiveKit development server listening on `localhost:7880`, run:

```bash
uv run python scripts/voice_ui_fixture.py
```

In another shell, start `banking-ui` on port 4174 and open
`http://127.0.0.1:4174/support/voice`. Local mock authentication activates when
`fbConfig.js` is absent. Start a consultation and send a typed fraud response.
The fixture acknowledges the message over reliable LiveKit data, echoes it once
through the server transcript event, and then emits confirmed fraud and
replacement events.

Verify all of the following before promotion:

- disconnected state has no composer; connected audio and avatar-fallback do
  have one
- accepted typed text appears exactly once and clears the draft
- fraud progress appears only after the confirmed result event and contains the
  four approved stages
- desktop (1440x900), short laptop (1024x700), tablet (768x1024), and mobile
  (390x844) retain reachable transcript, composer, and consultation controls
- light, dark, system-auto light, and system-auto dark remain legible
- the global chat launcher is absent from the voice route

While connected, simulate a representative joining and verify that the composer
is visibly disabled with the handoff explanation:

```bash
curl -X POST http://127.0.0.1:8080/fixture/handoff
```

For an avatar consultation, simulate decoder loss and confirm that the avatar
panel disappears, the transcript expands, typed input remains enabled, and one
voice-continuation notice appears:

```bash
curl -X POST http://127.0.0.1:8080/fixture/avatar-fallback
```

The fixture uses only the standard LiveKit development key pair and is bound to
loopback. Never expose it or deploy it as an application service.
- Durable ADK recovery retains bounded conversation events, including customer
  and agent transcript content, up to `VOICE_SESSION_MAX_EVENTS` and
  `VOICE_SESSION_TTL_SECONDS` (12 hours by default). Presenter and full resets
  invalidate prior authority immediately even if cleanup has not physically
  removed the row yet.
- An explicit human escalation may additionally copy the bounded in-session
  transcript into the support case. Do not copy transcript bodies into
  operational logs, metric attributes, readiness output, or canary output.

## Rollback

First route traffic to the prior Cloud Run revision. The database additions are
backward compatible and can remain in place. For a proposal-only rollback, set
`VOICE_AGENT_USE_ACTION_PROPOSALS=false` on the ADK service and leave the banking
proposal tables and tools deployed; prepared but uncommitted proposals expire
without mutating banking state. Rehearse one recognized and one disputed case
through the direct path before returning traffic. If a source rollback is required,
restore `google-adk==2.3.0` and its lock file, disable
`VOICE_AGENT_SESSION_RESUMPTION_ENABLED`, and deploy the prior agent image. No
banking or UI rollback is required because MCP and data-channel payloads remain
compatible.
