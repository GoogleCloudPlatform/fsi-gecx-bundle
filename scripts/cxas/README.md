# CX Agent Studio tooling

This directory contains deployment, qualification, and simulation utilities for
the repository's Customer Experience Suite (CES/CX Agent Studio) agents.

## SCRAPI's role

[`cxas-scrapi`](https://github.com/GoogleCloudPlatform/cxas-scrapi) complements
the repository's managed CES evaluations and live-trajectory qualification. It
can load an entire agent, start real CES Sessions API conversations, simulate a
customer, and judge behavior without requiring a manual microphone session.

SCRAPI is not an offline CES emulator. Its simulations call Google Cloud and
therefore require valid Application Default Credentials, access to the target
app, and model quota. A successful simulation does not deploy or overwrite the
agent.

The repository currently uses SCRAPI for:

- repeatable Gemini Live audio coverage across parent/child agent handoffs
- focused closeout checks around spoken farewell and `end_session` ordering
- broader workflow diagnostics with fake tools
- advisory bundle and prompt review

The managed evaluator in `ces_voice_qualification.py` remains authoritative for
exact agent-role and event-order assertions. Recorded live trajectories remain
authoritative for deployed transport, banking outcomes, and runtime provenance.

## Installation and authentication

The SCRAPI dependency is pinned in `requirements-scrapi.txt` and installed in a
separate ignored virtual environment. It does not enter the banking service or
agent runtime dependency graphs.

```bash
make setup-cxas-scrapi
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID
```

Re-running the setup target is safe. Override `SCRAPI_VENV` if the default
`scripts/cxas/.venv` path is unsuitable.

Local reports are written beneath the explicitly ignored
`scripts/cxas/.artifacts/` directory. Remove all reports, transcripts, and
traces in that dedicated directory with:

```bash
make clean-cxas-scrapi
```

The cleanup command does not remove the SCRAPI virtual environment or files
outside that fixed artifact directory.

## Closeout simulation

The default command evaluates the current Agent Studio draft through a single
bidirectional audio stream. The simulated customer declines further help, CES
performs the support-to-closeout handoff, and tool fakes prevent real banking
mutations.

```bash
make test-cxas-closeout \
  PROJECT_ID=PROJECT_ID \
  GECX_APP_ID=APP_ID
```

The focused contract requires:

1. A short spoken farewell after the final customer turn.
2. A `complete_consultation(reason="customer_query_ended")` intent after the
   farewell, converted by an after-model callback into a farewell-only completed
   turn.
3. After simulated or browser-confirmed playout, a before-model callback emits
   native `end_session(reason="customer_query_ended")` without invoking Gemini.
4. A native CES `EndSession` terminal signal.
5. No transfer back to the credit-card support agent.
6. No speech after `end_session`.
7. CES telemetry shows enough generated closeout audio to plausibly contain the
   full farewell. The conservative lower bound is 175 milliseconds per spoken
   word, with a 500 millisecond floor.

For audio simulations, the harness enables SCRAPI's simulated-playback wait and
retrieves the completed CES conversation trace. After SCRAPI's simulated
playback wait, the harness sends `closeout_playout_complete` on the same
session and verifies provider-side farewell generation plus native terminal
ordering. Proxy and banking UI tests cover outbound WebSocket flush, real
browser playout acknowledgment, the terminal event, and CES `EndSession`.

Useful overrides:

```bash
# Exercise a named immutable deployment instead of the draft.
make test-cxas-closeout \
  PROJECT_ID=PROJECT_ID \
  GECX_APP_ID=APP_ID \
  SCRAPI_DEPLOYMENT_ID=DEPLOYMENT_ID

# Exercise the credit-limit workflow before closeout.
make test-cxas-closeout \
  PROJECT_ID=PROJECT_ID \
  GECX_APP_ID=APP_ID \
  SCRAPI_SCENARIO=credit-limit

# Use text transport or choose a different local report path.
make test-cxas-closeout \
  PROJECT_ID=PROJECT_ID \
  GECX_APP_ID=APP_ID \
  SCRAPI_MODALITY=text \
  SCRAPI_OUTPUT=scripts/cxas/.artifacts/text-closeout.json
```

Supported scenarios are `checkpoint` and `credit-limit`; supported modalities
are `audio` and `text`. Audio is the default because closeout correctness
includes whether the farewell is available to the voice response before the
terminal tool call.

## Reports and data handling

SCRAPI reports are local diagnostics and include a transcript and detailed
trace. The Make target writes `scripts/cxas/.artifacts/closeout.json` by default,
and `.gitignore` excludes the entire artifact directory. Keep custom output
paths inside that directory, and do not treat the reports as sanitized
qualification artifacts. Use `ces_voice_qualification.py` when retainable,
bounded evidence is required.

## Linting boundary

`cxas lint` and `cxas llm-lint` are useful during prompt and bundle review, but
they are advisory rather than merge gates. The repository's CES YAML export can
produce format false positives when read directly, and SCRAPI's canonical pull
can still report naming, schema, and guardrail findings that do not represent
runtime failures. Review each finding against the exported agent and the
focused contract tests before changing production behavior.

Do not respond to generic LLM-lint hardening suggestions by expanding a
single-purpose agent's scope. For the session closeout agent, the relevant
contract is deliberately narrow: speak one farewell, select
`complete_consultation` without more speech, finish that turn, and let the
playout-complete callback emit native `end_session` separately.

## Related evaluation layers

- `ces_voice_qualification.py`: managed replay and retainable qualification
- `gecx/Credit_Support_Voice_Agent/evaluations/`: checked-in CES matrices and
  conversational references
- `docs/architecture/ai-and-voice/agent_trajectory_evaluation.md`: shared ADK
  and CES evaluation architecture
