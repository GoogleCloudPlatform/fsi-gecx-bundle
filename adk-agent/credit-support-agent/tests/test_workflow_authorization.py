from agent.workflow_authorization import (
    TRIAGE_CUSTOMER_REPORTED_FRAUD,
    TRIAGE_FRAUD_CASE,
    action_payload_fingerprint,
    authorize_from_model_tool_intent,
    create_workflow_authorization,
    mark_authorization_completed,
    mark_authorization_executing,
    mark_authorization_presented,
    validate_workflow_authorization,
)


def triage_payload(*, disputed_ids=None) -> dict:
    return {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": disputed_ids or ["auth-2", "auth-1"],
        "disputed_transaction_ids": ["txn-1"],
        "issue_replacement": True,
    }


def pending_authorization(*, now=1000.0, payload=None, action=TRIAGE_FRAUD_CASE):
    payload = payload or triage_payload()
    authorization = create_workflow_authorization(
        action=action,
        payload=payload,
        session_id="session-1",
        originating_customer_event_id="customer-origin",
        now_epoch_s=now,
        ttl_seconds=60,
    )
    return mark_authorization_presented(
        authorization,
        assistant_event_id="assistant-presentation",
        now_epoch_s=now + 1,
    )


def confirmed_authorization(*, now=1000.0, payload=None) -> dict:
    payload = payload or triage_payload()
    return authorize_from_model_tool_intent(
        pending_authorization(now=now, payload=payload),
        action=TRIAGE_FRAUD_CASE,
        payload=payload,
        session_id="session-1",
        customer_event_id="customer-confirmation",
        customer_observed_at_epoch_s=now + 2,
        now_epoch_s=now + 2,
    )


def test_payload_fingerprint_is_stable_for_reordered_selection() -> None:
    first = triage_payload(disputed_ids=["auth-2", "auth-1"])
    second = triage_payload(disputed_ids=["auth-1", "auth-2", "auth-1"])

    assert action_payload_fingerprint(
        TRIAGE_FRAUD_CASE, first
    ) == action_payload_fingerprint(TRIAGE_FRAUD_CASE, second)


def test_model_tool_intent_confirms_exact_presented_proposal_on_later_turn() -> None:
    authorization = confirmed_authorization()

    assert authorization["status"] == "CONFIRMED"
    assert authorization["confirmation_source"] == "MODEL_TOOL_INTENT"
    assert authorization["customer_event_id"] == "customer-confirmation"
    assert (
        validate_workflow_authorization(
            authorization,
            action=TRIAGE_FRAUD_CASE,
            payload=triage_payload(disputed_ids=["auth-1", "auth-2"]),
            session_id="session-1",
            now_epoch_s=1003.0,
        )
        is None
    )


def test_raw_transcript_is_not_an_authorization_input() -> None:
    authorization = pending_authorization()

    assert "transcript" not in authorize_from_model_tool_intent.__annotations__
    assert authorization["status"] == "PENDING"


def test_originating_or_pre_presentation_turn_cannot_confirm() -> None:
    pending = pending_authorization()
    same_turn = authorize_from_model_tool_intent(
        pending,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        customer_event_id="customer-origin",
        customer_observed_at_epoch_s=1002.0,
        now_epoch_s=1002.0,
    )
    earlier_turn = authorize_from_model_tool_intent(
        pending,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        customer_event_id="customer-earlier",
        customer_observed_at_epoch_s=1000.5,
        now_epoch_s=1002.0,
    )

    assert same_turn["status"] == "PENDING"
    assert earlier_turn["status"] == "PENDING"


def test_unpresented_authorization_cannot_confirm() -> None:
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        originating_customer_event_id="customer-origin",
        now_epoch_s=1000.0,
    )

    updated = authorize_from_model_tool_intent(
        authorization,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        customer_event_id="customer-confirmation",
        customer_observed_at_epoch_s=1002.0,
        now_epoch_s=1002.0,
    )

    assert updated["status"] == "PREPARED"


def test_changed_payload_or_session_cannot_confirm() -> None:
    pending = pending_authorization()
    changed_payload = authorize_from_model_tool_intent(
        pending,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(disputed_ids=["auth-1"]),
        session_id="session-1",
        customer_event_id="customer-confirmation",
        customer_observed_at_epoch_s=1002.0,
        now_epoch_s=1002.0,
    )
    changed_session = authorize_from_model_tool_intent(
        pending,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-2",
        customer_event_id="customer-confirmation",
        customer_observed_at_epoch_s=1002.0,
        now_epoch_s=1002.0,
    )

    assert changed_payload["status"] == "PENDING"
    assert changed_session["status"] == "PENDING"


def test_customer_reported_authorization_is_exact_selection_bound() -> None:
    payload = {
        "disputed_authorization_ids": ["auth-2", "auth-1"],
        "disputed_transaction_ids": ["txn-1"],
        "issue_replacement": True,
        "escalate": False,
    }
    pending = pending_authorization(
        payload=payload,
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
    )
    authorization = authorize_from_model_tool_intent(
        pending,
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
        payload=payload,
        session_id="session-1",
        customer_event_id="customer-confirmation",
        customer_observed_at_epoch_s=1002.0,
        now_epoch_s=1002.0,
    )

    assert (
        validate_workflow_authorization(
            authorization,
            action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
            payload={**payload, "disputed_authorization_ids": ["auth-1", "auth-2"]},
            session_id="session-1",
            now_epoch_s=1003.0,
        )
        is None
    )
    assert "differs from the exact payload" in validate_workflow_authorization(
        authorization,
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
        payload={**payload, "disputed_transaction_ids": ["txn-2"]},
        session_id="session-1",
        now_epoch_s=1003.0,
    )


def test_expired_authorization_cannot_confirm_or_execute() -> None:
    expired = authorize_from_model_tool_intent(
        pending_authorization(),
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        customer_event_id="customer-confirmation",
        customer_observed_at_epoch_s=1061.0,
        now_epoch_s=1061.0,
    )

    assert expired["status"] == "EXPIRED"
    assert "not confirmed" in validate_workflow_authorization(
        expired,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=1061.0,
    )


def test_authorization_is_consumed_and_completed_once() -> None:
    authorization = confirmed_authorization()
    executing = mark_authorization_executing(authorization, now_epoch_s=1003.0)
    completed = mark_authorization_completed(executing, now_epoch_s=1004.0)

    assert executing["status"] == "EXECUTING"
    assert completed["status"] == "COMPLETED"
    assert (
        validate_workflow_authorization(
            completed,
            action=TRIAGE_FRAUD_CASE,
            payload=triage_payload(),
            session_id="session-1",
            now_epoch_s=1005.0,
        )
        == "Customer authorization for TRIAGE_FRAUD_CASE is not confirmed."
    )
