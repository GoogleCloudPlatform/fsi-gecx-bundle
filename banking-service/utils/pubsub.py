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

import json
import logging
from datetime import datetime, timezone
from google.cloud import pubsub_v1
from utils.gcp import get_project_id

logger = logging.getLogger(__name__)

# Initialize thread-safe Pub/Sub Publisher Client globally
publisher_client = pubsub_v1.PublisherClient()

def publish_underwriting_exception(
    artifact_id: str,
    application_id: str,
    customer_id: str,
    file_path_gcs: str,
    flagged_fields: list[str],
    overall_confidence: float
) -> str:
    """
    FSI Data Governance Compliant: Asynchronously publishes a reference-only exception 
    payload to the manual-underwriting-review Pub/Sub queue for Human-in-the-Loop auditing.
    
    Returns:
        The published message ID.
    """
    project_id = get_project_id()
    topic_id = "manual-underwriting-review"
    topic_path = publisher_client.topic_path(project_id, topic_id)

    # Construct PII-free reference payload
    payload = {
        "artifact_id": artifact_id,
        "application_id": application_id,
        "customer_id": customer_id,
        "file_path_gcs": file_path_gcs,
        "flagged_fields": flagged_fields,
        "overall_confidence": float(overall_confidence),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    logger.info(f"Preparing exception queue dispatch for artifact ID: {artifact_id} (flagged fields: {flagged_fields})")
    
    try:
        message_bytes = json.dumps(payload).encode("utf-8")
        
        # Publish message asynchronously to prevent event loop blocking
        future = publisher_client.publish(topic_path, data=message_bytes)
        message_id = future.result(timeout=10.0)  # Block up to 10 seconds for confirmation
        
        logger.info(f"Successfully published underwriting exception message. ID: {message_id}")
        return message_id
        
    except Exception as pub_ex:
        # Safeguard: Catch but do not bubble up exception, preserving BQ updates in main pipeline
        logger.error(f"Failed to dispatch message to underwriting exception queue: {pub_ex}")
        return ""
