# Web Experience & Client Instrumentation

This folder documents the browser-side concerns of the `banking-ui` single-page application: how the client is configured at runtime, and how user behavior is measured.

| Specification | Description |
| :--- | :--- |
| [Google Analytics Instrumentation (Banking UI)](./google_analytics_banking_ui.md) | Firebase Analytics / GA4 bootstrap and runtime config injection, SPA `page_view` emission, the `select_content` interaction taxonomy, two-layer click capture with `AnalyticsButton` / `AnalyticsLink`, and user-ID binding. |

The sign-in surfaces that feed the `login` event are documented in [Identity & Access](../identity-access/README.md). The platform's server-side analytics estate — CDC, the Iceberg lakehouse, and BigQuery OLAP — is separate from this client-side GA4 stream and lives in [Data Platform](../data-platform/README.md).
