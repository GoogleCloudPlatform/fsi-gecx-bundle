# FSI Architecture Design: GECX Telephony Voice Agent & Bidi Stream Orchestration

This document details the system architecture, security design, and key implementation gotchas for the real-time **GECX Telephony Voice Agent** using Google Cloud Customer Experience Suite (GECX) bi-directional streaming.

---

## 📐 1. System Topology & Media Flow

The GECX Telephony Voice Agent establishes a low-latency, bidirectional audio streaming connection between the client browser and the Google Cloud Customer Experience Suite Bidi API via the `banking-service` acting as an authenticated proxy.

```mermaid
sequenceDiagram
    autonumber
    actor User as Cardholder (Browser)
    participant Proxy as banking-service Proxy (Cloud Run)
    participant GECX as Google Cloud Customer Experience Suite SessionService (Bidi)
    participant MCP as FastMCP Tool Host (banking-service)
    participant DB as SQL Database

    User->>Proxy: wss://[HOST]/voice/gecx-stream (Connect)
    User->>Proxy: Send AUTH frame { type: "AUTH", token: "[Firebase Token]" }
    Proxy->>Proxy: Validate Firebase Token & Extract User ID (sub)
    Proxy->>Proxy: Mint encrypted, short-lived CES session capability
    
    Proxy->>GECX: wss://ces.googleapis.com/.../BidiRunSession (Connect with OAuth2)
    Proxy->>GECX: Send Config message (input/output audio specs)
    
    %% Session Variables Gotcha Sequence
    Proxy->>GECX: Send Session Variables Frame (realtimeInput.variables)
    Proxy->>GECX: Send Welcome Event Frame (realtimeInput.event: "sys.welcome")
    
    GECX-->>Proxy: GECX welcome greeting audio stream
    Proxy-->>User: Forward welcome greeting audio stream
    
    User->>Proxy: User rejects the suspicious transactions
    Proxy->>GECX: Stream raw PCM audio packets
    
    Note over GECX: GECX Agent processes intent & decides to call tool
    
    GECX->>MCP: POST /mcp/ (Call Tool: propose_fraud_triage)
    Note over MCP: GECX injects x-banking-session-capability and bound session headers
    
    MCP->>MCP: Validate caller Google OIDC Token (Auth Header)
    MCP->>MCP: Decrypt capability; validate expiry, session binding, and reset generation
    MCP-->>GECX: Opaque proposal id + banking-authored summary
    GECX->>GECX: Record presentation only if all material facts match
    GECX-->>User: Present merchants, amounts, card suffix, and actions
    User->>Proxy: Later explicit confirmation
    GECX->>GECX: Classify complete customer utterance
    GECX->>MCP: POST /mcp/ (commit_fraud_triage)
    MCP->>MCP: Validate presentation and confirmation turn evidence
    MCP->>DB: Claim and execute immutable proposal exactly once
    DB-->>MCP: Committed fraud result

    %% OOB UI Sync
    MCP->>Proxy: send_session_event(session_id, fraud outcome and card state)
    Proxy-->>User: Push WebSocket EVENT (Update fraud and card UI)
    
    MCP-->>GECX: HTTP 200 (Success result)
    GECX-->>Proxy: GECX audio stream response from structured commit result
    Proxy-->>User: Forward audio response
```

---

## 🔒 2. Security Architecture & Identity Forwarding

Because GECX operates as a Google-managed cloud agent orchestrator, it must securely call on-premise or custom APIs (like our FastMCP endpoints) on behalf of the active user:

1. **Google OIDC ID Token Verification**: The FastMCP router ensures that invocations come exclusively from Google Cloud Customer Experience Suite services by verifying the Google service account OIDC token in the `Authorization: Bearer <JWT>` header.
2. **Banking-Issued Session Capability (`x-banking-session-capability`)**: The Firebase token terminates at the banking WebSocket gateway and is never sent to CES. After resolving the exact customer and reset generation, banking mints an encrypted 15-minute capability bound to the support session, CES runtime session, reset generation, app, and deployment. CES forwards the opaque capability with those protected headers. The MCP boundary accepts it only from an authorized CES service caller, verifies every binding, and checks the current reset generation before resolving the customer identity.
3. **Transport-Owned Consent Evidence**: CES callbacks, rather than model-authored tool arguments, own the proposal id, presentation turn, confirmation turn, method, and classification headers. Banking-service accepts a commit only when those values describe a later explicit confirmation for the active proposal.

### Protected action callback chain

The `Credit_Card_Support_Agent` callback chain keeps consent state outside the prompt:

1. `capture_proposal.py` records the opaque proposal id and banking-authored summary after `propose_fraud_triage`.
2. `record_presentation.py` records `proposal_presentation_turn_id` only when a completed assistant response asks for confirmation and contains every material fact from the summary. Equivalent written and spoken amounts are accepted; missing or altered merchants, amounts, card suffixes, or actions are rejected.
3. `classify_confirmation.py` classifies only a later customer turn. A bounded whole-utterance affirmative is `CONFIRMED`; negative or qualified language is `DECLINED`; partial or unrelated speech is `UNCLEAR`.
4. `enforce_proposal_context.py` binds an omitted proposal id from callback-owned state and blocks `commit_fraud_triage` unless the presentation turn, later confirmation turn, invocation id, explicit-verbal method, and `CONFIRMED` classification all agree.

