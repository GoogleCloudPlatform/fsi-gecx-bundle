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
    BehaviorPolicy,
    PlannedCardEvent,
    PlannedEventType,
    ScenarioExecutionRequest,
    ScenarioExecutionResult,
    ScenarioExecutionStatus,
    ScenarioMode,
    ScenarioOutcome,
    ScenarioStepResult,
    ScenarioStepStatus,
)

_EXECUTION_CACHE: dict[str, ScenarioExecutionResult] = {}
_OUTCOME_CACHE: dict[str, list[ScenarioOutcome]] = {}


def clear_execution_cache() -> None:
    _EXECUTION_CACHE.clear()
    _OUTCOME_CACHE.clear()


def list_scenario_outcomes(scenario_id: str) -> list[ScenarioOutcome]:
    return list(_OUTCOME_CACHE.get(scenario_id, []))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _execution_id(scenario_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(
        f"{scenario_id}|{idempotency_key}".encode("utf-8")
    ).hexdigest()[:16]
    return f"scenario-exec-{digest}"


def _rrn(scenario_id: str, event_id: str) -> str:
    digest = hashlib.sha256(f"{scenario_id}|{event_id}".encode("utf-8")).hexdigest()
    digits = "".join(str(int(char, 16) % 10) for char in digest)
    return digits[:12]


def _fraction(scenario_id: str, event_id: str, salt: str) -> float:
    digest = hashlib.sha256(
        f"{scenario_id}|{event_id}|{salt}".encode("utf-8")
    ).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def _card_token_for_event(
    event: PlannedCardEvent,
    *,
    scenario_id: str,
    request: ScenarioExecutionRequest,
    fallback_card_token: str | None,
) -> str:
    tokens = request.default_card_tokens or (
        [request.default_card_token] if request.default_card_token else []
    )
    if not tokens and fallback_card_token:
        tokens = [fallback_card_token]
    if not tokens:
        return "SCENARIO_CARD_TOKEN_REQUIRED"
    index = int(
        hashlib.sha256(
            f"{scenario_id}|{event.event_id}|card".encode("utf-8")
        ).hexdigest()[:8],
        16,
    ) % len(tokens)
    return tokens[index]


def _auth_payload(
    event: PlannedCardEvent, scenario_id: str, card_token: str
) -> dict[str, Any]:
    if not event.merchant_context:
        raise ValueError("authorization events require merchant_context")
    if event.amount_cents is None:
        raise ValueError("authorization events require amount_cents")

    merchant = event.merchant_context
    return {
        "card_token": card_token,
        "amount_cents": event.amount_cents,
        "retrieval_reference_number": _rrn(scenario_id, event.event_id),
        "merchant_category_code": merchant.mcc,
        "merchant_name": merchant.merchant_name_hint
        or f"SCENARIO {merchant.category}".upper(),
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
        "synthetic_outcome_label": event.outcome_label.value
        if event.outcome_label
        else None,
    }


def _dry_run_step(event: PlannedCardEvent) -> ScenarioStepResult:
    return ScenarioStepResult(
        event_id=event.event_id,
        event_type=event.event_type,
        status=ScenarioStepStatus.PLANNED,
        message="Dry run only; no data written.",
        outcome_label=event.outcome_label,
    )


def _outcome_from_step(
    *,
    scenario_id: str,
    execution_id: str,
    event: PlannedCardEvent,
    step: ScenarioStepResult,
    card_token: str | None,
) -> ScenarioOutcome | None:
    if not step.outcome_label or step.outcome_label.value == "not_applicable":
        return None
    payload = step.response_payload or {}
    authorization_payload = (
        payload.get("authorization")
        if isinstance(payload.get("authorization"), dict)
        else payload
    )
    actual_reason_codes = (
        authorization_payload.get("fraud_reason_codes")
        or authorization_payload.get("reason_codes")
        or []
    )
    if isinstance(actual_reason_codes, str):
        actual_reason_codes = [actual_reason_codes]
    actual_risk_score = authorization_payload.get(
        "fraud_risk_score"
    ) or authorization_payload.get("risk_score")
    try:
        actual_risk_score = (
            int(actual_risk_score) if actual_risk_score is not None else None
        )
    except (TypeError, ValueError):
        actual_risk_score = None
    return ScenarioOutcome(
        scenario_id=scenario_id,
        execution_id=execution_id,
        event_id=event.event_id,
        authorization_id=step.authorization_id,
        transaction_id=step.transaction_id,
        fraud_alert_id=step.alert_id,
        card_token=card_token,
        outcome_label=step.outcome_label,
        expected_reason_codes=event.expected_reason_codes,
        actual_reason_codes=list(actual_reason_codes),
        expected_score_band=event.expected_score_band,
        actual_risk_score=actual_risk_score,
        model_version=authorization_payload.get("fraud_model_version"),
        created_at=_now_iso(),
    )


def _policy_for_event(
    event: PlannedCardEvent, policies: list[BehaviorPolicy]
) -> BehaviorPolicy:
    for policy in policies:
        if event.persona_id in policy.policy_id:
            return policy
    return policies[0]


def _resolution_for_event(
    event: PlannedCardEvent, plan_id: str, policy: BehaviorPolicy
) -> str:
    value = _fraction(plan_id, event.event_id, "resolution")
    if value < policy.settlement_probability:
        return "settled"
    if value < policy.settlement_probability + policy.reversal_probability:
        return "reversed"
    return "pending"


async def _settle_authorization(
    client: httpx.AsyncClient,
    *,
    banking_service_url: str,
    headers: dict[str, str],
    rrn: str,
    amount_cents: int,
    timeout_seconds: float,
) -> tuple[bool, dict[str, Any], int]:
    try:
        response = await client.post(
            f"{banking_service_url}/api/v1/card-network/settle",
            json={"retrieval_reference_number": rrn, "amount_cents": amount_cents},
            headers=headers,
            timeout=timeout_seconds,
        )
    except httpx.RequestError as exc:
        return False, {"detail": f"Settlement request failed: {exc}"}, 0
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return response.status_code == 200, payload, response.status_code


async def _reverse_authorization(
    client: httpx.AsyncClient,
    *,
    banking_service_url: str,
    headers: dict[str, str],
    rrn: str,
    timeout_seconds: float,
) -> tuple[bool, dict[str, Any], int]:
    try:
        response = await client.post(
            f"{banking_service_url}/api/v1/card-network/reverse",
            json={"retrieval_reference_number": rrn},
            headers=headers,
            timeout=timeout_seconds,
        )
    except httpx.RequestError as exc:
        return False, {"detail": f"Reversal request failed: {exc}"}, 0
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return response.status_code == 200, payload, response.status_code


def _customer_action_resolution(event: PlannedCardEvent) -> str:
    if not event.outcome_label:
        return "skipped"
    if event.outcome_label.value in {"false_positive", "confirmed_legitimate"}:
        return "recognized"
    if event.outcome_label.value in {
        "customer_disputed",
        "confirmed_fraud",
        "expected_fraud",
    }:
        return "triaged"
    if event.outcome_label.value == "unresolved":
        return "unresolved"
    return "skipped"


async def _execute_customer_action(
    client: httpx.AsyncClient,
    *,
    banking_service_url: str,
    headers: dict[str, str],
    scenario_id: str,
    execution_id: str,
    event: PlannedCardEvent,
    fraud_alert_id: str,
    disputed_authorization_ids: list[str],
    timeout_seconds: float,
) -> tuple[bool, dict[str, Any], int]:
    should_dispute = bool(
        event.outcome_label
        and event.outcome_label.value
        in {"customer_disputed", "confirmed_fraud", "expected_fraud"}
    )
    disputed_authorization_ids = (
        list(dict.fromkeys(disputed_authorization_ids)) if should_dispute else []
    )
    response = await client.post(
        f"{banking_service_url}/api/v1/credit-card/fraud-alert/scenario-action",
        json={
            "fraud_alert_id": fraud_alert_id,
            "outcome_label": event.outcome_label.value
            if event.outcome_label
            else "not_applicable",
            "disputed_authorization_ids": disputed_authorization_ids,
            "disputed_transaction_ids": [],
            "issue_replacement": should_dispute,
            "escalate": event.outcome_label.value == "confirmed_fraud"
            if event.outcome_label
            else False,
            "idempotency_key": f"{scenario_id}:{execution_id}:{event.event_id}",
        },
        headers=headers,
        timeout=timeout_seconds,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return (
        response.status_code == 200 and bool(payload.get("success")),
        payload,
        response.status_code,
    )


async def _persist_scenario_outcomes(
    client: httpx.AsyncClient,
    *,
    banking_service_url: str,
    headers: dict[str, str],
    outcomes: list[ScenarioOutcome],
    steps: list[ScenarioStepResult],
    timeout_seconds: float,
) -> tuple[bool, dict[str, Any], int | None]:
    if not outcomes:
        return True, {"success": True, "persisted_count": 0}, None

    operational_status_by_event = {
        step.event_id: {
            "action": step.resolution,
            "status": step.response_payload.get("outcome")
            if step.response_payload
            else step.status.value,
        }
        for step in steps
        if step.event_type == PlannedEventType.CUSTOMER_ACTION
    }
    response = await client.post(
        f"{banking_service_url}/api/v1/credit-card/fraud-alert/scenario-outcomes",
        json={
            "outcomes": [outcome.model_dump(mode="json") for outcome in outcomes],
            "operational_status_by_event": operational_status_by_event,
        },
        headers=headers,
        timeout=timeout_seconds,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}
    return (
        response.status_code == 200 and bool(payload.get("success")),
        payload,
        response.status_code,
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
                "warnings": [
                    *cached.warnings,
                    "Duplicate idempotency key; returning cached scenario execution result.",
                ],
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
    outcome_events: list[tuple[PlannedCardEvent, ScenarioStepResult, str | None]] = []
    latest_alert_by_persona: dict[str, str] = {}
    authorizations_by_alert: dict[str, list[str]] = {}
    card_token_by_persona: dict[str, str] = {}

    try:
        for event in plan.timeline:
            if event.event_type != PlannedEventType.AUTHORIZATION:
                if event.event_type == PlannedEventType.CUSTOMER_ACTION:
                    fraud_alert_id = latest_alert_by_persona.get(event.persona_id)
                    if not fraud_alert_id:
                        step = ScenarioStepResult(
                            event_id=event.event_id,
                            event_type=event.event_type,
                            status=ScenarioStepStatus.SKIPPED,
                            message="Customer action skipped because no prior fraud alert was created for this persona.",
                            outcome_label=event.outcome_label,
                            resolution="skipped",
                        )
                        steps.append(step)
                        outcome_events.append(
                            (event, step, card_token_by_persona.get(event.persona_id))
                        )
                        continue
                    try:
                        (
                            ok,
                            action_payload,
                            action_status_code,
                        ) = await _execute_customer_action(
                            active_client,
                            banking_service_url=banking_service_url,
                            headers=headers,
                            scenario_id=plan.scenario_id,
                            execution_id=execution_id,
                            event=event,
                            fraud_alert_id=fraud_alert_id,
                            disputed_authorization_ids=authorizations_by_alert.get(
                                fraud_alert_id, []
                            ),
                            timeout_seconds=timeout_seconds,
                        )
                    except httpx.RequestError as exc:
                        step = ScenarioStepResult(
                            event_id=event.event_id,
                            event_type=event.event_type,
                            status=ScenarioStepStatus.FAILED,
                            message=f"Customer action request failed: {exc}",
                            alert_id=fraud_alert_id,
                            outcome_label=event.outcome_label,
                            resolution="failed",
                        )
                        steps.append(step)
                        outcome_events.append(
                            (event, step, card_token_by_persona.get(event.persona_id))
                        )
                        continue

                    step = ScenarioStepResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status=ScenarioStepStatus.SUCCEEDED
                        if ok
                        else ScenarioStepStatus.FAILED,
                        message=action_payload.get("message")
                        or (
                            "Customer action executed."
                            if ok
                            else "Customer action failed."
                        ),
                        alert_id=fraud_alert_id,
                        status_code=action_status_code,
                        response_payload=action_payload,
                        outcome_label=event.outcome_label,
                        resolution=_customer_action_resolution(event)
                        if ok
                        else "failed",
                    )
                    steps.append(step)
                    outcome_events.append(
                        (event, step, card_token_by_persona.get(event.persona_id))
                    )
                    continue

                step = ScenarioStepResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=ScenarioStepStatus.SKIPPED,
                    message=f"{event.event_type.value} execution is staged for a later story.",
                    outcome_label=event.outcome_label,
                )
                steps.append(step)
                outcome_events.append((event, step, None))
                continue

            card_token = _card_token_for_event(
                event,
                scenario_id=plan.scenario_id,
                request=request,
                fallback_card_token=default_card_token,
            )
            card_token_by_persona[event.persona_id] = card_token
            payload = _auth_payload(event, plan.scenario_id, card_token)
            try:
                response = await active_client.post(
                    f"{banking_service_url}/api/v1/card-network/authorize",
                    json=payload,
                    headers=headers,
                    timeout=timeout_seconds,
                )
            except httpx.RequestError as exc:
                step = ScenarioStepResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=ScenarioStepStatus.FAILED,
                    message=f"Authorization request failed: {exc}",
                    retrieval_reference_number=payload["retrieval_reference_number"],
                    outcome_label=event.outcome_label,
                )
                steps.append(step)
                outcome_events.append((event, step, card_token))
                continue

            response_payload = None
            try:
                response_payload = response.json()
            except ValueError:
                response_payload = {"raw": response.text}

            if response.status_code != 200:
                step = ScenarioStepResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=ScenarioStepStatus.FAILED,
                    message=f"Authorization failed with HTTP {response.status_code}.",
                    retrieval_reference_number=payload["retrieval_reference_number"],
                    status_code=response.status_code,
                    response_payload=response_payload,
                    outcome_label=event.outcome_label,
                    resolution="failed",
                )
                steps.append(step)
                outcome_events.append((event, step, card_token))
                continue

            action_code = response_payload.get("action_code")
            if action_code != "00":
                step = ScenarioStepResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=ScenarioStepStatus.SKIPPED,
                    message="Authorization declined or skipped.",
                    retrieval_reference_number=payload["retrieval_reference_number"],
                    authorization_id=response_payload.get("authorization_id")
                    or response_payload.get("id"),
                    alert_id=response_payload.get("fraud_alert_id"),
                    status_code=response.status_code,
                    response_payload=response_payload,
                    outcome_label=event.outcome_label,
                    resolution="declined",
                )
                steps.append(step)
                outcome_events.append((event, step, card_token))
                continue

            policy = _policy_for_event(event, plan.behavior_policies)
            resolution = _resolution_for_event(event, plan.scenario_id, policy)
            resolution_payload = response_payload
            resolution_status_code = response.status_code
            transaction_id = None
            retrieval_reference_number = response_payload.get(
                "retrieval_reference_number"
            ) or payload["retrieval_reference_number"]
            authorization_id = response_payload.get(
                "authorization_id"
            ) or response_payload.get("id")
            alert_id = response_payload.get("fraud_alert_id")
            if alert_id:
                latest_alert_by_persona[event.persona_id] = alert_id
                if authorization_id:
                    authorizations_by_alert.setdefault(alert_id, []).append(
                        authorization_id
                    )

            if resolution == "settled":
                (
                    ok,
                    resolution_payload,
                    resolution_status_code,
                ) = await _settle_authorization(
                    active_client,
                    banking_service_url=banking_service_url,
                    headers=headers,
                    rrn=retrieval_reference_number,
                    amount_cents=event.amount_cents or payload["amount_cents"],
                    timeout_seconds=timeout_seconds,
                )
                if not ok:
                    step = ScenarioStepResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status=ScenarioStepStatus.FAILED,
                        message="Authorization created, but settlement failed.",
                        retrieval_reference_number=retrieval_reference_number,
                        authorization_id=authorization_id,
                        alert_id=alert_id,
                        status_code=resolution_status_code,
                        response_payload=resolution_payload,
                        outcome_label=event.outcome_label,
                        resolution="failed",
                    )
                    steps.append(step)
                    outcome_events.append((event, step, card_token))
                    continue
                transaction_id = resolution_payload.get(
                    "transaction_id"
                ) or resolution_payload.get("id")
            elif resolution == "reversed":
                (
                    ok,
                    resolution_payload,
                    resolution_status_code,
                ) = await _reverse_authorization(
                    active_client,
                    banking_service_url=banking_service_url,
                    headers=headers,
                    rrn=retrieval_reference_number,
                    timeout_seconds=timeout_seconds,
                )
                if not ok:
                    step = ScenarioStepResult(
                        event_id=event.event_id,
                        event_type=event.event_type,
                        status=ScenarioStepStatus.FAILED,
                        message="Authorization created, but reversal failed.",
                        retrieval_reference_number=retrieval_reference_number,
                        authorization_id=authorization_id,
                        alert_id=alert_id,
                        status_code=resolution_status_code,
                        response_payload=resolution_payload,
                        outcome_label=event.outcome_label,
                        resolution="failed",
                    )
                    steps.append(step)
                    outcome_events.append((event, step, card_token))
                    continue

            step = ScenarioStepResult(
                event_id=event.event_id,
                event_type=event.event_type,
                status=ScenarioStepStatus.SUCCEEDED,
                message=f"Authorization created and {resolution}.",
                retrieval_reference_number=retrieval_reference_number,
                authorization_id=authorization_id,
                transaction_id=transaction_id,
                alert_id=alert_id,
                status_code=resolution_status_code,
                response_payload={
                    **response_payload,
                    "resolution_payload": resolution_payload,
                },
                outcome_label=event.outcome_label,
                resolution=resolution,
            )
            steps.append(step)
            outcome_events.append((event, step, card_token))
        succeeded = [
            step for step in steps if step.status == ScenarioStepStatus.SUCCEEDED
        ]
        failed = [step for step in steps if step.status == ScenarioStepStatus.FAILED]
        skipped = [step for step in steps if step.status == ScenarioStepStatus.SKIPPED]
        status = (
            ScenarioExecutionStatus.FAILED
            if failed and not succeeded
            else ScenarioExecutionStatus.PARTIAL
            if failed or skipped
            else ScenarioExecutionStatus.SUCCEEDED
        )
        outcomes = [
            outcome
            for event, step, card_token in outcome_events
            if (
                outcome := _outcome_from_step(
                    scenario_id=plan.scenario_id,
                    execution_id=execution_id,
                    event=event,
                    step=step,
                    card_token=card_token,
                )
            )
        ]
        warnings = list(plan.warnings)
        if outcomes:
            try:
                (
                    ok,
                    persistence_payload,
                    persistence_status_code,
                ) = await _persist_scenario_outcomes(
                    active_client,
                    banking_service_url=banking_service_url,
                    headers=headers,
                    outcomes=outcomes,
                    steps=steps,
                    timeout_seconds=timeout_seconds,
                )
                if not ok:
                    warnings.append(
                        f"Scenario outcome persistence failed with HTTP {persistence_status_code}: {persistence_payload}"
                    )
            except Exception as exc:
                warnings.append(f"Scenario outcome persistence failed: {exc}")

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
            attempted_events=sum(
                1 for step in steps if step.event_type == PlannedEventType.AUTHORIZATION
            ),
            succeeded_events=len(succeeded),
            skipped_events=len(skipped),
            failed_events=len(failed),
            authorizations_created=sum(
                1
                for step in succeeded
                if step.event_type == PlannedEventType.AUTHORIZATION
            ),
            settlements_created=sum(
                1 for step in succeeded if step.resolution == "settled"
            ),
            reversals_created=sum(
                1 for step in succeeded if step.resolution == "reversed"
            ),
            pending_holds_created=sum(
                1 for step in succeeded if step.resolution == "pending"
            ),
            created_authorization_ids=[
                step.authorization_id for step in succeeded if step.authorization_id
            ],
            created_transaction_ids=[
                step.transaction_id for step in succeeded if step.transaction_id
            ],
            created_alert_ids=sorted(
                {step.alert_id for step in succeeded if step.alert_id}
            ),
            outcomes=outcomes,
            steps=steps,
            warnings=warnings,
        )
        _EXECUTION_CACHE[cache_key] = result
        _OUTCOME_CACHE.setdefault(plan.scenario_id, []).extend(outcomes)
        return result
    finally:
        if owns_client:
            await active_client.aclose()


def scenario_execution_idempotency_key(plan_id: str) -> str:
    return f"scenario:{plan_id}:{uuid.uuid4().hex}"
