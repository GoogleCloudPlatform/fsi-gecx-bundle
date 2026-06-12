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

resource "time_sleep" "wait_for_kms_propagation" {
  depends_on = [
    google_kms_crypto_key_iam_member.docai_kms_binding
  ]
  create_duration = "30s"
}

resource "google_document_ai_processor" "master_splitter" {
  location     = var.docai_location
  type         = "CUSTOM_SPLITTING_PROCESSOR"
  display_name = "Master Lending Splitter"
  kms_key_name = google_kms_crypto_key.docai_cmek_key.id

  depends_on = [
    google_project_service.documentai_googleapis_com,
    time_sleep.wait_for_kms_propagation
  ]
}

resource "google_document_ai_processor_default_version" "master_splitter_version" {
  processor = google_document_ai_processor.master_splitter.id
  version   = "${google_document_ai_processor.master_splitter.id}/processorVersions/pretrained-splitter-v1.5-2025-07-14"
}

resource "google_document_ai_processor" "w2_extractor" {
  location     = var.docai_location
  type         = "FORM_W2_PROCESSOR"
  display_name = "Pre-trained W2 Extractor"
  kms_key_name = google_kms_crypto_key.docai_cmek_key.id

  depends_on = [
    google_project_service.documentai_googleapis_com,
    time_sleep.wait_for_kms_propagation
  ]
}

resource "google_document_ai_processor_default_version" "w2_extractor_version" {
  processor = google_document_ai_processor.w2_extractor.id
  version   = "${google_document_ai_processor.w2_extractor.id}/processorVersions/pretrained-w2-v2.1-2022-06-08"
}

resource "google_document_ai_processor" "paystub_extractor" {
  location     = var.docai_location
  type         = "PAYSTUB_PROCESSOR"
  display_name = "Pre-trained Paystub Extractor"
  kms_key_name = google_kms_crypto_key.docai_cmek_key.id

  depends_on = [
    google_project_service.documentai_googleapis_com,
    time_sleep.wait_for_kms_propagation
  ]
}

resource "google_document_ai_processor_default_version" "paystub_extractor_version" {
  processor = google_document_ai_processor.paystub_extractor.id
  version   = "${google_document_ai_processor.paystub_extractor.id}/processorVersions/pretrained-paystub-v3.0-2023-12-06"
}

resource "google_document_ai_processor" "bank_statement_extractor" {
  location     = var.docai_location
  type         = "BANK_STATEMENT_PROCESSOR"
  display_name = "Pre-trained Bank Statement Extractor"
  kms_key_name = google_kms_crypto_key.docai_cmek_key.id

  depends_on = [
    google_project_service.documentai_googleapis_com,
    time_sleep.wait_for_kms_propagation
  ]
}

resource "google_document_ai_processor_default_version" "bank_statement_extractor_version" {
  processor = google_document_ai_processor.bank_statement_extractor.id
  version   = "${google_document_ai_processor.bank_statement_extractor.id}/processorVersions/pretrained-bankstatement-v5.0-2023-12-06"
}

resource "google_project_iam_member" "banking_service_docai_user" {
  project = data.google_project.project.project_id
  role    = "roles/documentai.apiUser"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}
