# Catalog-native compliance and financial journal tables. Namespace and table
# creation is performed by the reproducible audit-iceberg-bootstrap Cloud Run
# job because the Lakehouse REST catalog does not support BigQuery DDL.
resource "google_biglake_iceberg_catalog" "audit_lakehouse" {
  name             = var.audit_iceberg_catalog_id
  project          = var.project_id
  catalog_type     = "CATALOG_TYPE_BIGLAKE"
  credential_mode  = "CREDENTIAL_MODE_VENDED_CREDENTIALS"
  default_location = "gs://${google_storage_bucket.iceberg_warehouse.name}/audit-lakehouse"
  primary_location = "US"
  deletion_policy  = "PREVENT"

  depends_on = [google_project_service.biglake_googleapis_com]
}

resource "google_storage_bucket_iam_member" "audit_catalog_warehouse_object_user" {
  bucket = google_storage_bucket.iceberg_warehouse.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_biglake_iceberg_catalog.audit_lakehouse.biglake_service_account}"
}

resource "google_storage_bucket_iam_member" "audit_dataflow_staging_object_admin" {
  bucket = google_storage_bucket.audit_dataflow_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_storage_bucket_iam_member" "audit_dataflow_warehouse_viewer" {
  bucket = google_storage_bucket.iceberg_warehouse.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_dataflow_worker" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_compute_subnetwork_iam_member" "audit_dataflow_network_user" {
  project    = var.project_id
  region     = var.region
  subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
  role       = "roles/compute.networkUser"
  member     = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_dataflow_biglake_editor" {
  project = var.project_id
  role    = "roles/biglake.editor"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_dataflow_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_dataflow_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_processing_dataproc_worker" {
  project = var.project_id
  role    = "roles/dataproc.worker"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_processing_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_processing_bigquery_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_project_iam_member" "audit_processing_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_artifact_registry_repository_iam_member" "audit_dataflow_artifact_reader" {
  repository = google_artifact_registry_repository.fsi_gecx_bundle.id
  location   = var.region
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.audit_iceberg_dataflow_service_account.email}"
}

resource "google_service_account_iam_member" "terraform_cloudbuild_can_run_audit_dataflow" {
  service_account_id = google_service_account.audit_iceberg_dataflow_service_account.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cloudbuild_terraform_service_account.email}"
}
