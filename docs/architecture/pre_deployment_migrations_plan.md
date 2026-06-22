# Architectural Plan: Pre-Deployment Migration Isolation (Cloud Run Jobs)

This document outlines the design, architecture, and step-by-step execution plan to transition the FSI GECX backend database migrations to a **pre-deployment isolated job pattern**. 

It implements the **Principle of Least Privilege** (splitting database DDL/DML roles) and utilizes **Google Cloud Run Jobs** orchestrated by **Cloud Build** to guarantee zero-downtime, schema-safe deployments.

---

## 📐 1. Target Architecture

```
                       ┌──────────────────────────────┐
                       │   Google Cloud Build (CD)    │
                       └──────────────┬───────────────┘
                                      │
                         1. Execute Migration Job
                                      ▼
                       ┌──────────────────────────────┐
                       │     Cloud Run Job (DDL)      │
                       └──────────────┬───────────────┘
                                      │ (High Privileges: CREATE/ALTER)
                                      ▼
┌──────────────┐       ┌──────────────────────────────┐
│  Cloud Run   │◄──────┤    Cloud SQL (PostgreSQL)    │
│  App (DML)   │       └──────────────────────────────┘
└──────────────┘         (Restricted Privileges: SELECT/INSERT/UPDATE)
```

### Key Components:
1.  **DDL Database User (`banking_migration`)**: Owner of the database. Has full privileges to create, alter, and drop tables/indexes. Only used by the short-lived Cloud Run Migration Job.
2.  **DML Database User (`banking_runtime`)**: Restricted user. Has read/write permissions on table data, but is blocked from executing DDL statements. Used by the FastAPI web service.
3.  **Cloud Run Migration Job**: A short-lived task running our backend image, executing the database schema migrations (`alembic upgrade head`), and terminating immediately.
4.  **Orchestrated CD Pipeline**: Cloud Build will trigger and block on the Migration Job. If it fails, the pipeline halts immediately, preventing broken code from reaching the application servers.

---

## 🛠️ 2. Execution Steps

### Phase 1: Database Privilege Splitting (SQL & Terraform)

We need to modify the PostgreSQL initialization scripts and Terraform configurations to provision two distinct database users with least-privilege roles.

1.  **Modify `deployment/terraform/sql.tf`**:
    *   Remove the single `google_sql_user.banking_user` resource.
    *   Provision two distinct users:
        ```hcl
        # Owner / Migration User (DDL)
        resource "google_sql_user" "db_migration_user" {
          name     = "banking_migration"
          instance = google_sql_database_instance.banking_data.name
          password = random_password.db_migration_password.result
        }

        # Runtime Application User (DML Only)
        resource "google_sql_user" "db_runtime_user" {
          name     = "banking_runtime"
          instance = google_sql_database_instance.banking_data.name
          password = random_password.db_runtime_password.result
        }
        ```
2.  **Schema Privilege Granting**:
    Add a post-creation SQL script or SQL execution block during database seeding to grant strict DML-only permissions on the `public` schema to the `banking_runtime` user:
    ```sql
    -- Executed as Owner (banking_migration)
    REVOKE ALL ON SCHEMA public FROM public;
    GRANT USAGE, CREATE ON SCHEMA public TO banking_migration;

    -- Grant read/write but block DDL schema modifications
    GRANT USAGE ON SCHEMA public TO banking_runtime;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO banking_runtime;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO banking_runtime;
    ```

---

### Phase 2: Provision Cloud Run Job (Terraform)

We will define the Cloud Run Job inside `deployment/terraform/cloud_run_v2.tf`. This job will execute the migration steps.

1.  **Define `google_cloud_run_v2_job`**:
    ```hcl
    resource "google_cloud_run_v2_job" "db_migration_job" {
      name     = "banking-db-migrate"
      location = var.region

      template {
        template {
          containers {
            image = "us-central1-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
            
            # Override default CMD to run migration steps directly
            command = ["alembic", "upgrade", "head"]

            env {
              name = "DATABASE_URL"
              value_source {
                secret_key_ref {
                  secret  = google_secret_manager_secret.db_migration_url.id
                  version = "latest"
                }
              }
            }
          }
          
          vpc_access {
            connector = google_vpc_access_connector.connector.id
            egress    = "PRIVATE_RANGES_ONLY"
          }
        }
      }
    }
    ```

---

### Phase 3: Restrict FastAPI App Service (Terraform)

Modify the environment variables of the runtime web service (`google_cloud_run_v2_service.banking_service`) to point to the restricted `db_runtime_password` connection string instead of the owner string.

1.  **Update Secret Manager References**:
    *   Ensure `banking_service` mounts the `db_runtime_url` secret for its `DATABASE_URL` env variable.
2.  **Remove migration invocation from startup script**:
    *   In the FastAPI runtime, we can revert `Dockerfile` back to starting `uvicorn` directly, or simplify `run.sh` to skip migrations entirely. The app container will no longer need `alembic` installed at runtime (though keeping it in the image is fine for the Job to reuse).

---

### Phase 4: Cloud Build Pipeline Orchestration

We will update the backend deployment trigger configuration (`cloudbuild-publish-deploy.yaml`) to orchestrate the pre-deployment flow.

1.  **Edit `banking-service/cloudbuild-publish-deploy.yaml`**:
    ```yaml
    steps:
      # Step 1: Compile and Push Container Image (as usual)
      - name: "gcr.io/cloud-builders/docker"
        id: "build-image"
        # ... standard build blocks ...

      # Step 2: Trigger Cloud Run Migration Job and block until success
      - name: "gcr.io/google.com/cloudsdktool/cloud-sdk"
        id: "run-migrations"
        entrypoint: "bash"
        args:
          - "-c"
          - |
            echo "Executing pre-deployment database migrations..."
            gcloud run jobs execute banking-db-migrate \
              --region="${_REGION}" \
              --wait
            echo "Migrations completed successfully!"

      # Step 3: Deploy FastAPI Service (only triggered if Step 2 succeeds)
      - name: "gcr.io/google.com/cloudsdktool/cloud-sdk"
        id: "deploy-service"
        entrypoint: "bash"
        args:
          - "-c"
          - |
            gcloud run deploy banking-service \
              --image="${_REGION}-docker.pkg.dev/$PROJECT_ID/fsi-gecx-bundle/banking-service:$${COMMIT_SHA}" \
              --region="${_REGION}"
    ```

---

## 🧪 3. Rollback & Migration Safety Strategy

### Zero-Downtime Migration Rule:
All database migrations **must be backward-compatible** (often referred to as the **Expand/Contract** phase).
*   **Expansion (Deploy Phase 1)**: Add columns, tables, or indexes. The old app container version will ignore these new fields, while the new app container version can read them.
*   **Contraction (Deploy Phase 2)**: Once the old app version is fully decommissioned, a subsequent deployment can run a migration to drop old columns or tables.

### Rollback Process:
If the Cloud Run Migration Job fails:
1.  **Automatic Pipeline Halt**: Cloud Build halts immediately on Step 2.
2.  **Zero Service Impact**: Because the application deployment (Step 3) was never reached, your active web servers continue running the older, healthy container version against the unaffected database. No traffic is dropped.
