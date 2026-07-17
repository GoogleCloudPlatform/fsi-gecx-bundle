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
