# CES Voice Qualification

`ces_fraud_qualification_matrix.json` defines the first bounded CES
qualification case. The runner:

1. reads a named CES live conversation through the CES API
2. normalizes it into the shared ADK/CES trajectory vocabulary
3. checks runtime, version, catalog, proposal, confirmation, commit, banking,
   and terminal invariants
4. optionally creates a sanitized CES golden evaluation and runs stable replay
   against a named app version

Run it from the repository root:

```bash
./adk-agent/credit-support-agent/.venv/bin/python \
  scripts/cxas/ces_voice_qualification.py \
  --project PROJECT_ID \
  --account ACCOUNT \
  --app projects/PROJECT_ID/locations/us/apps/APP_ID \
  --conversation projects/PROJECT_ID/locations/us/apps/APP_ID/conversations/CONVERSATION_ID \
  --app-version projects/PROJECT_ID/locations/us/apps/APP_ID/versions/VERSION_ID \
  --managed \
  --output /tmp/ces-qualification.json
```

The persisted report contains resource provenance and aggregate metrics only.
It never includes tool arguments, transcripts, session capabilities, customer
identifiers, or raw tool responses. The generated CES golden is also curated
before storage to remove live credentials and ephemeral customer/session state.

## Evaluation Boundary

The CES managed replay gates exact tool selection and rejects missing or extra
tool calls. Its MCP fake-tool payload is not exposed to CES semantic and
hallucination metrics as grounded output parameters, so those two metrics are
disabled for this evaluation only.

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
