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

moved {
  from = google_bigquery_dataset.iceberg_catalog
  to   = google_bigquery_dataset.oltp_cdc
}

moved {
  from = google_bigquery_dataset_iam_member.database_viewer_iceberg_catalog_data_viewer
  to   = google_bigquery_dataset_iam_member.database_viewer_oltp_cdc_data_viewer
}

moved {
  from = google_bigquery_dataset_iam_member.reporting_iceberg_data_editor
  to   = google_bigquery_dataset_iam_member.reporting_oltp_cdc_data_editor
}

moved {
  from = google_bigquery_dataset_iam_member.banking_service_iceberg_data_editor
  to   = google_bigquery_dataset_iam_member.banking_service_oltp_cdc_data_editor
}

moved {
  from = google_bigquery_dataset_iam_member.lakehouse_reconcile_iceberg_data_viewer
  to   = google_bigquery_dataset_iam_member.lakehouse_reconcile_oltp_cdc_data_viewer
}
