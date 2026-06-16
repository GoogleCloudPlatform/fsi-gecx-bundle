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

import datetime
import logging
import uuid

from google.cloud import bigquery

from utils.gcp import get_project_id

from pathlib import Path

PROJECT_ID = get_project_id()

logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "resources" / "sql"


def _load_sql(filename: str) -> str:
    """Loads a clean SQL query template from the resources directory."""
    return (SQL_DIR / filename).read_text()



def _get_client():
    return bigquery.Client(project=PROJECT_ID)


def log_artifact_to_bigquery(
    application_id: str,
    artifact_type: str,
    gcs_uri: str,
    customer_id: str,
    artifact_id: str | None = None,
    status: str = "PENDING_CLASSIFICATION"
) -> str:
    if not artifact_id:
        artifact_id = str(uuid.uuid4())
    dataset_id = "banking"
    table_id = "application_artifact"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    from datetime import datetime, timezone
    current_timestamp = datetime.now(timezone.utc).isoformat()
    version_id = str(uuid.uuid4())

    query = _load_sql("insert_application_artifact.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("artifact_id", "STRING", artifact_id),
            bigquery.ScalarQueryParameter("customer_id", "STRING", customer_id),
            bigquery.ScalarQueryParameter("application_id", "STRING", application_id),
            bigquery.ScalarQueryParameter("claimed_artifact_type", "STRING", artifact_type.upper() if artifact_type else None),
            bigquery.ScalarQueryParameter("status", "STRING", status),
            bigquery.ScalarQueryParameter("file_path_gcs", "STRING", gcs_uri),
            bigquery.ScalarQueryParameter("uploaded_at", "STRING", current_timestamp),
            bigquery.ScalarQueryParameter("version_id", "STRING", version_id),
        ]
    )

    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"Failed to perform DML insert in log_artifact_to_bigquery: {e}")
        raise e

    return artifact_id


def create_customer_in_bigquery(user_id: str, first_name: str | None, last_name: str | None,
                                email: str | None = None, phone_number: str | None = None):
    dataset_id = "banking"
    table_id = "user"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    query = _load_sql("create_customer.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("first_name", "STRING", first_name),
            bigquery.ScalarQueryParameter("last_name", "STRING", last_name),
            bigquery.ScalarQueryParameter("email", "STRING", email),
            bigquery.ScalarQueryParameter("phone_number", "STRING", phone_number),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery DML insert user failed: {e}")
        raise e

    return user_id


def get_customer_from_bigquery(user_id: str):
    dataset_id = "banking"
    table_id = "user"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    query = _load_sql("get_customer.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())

        if not results:
            return None

        row = results[0]
        return {
            "user_id": row.user_id,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "phone_number": row.phone_number
        }
    except Exception as e:
        logger.error(f"BigQuery fetch user failed: {e}")
        raise e



def log_application_to_bigquery(
        user_id: str,
        product_category: str | None,
        product_type: str | None,
        requested_amount: float | None
):
    application_id = str(uuid.uuid4())
    dataset_id = "banking"
    table_id = "application"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    from datetime import datetime, timezone
    current_timestamp = datetime.now(timezone.utc)

    query = _load_sql("create_application.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("application_id", "STRING", application_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("product_category", "STRING", product_category),
            bigquery.ScalarQueryParameter("product_type", "STRING", product_type),
            bigquery.ScalarQueryParameter("requested_amount", "NUMERIC", requested_amount),
            bigquery.ScalarQueryParameter("application_status", "STRING", "STARTED"),
            bigquery.ScalarQueryParameter("started_at", "TIMESTAMP", current_timestamp),
            bigquery.ScalarQueryParameter("last_updated_at", "TIMESTAMP", current_timestamp),
        ]
    )

    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery DML insert application failed: {e}")
        raise e

    return application_id


def update_application_in_bigquery(
        application_id: str,
        user_id: str,
        requested_amount: float | None = None,
        application_status: str | None = None
):
    dataset_id = "banking"
    table_id = "application"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    from datetime import datetime, timezone
    current_timestamp = datetime.now(timezone.utc)

    query = _load_sql("update_application.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("application_id", "STRING", application_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("requested_amount", "NUMERIC", requested_amount),
            bigquery.ScalarQueryParameter("application_status", "STRING", application_status),
            bigquery.ScalarQueryParameter("last_updated_at", "TIMESTAMP", current_timestamp),
        ]
    )

    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery DML update application failed: {e}")
        raise e


