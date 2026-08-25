# AI, Multimodal & Voice Architecture

This folder documents the Google Cloud AI integrations: conversational voice agents, multimodal document extraction, and knowledge retrieval surfaces.

| Specification | Description |
| :--- | :--- |
| [Gemini Multimodal Live Voice Agent](./gemini_live_voice_agent.md) | Bidirectional WebSocket voice streaming, PyTorch CPU optimization, and real-time tool orchestration with Gemini Live. |
| [GECX Telephony Voice Agent](./gecx_telephony_voice_agent.md) | Customer Experience Suite Bidi audio proxy, session capability, callback-owned consent, and managed conversational workflows. |
| [Gemini Enterprise BigQuery A2A](./gemini_enterprise_bigquery_a2a.md) | Environment-local Gemini Enterprise apps, A2A routing to the governed BigQuery DataAgent, OAuth delegation, and promotion boundaries. |
| [Runtime-Neutral Banking Action Proposal/Commit Protocol](./runtime_neutral_action_proposal_protocol.md) | Shared ADK/CES authorization boundary, trusted runtime evidence, immutable banking proposals, and exactly-once consequential commits. |
| [Agent Trajectory Evaluation](./agent_trajectory_evaluation.md) | Runtime-neutral ADK/CES event model, release evidence layers, typed-decision samples, and trajectory qualification commands. |
| [Document AI Processing Pipeline](./doc_ai_processing_pipeline.md) | Asynchronous OCR and structured entity extraction for W-2 tax forms, paystubs, and bank statements. |
| [Enterprise Search & Generative Answers](./enterprise_search_and_answers.md) | Vertex AI Discovery Engine ranked search and grounded conversational answers over the bank's published content. |
| [Search Content Ingestion Pipeline](./search_content_ingestion_pipeline.md) | Playwright crawler that renders the banking UI from its sitemap, uploads content to GCS, and imports a document manifest into the Discovery Engine datastore. |

Business workflow behavior belongs in [Domain Workflows](../domain-workflows/README.md). Data platform, CDC, and lakehouse mechanics belong in [Data Platform](../data-platform/README.md).
