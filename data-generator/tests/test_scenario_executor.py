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

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import main
from main import BANKING_SERVICE_URL, app
from scenarios import ScenarioExecutionRequest, ScenarioRequest, execute_scenario, plan_scenario
from scenarios.executor import clear_execution_cache
from scenarios.schemas import ScenarioMode, ScenarioStepStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_execution_cache():
    clear_execution_cache()
    yield
    clear_execution_cache()


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_execution_does_not_write_authorizations():
    plan = plan_scenario(ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=2))
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "authorization_id": "auth-1"})
    )

    result = await execute_scenario(
        ScenarioExecutionRequest(plan=plan, idempotency_key="dry-run-001"),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
        default_card_token="tok_test",
    )

    assert result.status == "dry_run"
    assert result.attempted_events == 0
    assert result.skipped_events == len(plan.timeline)
    assert all(step.status == ScenarioStepStatus.PLANNED for step in result.steps)
    assert not auth_route.called


@pytest.mark.asyncio
@respx.mock
async def test_execute_scenario_sends_bounded_authorization_payloads():
    plan = plan_scenario(ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=2))
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "authorization_id": "auth-123"})
    )

    result = await execute_scenario(
        ScenarioExecutionRequest(plan=plan, mode=ScenarioMode.EXECUTE, idempotency_key="execute-001", default_card_token="tok_scenario"),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    assert result.status == "succeeded"
    assert result.attempted_events == 2
    assert result.succeeded_events == 2
    assert result.created_authorization_ids == ["auth-123", "auth-123"]
    assert auth_route.call_count == 2

    payload = json.loads(auth_route.calls[0].request.content.decode())
    assert payload["card_token"] == "tok_scenario"
    assert payload["synthetic_scenario_id"] == plan.scenario_id
    assert payload["synthetic_event_id"] == plan.timeline[0].event_id
    assert payload["retrieval_reference_number"].isdigit()
    assert len(payload["retrieval_reference_number"]) == 12


@pytest.mark.asyncio
@respx.mock
async def test_execute_scenario_idempotency_returns_cached_result():
    plan = plan_scenario(ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=1))
    auth_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(200, json={"action_code": "00", "authorization_id": "auth-123"})
    )
    request = ScenarioExecutionRequest(
        plan=plan,
        mode=ScenarioMode.EXECUTE,
        idempotency_key="execute-idempotent-001",
        default_card_token="tok_scenario",
    )

    first = await execute_scenario(request, banking_service_url=BANKING_SERVICE_URL, headers={"X-Card-Network-Token": "test"})
    second = await execute_scenario(request, banking_service_url=BANKING_SERVICE_URL, headers={"X-Card-Network-Token": "test"})

    assert first.execution_id == second.execution_id
    assert auth_route.call_count == 1
    assert any("Duplicate idempotency key" in warning for warning in second.warnings)


def test_execute_endpoint_dry_run_returns_structured_result():
    plan = plan_scenario(ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=2))

    response = client.post(
        "/scenarios/execute",
        json={
            "plan": plan.model_dump(mode="json"),
            "idempotency_key": "endpoint-dry-run-001",
            "mode": "dry_run",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "dry_run"
    assert body["planned_events"] == 2
    assert body["attempted_events"] == 0
