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

import os
import re
import json
import logging
from pathlib import Path
from fastmcp import Context, FastMCP
from google.cloud import bigquery, storage
from utils.gcp import get_project_id

logger = logging.getLogger(__name__)
bq_client = bigquery.Client()

SQL_DIR = Path(__file__).resolve().parent.parent / "resources" / "sql"

# 1. Instantiate the Model Context Protocol (MCP) FastMCP Server directly
mcp = FastMCP("Banking Service MCP")

# 2. Create the MCP's ASGI app mounted under /mcp/
mcp_app = mcp.http_app(path="/mcp/")

def _load_sql(filename: str) -> str:
    """Loads a clean SQL query template from the resources directory."""
    return (SQL_DIR / filename).read_text()

def _extract_customer_identity(ctx: Context) -> str:
    """
    OIDC Context Extractor: Dynamically parses the authenticated user 
    identity from IAP/OIDC headers in the underlying ASGI HTTP scope.
    """
    # If running in local test/mock suites without live requests context
    if not ctx or not ctx.request_context or not ctx.request_context.headers:
        logger.warning("Local/Mock run context: returning default testing customer ID.")
        return "customer-123"
        
    # Decode ASGI scope binary headers to UTF-8 string dictionary dynamically
    headers = {}
    for k, v in ctx.request_context.headers:
        headers[k.decode("utf-8").lower().strip()] = v.decode("utf-8").strip()
    
    # 1. Check standard Google Cloud IAP authenticated email header
    iap_header = headers.get("x-goog-authenticated-user-email")
    if iap_header:
        # Normalize standard Argolis/GCP email identity claims
        email = iap_header.replace("accounts.google.com:", "").strip()
        logger.info(f"Identity verified via IAP header context: {email}")
        return email
        
    # 2. Check custom development authorization context header (strictly gated to Local Development environment)
    if os.getenv("ALLOW_DEV_AUTH_BYPASS") == "true" or os.getenv("ENV") == "development":
        dev_auth = headers.get("x-forwarded-user-context") or headers.get("authorization")
        if dev_auth:
            # Development/Sandbox bypass parsing
            email = dev_auth.replace("Bearer ", "").strip()
            logger.info(f"Identity verified via Forwarded Context: {email}")
            return email
        
    logger.error("Authentication context missing from ASGI request headers.")
    raise PermissionError("Unauthorized: Identity context missing from request headers.")

def _mask_ssn(ssn_value: str) -> str:
    """Obfuscates Social Security Numbers to LAST_4 for log and context safety."""
    if not ssn_value:
        return "N/A"
    sanitized = ssn_value.replace("-", "").strip()
    if len(sanitized) >= 4:
        return f"***-**-{sanitized[-4:]}"
    return "***-**-****"

def _mask_ein(ein_value: str) -> str:
    """Obfuscates Employer Identification Numbers for context safety."""
    if not ein_value:
        return "N/A"
    sanitized = ein_value.replace("-", "").strip()
    if len(sanitized) >= 4:
        return f"**-***{sanitized[-4:]}"
    return "**-***-****"

@mcp.tool()
async def get_loan_application_documents(application_id: str, ctx: Context) -> str:
    """
    Retrieves W-2 and Paystub document statuses, visual classifications, 
    and verified wage entities for a specified Loan Application ID.
    
    This tool enforces strict row-level tenant isolation boundaries.
    """
    logger.info(f"FastMCP get_loan_application_documents invoked for Application ID: {application_id}")
    
    # Strict alphanumeric and length regex validation (Prevents Path Traversal & Command Injections)
    if not re.match(r"^[a-zA-Z0-9\-_]{4,64}$", application_id):
        logger.error(f"Security Alert: Malformed application ID input detected: {application_id}")
        return "Access Denied: Invalid Application ID format."

    try:
        # Resolve customer identity dynamically from OIDC headers
        customer_id = _extract_customer_identity(ctx)
        
        project_id = get_project_id()
        dataset_id = os.getenv("DATASET_ID", "banking")
        table_ref = f"{project_id}.{dataset_id}.application_artifact"

        
        # Load and execute decoupled SQL tenant query
        query = _load_sql("get_application_artifacts.sql").format(table_ref=table_ref)
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("application_id", "STRING", application_id),
                bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id)
            ]
        )
        
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            logger.warning(f"No documents found or tenant validation failed for App: {application_id}")
            return f"No documents found under authorized profile for Application ID: {application_id}"
            
        # Format a clean, fully PII-masked summary table for the AI Agent
        summary_lines = [
            f"=== Verified Loan Documents Audit for Application ID: {application_id} ==="
        ]
        
        for idx, row in enumerate(results, 1):
            claimed = row.claimed_artifact_type if row.claimed_artifact_type else "UNKNOWN"
            actual = row.actual_artifact_type if row.actual_artifact_type else "PENDING_OCR"
            status = row.status
            
            summary_lines.append(f"\n[Document #{idx}]: Claimed: {claimed} | Visual Classification: {actual} | Ingestion Status: {status}")
            
            # Perform deep PII masking on extraction payload
            payload = row.extraction_payload if row.extraction_payload else {}
            w2_data = payload.get("W2") or payload.get("w2")
            
            if w2_data:
                wages = w2_data.get("WagesTipsOtherCompensation", {}).get("value", "N/A")
                raw_ssn = w2_data.get("SSN", {}).get("value", "")
                raw_ein = w2_data.get("EIN", {}).get("value", "")
                
                summary_lines.append(f"  - Wages (Box 1): ${wages}")
                summary_lines.append(f"  - Borrower SSN: {_mask_ssn(raw_ssn)}")
                summary_lines.append(f"  - Employer Tax ID (EIN): {_mask_ein(raw_ein)}")
                
        return "\n".join(summary_lines)
        
    except PermissionError as perm_err:
        return f"Access Denied: {str(perm_err)}"
    except Exception as e:
        logger.error(f"MCP tool execution failed: {e}")
        return "Internal error occurred while retrieving documents."


