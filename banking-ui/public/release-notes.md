## ✨ New Features
* **Fraud Mitigation & Triage**: Introduced comprehensive Gemini Live fraud triage flows, MCP tooling for remediation, and Dataplex knowledge catalog guidance for voice support.
* **Advanced Data Generator**: Exposed new direct scenario control surfaces, fraud campaign templates, and travel geography scenarios with persona-aware baselines.
* **Fraud Observability**: Surfaced fraud model risk metrics, alert generation from model decisions, and detailed decision history through the lakehouse.
* **UI Banners & Integration**: Added environmental/feedback banners, requested notification permissions on sign-in, and integrated GCP info button links to CX agents.

## 🐛 Bug Fixes
* **Voice Agent Stability**: Hardened voice flow pacing, isolated voice MCP sessions, and correctly mapped the voice token fraud context.
* **Database & Ledger Race Conditions**: Fixed IAM DB role bootstrap races, isolated ledger appending access, and solved asynchronous full demo resets.
* **UI Previews**: Removed guest account previews and prevented simulation Server-Sent Events (SSE) from holding open database sessions.
* **Data Integration**: Unblocked premium travel offer view reconciliation and added idempotent data-generator pulse admission.

## 📝 Enhancements
* **Refined Styling**: Polished disclosures styling, modal text, menu ordering, and centered buttons on the landing view.
* **Architecture Improvements**: Modularized voice agent prompts and guardrails, and scoped voice agent session states strictly per consultation.
* **Build Info**: Added hyperlinked commit IDs and "built with Cloud Build" annotations for better visibility.
