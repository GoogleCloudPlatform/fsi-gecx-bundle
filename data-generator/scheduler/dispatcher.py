from __future__ import annotations

from typing import Any

import httpx

from scenarios.executor import (
    _execute_customer_action,
    _persist_scenario_outcomes,
    _settle_authorization,
    _reverse_authorization,
)
from scenarios.schemas import OutcomeLabel, PlannedEventType, ScenarioOutcome

from .client import SyntheticScheduleClient
from .schemas import ScheduledEventDispatchResult, ScheduledEventRecord


def _latest_auth_context(context: dict[str, Any], *, persona_id: str | None) -> dict[str, Any]:
    events = context.get("events", [])
    for event in reversed(events):
        if persona_id and event.get("persona_id") != persona_id:
            continue
        result = event.get("result_payload") or {}
        if event.get("event_type") == "authorization" and result.get("authorization_id"):
            return result
    return {}


def _outcome_from_payload(
    *,
    event: ScheduledEventRecord,
    auth_context: dict[str, Any],
    execution_id: str,
) -> ScenarioOutcome | None:
    payload = event.payload or {}
    outcome_label = payload.get("outcome_label") or auth_context.get("outcome_label")
    if not outcome_label or outcome_label == "not_applicable":
        return None
    auth_payload = auth_context.get("authorization") or auth_context
    reason_codes = auth_payload.get("fraud_reason_codes") or auth_payload.get("reason_codes") or []
    if isinstance(reason_codes, str):
        reason_codes = [reason_codes]
    risk_score = auth_payload.get("fraud_risk_score") or auth_payload.get("risk_score")
    try:
        risk_score = int(risk_score) if risk_score is not None else None
    except (TypeError, ValueError):
        risk_score = None
    return ScenarioOutcome(
        scenario_id=event.scenario_id or event.schedule_id,
        execution_id=execution_id,
        event_id=event.event_id,
        authorization_id=auth_context.get("authorization_id"),
        transaction_id=auth_context.get("transaction_id"),
        fraud_alert_id=auth_context.get("fraud_alert_id"),
        card_token=auth_context.get("card_token"),
        outcome_label=OutcomeLabel(outcome_label),
        expected_reason_codes=payload.get("expected_reason_codes") or [],
        actual_reason_codes=reason_codes,
        expected_score_band=payload.get("expected_score_band"),
        actual_risk_score=risk_score,
        model_version=auth_payload.get("fraud_model_version"),
        created_at=payload.get("created_at") or event.scheduled_for.isoformat(),
    )


