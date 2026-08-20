# Current Release

## ✨ Runtime-Neutral Voice Actions

* **Consistent action confirmation**: ADK and CES voice agents now use the same proposal-and-confirmation protocol for fraud triage, card replacement, and Google Wallet provisioning.
* **Natural conversations with guarded execution**: Customers can ask questions, revise a request, decline, or confirm later without relying on exact confirmation phrases. Banking actions execute only after a typed decision and trusted later-turn evidence.
* **Reliable retries**: Immutable proposal identifiers, durable results, and exactly-once execution prevent duplicate banking actions when a response or connection is interrupted.

## 🐛 Voice Reliability

* **CES session closeout**: Added a guarded farewell handoff and native session termination, with terminal audio draining before the browser disconnects.
* **Authoritative Wallet status**: Voice agents report Google Wallet provisioning as queued only after the banking service confirms the request.
* **Runtime parity checks**: Added shared ADK/CES trajectory qualification, negative-path coverage, and release metadata gates for safer promotion and rollback.

## 🛠️ Architecture and Operations

* **Reusable proposal kernel**: Extracted lifecycle, authorization policy, evidence validation, and typed action specifications from the individual agent runtimes.
* **CES reproducibility**: Agent deployment now materializes its generated MCP toolset, and local SCRAPI tooling supports repeatable bundle and closeout evaluation.
* **Documented workflow**: Added an end-to-end architecture guide for proposal creation, presentation, typed decisions, exactly-once commit, recovery, and runtime ownership.

---

# Earlier Updates

## Week of July 27

* **Analytics**: Enabled Google Analytics throughout the application interaction areas.

## Week of July 20

### ✨ New Features

* **Fraud Mitigation & Triage**: Introduced comprehensive Gemini Live fraud triage flows, MCP tooling for remediation, and Dataplex knowledge catalog guidance for voice support.
* **Advanced Data Generator**: Exposed new direct scenario control surfaces, fraud campaign templates, and travel geography scenarios with persona-aware baselines.
* **Fraud Observability**: Surfaced fraud model risk metrics, alert generation from model decisions, and detailed decision history through the lakehouse.
* **UI Banners & Integration**: Added environmental/feedback banners, requested notification permissions on sign-in, and integrated GCP info button links to CX agents.

### 🐛 Bug Fixes

* **Voice Agent Stability**: Hardened voice flow pacing, isolated voice MCP sessions, and correctly mapped the voice token fraud context.
* **Database & Ledger Race Conditions**: Fixed IAM DB role bootstrap races, isolated ledger appending access, and solved asynchronous full demo resets.
* **UI Previews**: Removed guest account previews and prevented simulation Server-Sent Events (SSE) from holding open database sessions.
* **Data Integration**: Unblocked premium travel offer view reconciliation and added idempotent data-generator pulse admission.

### 📝 Enhancements

* **Refined Styling**: Polished disclosures styling, modal text, menu ordering, and centered buttons on the landing view.
* **Architecture Improvements**: Modularized voice agent prompts and guardrails, and scoped voice agent session states strictly per consultation.
* **Build Info**: Added hyperlinked commit IDs and "built with Cloud Build" annotations for better visibility.
