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

output "banking_interaction_artifacts_bucket" {
  value = google_storage_bucket.banking_interaction_artifacts.name
}

output "ccai_insights_artifacts_bucket" {
  value = google_storage_bucket.ccai_insights_artifacts.name
}

output "load_balancer_ip" {
  value       = var.deploy_cloud_run_services ? google_compute_global_address.lb_ip[0].address : null
  description = "The static IP address of the external load balancer."
}

output "region" {
  value = var.region
}

output "docai_splitter_processor_id" {
  value       = google_document_ai_processor.master_splitter.id
  description = "The ID of the Document AI Master Splitter processor."
}

output "docai_w2_processor_id" {
  value       = google_document_ai_processor.w2_extractor.id
  description = "The ID of the Document AI W-2 Extractor processor."
}

output "docai_paystub_processor_id" {
  value       = google_document_ai_processor.paystub_extractor.id
  description = "The ID of the Document AI Paystub Extractor processor."
}

output "docai_bank_statement_processor_id" {
  value       = google_document_ai_processor.bank_statement_extractor.id
  description = "The ID of the Document AI Bank Statement Extractor processor."
}

output "banking_service_uri" {
  value = var.deploy_cloud_run_services == true ? google_cloud_run_v2_service.banking_service[0].urls[0] : null
}

output "banking_ui_uri" {
  value = var.deploy_cloud_run_services == true ? google_cloud_run_v2_service.banking_ui[0].urls[0] : null
}