async def dispatch_scheduled_event(
    *,
    event: ScheduledEventRecord,
    schedule_client: SyntheticScheduleClient,
    banking_service_url: str,
    headers: dict[str, str],
    timeout_seconds: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> ScheduledEventDispatchResult:
    if event.status == "SUCCEEDED":
        return ScheduledEventDispatchResult(
            event_record_id=event.id,
            schedule_id=event.schedule_id,
            event_id=event.event_id,
            event_type=str(event.event_type),
            status="SUCCEEDED",
            message="Scheduled event was already completed.",
            result_payload=event.result_payload,
        )
    if event.status == "CANCELED":
        return ScheduledEventDispatchResult(
            event_record_id=event.id,
            schedule_id=event.schedule_id,
            event_id=event.event_id,
            event_type=str(event.event_type),
            status="CANCELED",
            message="Scheduled event was canceled.",
            result_payload=event.result_payload,
        )

    marked = await schedule_client.mark_dispatching(event.id)
    payload = dict(marked.payload or {})
    owns_client = client is None
    active_client = client or httpx.AsyncClient()
    try:
        if marked.event_type == "authorization":
            response = await active_client.post(
                f"{banking_service_url}/api/v1/card-network/authorize",
                json=payload["authorization_payload"],
                headers=headers,
                timeout=timeout_seconds,
            )
            response_payload = response.json()
            ok = response.status_code == 200 and response_payload.get("action_code") == "00"
            result_payload = {
                "authorization": response_payload,
                "authorization_id": response_payload.get("authorization_id")
                or response_payload.get("id"),
                "fraud_alert_id": response_payload.get("fraud_alert_id"),
                "retrieval_reference_number": payload["authorization_payload"].get(
                    "retrieval_reference_number"
                ),
                "card_token": payload["authorization_payload"].get("card_token"),
                "outcome_label": payload.get("outcome_label"),
                "status_code": response.status_code,
            }
            if not ok:
                await schedule_client.mark_failed(
                    marked.id,
                    error="Authorization declined or failed.",
                    result_payload=result_payload,
                )
                return ScheduledEventDispatchResult(
                    event_record_id=marked.id,
                    schedule_id=marked.schedule_id,
                    event_id=marked.event_id,
                    event_type=marked.event_type,
                    status="FAILED",
                    message="Authorization declined or failed.",
                    result_payload=result_payload,
                )

        elif marked.event_type == "settlement":
            context = await schedule_client.get_context(
                schedule_id=marked.schedule_id, persona_id=marked.persona_id
            )
            auth_context = _latest_auth_context(context, persona_id=marked.persona_id)
            ok, settle_payload, status_code = await _settle_authorization(
                active_client,
                banking_service_url=banking_service_url,
                headers=headers,
                rrn=auth_context["retrieval_reference_number"],
                amount_cents=payload["amount_cents"],
                timeout_seconds=timeout_seconds,
            )
            result_payload = {
                **auth_context,
                "settlement": settle_payload,
                "transaction_id": settle_payload.get("transaction_id")
                or settle_payload.get("id"),
                "status_code": status_code,
            }
            if not ok:
                raise RuntimeError("Settlement failed.")

        elif marked.event_type == "reversal":
            context = await schedule_client.get_context(
                schedule_id=marked.schedule_id, persona_id=marked.persona_id
            )
            auth_context = _latest_auth_context(context, persona_id=marked.persona_id)
            ok, reverse_payload, status_code = await _reverse_authorization(
                active_client,
                banking_service_url=banking_service_url,
                headers=headers,
                rrn=auth_context["retrieval_reference_number"],
                timeout_seconds=timeout_seconds,
            )
            result_payload = {
                **auth_context,
                "reversal": reverse_payload,
                "status_code": status_code,
            }
            if not ok:
                raise RuntimeError("Reversal failed.")

        elif marked.event_type == "customer_action":
            context = await schedule_client.get_context(
                schedule_id=marked.schedule_id, persona_id=marked.persona_id
            )
            auth_context = dict(payload.get("auth_context") or {})
            if not auth_context:
                auth_context = _latest_auth_context(context, persona_id=marked.persona_id)
            fraud_alert_id = auth_context.get("fraud_alert_id")
            if not fraud_alert_id:
                raise RuntimeError("Customer action has no prior fraud alert.")
            outcome_label = OutcomeLabel(payload.get("outcome_label", "unresolved"))
            synthetic_event = type(
                "SyntheticEvent",
                (),
                {
                    "event_id": marked.event_id,
                    "event_type": PlannedEventType.CUSTOMER_ACTION,
                    "outcome_label": outcome_label,
                },
            )()
            ok, action_payload, status_code = await _execute_customer_action(
                active_client,
                banking_service_url=banking_service_url,
                headers=headers,
                scenario_id=marked.scenario_id or marked.schedule_id,
                execution_id=marked.execution_id or marked.schedule_id,
                event=synthetic_event,
                fraud_alert_id=fraud_alert_id,
                disputed_authorization_ids=[auth_context["authorization_id"]]
                if auth_context.get("authorization_id")
                else [],
                timeout_seconds=timeout_seconds,
            )
            result_payload = {
                **auth_context,
                "customer_action": action_payload,
                "outcome_label": outcome_label.value,
                "status_code": status_code,
            }
            outcome = _outcome_from_payload(
                event=marked,
                auth_context=result_payload,
                execution_id=marked.execution_id or marked.schedule_id,
            )
            if outcome:
                await _persist_scenario_outcomes(
                    active_client,
                    banking_service_url=banking_service_url,
                    headers=headers,
                    outcomes=[outcome],
                    steps=[],
                    timeout_seconds=timeout_seconds,
                )
            if not ok:
                raise RuntimeError("Customer action failed.")

        else:
            raise RuntimeError(f"Unsupported scheduled event type: {marked.event_type}")

        completed = await schedule_client.mark_succeeded(marked.id, result_payload)
        return ScheduledEventDispatchResult(
            event_record_id=completed.id,
            schedule_id=completed.schedule_id,
            event_id=completed.event_id,
            event_type=str(completed.event_type),
            status="SUCCEEDED",
            message="Scheduled event dispatched.",
            result_payload=completed.result_payload,
        )
    except Exception as exc:
        failed = await schedule_client.mark_failed(
            marked.id,
            error=str(exc),
            result_payload=locals().get("result_payload", {}),
        )
        return ScheduledEventDispatchResult(
            event_record_id=failed.id,
            schedule_id=failed.schedule_id,
            event_id=failed.event_id,
            event_type=str(failed.event_type),
            status="FAILED",
            message=str(exc),
            result_payload=failed.result_payload,
        )
    finally:
        if owns_client:
            await active_client.aclose()