The model can attempt a blocked tool call, but the callback returns `PROTECTED_CONFIRMATION_REQUIRED` before the banking or evaluation fake tool executes.

---

## ⚠️ 3. Key Gotchas & Solutions

### A. Session Variables & Welcoming Protocol Union Constraint (The `oneof` Gotcha)
* **The Pitfall**: The Google Cloud Customer Experience Suite `SessionInput` proto message represents input types inside a Protobuf `oneof input_type` union block:
  ```protobuf
  message SessionInput {
    oneof input_type {
      string text = 2;
      ...
      google.protobuf.Struct variables = 8;
      Event event = 9;
    }
  }
  ```
  Sending session variables and triggering the welcome greeting (`sys.welcome` event) in a single consolidated WebSocket message results in an immediate connection termination with code `1007` (`oneof field 'input_type' is already set`).
* **The Solution**: The two payloads must be sent as **two separate, sequential WebSocket frames**:
  1. Write a `realtimeInput` frame containing only the `variables` to seed GECX's session state.
  2. Write a `realtimeInput` frame containing only the `event` to prompt the greeting.

### B. Session Registry Identity Mismatch (Firebase UID vs Database Customer ID)
* **The Pitfall**: The WebSocket proxy session is authenticated via Firebase ID tokens and registers the active audio loop under the Firebase UID (`sub` claim, e.g., `JMZkJxwLgWSaa0YPmB41lmCQc9L2`). However, MCP tools query the SQL database and perform operations based on DB Customer IDs (which fallback to the seed ID `cust-123` for demo purposes). Discarding UI refresh events due to key mismatches results in the UI failing to update in real-time.
* **The Solution**: During WebSocket startup, the proxy queries the database to resolve the customer ID associated with the Firebase UID. It registers the active session under **both** keys in the `active_sessions` registry, ensuring that out-of-band updates sent to either ID are routed to the user's browser UI.

### C. Continuous PCM Is Required

* **The Pitfall**: CES `BidiRunSession` requires audio frames continuously, including during silence. An `AudioWorkletNode` that is not connected to the browser's rendered audio graph may stop processing, causing CES to close the upstream stream near the one-minute boundary. Pausing frames when the microphone is muted has the same effect.
* **The Solution**: Connect the capture worklet to a zero-gain sink and the `AudioContext` destination. Send its PCM frames continuously; while muted, replace microphone samples with zero-valued frames instead of stopping the stream.

### D. Do Not Forward Reusable Credentials Through CES Variables

* **The Pitfall**: CES built-in conversation redaction does not guarantee that a JWT stored in an updated session variable will be de-identified. Forwarding the Firebase ID token therefore risks retaining a reusable credential in managed conversation history.
* **The Solution**: Keep the Firebase credential inside the banking gateway. Send only the encrypted, short-lived session capability described above. A demo reset invalidates the capability immediately, and expiry limits replay even if its opaque value is retained in a trace.

### E. Voice Session and Cloud Run Timeout Headroom

* **The Pitfall**: If the Cloud Run request timeout and CES Bidi session timeout are equal, infrastructure termination can interrupt cleanup, terminal telemetry, and the final audio frames.
* **The Solution**: The banking proxy enforces `VOICE_BIDI_SESSION_TIMEOUT_SECONDS` independently from Cloud Run. The deployment contract requires Cloud Run to retain shutdown headroom beyond the voice session; the current defaults are 600 seconds for the CES session and 720 seconds for the Cloud Run request.

---

## 🧪 4. Trajectory Evaluation and Managed Qualification

Completed CES conversations are normalized into the same event vocabulary as ADK sessions. The checked-in fraud matrix requires one alert read, one proposal, one protected presentation, one later confirmation, one commit, Knowledge Catalog and reset provenance, `fraud-triage.v1`, `PENDING_SPECIALIST_REVIEW`, and normal termination.

Managed CES qualification has two separate resources:

- a generated, sanitized contract replay with strict tool correctness and no conversational-copy claim
- a hand-authored conversational reference that checks branding, complete transaction readout, exactly one protected confirmation, post-remediation wallet guidance, and closeout

Consent-related releases additionally exercise exact confirmation, an affirmative embedded in unrelated speech, and an altered or incomplete proposal presentation. Negative samples pass only when the callback blocks every commit attempt and no fake or real banking commit executes.

See [Agent Trajectory Evaluation Architecture](./agent_trajectory_evaluation.md) for the shared evaluator and evidence model, and [CES Voice Qualification](../../../gecx/Credit_Support_Voice_Agent/evaluations/README.md) for commands and fixture boundaries.
