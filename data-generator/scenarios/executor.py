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

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from .schemas import (
    PlannedCardEvent,
    PlannedEventType,
    ScenarioExecutionRequest,
    ScenarioExecutionResult,
    ScenarioExecutionStatus,
    ScenarioMode,
    ScenarioStepResult,
    ScenarioStepStatus,
)

_EXECUTION_CACHE: dict[str, ScenarioExecutionResult] = {}


def clear_execution_cache() -> None:
    _EXECUTION_CACHE.clear()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _execution_id(scenario_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{scenario_id}|{idempotency_key}".encode("utf-8")).hexdigest()[:16]
    return f"scenario-exec-{digest}"


def _rrn(scenario_id: str, event_id: str) -> str:
    digest = hashlib.sha256(f"{scenario_id}|{event_id}".encode("utf-8")).hexdigest()
    digits = "".join(str(int(char, 16) % 10) for char in digest)
    return digits[:12]


def _auth_payload(event: PlannedCardEvent, scenario_id: str, default_card_token: str | None) -> dict[str, Any]:
    if not event.merchant_context:
        raise ValueError("authorization events require merchant_context")
    if event.amount_cents is None:
        raise ValueError("authorization events require amount_cents")

    merchant = event.merchant_context
    return {
        "card_token": default_card_token or "SCENARIO_CARD_TOKEN_REQUIRED",
        "amount_cents": event.amount_cents,
        "retrieval_reference_number": _rrn(scenario_id, event.event_id),
        "merchant_category_code": merchant.mcc,
        "merchant_name": merchant.merchant_name_hint or f"SCENARIO {merchant.category}".upper(),
        "card_network": "VISA",
        "transaction_channel": merchant.transaction_channel,
        "entry_mode": merchant.entry_mode,
        "merchant_country_code": merchant.country_code,
        "merchant_city": merchant.city,
        "merchant_region": merchant.region,
        "merchant_latitude": merchant.latitude,
        "merchant_longitude": merchant.longitude,
        "ip_country_code": merchant.ip_country_code,
        "shipping_country_code": merchant.shipping_country_code,
        "is_digital_goods": merchant.is_digital_goods,
        "merchant_high_risk_flags": merchant.high_risk_flags,
        "synthetic_scenario_id": scenario_id,
        "synthetic_event_id": event.event_id,
        "synthetic_outcome_label": event.outcome_label.value if event.outcome_label else None,
    }


def _dry_run_step(event: PlannedCardEvent) -> ScenarioStepResult:
    return ScenarioStepResult(
        event_id=event.event_id,
        event_type=event.event_type,
        status=ScenarioStepStatus.PLANNED,
        message="Dry run only; no data written.",
        outcome_label=event.outcome_label,
    )


async def execute_scenario(
    request: ScenarioExecutionRequest,
    *,
    banking_service_url: str,
    headers: dict[str, str],
    default_card_token: str | None = None,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 10.0,
) -> ScenarioExecutionResult:
    cache_key = request.idempotency_key
    if cache_key in _EXECUTION_CACHE:
        cached = _EXECUTION_CACHE[cache_key]
        return cached.model_copy(
            update={
                "warnings": [*cached.warnings, "Duplicate idempotency key; returning cached scenario execution result."],
            }
        )

    plan = request.plan
    mode = request.mode or plan.mode
    started_at = _now_iso()
    execution_id = _execution_id(plan.scenario_id, request.idempotency_key)

    if mode == ScenarioMode.DRY_RUN:
        completed_at = _now_iso()
        result = ScenarioExecutionResult(
            scenario_id=plan.scenario_id,
            execution_id=execution_id,
            idempotency_key=request.idempotency_key,
            mode=mode,
            status=ScenarioExecutionStatus.DRY_RUN,
            operator=request.operator,
            started_at=started_at,
            completed_at=completed_at,
            planned_events=len(plan.timeline),
            attempted_events=0,
            succeeded_events=0,
            skipped_events=len(plan.timeline),
            failed_events=0,
            steps=[_dry_run_step(event) for event in plan.timeline],
            warnings=plan.warnings,
        )
        _EXECUTION_CACHE[cache_key] = result
        return result

    if plan.scenario_type.value == "unknown_request":
        completed_at = _now_iso()
        result = ScenarioExecutionResult(
            scenario_id=plan.scenario_id,
            execution_id=execution_id,
            idempotency_key=request.idempotency_key,
            mode=mode,
            status=ScenarioExecutionStatus.SKIPPED,
            operator=request.operator,
            started_at=started_at,
            completed_at=completed_at,
            planned_events=len(plan.timeline),
            attempted_events=0,
            succeeded_events=0,
            skipped_events=len(plan.timeline),
            failed_events=0,
            warnings=[*plan.warnings, "Unknown scenario requests are not executable."],
        )
        _EXECUTION_CACHE[cache_key] = result
        return result

    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    steps: list[ScenarioStepResult] = []

    try:
        for event in plan.timeline:
            if event.event_type != PlannedEventType.AUTHORIZATION:
                steps.append(
                    ScenarioStepResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status=ScenarioStepStatus.SKIPPED,
                        message=f"{event.event_type.value} execution is staged for a later story.",
                        outcome_label=event.outcome_label,
                    )
                )
                continue

            payload = _auth_payload(event, plan.scenario_id, default_card_token or request.default_card_token)
            try:
                response = await active_client.post(
                    f"{banking_service_url}/api/v1/card-network/authorize",
                    json=payload,
                    headers=headers,
                    timeout=timeout_seconds,
                )
            except httpx.RequestError as exc:
                steps.append(
                    ScenarioStepResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status=ScenarioStepStatus.FAILED,
                        message=f"Authorization request failed: {exc}",
                        retrieval_reference_number=payload["retrieval_reference_number"],
                        outcome_label=event.outcome_label,
                    )
                )
                continue

            response_payload = None
            try:
                response_payload = response.json()
            except ValueError:
                response_payload = {"raw": response.text}

            if response.status_code != 200:
                steps.append(
                    ScenarioStepResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status=ScenarioStepStatus.FAILED,
                        message=f"Authorization failed with HTTP {response.status_code}.",
                        retrieval_reference_number=payload["retrieval_reference_number"],
                        status_code=response.status_code,
                        response_payload=response_payload,
                        outcome_label=event.outcome_label,
                    )
                )
                continue

            action_code = response_payload.get("action_code")
            step_status = ScenarioStepStatus.SUCCEEDED if action_code == "00" else ScenarioStepStatus.SKIPPED
            steps.append(
                ScenarioStepResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=step_status,
                    message="Authorization created." if action_code == "00" else "Authorization declined or skipped.",
                    retrieval_reference_number=payload["retrieval_reference_number"],
                    authorization_id=response_payload.get("authorization_id") or response_payload.get("id"),
                    status_code=response.status_code,
                    response_payload=response_payload,
                    outcome_label=event.outcome_label,
                )
            )
    finally:
        if owns_client:
            await active_client.aclose()

    succeeded = [step for step in steps if step.status == ScenarioStepStatus.SUCCEEDED]
    failed = [step for step in steps if step.status == ScenarioStepStatus.FAILED]
    skipped = [step for step in steps if step.status == ScenarioStepStatus.SKIPPED]
    status = (
        ScenarioExecutionStatus.FAILED
        if failed and not succeeded
        else ScenarioExecutionStatus.PARTIAL
        if failed or skipped
        else ScenarioExecutionStatus.SUCCEEDED
    )
    result = ScenarioExecutionResult(
        scenario_id=plan.scenario_id,
        execution_id=execution_id,
        idempotency_key=request.idempotency_key,
        mode=mode,
        status=status,
        operator=request.operator,
        started_at=started_at,
        completed_at=_now_iso(),
        planned_events=len(plan.timeline),
        attempted_events=sum(1 for step in steps if step.event_type == PlannedEventType.AUTHORIZATION),
        succeeded_events=len(succeeded),
        skipped_events=len(skipped),
        failed_events=len(failed),
        created_authorization_ids=[step.authorization_id for step in succeeded if step.authorization_id],
        steps=steps,
        warnings=plan.warnings,
    )
    _EXECUTION_CACHE[cache_key] = result
    return result


def scenario_execution_idempotency_key(plan_id: str) -> str:
    return f"scenario:{plan_id}:{uuid.uuid4().hex}"
