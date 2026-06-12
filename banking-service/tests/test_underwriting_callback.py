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

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from services.underwriting_callback import trigger_session_propagation_flow, propagate_underwriting_to_session

@pytest.fixture
def mock_bq_client():
    """Mock BigQuery Client."""
    with patch("services.underwriting_callback.bigquery.Client") as mock_bq:
        yield mock_bq

@pytest.fixture
def mock_google_auth():
    """Mock Google credentials refresh."""
    with patch("services.underwriting_callback.google.auth.default") as mock_auth:
        mock_creds = MagicMock()
        mock_creds.token = "fake-oauth-access-token"
        mock_auth.return_value = (mock_creds, "mock-project")
        yield mock_auth

@pytest.mark.asyncio
@patch("services.underwriting_callback.get_project_id")
@patch("services.underwriting_callback.http_client")
async def test_propagate_underwriting_to_session_success(mock_http_client, mock_get_project_id, mock_google_auth):
    """Verify that the webhook dispatches correctly formatted payloads to Dialogflow CX API."""
    mock_get_project_id.return_value = "test-project-123"
    
    # Mock Async HTTP client post
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    mock_http_client.post = AsyncMock(return_value=mock_response)

    success = await propagate_underwriting_to_session(
        session_id="session-xyz-789",
        wages_verified=True,
        gross_income=6250.00
    )
    
    assert success is True
    
    # Verify endpoint URL and payload content
    mock_http_client.post.assert_called_once()
    args, kwargs = mock_http_client.post.call_args
    
    url = args[0]
    expected_url = "https://us-central1-dialogflow.googleapis.com/v3/projects/test-project-123/locations/us-central1/agents/e0b952c1-280d-41d0-8da5-46db4b0e6ad9/sessions/session-xyz-789:detectIntent"
    assert url == expected_url
    
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer fake-oauth-access-token"
    
    payload = kwargs["json"]
    params = payload["queryParams"]["parameters"]
    assert params["wages_verified"] is True
    assert params["gross_monthly_income"] == 6250.00
    assert params["verification_status"] == "PROCESSED"

@pytest.mark.asyncio
async def test_propagate_underwriting_to_session_missing_id():
    """Verify the callback fails fast if the session_id is unmapped or missing."""
    success = await propagate_underwriting_to_session(
        session_id="",
        wages_verified=True,
        gross_income=4500.00
    )
    assert success is False

@pytest.mark.asyncio
@patch("services.underwriting_callback._create_automated_underwriting_message")
@patch("services.underwriting_callback.propagate_underwriting_to_session")
async def test_trigger_session_propagation_flow_success(mock_propagate, mock_create_msg, mock_bq_client):
    """Verify BQ resolves the session_id and passes it cleanly to the propagator."""
    mock_propagate.return_value = True
    
    # Mock BigQuery row mapping
    mock_row = MagicMock()
    mock_row.session_id = "session-resolved-from-bq-101"
    mock_row.customer_id = "cust-123"
    mock_row.claimed_artifact_type = "W-2"
    
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_bq_client.return_value.query.return_value = mock_query_job
    
    success = await trigger_session_propagation_flow(
        table_ref="mock_project.mock_dataset.mock_table",
        artifact_id="art-ssn-111",
        wages_verified=True,
        gross_income=8500.00
    )
    
    assert success is True
    
    # Verify BigQuery lookup query parameters
    mock_bq_client.return_value.query.assert_called_once()
    args, kwargs = mock_bq_client.return_value.query.call_args
    query_params = kwargs["job_config"].query_parameters
    assert query_params[0].name == "artifact_id"
    assert query_params[0].value == "art-ssn-111"
    
    # Verify secure message creation helper was called once
    mock_create_msg.assert_called_once_with(
        user_id="cust-123",
        artifact_type="W-2",
        approved=True,
        gross_income=8500.00
    )
    # Verify propagation arguments
    mock_propagate.assert_called_once_with("session-resolved-from-bq-101", True, 8500.00)
