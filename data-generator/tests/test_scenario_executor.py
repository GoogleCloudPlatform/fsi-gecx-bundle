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
from scenarios import (
    ScenarioExecutionRequest,
    ScenarioRequest,
    execute_scenario,
    plan_scenario,
)
from scenarios.executor import clear_execution_cache, list_scenario_outcomes
from scenarios.schemas import (
    OutcomeLabel,
    ScenarioMode,
    ScenarioStepStatus,
    ScenarioType,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_execution_cache():
    clear_execution_cache()
    yield
    clear_execution_cache()


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_execution_does_not_write_authorizations():
    plan = plan_scenario(
        ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=2)
    )
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "authorization_id": "auth-1"}
        )
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
    plan = plan_scenario(
        ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=2)
    )
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "authorization_id": "auth-123"}
        )
    )
    settle_route = respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-123"}
        )
    )
    reverse_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse"
    ).mock(return_value=httpx.Response(200, json={"status": "REVERSED"}))

    result = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key="execute-001",
            default_card_token="tok_scenario",
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    assert result.status == "succeeded"
    assert result.attempted_events == 2
    assert result.succeeded_events == 2
    assert result.created_authorization_ids == ["auth-123", "auth-123"]
    assert (
        result.settlements_created
        + result.reversals_created
        + result.pending_holds_created
        == 2
    )
    assert auth_route.call_count == 2
    assert settle_route.call_count + reverse_route.call_count <= 2

    payload = json.loads(auth_route.calls[0].request.content.decode())
    assert payload["card_token"] == "tok_scenario"
    assert payload["synthetic_scenario_id"] == plan.scenario_id
    assert payload["synthetic_event_id"] == plan.timeline[0].event_id
    assert payload["retrieval_reference_number"].isdigit()
    assert len(payload["retrieval_reference_number"]) == 12


