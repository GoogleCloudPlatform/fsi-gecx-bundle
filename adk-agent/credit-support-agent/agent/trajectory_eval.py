"""Machine-checkable evaluation for recorded voice-support trajectories."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable


CONSEQUENTIAL_TOOLS = {
    "triage_fraud_case",
    "triage_customer_reported_fraud",
    "push_card_to_google_wallet",
    "transfer_to_human",
}


@dataclass(frozen=True)
class TrajectoryExpectation:
    required_tools: dict[str, int] = field(default_factory=dict)
    forbidden_tools: tuple[str, ...] = ()
    required_ui_events: tuple[str, ...] = ()
    allowed_terminal_outcomes: tuple[str, ...] = ("NORMAL_DISCONNECT",)
    require_guidance: bool = True
    require_reset_generation: bool = True


@dataclass(frozen=True)
class TrajectoryResult:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, Any]


def _events_of_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == event_type]


def evaluate_trajectory(
    raw_events: Iterable[dict[str, Any]],
    expectation: TrajectoryExpectation,
) -> TrajectoryResult:
    """Evaluate an ordered, normalized session event stream.

    The evaluator intentionally consumes application events rather than model
    internals so the same contract can validate fixtures, deployed log exports,
    and future audio-driven canaries.
    """
    events = list(raw_events)
    failures: list[str] = []
    tool_calls = _events_of_type(events, "TOOL_CALL")
    tool_results = _events_of_type(events, "TOOL_RESULT")
    calls_by_name = Counter(str(event.get("tool")) for event in tool_calls)
    successful_results = Counter(
        str(event.get("tool"))
        for event in tool_results
        if event.get("success") is True
    )

    for tool_name, expected_count in expectation.required_tools.items():
        actual = calls_by_name[tool_name]
        if actual != expected_count:
            failures.append(
                f"Expected {expected_count} {tool_name} call(s), observed {actual}."
            )
        if successful_results[tool_name] != expected_count:
            failures.append(
                f"Expected {expected_count} successful {tool_name} result(s), "
                f"observed {successful_results[tool_name]}."
            )

    for tool_name in expectation.forbidden_tools:
        if calls_by_name[tool_name]:
            failures.append(f"Forbidden tool {tool_name} was called.")

    for tool_name in CONSEQUENTIAL_TOOLS:
        if calls_by_name[tool_name] > max(
            1, expectation.required_tools.get(tool_name, 0)
        ):
            failures.append(f"Consequential tool {tool_name} was called more than once.")

    result_positions: dict[str, int] = {}
    for index, event in enumerate(events):
        if event.get("type") == "TOOL_RESULT" and event.get("success") is True:
            result_positions[str(event.get("tool"))] = index
        if event.get("type") == "SUCCESS_CLAIM":
            tool_name = str(event.get("tool") or "")
            if tool_name not in result_positions or result_positions[tool_name] >= index:
                failures.append(
                    f"Success for {tool_name or 'an action'} was claimed before its tool result."
                )

    ui_events = {
        str(event.get("event"))
        for event in _events_of_type(events, "UI_EVENT")
    }
    for required_event in expectation.required_ui_events:
        if required_event not in ui_events:
            failures.append(f"Required UI event {required_event} was not observed.")

    session_start = next(iter(_events_of_type(events, "SESSION_STARTED")), {})
    guidance = next(iter(_events_of_type(events, "GUIDANCE_SNAPSHOT")), {})
    if expectation.require_guidance and (
        not guidance.get("source") or not guidance.get("topic_ids")
    ):
        failures.append("The trajectory does not contain a grounded guidance snapshot.")
    if expectation.require_reset_generation and not session_start.get(
        "reset_generation"
    ):
        failures.append("The trajectory does not record a reset generation.")

    terminal_events = _events_of_type(events, "SESSION_ENDED")
    terminal_outcome = (
        str(terminal_events[-1].get("outcome")) if terminal_events else "MISSING"
    )
    if terminal_outcome not in expectation.allowed_terminal_outcomes:
        failures.append(f"Unexpected terminal outcome {terminal_outcome}.")

    timestamps = [
        float(event["elapsed_ms"])
        for event in events
        if isinstance(event.get("elapsed_ms"), (int, float))
    ]
    return TrajectoryResult(
        passed=not failures,
        failures=tuple(failures),
        metrics={
            "event_count": len(events),
            "tool_calls": dict(calls_by_name),
            "tool_failures": sum(
                1
                for event in tool_results
                if event.get("success") is not True
            ),
            "interruptions": len(_events_of_type(events, "INTERRUPTION")),
            "duration_ms": max(timestamps, default=0.0),
            "guidance_source": guidance.get("source"),
            "terminal_outcome": terminal_outcome,
        },
    )
