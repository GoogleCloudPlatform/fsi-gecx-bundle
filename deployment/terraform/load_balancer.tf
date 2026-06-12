# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Data sources for IAP credentials from Secret Manager
data "google_secret_manager_secret_version_access" "iap_client_id" {
  secret  = "iap-client-id"
  version = "latest"
}

data "google_secret_manager_secret_version_access" "iap_client_secret" {
  secret  = "iap-client-secret"
  version = "latest"
}

# Static IP for the Load Balancer
resource "google_compute_global_address" "lb_ip" {
  count = var.deploy_cloud_run_services ? 1 : 0
  name  = "banking-lb-ip"
}

# Managed SSL Certificate
resource "google_certificate_manager_certificate" "lb_cert" {
  count       = var.deploy_cloud_run_services ? 1 : 0
  name        = "banking-lb-cert"
  description = "Cert with LB authorization"
  managed {
    domains = [var.custom_domain]
  }
  depends_on = [google_project_service.certificatemanager_googleapis_com]
}

resource "google_certificate_manager_certificate_map" "lb_cert_map" {
  count      = var.deploy_cloud_run_services ? 1 : 0
  name       = "banking-lb-cert-map"
  depends_on = [google_project_service.certificatemanager_googleapis_com]
}

resource "google_certificate_manager_certificate_map_entry" "lb_cert_map_entry" {
  count        = var.deploy_cloud_run_services ? 1 : 0
  name         = "banking-lb-cert-map-entry"
  map          = google_certificate_manager_certificate_map.lb_cert_map[0].name
  certificates = [google_certificate_manager_certificate.lb_cert[0].id]
  hostname     = var.custom_domain
}

# Serverless NEGs for Cloud Run
resource "google_compute_region_network_endpoint_group" "ui_neg" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "banking-ui-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.banking_ui[0].name
  }
}

resource "google_compute_region_network_endpoint_group" "service_neg" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "banking-service-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.banking_service[0].name
  }
}

resource "google_compute_region_network_endpoint_group" "iap_login_ui_neg" {
  count                 = var.deploy_cloud_run_services && var.use_external_identities ? 1 : 0
  name                  = "iap-login-ui-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = one(google_cloud_run_v2_service.iap_login_ui[*].name)
  }
}

# Backend Services
resource "google_compute_backend_service" "ui_backend" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "banking-ui-backend"
  protocol              = "HTTP"
  timeout_sec           = 30
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.ui_neg[0].id
  }

  iap {
    enabled              = true
    oauth2_client_id     = data.google_secret_manager_secret_version_access.iap_client_id.secret_data
    oauth2_client_secret = data.google_secret_manager_secret_version_access.iap_client_secret.secret_data
  }
}

resource "google_compute_backend_service" "service_backend" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "banking-service-backend"
  protocol              = "HTTP"
  timeout_sec           = 30
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.service_neg[0].id
  }

  iap {
    enabled              = true
    oauth2_client_id     = data.google_secret_manager_secret_version_access.iap_client_id.secret_data
    oauth2_client_secret = data.google_secret_manager_secret_version_access.iap_client_secret.secret_data
  }
}

resource "google_compute_backend_service" "iap_login_ui_backend" {
  count                 = var.deploy_cloud_run_services && var.use_external_identities ? 1 : 0
  name                  = "iap-login-ui-backend"
  protocol              = "HTTP"
  timeout_sec           = 30
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = one(google_compute_region_network_endpoint_group.iap_login_ui_neg[*].id)
  }
}

# START DESTROY AND RECREATE WITH CHANGE OF IAP EXTERNAL TO IAM
# URL Map
resource "google_compute_url_map" "lb_url_map" {
  count           = var.deploy_cloud_run_services ? 1 : 0
  name            = "banking-lb-url-map"
  default_service = google_compute_backend_service.ui_backend[0].id

  depends_on = [
    google_compute_backend_service.ui_backend,
    google_compute_backend_service.service_backend,
    google_compute_backend_service.iap_login_ui_backend
  ]

  host_rule {
    hosts        = [var.custom_domain]
    path_matcher = "allpaths"
  }

  path_matcher {
    name            = "allpaths"
    default_service = google_compute_backend_service.ui_backend[0].id

    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.service_backend[0].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    dynamic "path_rule" {
      for_each = var.use_external_identities ? [1] : []
      content {
        paths   = ["/login", "/login/*"]
        service = one(google_compute_backend_service.iap_login_ui_backend[*].id)
        route_action {
          url_rewrite {
            path_prefix_rewrite = "/"
          }
        }
      }
    }

    dynamic "path_rule" {
      for_each = var.use_external_identities ? [1] : []
      content {
        paths   = ["/__/auth", "/__/auth/*"]
        service = one(google_compute_backend_service.iap_login_ui_backend[*].id)
      }
    }
  }
}

# Target HTTPS Proxy
resource "google_compute_target_https_proxy" "lb_proxy" {
  count           = var.deploy_cloud_run_services ? 1 : 0
  name            = "banking-lb-proxy"
  url_map         = google_compute_url_map.lb_url_map[0].id
  certificate_map = "//certificatemanager.googleapis.com/${google_certificate_manager_certificate_map.lb_cert_map[0].id}"
}

# Global Forwarding Rule
resource "google_compute_global_forwarding_rule" "lb_forwarding_rule" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "banking-lb-forwarding-rule"
  target                = google_compute_target_https_proxy.lb_proxy[0].id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb_ip[0].address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
## END DESTROY

resource "google_iap_settings" "ui_backend_iap" {
  count = var.deploy_cloud_run_services ? 1 : 0
  name  = "projects/${data.google_project.project.number}/iap_web/compute/services/${google_compute_backend_service.ui_backend[0].name}"

  dynamic "access_settings" {
    for_each = var.use_external_identities ? [1] : []
    content {
      gcip_settings {
        tenant_ids     = ["_${data.google_project.project.number}"]
        login_page_uri = "https://${var.custom_domain}/login?apiKey=${data.google_firebase_web_app_config.banking_ui_app_config.api_key}"
      }
    }
  }
}

resource "google_iap_settings" "service_backend_iap" {
  count = var.deploy_cloud_run_services ? 1 : 0
  name  = "projects/${data.google_project.project.number}/iap_web/compute/services/${google_compute_backend_service.service_backend[0].name}"

  dynamic "access_settings" {
    for_each = var.use_external_identities ? [1] : []
    content {
      gcip_settings {
        tenant_ids     = ["_${data.google_project.project.number}"]
        login_page_uri = "https://${var.custom_domain}/login?apiKey=${data.google_firebase_web_app_config.banking_ui_app_config.api_key}"
      }
    }
  }
}