@pytest.mark.asyncio
@respx.mock
async def test_execute_scenario_idempotency_returns_cached_result():
    plan = plan_scenario(
        ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=1)
    )
    auth_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    ).mock(
        return_value=httpx.Response(
            200, json={"action_code": "00", "authorization_id": "auth-123"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-123"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    request = ScenarioExecutionRequest(
        plan=plan,
        mode=ScenarioMode.EXECUTE,
        idempotency_key="execute-idempotent-001",
        default_card_token="tok_scenario",
    )

    first = await execute_scenario(
        request,
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )
    second = await execute_scenario(
        request,
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    assert first.execution_id == second.execution_id
    assert auth_route.call_count == 1
    assert any("Duplicate idempotency key" in warning for warning in second.warnings)


def test_execute_endpoint_dry_run_returns_structured_result():
    plan = plan_scenario(
        ScenarioRequest(goal="Run lakehouse spend velocity surge", max_events=2)
    )

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


def test_simulation_status_endpoint_returns_control_surface_summary():
    response = client.get("/simulation/status")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "data-generator"
    assert body["control_surface"] == "direct-fastapi"
    assert "/scenarios/dry-run" in body["supported_routes"]
    assert body["pulse"]["min_events"] >= 0


def test_scenario_endpoint_accepts_iap_operator_header_in_deployed_mode(monkeypatch):
    monkeypatch.setattr(main, "is_local_dev", lambda: False)

    response = client.post(
        "/scenarios/plan",
        headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:operator@google.com"
        },
        json={
            "goal": "Run lakehouse spend velocity surge",
            "scenario_type": "lakehouse_spend_velocity_surge",
            "max_events": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["scenario_type"] == "lakehouse_spend_velocity_surge"


def test_scenario_endpoint_rejects_missing_operator_context_in_deployed_mode(
    monkeypatch,
):
    monkeypatch.setattr(main, "is_local_dev", lambda: False)

    response = client.post(
        "/scenarios/plan",
        json={
            "goal": "Run lakehouse spend velocity surge",
            "scenario_type": "lakehouse_spend_velocity_surge",
            "max_events": 1,
        },
    )

    assert response.status_code == 401


def test_dry_run_endpoint_returns_execution_result_with_operator():
    response = client.post(
        "/scenarios/dry-run",
        headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:operator@google.com"
        },
        json={
            "goal": "Run lakehouse spend velocity surge",
            "scenario_type": "lakehouse_spend_velocity_surge",
            "max_events": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "dry_run"
    assert body["operator"] == "operator@google.com"
    assert body["planned_events"] == 2
    assert body["attempted_events"] == 0


def test_replay_endpoint_sets_replay_mode_for_dry_run_plan():
    plan = plan_scenario(
        ScenarioRequest(goal="Make something interesting happen", max_events=1)
    )

    response = client.post(
        "/scenarios/replay",
        json={
            "plan": plan.model_dump(mode="json"),
            "idempotency_key": "endpoint-replay-001",
            "default_card_token": "tok_replay",
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "replay"


@pytest.mark.asyncio
@respx.mock
async def test_execute_scenario_records_synthetic_outcomes():
    plan = plan_scenario(
        ScenarioRequest(
            goal="Run a card not present gift card campaign",
            scenario_type=ScenarioType.CNP_GIFT_CARD_CAMPAIGN,
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "00",
                "authorization_id": "auth-feedback-1",
                "fraud_risk_score": 86,
                "fraud_reason_codes": ["CNP_DESCRIPTOR", "GIFT_CARD_VELOCITY"],
                "fraud_model_version": "local-deterministic-v1",
            },
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-feedback-1"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    persistence_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-outcomes"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "persisted_count": len(plan.timeline),
                "outcome_ids": ["outcome-1"],
            },
        )
    )

    result = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key="execute-outcome-001",
            default_card_token="tok_feedback",
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    assert result.outcomes
    outcome = result.outcomes[0]
    assert outcome.scenario_id == plan.scenario_id
    assert outcome.execution_id == result.execution_id
    assert outcome.authorization_id == "auth-feedback-1"
    assert outcome.card_token == "tok_feedback"
    assert outcome.synthetic_label is True
    assert outcome.expected_reason_codes
    assert outcome.actual_reason_codes == ["CNP_DESCRIPTOR", "GIFT_CARD_VELOCITY"]
    assert outcome.actual_risk_score == 86
    assert outcome.model_version == "local-deterministic-v1"
    assert list_scenario_outcomes(plan.scenario_id) == result.outcomes
    assert persistence_route.called
    persisted = json.loads(persistence_route.calls[0].request.content.decode())
    assert persisted["outcomes"][0]["scenario_id"] == plan.scenario_id
    assert persisted["outcomes"][0]["outcome_label"] == "expected_fraud"
    assert persisted["outcomes"][0]["authorization_id"] == "auth-feedback-1"


@pytest.mark.asyncio
@respx.mock
async def test_scenario_outcomes_endpoint_returns_cached_feedback():
    plan = plan_scenario(
        ScenarioRequest(
            goal="Run a card testing campaign",
            scenario_type=ScenarioType.DIGITAL_CARD_TESTING_CAMPAIGN,
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "00",
                "authorization_id": "auth-endpoint-1",
                "fraud_risk_score": 78,
                "fraud_reason_codes": ["DIGITAL_GOODS", "CARD_TESTING"],
                "fraud_model_version": "local-deterministic-v1",
            },
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-endpoint-1"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-outcomes"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "persisted_count": len(plan.timeline),
                "outcome_ids": ["outcome-1"],
            },
        )
    )

    await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key="endpoint-outcome-001",
            default_card_token="tok_endpoint",
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    response = client.get(f"/scenarios/{plan.scenario_id}/outcomes")

    assert response.status_code == 200
    body = response.json()
    assert body["scenario_id"] == plan.scenario_id
    assert body["count"] == len(plan.timeline)
    assert body["outcomes"][0]["authorization_id"] == "auth-endpoint-1"
    assert body["outcomes"][0]["actual_risk_score"] == 78


@pytest.mark.asyncio
@respx.mock
async def test_customer_action_resolves_false_positive_alert():
    plan = plan_scenario(
        ScenarioRequest(
            goal="Create a false positive travel story.",
            scenario_type=ScenarioType.TRAVEL_FALSE_POSITIVE_STORY,
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "00",
                "authorization_id": "auth-fp-1",
                "fraud_alert_id": "alert-fp-1",
                "fraud_risk_score": 72,
                "fraud_reason_codes": ["INTERNATIONAL_ANOMALY"],
                "fraud_model_version": "local-deterministic-v1",
            },
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-fp-1"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    action_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-action"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "message": "Fraud alert marked as recognized activity.",
                "outcome": "CUSTOMER_RECOGNIZED",
                "fraud_alert": {
                    "fraud_alert_id": "alert-fp-1",
                    "status": "RESOLVED_CUSTOMER_RECOGNIZED",
                },
            },
        )
    )
    respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-outcomes"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "persisted_count": len(plan.timeline),
                "outcome_ids": ["outcome-1"],
            },
        )
    )

    result = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key="execute-false-positive-001",
            default_card_token="tok_false_positive",
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    customer_action = next(
        step for step in result.steps if step.event_type == "customer_action"
    )
    assert customer_action.status == ScenarioStepStatus.SUCCEEDED
    assert customer_action.resolution == "recognized"
    assert customer_action.alert_id == "alert-fp-1"
    assert result.created_alert_ids == ["alert-fp-1"]
    payload = json.loads(action_route.calls[0].request.content.decode())
    assert payload["fraud_alert_id"] == "alert-fp-1"
    assert payload["outcome_label"] == "confirmed_legitimate"
    assert payload["disputed_authorization_ids"] == []
    assert payload["issue_replacement"] is False


