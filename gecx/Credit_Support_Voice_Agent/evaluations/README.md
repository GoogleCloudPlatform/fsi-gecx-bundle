# CES Voice Qualification

The architectural model shared with the ADK runtime is documented in
[Agent Trajectory Evaluation Architecture](../../../docs/architecture/ai-and-voice/agent_trajectory_evaluation.md).

`ces_fraud_qualification_matrix.json` defines the bounded CES fraud contract,
question, decline, and revise trajectories. The runner:

1. reads a named CES live conversation through the CES API
2. normalizes it into the shared ADK/CES trajectory vocabulary
3. checks runtime, version, catalog, proposal, confirmation, commit, banking,
   and terminal invariants
4. optionally creates a sanitized CES `GOLDEN`-type contract replay and runs
   it against a named app version
5. separately runs the hand-curated conversational reference in
   `ces_fraud_conversational_reference.json`

Run it from the repository root:

```bash
./adk-agent/credit-support-agent/.venv/bin/python \
  scripts/cxas/ces_voice_qualification.py \
  --project PROJECT_ID \
  --account ACCOUNT \
  --app projects/PROJECT_ID/locations/us/apps/APP_ID \
  --latest \
  --app-version projects/PROJECT_ID/locations/us/apps/APP_ID/versions/VERSION_ID \
  --managed \
  --output /tmp/ces-qualification.json
```

`--latest` selects the newest completed conversation whose CES source is
`LIVE`. It ignores evaluation conversations and live conversations that have
not ended. To evaluate a specific recorded consultation instead, replace
`--latest` with its full `--conversation` resource name.

The persisted report contains resource provenance and aggregate metrics only.
It never includes tool arguments, transcripts, session capabilities, customer
identifiers, or raw tool responses. The generated contract fixture is curated
before storage to remove live credentials and ephemeral customer/session state.

CES calls both stable-replay resources `GOLDEN` evaluations. In this repository,
only the hand-authored conversational reference is approved copy. A captured
live trace is never promoted to conversational gold merely because its
workflow contract passed.

## Evaluation Boundary

The CES contract replay gates exact tool selection and rejects missing or extra
tool calls. Its semantic threshold is intentionally zero because the replay
exists only to pin the workflow shape. It must never be used as evidence that
the wording or customer experience passed.

The conversational reference uses a semantic threshold of 2 and additional
deterministic checks over observed agent responses. It rejects:

- incorrect or missing Nova Horizon Bank branding
- phone/calling terminology in the in-app web voice session
- omission of any flagged merchant or exact amount in the initial readout
- more or fewer than one protected proposal confirmation

Its reference trajectory also verifies that the consultation remains open
after fraud remediation, answers an immediate-card-access question, queues the
virtual replacement for Google Wallet only after customer agreement, and then
closes on a later customer turn.

Conversation grounding and banking truth are not waived. They are checked
against the real live-audio conversation by the shared trajectory evaluator:

- native `CES_GEMINI_LIVE` runtime and saved app version
- reset generation and Knowledge Catalog provenance
- one alert read, one proposal, and one commit
- complete review before proposal
- one later protected confirmation
- `fraud-triage.v1`
- `PENDING_SPECIALIST_REVIEW`
- normal session termination

The fake toolset configuration is active only when an evaluation run explicitly
selects fake tool behavior. Live sessions continue to call the authenticated
banking MCP service.

## Typed-decision sample set

Changes to proposal capture, customer-decision handling, or commit enforcement
require varied managed samples against the saved app version:

| Sample | Expected result |
| :--- | :--- |
| Clear acceptance | A later customer turn causes the model to choose typed commit and exactly one fake commit succeeds. |
| Question or uncertainty | The model answers or clarifies without choosing a decision tool; no fake commit span is present. |
| Qualified or unrelated response | The model does not choose commit. A structurally invalid attempt is rejected before fake execution. |
| Decline or changed scope | The model chooses typed `DECLINE`, `REVISE`, or `CANCEL`; the old proposal becomes terminal and revision requires a new immutable proposal. |

The model's typed tool choice is the one semantic decision. Callbacks validate
opaque proposal state, action type, and protected turn ordering without reading
transcript words. Inspect the evaluation conversation:

- a negative sample has no successful commit response or `COMMITTED` state
- no `FakeTool: banking_service_mcp_toolset_commit_fraud_triage` span exists
  unless the expected typed decision is commit
- questions preserve the pending proposal without manufacturing another gate

Stable replay injects prior golden responses and variable updates into later
turns. Curate protected identifiers and reusable credentials out of fixtures;
do not use saved transcript wording as authorization state.

An app overwrite can remove app-level evaluations and datasets. After importing
a new bundle, rerun the managed qualification to recreate the contract replay
and conversational reference before running these typed-decision samples.
