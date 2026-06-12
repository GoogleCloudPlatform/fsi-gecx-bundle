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
import logging
import httpx
import google.auth
from google.auth.transport.requests import Request
from google.cloud import bigquery
from cachetools import TTLCache
from utils.gcp import get_project_id

logger = logging.getLogger(__name__)

# Externalize Dialogflow config to satisfy 12-Factor App environment principles
DIALOGFLOW_AGENT_ID = os.getenv("DIALOGFLOW_AGENT_ID", "091ad616-f42f-422e-864d-94523ee36a34")
DIALOGFLOW_LOCATION = os.getenv("DIALOGFLOW_LOCATION", "us-central1")

# Cache OAuth2 access token for 50 minutes (3000 seconds) to minimize GCloud API latency
token_cache = TTLCache(maxsize=1, ttl=3000)

# Re-use connection pooling globally to prevent TCP port exhaustion
http_client = httpx.AsyncClient(timeout=10.0)


def _get_cached_access_token() -> str:
    """Retrieves and caches Google OAuth2 access token to avoid high-latency refreshes."""
    if "token" in token_cache:
        return token_cache["token"]
        
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        auth_request = Request()
        credentials.refresh(auth_request)
        token_cache["token"] = credentials.token
        return credentials.token
    except Exception as auth_err:
        logger.error(f"Failed to retrieve Google credentials token for Dialogflow callback: {auth_err}")
        raise RuntimeError("OAuth2 credentials refresh failed.")

async def propagate_underwriting_to_session(
    session_id: str,
    wages_verified: bool,
    gross_income: float
) -> bool:
    """
    Securely injects verified underwriting parameters directly into the borrower's 
    active GECX/Dialogflow CX session state using Google Oauth2 REST API.
    """
    if not session_id or session_id == "N/A":
        logger.warning("Cannot propagate underwriting: session_id is missing or unmapped.")
        return False

    project_id = get_project_id()
    
    # 1. Standardize Dialogflow CX session path
    # Support both raw session UUIDs and fully qualified Dialogflow session paths
    if not session_id.startswith("projects/"):
        session_path = f"projects/{project_id}/locations/{DIALOGFLOW_LOCATION}/agents/{DIALOGFLOW_AGENT_ID}/sessions/{session_id}"
    else:
        session_path = session_id

    logger.info(f"Propagating underwriting override to Dialogflow CX session: {session_path}")

    # 2. Retrieve Google OAuth2 Access Token securely via cached TTL getter
    try:
        access_token = _get_cached_access_token()
    except Exception as auth_err:
        logger.error(f"Failed to obtain cached Google OAuth2 access token: {auth_err}")
        return False

    # 3. Construct the Dialogflow CX REST API detectIntent payload carrying verified parameters
    url = f"https://{DIALOGFLOW_LOCATION}-dialogflow.googleapis.com/v3/{session_path}:detectIntent"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Inject verified claims into session params block
    payload = {
        "queryInput": {
            "text": {
                "text": "underwriting_system_override_event" # System event intent trigger
            },
            "languageCode": "en"
        },
        "queryParams": {
            "parameters": {
                "wages_verified": wages_verified,
                "gross_monthly_income": float(gross_income),
                "verification_status": "PROCESSED"
            }
        }
    }

    # 4. Dispatch asynchronous HTTP POST request utilizing globally pooled HTTPX client singleton
    try:
        response = await http_client.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            logger.info("Successfully propagated underwriting parameters to Dialogflow CX session.")
            return True
        else:
            logger.error(f"Dialogflow CX Session parameter update failed with status {response.status_code}: {response.text}")
            return False
            
    except Exception as post_err:
        logger.error(f"Failed to dispatch async HTTP Webhook to Dialogflow CX: {post_err}")
        return False
def _create_automated_underwriting_message(
    user_id: str,
    artifact_type: str,
    approved: bool,
    gross_income: float
):
    import uuid
    from datetime import datetime, timezone
    from utils.bq import create_message_in_bigquery, get_device_tokens_for_customer
    from firebase_admin import messaging

    message_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    
    category = "Loans"
    
    if approved:
        message_text = (
            f"Your submitted {artifact_type} document has been reviewed and approved by our underwriting team. "
            f"Verified Gross Monthly Income: ${gross_income:,.2f}. Your home loan preapproval process is moving forward!"
        )
        notification_title = f"Document Approved: {artifact_type}"
    else:
        message_text = (
            f"Your submitted {artifact_type} document could not be verified by our underwriting team. "
            f"Please contact support or re-upload a clear, high-resolution copy of the document."
        )
        notification_title = f"Document Verification Issue: {artifact_type}"

    try:
        logger.info(f"Creating automated secure message for customer {user_id} (Artifact: {artifact_type}, Approved: {approved})")
        create_message_in_bigquery(
            message_id=message_id,
            user_id=user_id,
            sender="bank",
            category=category,
            message=message_text,
            created_at=created_at,
            thread_id=thread_id
        )
        
        # Dispatch push notification via Firebase
        try:
            tokens = get_device_tokens_for_customer(user_id)
            if tokens:
                msg_body = message_text
                if len(msg_body) > 100:
                    msg_body = msg_body[:97] + "..."
                
                push_message = messaging.MulticastMessage(
                    data={
                        "title": notification_title,
                        "body": msg_body,
                        "thread_id": str(thread_id),
                        "type": "support_message",
                        "category": category,
                        "user_id": str(user_id)
                    },
                    tokens=tokens,
                )
                messaging.send_multicast(push_message)
                logger.info(f"FCM push notification dispatched successfully to {len(tokens)} devices.")
        except Exception as fcm_err:
            logger.warning(f"FCM push notification dispatch skipped or failed: {fcm_err}")
    except Exception as e:
        logger.error(f"Failed to generate automated secure message: {e}")

async def trigger_session_propagation_flow(
    table_ref: str,
    artifact_id: str,
    wages_verified: bool,
    gross_income: float
) -> bool:
    """
    Loads session, customer, and artifact details from BigQuery, automatically writes
    a secure customer message record, and propagates status back to Dialogflow CX.
    """
    logger.info(f"Resolving session mapping for underwriting override callback. Artifact ID: {artifact_id}")
    
    bq_client = bigquery.Client()
    query = f"""
        SELECT 
            JSON_VALUE(audit_metadata.session_id) AS session_id,
            customer_id,
            claimed_artifact_type
        FROM `{table_ref}`
        WHERE artifact_id = @artifact_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("artifact_id", "STRING", artifact_id)
        ]
    )
    
    try:
        query_job = bq_client.query(query, job_config=job_config)
        results = list(query_job.result())
        
        if not results:
            logger.warning(f"Artifact not found in database: {artifact_id}. Skipping callback.")
            return False
            
        row = results[0]
        customer_id = getattr(row, "customer_id", None)
        claimed_artifact_type = getattr(row, "claimed_artifact_type", "W-2")
        session_id = getattr(row, "session_id", None)
        
        # Generate secure support message and push notification for the customer
        if customer_id:
            _create_automated_underwriting_message(
                user_id=customer_id,
                artifact_type=claimed_artifact_type,
                approved=wages_verified,
                gross_income=gross_income
            )
        
        if not session_id:
            logger.warning(f"Dialogflow session_id not found inside BQ audit_metadata for artifact: {artifact_id}. Skipping session propagation.")
            return True  # Still return True since secure message was handled
            
        return await propagate_underwriting_to_session(session_id, wages_verified, gross_income)
        
    except Exception as e:
        logger.error(f"Error executing underwriting override callback: {e}")
        return False