@pytest.mark.asyncio
@respx.mock
async def test_customer_action_triages_disputed_fraud_alert():
    plan = plan_scenario(
        ScenarioRequest(
            goal="Create a fraud story for a traveling executive.",
            scenario_type=ScenarioType.FRAUD_TRAVEL_STORY,
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        side_effect=[
            httpx.Response(
                200, json={"action_code": "00", "authorization_id": "auth-base-1"}
            ),
            httpx.Response(
                200, json={"action_code": "00", "authorization_id": "auth-travel-1"}
            ),
            httpx.Response(
                200, json={"action_code": "00", "authorization_id": "auth-hotel-1"}
            ),
            httpx.Response(
                200,
                json={
                    "action_code": "00",
                    "authorization_id": "auth-fraud-1",
                    "fraud_alert_id": "alert-fraud-1",
                    "fraud_risk_score": 82,
                },
            ),
            httpx.Response(
                200,
                json={
                    "action_code": "00",
                    "authorization_id": "auth-fraud-2",
                    "fraud_alert_id": "alert-fraud-1",
                    "fraud_risk_score": 91,
                },
            ),
        ]
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-fraud-1"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    action_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-action"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "message": "Fraud case triaged and pending specialist review.",
                "outcome": "PENDING_SPECIALIST_REVIEW",
                "fraud_alert": {
                    "fraud_alert_id": "alert-fraud-1",
                    "status": "TRIAGED_PENDING_REVIEW",
                },
            },
        )
    )
    respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-outcomes"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "persisted_count": len(plan.timeline),
                "outcome_ids": ["outcome-1"],
            },
        )
    )

    result = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key="execute-disputed-fraud-001",
            default_card_token="tok_disputed_fraud",
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    customer_action = next(
        step for step in result.steps if step.event_type == "customer_action"
    )
    assert customer_action.status == ScenarioStepStatus.SUCCEEDED
    assert customer_action.resolution == "triaged"
    payload = json.loads(action_route.calls[0].request.content.decode())
    assert payload["fraud_alert_id"] == "alert-fraud-1"
    assert payload["outcome_label"] == "customer_disputed"
    assert payload["disputed_authorization_ids"] == ["auth-fraud-1", "auth-fraud-2"]
    assert payload["issue_replacement"] is True


@pytest.mark.asyncio
@respx.mock
async def test_customer_action_unresolved_keeps_alert_open():
    plan = plan_scenario(
        ScenarioRequest(
            goal="Create a fraud story for a traveling executive.",
            scenario_type=ScenarioType.FRAUD_TRAVEL_STORY,
        )
    )
    plan.timeline[-1].outcome_label = OutcomeLabel.UNRESOLVED
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize").mock(
        return_value=httpx.Response(
            200,
            json={
                "action_code": "00",
                "authorization_id": "auth-unresolved-1",
                "fraud_alert_id": "alert-open-1",
            },
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/settle").mock(
        return_value=httpx.Response(
            200, json={"status": "SETTLED", "transaction_id": "txn-open-1"}
        )
    )
    respx.post(f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse").mock(
        return_value=httpx.Response(200, json={"status": "REVERSED"})
    )
    action_route = respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-action"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "message": "Scenario outcome intentionally left the fraud alert open.",
                "outcome": "UNRESOLVED",
                "fraud_alert": {"fraud_alert_id": "alert-open-1", "status": "OPEN"},
            },
        )
    )
    respx.post(
        f"{BANKING_SERVICE_URL}/api/v1/credit-card/fraud-alert/scenario-outcomes"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "persisted_count": len(plan.timeline),
                "outcome_ids": ["outcome-1"],
            },
        )
    )

    result = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key="execute-unresolved-001",
            default_card_token="tok_unresolved",
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={"X-Card-Network-Token": "test"},
    )

    customer_action = next(
        step for step in result.steps if step.event_type == "customer_action"
    )
    assert customer_action.status == ScenarioStepStatus.SUCCEEDED
    assert customer_action.resolution == "unresolved"
    payload = json.loads(action_route.calls[0].request.content.decode())
    assert payload["outcome_label"] == "unresolved"
