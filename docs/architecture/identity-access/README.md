# Identity & Access Architecture

This folder documents the authentication and access-control layer that fronts the platform: the custom Identity-Aware Proxy (IAP) sign-in experience and the Cloud Identity Platform (GCIP) blocking functions that enforce who may authenticate.

| Specification | Description |
| :--- | :--- |
| [Custom IAP Login UI (External Identities)](./custom_iap_login_ui.md) | Self-hosted `gcip-iap` + FirebaseUI sign-in page served at `/login`, multi-tenant GCIP configuration, runtime config injection, and deployment gating on `use_external_identities`. |
| [GCIP Blocking Functions](./gcip_blocking_functions.md) | `beforeCreate` / `beforeSignIn` email-domain restriction, Gen2 Cloud Functions deployment, Identity Platform trigger wiring, and least-privilege credential handling. |

Database-access security (operator connectivity to AlloyDB) is documented in [Secure Database Access via IAP SSH Tunnel](../data-platform/iap_ssh_tunnel_database_access.md).
