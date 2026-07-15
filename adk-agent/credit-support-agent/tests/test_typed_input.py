import json

import pytest

from agent.typed_input import (
    CUSTOMER_TEXT_INPUT,
    TypedInputError,
    parse_customer_text_packet,
    typed_input_ack,
    validate_typed_turn_availability,
)


def packet(**overrides) -> bytes:
    payload = {
        "type": CUSTOMER_TEXT_INPUT,
        "message_id": "message_1234",
        "text": "Yes, please proceed.",
    }
    payload.update(overrides)
    return json.dumps(payload).encode()


def test_parse_typed_customer_message() -> None:
    result = parse_customer_text_packet(
        packet(),
        participant_identity="user-customer-1",
        expected_identity="user-customer-1",
        seen_message_ids=set(),
    )

    assert result.message_id == "message_1234"
    assert result.text == "Yes, please proceed."


def test_rejects_other_room_participant() -> None:
    with pytest.raises(TypedInputError) as error:
        parse_customer_text_packet(
            packet(),
            participant_identity="agent-human-supervisor",
            expected_identity="user-customer-1",
            seen_message_ids=set(),
        )

    assert error.value.code == "UNAUTHORIZED_PARTICIPANT"


def test_rejects_duplicate_message() -> None:
    with pytest.raises(TypedInputError) as error:
        parse_customer_text_packet(
            packet(),
            participant_identity="user-customer-1",
            expected_identity="user-customer-1",
            seen_message_ids={"message_1234"},
        )

    assert error.value.code == "DUPLICATE_MESSAGE"


def test_ack_does_not_echo_customer_text() -> None:
    result = json.loads(
        typed_input_ack(message_id="message_1234", accepted=True)
    )

    assert result["type"] == "CUSTOMER_TEXT_ACCEPTED"
    assert "text" not in result


def test_ignores_unrelated_supervisor_data_packet() -> None:
    result = parse_customer_text_packet(
        json.dumps({"type": "HIGHLIGHT_TRANSACTION", "id": "txn-1"}).encode(),
        participant_identity="agent-human-supervisor",
        expected_identity="user-customer-1",
        seen_message_ids=set(),
    )

    assert result is None


@pytest.mark.parametrize(
    ("flag", "expected_code", "retryable"),
    [
        ("tool_processing", "TOOL_IN_PROGRESS", True),
        ("voice_input_active", "VOICE_INPUT_ACTIVE", True),
        ("typed_turn_active", "TURN_IN_PROGRESS", True),
        ("runtime_transition_active", "RUNTIME_TRANSITION", True),
        ("session_ending", "SESSION_ENDING", False),
        ("human_handoff_active", "HUMAN_HANDOFF_ACTIVE", False),
    ],
)
def test_typed_turn_serialization_gate(flag, expected_code, retryable) -> None:
    state = {
        "tool_processing": False,
        "voice_input_active": False,
        "typed_turn_active": False,
        "runtime_transition_active": False,
        "session_ending": False,
        "human_handoff_active": False,
    }
    state[flag] = True

    with pytest.raises(TypedInputError) as error:
        validate_typed_turn_availability(**state)

    assert error.value.code == expected_code
    assert error.value.retryable is retryable
