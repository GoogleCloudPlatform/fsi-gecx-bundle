from agent.workflow_authorization import (
    TRIAGE_CUSTOMER_REPORTED_FRAUD,
    TRIAGE_FRAUD_CASE,
    action_payload_fingerprint,
    apply_customer_authorization_response,
    classify_confirmation_response,
    create_workflow_authorization,
    mark_authorization_completed,
    mark_authorization_executing,
    mark_authorization_prompted,
    validate_workflow_authorization,
)


def test_common_explicit_confirmation_phrases_are_recognized() -> None:
    for transcript in (
        "Correct",
        "That's correct.",
        "That’s correct.",
        "That is correct",
        "Exactly",
        "Affirmative",
        "Yes, that's correct",
        "Yeah, that'd be great, thanks",
        "That’d be perfect.",
        "I'd appreciate that.",
        "Let's do it.",
    ):
        assert classify_confirmation_response(transcript) == "CONFIRMED"


def triage_payload(*, disputed_ids=None) -> dict:
    return {
        "fraud_alert_id": "fraud-123",
        "disputed_authorization_ids": disputed_ids or ["auth-2", "auth-1"],
        "disputed_transaction_ids": ["txn-1"],
        "issue_replacement": True,
    }


def confirmed_authorization(*, now=1000.0, payload=None) -> dict:
    payload = payload or triage_payload()
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=payload,
        session_id="session-1",
        now_epoch_s=now,
        ttl_seconds=60,
    )
    authorization = mark_authorization_prompted(
        authorization,
        assistant_event_id="assistant-1",
        now_epoch_s=now + 1,
    )
    return apply_customer_authorization_response(
        authorization,
        transcript="Yes, that's right.",
        customer_event_id="customer-1",
        now_epoch_s=now + 2,
    )


def test_payload_fingerprint_is_stable_for_reordered_selection() -> None:
    first = triage_payload(disputed_ids=["auth-2", "auth-1"])
    second = triage_payload(disputed_ids=["auth-1", "auth-2", "auth-1"])

    assert action_payload_fingerprint(TRIAGE_FRAUD_CASE, first) == action_payload_fingerprint(
        TRIAGE_FRAUD_CASE, second
    )


def test_customer_reported_authorization_is_exact_selection_bound() -> None:
    payload = {
        "disputed_authorization_ids": ["auth-2", "auth-1"],
        "disputed_transaction_ids": ["txn-1"],
        "issue_replacement": True,
        "escalate": False,
    }
    authorization = create_workflow_authorization(
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
        payload=payload,
        session_id="session-1",
        now_epoch_s=1000.0,
    )
    authorization = mark_authorization_prompted(
        authorization,
        assistant_event_id="assistant-1",
        now_epoch_s=1001.0,
    )
    authorization = apply_customer_authorization_response(
        authorization,
        transcript="Yes, those are the charges.",
        customer_event_id="customer-1",
        now_epoch_s=1002.0,
    )

    assert validate_workflow_authorization(
        authorization,
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
        payload={**payload, "disputed_authorization_ids": ["auth-1", "auth-2"]},
        session_id="session-1",
        now_epoch_s=1003.0,
    ) is None
    assert "differs from the exact payload" in validate_workflow_authorization(
        authorization,
        action=TRIAGE_CUSTOMER_REPORTED_FRAUD,
        payload={**payload, "disputed_transaction_ids": ["txn-2"]},
        session_id="session-1",
        now_epoch_s=1003.0,
    )


def test_authorization_requires_separate_assistant_and_customer_turns() -> None:
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=1000.0,
    )

    error = validate_workflow_authorization(
        authorization,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=1001.0,
    )

    assert error == "Customer authorization for TRIAGE_FRAUD_CASE is not confirmed."


def test_confirmed_authorization_is_payload_and_session_bound() -> None:
    authorization = confirmed_authorization()

    assert validate_workflow_authorization(
        authorization,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(disputed_ids=["auth-1", "auth-2"]),
        session_id="session-1",
        now_epoch_s=1003.0,
    ) is None
    assert "different support session" in validate_workflow_authorization(
        authorization,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-2",
        now_epoch_s=1003.0,
    )


def test_changed_selection_cannot_reuse_confirmation() -> None:
    authorization = confirmed_authorization()
    changed = triage_payload(disputed_ids=["auth-1"])

    error = validate_workflow_authorization(
        authorization,
        action=TRIAGE_FRAUD_CASE,
        payload=changed,
        session_id="session-1",
        now_epoch_s=1003.0,
    )

    assert error == "The requested action differs from the exact payload the customer confirmed."


def test_expired_or_declined_authorization_cannot_execute() -> None:
    authorization = confirmed_authorization()
    expired_error = validate_workflow_authorization(
        authorization,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=1061.0,
    )
    declined = apply_customer_authorization_response(
        authorization,
        transcript="Actually no, that selection is wrong.",
        customer_event_id="customer-2",
        now_epoch_s=1004.0,
    )

    assert expired_error == "Customer authorization has expired. Prepare and confirm the action again."
    assert declined["status"] == "DECLINED"
    assert declined["invalidation_reason"] == "CUSTOMER_DECLINED"


def test_ambiguous_response_requires_later_explicit_confirmation() -> None:
    authorization = create_workflow_authorization(
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=1000.0,
    )
    prompted = mark_authorization_prompted(
        authorization,
        assistant_event_id="assistant-1",
        now_epoch_s=1001.0,
    )
    unclear = apply_customer_authorization_response(
        prompted,
        transcript="What happens after that?",
        customer_event_id="customer-1",
        now_epoch_s=1002.0,
    )
    confirmed = apply_customer_authorization_response(
        unclear,
        transcript="Okay, yes, that is correct.",
        customer_event_id="customer-2",
        now_epoch_s=1003.0,
    )

    assert unclear["status"] == "UNCLEAR"
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["customer_event_id"] == "customer-2"


def test_authorization_is_consumed_and_completed_once() -> None:
    authorization = confirmed_authorization()
    executing = mark_authorization_executing(authorization, now_epoch_s=1003.0)
    completed = mark_authorization_completed(executing, now_epoch_s=1004.0)

    assert executing["status"] == "EXECUTING"
    assert completed["status"] == "COMPLETED"
    assert validate_workflow_authorization(
        completed,
        action=TRIAGE_FRAUD_CASE,
        payload=triage_payload(),
        session_id="session-1",
        now_epoch_s=1005.0,
    ) == "Customer authorization for TRIAGE_FRAUD_CASE is not confirmed."
