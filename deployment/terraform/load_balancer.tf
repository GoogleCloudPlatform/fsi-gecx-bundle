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

resource "google_compute_region_network_endpoint_group" "data_generator_neg" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "data-generator-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.data_generator[0].name
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
  timeout_sec           = var.banking_service_timeout_seconds
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
  timeout_sec           = var.banking_service_timeout_seconds
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

resource "google_compute_backend_service" "data_generator_backend" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "data-generator-backend"
  protocol              = "HTTP"
  timeout_sec           = var.banking_service_timeout_seconds
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.data_generator_neg[0].id
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
  timeout_sec           = var.banking_service_timeout_seconds
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
    google_compute_backend_service.data_generator_backend,
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

    path_rule {
      paths   = ["/data-generator", "/data-generator/*"]
      service = google_compute_backend_service.data_generator_backend[0].id
      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }

    path_rule {
      paths   = ["/rtc", "/rtc/*"]
      service = google_compute_backend_service.livekit_backend[0].id
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

resource "google_iap_settings" "data_generator_backend_iap" {
  count = var.deploy_cloud_run_services ? 1 : 0
  name  = "projects/${data.google_project.project.number}/iap_web/compute/services/${google_compute_backend_service.data_generator_backend[0].name}"

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

# LiveKit GCE Network Endpoint Group (NEG) for Port 7880 signaling
resource "google_compute_network_endpoint_group" "livekit_neg" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "livekit-neg"
  network               = google_compute_network.fsi_gecx_vpc.id
  subnetwork            = google_compute_subnetwork.livekit_subnet.id
  default_port          = 7880
  network_endpoint_type = "GCE_VM_IP_PORT"
  zone                  = "us-central1-c"
}

# Bind GCE VM network endpoint to the NEG
resource "google_compute_network_endpoint" "livekit_endpoint" {
  count                  = var.deploy_cloud_run_services ? 1 : 0
  network_endpoint_group = google_compute_network_endpoint_group.livekit_neg[0].name
  instance               = google_compute_instance.livekit_server.name
  port                   = 7880
  ip_address             = google_compute_instance.livekit_server.network_interface[0].network_ip
  zone                   = "us-central1-c"
}

# Health Check for LiveKit Server HTTP status response
resource "google_compute_health_check" "livekit_hc" {
  count = var.deploy_cloud_run_services ? 1 : 0
  name  = "livekit-health-check"
  http_health_check {
    port         = 7880
    request_path = "/"
  }
}

# Cloud Armor Standard Security Policy with rate limiting to protect signaling from flood attacks
resource "google_compute_security_policy" "cloud_armor_policy" {
  count       = var.deploy_cloud_run_services ? 1 : 0
  name        = "livekit-cloud-armor-policy"
  description = "Cloud Armor security policy for LiveKit signaling server"

  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow rule"
  }

  rule {
    action   = "throttle"
    priority = "1000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"

      rate_limit_threshold {
        count        = 120
        interval_sec = 60
      }

      enforce_on_key = "IP"
    }
    description = "Rate limit rule to throttle signaling flood attacks"
  }
}

# Load Balancer Backend Service routing traffic to GCE NEG with Cloud Armor protection policy
resource "google_compute_backend_service" "livekit_backend" {
  count                 = var.deploy_cloud_run_services ? 1 : 0
  name                  = "livekit-backend"
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 300
  security_policy       = google_compute_security_policy.cloud_armor_policy[0].id
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group                 = google_compute_network_endpoint_group.livekit_neg[0].id
    balancing_mode        = "RATE"
    max_rate_per_endpoint = 100
  }

  health_checks = [google_compute_health_check.livekit_hc[0].id]
}
