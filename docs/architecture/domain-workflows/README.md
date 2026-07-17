# Domain Workflow Architecture

This folder documents customer-facing and operations-facing banking workflows. These docs describe how domain journeys move across UI, services, databases, support tools, and AI-assisted experiences.

| Area | Specifications |
| :--- | :--- |
| Origination & Onboarding | [Credit Card Prefill Integration](./origination/credit_card_prefill_integration.md), [Home Loan Preapproval Integration](./origination/home_loan_preapproval_integration.md) |
| Account Servicing & Self-Service | [Cardholder Self-Service & Account Servicing](./servicing/cardholder_self_service.md), [Branch & ATM Locator](./servicing/branch_atm_locator.md) |
| Open Banking & Data Sharing | [FDX v6 Open Banking Integration](./open-banking/fdx_open_banking_integration.md) |
| Customer Support & Messaging | [Secure Messaging Backend Integration](./support/secure_messaging_backend_integration.md), [Live Agent Escalation & Human Handoff](./support/live_agent_escalation.md) |
| Fraud Detection & Remediation | [Fraud Detection Workflow](./fraud/fraud_detection_workflow.md) |

Use this folder for end-to-end business workflows. Put CDC, lakehouse, schema, and analytics platform mechanics in [Data Platform](../data-platform/README.md), and put voice-agent or multimodal integration architecture in [AI & Voice](../ai-and-voice/).
