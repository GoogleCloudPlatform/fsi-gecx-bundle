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

# 1. Pub/Sub Service Identity for CMEK KMS decryption authorization
resource "google_project_service_identity" "pubsub_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "pubsub.googleapis.com"
}

resource "google_kms_crypto_key_iam_member" "pubsub_kms_binding" {
  crypto_key_id = google_kms_crypto_key.docai_cmek_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_project_service_identity.pubsub_sa.email}"
}

# 2. Manual Underwriting Exception Queue: Pub/Sub DLQ Topic & Subscription
resource "google_pubsub_topic" "manual_underwriting_review_dlq" {
  name         = "manual-underwriting-review-dlq"
  project      = var.project_id
  kms_key_name = google_kms_crypto_key.docai_cmek_key.id

  depends_on = [google_kms_crypto_key_iam_member.pubsub_kms_binding]
}

resource "google_pubsub_subscription" "manual_underwriting_review_dlq_sub" {
  name    = "manual-underwriting-review-dlq-sub"
  topic   = google_pubsub_topic.manual_underwriting_review_dlq.name
  project = var.project_id

  message_retention_duration = "604800s" # 7 days message retention
  retain_acked_messages      = false
  ack_deadline_seconds       = 60
}

# 3. Manual Underwriting Exception Queue: Primary Topic & Subscription
resource "google_pubsub_topic" "manual_underwriting_review" {
  name         = "manual-underwriting-review"
  project      = var.project_id
  kms_key_name = google_kms_crypto_key.docai_cmek_key.id

  depends_on = [google_kms_crypto_key_iam_member.pubsub_kms_binding]
}

resource "google_pubsub_subscription" "manual_underwriting_review_sub" {
  name    = "manual-underwriting-review-sub"
  topic   = google_pubsub_topic.manual_underwriting_review.name
  project = var.project_id

  ack_deadline_seconds = 60

  # Exponential Backoff Retry Policy
  retry_policy {
    minimum_backoff = "5s"
    maximum_backoff = "600s"
  }

  # Dead Letter Policy routing failed human-review messages to DLQ
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.manual_underwriting_review_dlq.id
    max_delivery_attempts = 5
  }

  depends_on = [
    google_pubsub_topic.manual_underwriting_review_dlq
  ]
}

# 4. IAM Authorizations: Grant banking-service-sa publishing bounds
resource "google_pubsub_topic_iam_member" "banking_service_sa_publisher" {
  topic   = google_pubsub_topic.manual_underwriting_review.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
  project = var.project_id
}