def update_customer_in_bigquery(
        user_id: str,
        first_name: str | None = None,
        last_name: str | None = None,
        phone_number: str | None = None
):
    dataset_id = "banking"
    table_id = "user"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    query = _load_sql("update_customer.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("first_name", "STRING", first_name),
            bigquery.ScalarQueryParameter("last_name", "STRING", last_name),
            bigquery.ScalarQueryParameter("phone_number", "STRING", phone_number),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()  # Wait for the job to complete
    except Exception as e:
        logger.error(f"BigQuery update user failed: {e}")
        raise e


def save_device_token_in_bigquery(user_id: str, device_token: str):
    dataset_id = "banking"
    table_id = "user_device"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    query = _load_sql("merge_customer_device.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("device_token", "STRING", device_token),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery merge user_device failed: {e}")
        raise e


def delete_device_token_from_bigquery(user_id: str, device_token: str):
    dataset_id = "banking"
    table_id = "user_device"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    query = _load_sql("delete_customer_device.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("device_token", "STRING", device_token),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery delete user_device failed: {e}")
        raise e


def get_device_tokens_for_customer(user_id: str) -> list[str]:
    dataset_id = "banking"
    table_id = "user_device"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"


    query = _load_sql("get_customer_devices.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())
        return [row.device_token for row in results]
    except Exception as e:
        logger.error(f"BigQuery fetch user_device failed: {e}")
        raise e



def create_message_in_bigquery(
        message_id: str,
        user_id: str,
        sender: str,
        category: str,
        message: str,
        created_at: datetime.datetime,
        thread_id: str
):
    dataset_id = "banking"
    table_id = "user_secure_message"

    is_user_read = True if sender == "user" else False
    is_agent_read = False if sender == "user" else True

    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("create_secure_message.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("message_id", "STRING", message_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ScalarQueryParameter("sender", "STRING", sender),
            bigquery.ScalarQueryParameter("category", "STRING", category),
            bigquery.ScalarQueryParameter("message", "STRING", message),
            bigquery.ScalarQueryParameter("created_at", "TIMESTAMP", created_at),
            bigquery.ScalarQueryParameter("thread_id", "STRING", thread_id),
            bigquery.ScalarQueryParameter("is_user_read", "BOOL", is_user_read),
            bigquery.ScalarQueryParameter("is_agent_read", "BOOL", is_agent_read),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery DML insert secure message failed: {e}")
        raise e


def get_messages_for_customer(user_id: str) -> list[dict]:
    dataset_id = "banking"
    table_id = "user_secure_message"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("get_secure_messages.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id)
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())
        return [
            {
                "message_id": row.message_id,
                "user_id": row.user_id,
                "sender": row.sender,
                "category": row.category,
                "message": row.message,
                "created_at": row.created_at,
                "deleted": row.deleted,
                "thread_id": row.thread_id,
                "is_user_read": True if row.is_user_read is None else row.is_user_read,
                "is_agent_read": True if row.is_agent_read is None else row.is_agent_read,
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"BigQuery fetch secure messages failed: {e}")
        raise e


def soft_delete_message_in_bigquery(message_id: str, user_id: str):
    dataset_id = "banking"
    table_id = "user_secure_message"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("soft_delete_secure_message.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("message_id", "STRING", message_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery soft delete message failed: {e}")
        raise e


def soft_delete_thread_in_bigquery(thread_id: str, user_id: str):
    dataset_id = "banking"
    table_id = "user_secure_message"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("soft_delete_secure_thread.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("thread_id", "STRING", thread_id),
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery soft delete thread failed: {e}")
        raise e


def get_user_id_for_thread(thread_id: str) -> str | None:
    dataset_id = "banking"
    table_id = "user_secure_message"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("get_secure_thread_user.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("thread_id", "STRING", thread_id)
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())
        if results:
            return results[0].user_id
        return None
    except Exception as e:
        logger.error(f"BigQuery fetch user_id for thread failed: {e}")
        raise e


def mark_messages_as_user_read_in_bigquery(message_ids: list[str], user_id: str):
    dataset_id = "banking"
    table_id = "user_secure_message"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    if not message_ids:
        return

    query = _load_sql("mark_secure_messages_user_read.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ArrayQueryParameter("message_ids", "STRING", message_ids),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery mark messages as user read failed: {e}")
        raise e


def mark_messages_as_agent_read_in_bigquery(message_ids: list[str], user_id: str):
    dataset_id = "banking"
    table_id = "user_secure_message"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    if not message_ids:
        return

    query = _load_sql("mark_secure_messages_agent_read.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
            bigquery.ArrayQueryParameter("message_ids", "STRING", message_ids),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        query_job.result()
    except Exception as e:
        logger.error(f"BigQuery mark messages as agent read failed: {e}")
        raise e


def get_all_customers_from_bigquery() -> list[dict]:
    dataset_id = "banking"
    table_id = "user"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("get_all_customers.sql").format(table_ref=table_ref)
    client = _get_client()
    try:
        query_job = client.query(query)
        results = list(query_job.result())
        return [
            {
                "user_id": row.user_id,
                "first_name": row.first_name,
                "last_name": row.last_name,
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"BigQuery fetch all users failed: {e}")
        raise e


def find_nearest_locations(lat: float, lng: float, location_type: str = "ALL") -> list[dict]:
    dataset_id = "banking"
    table_id = "retail_location"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("find_nearest_locations.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("lat", "FLOAT64", lat),
            bigquery.ScalarQueryParameter("lng", "FLOAT64", lng),
            bigquery.ScalarQueryParameter("type", "STRING", location_type.upper()),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())
        return [
            {
                "id": row.id,
                "type": row.type,
                "name": row.name,
                "address": row.address,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "hours": row.hours,
                "phone_number": row.phone_number,
                "distance_meters": row.distance_meters,
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"BigQuery find_nearest_locations failed: {e}")
        raise e


def search_locations_by_text(search_text: str, location_type: str = "ALL") -> list[dict]:
    dataset_id = "banking"
    table_id = "retail_location"
    table_ref = f"{PROJECT_ID}.{dataset_id}.{table_id}"

    query = _load_sql("search_locations_by_text.sql").format(table_ref=table_ref)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("search_text", "STRING", search_text),
            bigquery.ScalarQueryParameter("type", "STRING", location_type.upper()),
        ]
    )
    client = _get_client()
    try:
        query_job = client.query(query, job_config=job_config)
        results = list(query_job.result())
        return [
            {
                "id": row.id,
                "type": row.type,
                "name": row.name,
                "address": row.address,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "hours": row.hours,
                "phone_number": row.phone_number,
                "distance_meters": row.distance_meters,
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"BigQuery search_locations_by_text failed: {e}")
        raise e


