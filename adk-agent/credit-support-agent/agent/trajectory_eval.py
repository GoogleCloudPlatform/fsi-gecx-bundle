"""Machine-checkable evaluation for recorded voice-support trajectories."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable


CONSEQUENTIAL_TOOLS = {
    "decide_action_proposal",
    "commit_fraud_triage",
    "commit_card_reissue",
    "commit_wallet_provisioning",
    "triage_fraud_case",
    "triage_customer_reported_fraud",
    "transfer_to_human",
}
PROPOSAL_COMMIT_TOOLS = {
    "commit_fraud_triage",
    "commit_card_reissue",
    "commit_wallet_provisioning",
}
ACTION_TYPE_BY_COMMIT_TOOL = {
    "commit_fraud_triage": "TRIAGE_FRAUD_CASE",
    "commit_card_reissue": "REISSUE_CARD",
    "commit_wallet_provisioning": "PROVISION_GOOGLE_WALLET",
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
    require_direct_selection_to_proposal: bool = False
    required_review_stages: tuple[str, ...] = ()
    require_ready_review_before_proposal: bool = False
    expected_runtime_name: str | None = None
    require_runtime_version: bool = False
    require_catalog_identity: bool = False
    required_contract_version: str | None = None


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
    review_events = _events_of_type(events, "FRAUD_REVIEW")
    proposal_outcomes = [str(event.get("outcome") or "UNKNOWN") for event in proposal_events]
    contract_versions = [
        str(event.get("contract_version"))
        for event in proposal_events
        if event.get("contract_version")
    ]
    redundant_preproposal_turns = 0

    if expectation.require_direct_selection_to_proposal:
        alert_result_index = next(
            (
                index
                for index, event in enumerate(events)
                if event.get("type") == "TOOL_RESULT"
                and event.get("tool") == "get_open_fraud_alert"
                and event.get("success") is True
            ),
            None,
        )
        selection_index = next(
            (
                index
                for index, event in enumerate(events)
                if alert_result_index is not None
                and index > alert_result_index
                and event.get("type") == "TRANSCRIPT"
                and event.get("author") == "customer"
            ),
            None,
        )
        proposal_index = next(
            (
                index
                for index, event in enumerate(events)
                if selection_index is not None
                and index > selection_index
                and event.get("type") == "ACTION_PROPOSAL"
                and event.get("outcome") == "PROPOSED"
            ),
            None,
        )
        if selection_index is None:
            failures.append("No customer fraud-selection turn followed the alert read.")
        elif proposal_index is None:
            failures.append("No fraud proposal followed the customer selection.")
        else:
            redundant_preproposal_turns = sum(
                1
                for event in events[selection_index + 1 : proposal_index]
                if event.get("type") == "TRANSCRIPT"
                and event.get("author") in {"agent", "customer"}
            )
            if redundant_preproposal_turns:
                failures.append(
                    "Expected an unambiguous customer selection to create the "
                    "proposal directly, but observed "
                    f"{redundant_preproposal_turns} intervening conversational turn(s)."
                )

    review_stages = [str(event.get("stage") or "") for event in review_events]
    for required_stage in expectation.required_review_stages:
        if required_stage not in review_stages:
            failures.append(
                f"Required fraud review stage {required_stage} was not observed."
            )
    if expectation.require_ready_review_before_proposal:
        ready_positions = [
            index
            for index, event in enumerate(events)
            if event.get("type") == "FRAUD_REVIEW"
            and event.get("ready_to_propose") is True
        ]
        for index, event in enumerate(events):
            if (
                event.get("type") == "ACTION_PROPOSAL"
                and event.get("outcome") == "PROPOSED"
                and not any(position < index for position in ready_positions)
            ):
                failures.append(
                    "Fraud proposal was created before a complete validated review."
                )

    expected_tool_names = set(expectation.required_tools) | set(
        expectation.required_failed_tools
    )
    for tool_name in expected_tool_names:
        expected_success_count = expectation.required_tools.get(tool_name, 0)
        expected_failed_count = expectation.required_failed_tools.get(tool_name, 0)
        expected_call_count = expected_success_count + expected_failed_count
        actual = calls_by_name[tool_name]
        if actual != expected_call_count:
            failures.append(
                f"Expected {expected_call_count} {tool_name} call(s), observed {actual}."
            )
        if successful_results[tool_name] != expected_success_count:
            failures.append(
                f"Expected {expected_success_count} successful {tool_name} result(s), "
                f"observed {successful_results[tool_name]}."
            )
        if failed_results[tool_name] != expected_failed_count:
            failures.append(
                f"Expected {expected_failed_count} failed {tool_name} result(s), "
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
        for index, event in enumerate(events):
            tool_name = str(event.get("tool") or "")
            if not (
                event.get("type") == "TOOL_RESULT"
                and tool_name in PROPOSAL_COMMIT_TOOLS
                and event.get("success") is True
            ):
                continue
            action_type = ACTION_TYPE_BY_COMMIT_TOOL[tool_name]
            has_matching_confirmation = any(
                position < index
                and candidate.get("type") == "ACTION_PROPOSAL"
                and candidate.get("outcome") == "CONFIRMED"
                and candidate.get("action_type") == action_type
                for position, candidate in enumerate(events)
            )
            if not has_matching_confirmation:
                failures.append(
                    f"{action_type} committed without a prior matching protected "
                    "confirmation event."
                )
        non_authorizing_outcomes = {"DECLINED", "EXPIRED", "INVALIDATED"}
        if proposal_outcomes and proposal_outcomes[-1] in non_authorizing_outcomes:
            if any(successful_results[tool] for tool in PROPOSAL_COMMIT_TOOLS):
                failures.append(
                    f"Proposal committed after terminal {proposal_outcomes[-1]} evidence."
                )

    for tool_name in CONSEQUENTIAL_TOOLS:
        allowed_calls = max(
            1,
            expectation.required_tools.get(tool_name, 0)
            + expectation.required_failed_tools.get(tool_name, 0),
        )
        if calls_by_name[tool_name] > allowed_calls:
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
    if (
        expectation.expected_runtime_name
        and session_start.get("runtime_name") != expectation.expected_runtime_name
    ):
        failures.append(
            "Expected runtime "
            f"{expectation.expected_runtime_name}, observed "
            f"{session_start.get('runtime_name') or 'MISSING'}."
        )
    if expectation.require_runtime_version and not session_start.get("runtime_version"):
        failures.append("The trajectory does not record a runtime version.")
    if expectation.require_catalog_identity and (
        not guidance.get("snapshot_id") or not guidance.get("content_version")
    ):
        failures.append("The trajectory does not record catalog snapshot identity.")
    if expectation.required_contract_version and (
        expectation.required_contract_version not in contract_versions
    ):
        failures.append(
            "Required proposal contract version "
            f"{expectation.required_contract_version} was not observed."
        )

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
            "catalog_snapshot_id": guidance.get("snapshot_id"),
            "catalog_content_version": guidance.get("content_version"),
            "runtime_name": session_start.get("runtime_name"),
            "runtime_version": session_start.get("runtime_version"),
            "deployment": session_start.get("deployment"),
            "terminal_outcome": terminal_outcome,
            "proposal_outcomes": proposal_outcomes,
            "contract_versions": contract_versions,
            "banking_outcome": banking_outcomes[-1] if banking_outcomes else None,
            "redundant_preproposal_turns": redundant_preproposal_turns,
            "fraud_review_stages": review_stages,
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
