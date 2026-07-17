# AI, Multimodal & Voice Architecture

This folder documents the Google Cloud AI integrations: conversational voice agents, multimodal document extraction, and knowledge retrieval surfaces.

| Specification | Description |
| :--- | :--- |
| [Gemini Multimodal Live Voice Agent](./gemini_live_voice_agent.md) | Bidirectional WebSocket voice streaming, PyTorch CPU optimization, and real-time tool orchestration with Gemini Live. |
| [GECX Telephony Voice Agent](./gecx_telephony_voice_agent.md) | Google Enterprise Contact Center Experience (GECX) integration, SIP telephony bridging, and conversational customer support workflows. |
| [Document AI Processing Pipeline](./doc_ai_processing_pipeline.md) | Asynchronous OCR and structured entity extraction for W-2 tax forms, paystubs, and bank statements. |
| [Enterprise Search & Generative Answers](./enterprise_search_and_answers.md) | Vertex AI Discovery Engine ranked search and grounded conversational answers over the bank's published content. |
| [Search Content Ingestion Pipeline](./search_content_ingestion_pipeline.md) | Playwright crawler that renders the banking UI from its sitemap, uploads content to GCS, and imports a document manifest into the Discovery Engine datastore. |

Business workflow behavior belongs in [Domain Workflows](../domain-workflows/README.md). Data platform, CDC, and lakehouse mechanics belong in [Data Platform](../data-platform/README.md).