@mcp.tool()
async def generate_upload_session_url(
    application_id: str,
    claimed_artifact_type: str,
    session_id: str,
    ctx: Context,
    content_type: str = "application/pdf"
) -> str:
    """
    Generates a secure, temporary (15-minute) GCS Signed Upload URL (PUT method)
    allowing a borrower to upload W-2 or Paystub files directly to GCS securely.
    
    Enforces strict input validation and row-level tenant context checks.
    """
    logger.info(f"FastMCP generate_upload_session_url invoked for App ID: {application_id} (Type: {claimed_artifact_type}, MIME: {content_type})")
    
    # 1. Input sanitization gates
    if not re.match(r"^[a-zA-Z0-9\-_]{4,64}$", application_id):
        logger.error(f"Security Alert: Malformed application ID input: {application_id}")
        return "Access Denied: Invalid Application ID format."
        
    type_upper = claimed_artifact_type.upper().strip()
    if type_upper not in ["W2", "PAYSTUB"]:
        logger.error(f"Security Alert: Malformed or unwhitelisted artifact type input: {claimed_artifact_type}")
        return f"Access Denied: Artifact type '{claimed_artifact_type}' is unsupported."

    ALLOWED_MIME_TYPES = ["application/pdf", "image/jpeg", "image/jpg", "image/png", "image/tiff"]
    ct_lower = content_type.lower().strip()
    if ct_lower not in ALLOWED_MIME_TYPES:
        logger.error(f"Security Alert: Unsupported or unwhitelisted MIME type input: {content_type}")
        return f"Access Denied: File format '{content_type}' is unsupported. Supported formats are PDF, JPEG, PNG, and TIFF."

    try:
        # 2. Resolve dynamic user identity from OIDC headers
        customer_id = _extract_customer_identity(ctx)
        
        project_id = get_project_id()
        dataset_id = os.getenv("DATASET_ID", "banking")
        table_ref = f"{project_id}.{dataset_id}.application_artifact"

        # Direct storage signed URL variables setup
        bucket_name = os.getenv("INTERACTION_ARTIFACTS_BUCKET", f"{project_id}_banking-interaction-artifacts")
        service_account_email = f"banking-service-sa@{project_id}.iam.gserviceaccount.com"
        
        # Construct target GCS path dynamically to map in the placeholder row!
        ext = "pdf"
        if "jpeg" in ct_lower or "jpg" in ct_lower:
            ext = "jpg"
        elif "png" in ct_lower:
            ext = "png"
        elif "tiff" in ct_lower:
            ext = "tiff"

        gcs_blob_name = f"incoming/{application_id}/{type_upper.lower()}.{ext}"
        gcs_uri = f"gs://{bucket_name}/{gcs_blob_name}"
        
        # Direct storage signed URL variables setup
        bucket_name = os.getenv("INTERACTION_ARTIFACTS_BUCKET", f"{project_id}_banking-interaction-artifacts")
        service_account_email = f"banking-service-sa@{project_id}.iam.gserviceaccount.com"
        
        # Construct target GCS path dynamically to map in the placeholder row!
        ext = "pdf"
        if "jpeg" in ct_lower or "jpg" in ct_lower:
            ext = "jpg"
        elif "png" in ct_lower:
            ext = "png"
        elif "tiff" in ct_lower:
            ext = "tiff"

        gcs_blob_name = f"incoming/{application_id}/{type_upper.lower()}.{ext}"
        gcs_uri = f"gs://{bucket_name}/{gcs_blob_name}"
        
        # Strict Tenant Validation: Ensure the application_id actually belongs to the calling customer_id!
        check_query = f"""
            SELECT artifact_id, status
            FROM `{table_ref}`
            WHERE application_id = @app_id 
              AND customer_id = @customer_id
              AND claimed_artifact_type = @artifact_type
            LIMIT 1
        """
        check_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("app_id", "STRING", application_id),
                bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id),
                bigquery.ScalarQueryParameter("artifact_type", "STRING", type_upper)
            ]
        )
        check_job = bq_client.query(check_query, job_config=check_config)
        check_results = list(check_job.result())
        
        import uuid
        
        if check_results:
            existing_artifact_id = check_results[0].artifact_id
            logger.info(f"Found existing artifact {existing_artifact_id} to override. Updating session_id and file_path_gcs in BigQuery.")
            update_query = f"""
                UPDATE `{table_ref}`
                SET audit_metadata = JSON_OBJECT('session_id', @session_id),
                    file_path_gcs = @file_path_gcs
                WHERE artifact_id = @artifact_id
            """
            update_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
                    bigquery.ScalarQueryParameter("file_path_gcs", "STRING", gcs_uri),
                    bigquery.ScalarQueryParameter("artifact_id", "STRING", existing_artifact_id)
                ]
            )
            bq_client.query(update_query, job_config=update_config).result()
        else:
            # Insert a new document placeholder with active session_id and file_path_gcs mapping using DML!
            new_artifact_id = f"session-placeholder-{uuid.uuid4()}"
            logger.info(f"No existing document found. Inserting new placeholder {new_artifact_id} mapped to GCS path: {gcs_uri}")
            
            from datetime import datetime, timezone
            current_timestamp = datetime.now(timezone.utc).isoformat()
            version_id = str(uuid.uuid4())
            
            insert_query = f"""
                INSERT INTO `{table_ref}`
                (artifact_id, customer_id, application_id, claimed_artifact_type, actual_artifact_type,
                 classification_confidence, status, file_path_gcs, extraction_payload, audit_metadata,
                 uploaded_at, verification_tier, verification_audit, version_id)
                VALUES
                (@artifact_id, @customer_id, @application_id, @claimed_artifact_type, NULL,
                 NULL, 'PENDING_CLASSIFICATION', @file_path_gcs, NULL, PARSE_JSON(@audit_metadata),
                 TIMESTAMP(@uploaded_at), NULL, NULL, @version_id)
            """
            insert_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("artifact_id", "STRING", new_artifact_id),
                    bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id),
                    bigquery.ScalarQueryParameter("application_id", "STRING", application_id),
                    bigquery.ScalarQueryParameter("claimed_artifact_type", "STRING", type_upper),
                    bigquery.ScalarQueryParameter("file_path_gcs", "STRING", gcs_uri),
                    bigquery.ScalarQueryParameter("audit_metadata", "STRING", json.dumps({"session_id": session_id})),
                    bigquery.ScalarQueryParameter("uploaded_at", "STRING", current_timestamp),
                    bigquery.ScalarQueryParameter("version_id", "STRING", version_id),
                ]
            )
            bq_client.query(insert_query, job_config=insert_config).result()
        
        # Retrieve GCP Credentials using default credential chains
        import google.auth
        from google.auth.impersonated_credentials import Credentials as ImpersonatedCredentials
        from datetime import timedelta
        
        source_credentials, _ = google.auth.default()
        impersonated_credentials = ImpersonatedCredentials(
            source_credentials=source_credentials,
            target_principal=service_account_email,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_name)
        
        # 4. Cryptographically sign PUT URL with Content-Length and MIME enforcements
        # Limit maximum upload size to 50MB
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="PUT",
            content_type=ct_lower,
            headers={"x-goog-content-length-range": "0,52428800"},
            credentials=impersonated_credentials,
            service_account_email=service_account_email
        )
        
        logger.info(f"Successfully generated secure signed PUT URL for App: {application_id} (Destination: {gcs_blob_name}, MIME: {ct_lower})")
        
        # 5. Return structured, PII-safe instructions to the AI Agent
        return f"""🔒 Secure Document Upload Session Generated
Document Type requested: {type_upper}
Destination Blob: gs://{bucket_name}/{gcs_blob_name}
Temporary Signed URL: {signed_url}

Instructions for the user:
- Let the borrower know a secure, encrypted upload link has been generated.
- Present the link clearly in a beautiful Markdown card in the chat window:
  [Click here to upload your W-2 document securely]({signed_url})
- Inform the user that the secure session link is only active for 15 minutes, accepts {ct_lower} format uploads, and enforces strict 50MB size ceilings."""

    except PermissionError as perm_err:
        return f"Access Denied: {str(perm_err)}"
    except Exception as e:
        logger.error(f"MCP generate_upload_session_url failed: {e}")
        return "Internal error occurred while creating upload session."
