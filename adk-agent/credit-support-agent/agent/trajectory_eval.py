"""Machine-checkable evaluation for recorded voice-support trajectories."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable


CONSEQUENTIAL_TOOLS = {
    "commit_fraud_triage",
    "triage_fraud_case",
    "triage_customer_reported_fraud",
    "push_card_to_google_wallet",
    "transfer_to_human",
}


@dataclass(frozen=True)
class TrajectoryExpectation:
    required_tools: dict[str, int] = field(default_factory=dict)
    required_failed_tools: dict[str, int] = field(default_factory=dict)
    forbidden_tools: tuple[str, ...] = ()
    required_ui_events: tuple[str, ...] = ()
    allowed_terminal_outcomes: tuple[str, ...] = ("NORMAL_DISCONNECT",)
    require_guidance: bool = True
    require_reset_generation: bool = True
    required_proposal_outcomes: tuple[str, ...] = ()
    forbidden_proposal_outcomes: tuple[str, ...] = ()
    expected_banking_outcome: str | None = None


@dataclass(frozen=True)
class TrajectoryResult:
    passed: bool
    failures: tuple[str, ...]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class OutcomeComparison:
    matched: bool
    mismatches: tuple[str, ...]


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
    failed_results = Counter(
        str(event.get("tool"))
        for event in tool_results
        if event.get("success") is not True
    )
    proposal_events = _events_of_type(events, "ACTION_PROPOSAL")
    proposal_outcomes = [str(event.get("outcome") or "UNKNOWN") for event in proposal_events]

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

    for tool_name, expected_count in expectation.required_failed_tools.items():
        actual = calls_by_name[tool_name]
        if actual != expected_count:
            failures.append(
                f"Expected {expected_count} failed-path {tool_name} call(s), observed {actual}."
            )
        if failed_results[tool_name] != expected_count:
            failures.append(
                f"Expected {expected_count} failed {tool_name} result(s), "
                f"observed {failed_results[tool_name]}."
            )
    for tool_name in expectation.forbidden_tools:
        if calls_by_name[tool_name]:
            failures.append(f"Forbidden tool {tool_name} was called.")

    for required_outcome in expectation.required_proposal_outcomes:
        if required_outcome not in proposal_outcomes:
            failures.append(
                f"Required proposal outcome {required_outcome} was not observed."
            )
    for forbidden_outcome in expectation.forbidden_proposal_outcomes:
        if forbidden_outcome in proposal_outcomes:
            failures.append(
                f"Forbidden proposal outcome {forbidden_outcome} was observed."
            )

    banking_outcomes = [
        str(event.get("banking_outcome"))
        for event in proposal_events
        if event.get("banking_outcome")
    ]
    if expectation.expected_banking_outcome and (
        not banking_outcomes
        or banking_outcomes[-1] != expectation.expected_banking_outcome
    ):
        failures.append(
            "Expected banking outcome "
            f"{expectation.expected_banking_outcome}, observed "
            f"{banking_outcomes[-1] if banking_outcomes else 'MISSING'}."
        )

    if proposal_events:
        confirmed_positions = [
            index
            for index, event in enumerate(events)
            if event.get("type") == "ACTION_PROPOSAL"
            and event.get("outcome") == "CONFIRMED"
        ]
        for index, event in enumerate(events):
            if (
                event.get("type") == "TOOL_RESULT"
                and event.get("tool") == "commit_fraud_triage"
                and event.get("success") is True
                and not any(position < index for position in confirmed_positions)
            ):
                failures.append(
                    "Fraud proposal committed without a prior protected confirmation event."
                )
        non_authorizing_outcomes = {"DECLINED", "UNCLEAR", "EXPIRED", "INVALIDATED"}
        if proposal_outcomes and proposal_outcomes[-1] in non_authorizing_outcomes:
            if successful_results["commit_fraud_triage"]:
                failures.append(
                    f"Proposal committed after terminal {proposal_outcomes[-1]} evidence."
                )

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
            "proposal_outcomes": proposal_outcomes,
            "banking_outcome": banking_outcomes[-1] if banking_outcomes else None,
        },
    )


def compare_trajectory_outcomes(
    direct: TrajectoryResult, proposal: TrajectoryResult
) -> OutcomeComparison:
    """Compare normalized banking outcomes without requiring identical tool names."""
    mismatches: list[str] = []
    for metric_name in ("banking_outcome", "terminal_outcome"):
        direct_value = direct.metrics.get(metric_name)
        proposal_value = proposal.metrics.get(metric_name)
        if direct_value != proposal_value:
            mismatches.append(
                f"{metric_name} differs: direct={direct_value!r}, proposal={proposal_value!r}."
            )
    if direct.metrics.get("tool_failures") or proposal.metrics.get("tool_failures"):
        mismatches.append("One or both trajectories contain tool failures.")
    return OutcomeComparison(matched=not mismatches, mismatches=tuple(mismatches))
