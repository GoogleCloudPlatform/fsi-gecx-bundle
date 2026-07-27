#!/usr/bin/env python3
"""Evaluate a CES conversation and optionally create a pinned managed replay."""

from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "adk-agent" / "credit-support-agent"
DEFAULT_MATRIX = (
    ROOT
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "evaluations"
    / "ces_fraud_qualification_matrix.json"
)
sys.path.insert(0, str(AGENT_ROOT))

from agent.ces_trajectory import (  # noqa: E402
    normalize_ces_conversation,
    safe_conversation_identity,
)
from agent.trajectory_eval import TrajectoryExpectation, evaluate_trajectory  # noqa: E402


class CesApi:
    def __init__(self, *, project: str, account: str | None = None) -> None:
        self.project = project
        self.account = account
        self.base_url = "https://ces.googleapis.com/v1beta"

    def _token(self) -> str:
        command = ["gcloud", "auth", "print-access-token"]
        if self.account:
            command.append(f"--account={self.account}")
        return subprocess.check_output(command, text=True).strip()

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        data = json.dumps(body).encode() if body is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
                "x-goog-user-project": self.project,
            },
        )
        for attempt in range(5):
            try:
                with urlopen(request, timeout=60) as response:
                    payload = response.read()
                break
            except HTTPError as error:
                detail = error.read().decode(errors="replace")
                if error.code not in {429, 500, 502, 503, 504} or attempt == 4:
                    raise RuntimeError(
                        f"CES API {method} {path} failed with HTTP "
                        f"{error.code}: {detail}"
                    ) from error
            except URLError as error:
                if attempt == 4:
                    raise RuntimeError(
                        f"CES API {method} {path} failed after retries: {error}"
                    ) from error
            time.sleep(2**attempt)
        return json.loads(payload) if payload else {}

    def wait_operation(
        self, operation: dict[str, Any], *, timeout_seconds: int = 600
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        current = operation
        while not current.get("done"):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"CES operation {current.get('name')} timed out.")
            time.sleep(3)
            current = self.request("GET", str(current["name"]))
        if current.get("error"):
            raise RuntimeError(
                f"CES operation {current.get('name')} failed: {current['error']}"
            )
        return current


def _expectation(raw: dict[str, Any]) -> TrajectoryExpectation:
    tuple_fields = {
        "forbidden_tools",
        "required_ui_events",
        "allowed_terminal_outcomes",
        "required_proposal_outcomes",
        "forbidden_proposal_outcomes",
        "required_review_stages",
    }
    allowed = {item.name for item in fields(TrajectoryExpectation)}
    values = {key: value for key, value in raw.items() if key in allowed}
    for key in tuple_fields:
        if key in values:
            values[key] = tuple(values[key])
    return TrajectoryExpectation(**values)


def _scenario(matrix: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    for item in matrix.get("scenarios") or []:
        if item.get("id") == scenario_id:
            return item
    raise ValueError(f"Scenario {scenario_id!r} is not present in the matrix.")


def _resource_id(name: str | None) -> str | None:
    return name.rsplit("/", 1)[-1] if name else None


def _managed_fake_output(tool: str) -> dict[str, Any]:
    authorizations = [
        {
            "authorization_id": f"eval-auth-{index}",
            "merchant_name": merchant,
            "amount_cents": amount,
        }
        for index, (merchant, amount) in enumerate(
            (
                ("GAME*TEST TOKEN ONLINE", 499),
                ("APPLE.COM*ONLINE", 149900),
                ("BEST BUY*MKTPLACE", 215000),
                ("RAZER GOLD GIFT CARD", 125000),
                ("TARGET.COM GIFT CARDS", 95000),
            ),
            start=1,
        )
    ]
    if tool == "get_open_fraud_alert":
        return {
            "success": True,
            "fraud_alert": {
                "fraud_alert_id": "eval-alert-1",
                "status": "OPEN",
                "card_last_four": "0001",
                "suspicious_transactions": authorizations,
            },
            "support_guidance": {
                "source": "knowledge_catalog",
                "topic_ids": ["fraud_golden_path", "replacement_card"],
                "snapshot_id": "eval-catalog-snapshot",
                "content_version": "2.2+2.4+2.5",
            },
        }
    if tool == "propose_fraud_triage":
        return {
            "success": True,
            "status": "PROPOSED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to dispute all five listed charges on card "
                "ending 0001, block the current card, and issue a replacement."
            ),
        }
    if tool == "commit_fraud_triage":
        return {
            "success": True,
            "status": "COMMITTED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "outcome": "PENDING_SPECIALIST_REVIEW",
            "replacement_card": {
                "new_last_four": "0002",
                "is_virtual": True,
                "status": "ACTIVE",
            },
            "customer_safe_result_summary": (
                "Your fraud report was submitted for specialist review. Five "
                "pending charges were released. Your compromised card was blocked, "
                "and a replacement virtual card ending in 0002 is active. A secure "
                "message with the case details was sent."
            ),
        }
    return {}


def _curate_generated_golden(golden: dict[str, Any]) -> dict[str, Any]:
    """Remove live credentials/state and retain only reusable golden expectations."""
    safe_session_variables = {
        "has_active_fraud_alert",
        "entry_reason",
        "runtime_name",
        "catalog_content_version",
        "catalog_snapshot_id",
        "reset_generation",
        "language_code",
        "runtime_language_code",
        "language_selection_source",
        "ces_app_id",
        "ces_version_or_deployment_id",
    }
    for turn_index, turn in enumerate(golden.get("turns") or []):
        curated_steps: list[dict[str, Any]] = []
        for step in turn.get("steps") or []:
            user_input = step.get("userInput")
            if isinstance(user_input, dict):
                variables = user_input.get("variables")
                if isinstance(variables, dict):
                    user_input["variables"] = {
                        key: value
                        for key, value in variables.items()
                        if key in safe_session_variables
                    }
                if (
                    turn_index == len(golden.get("turns") or []) - 1
                    and isinstance(user_input.get("text"), str)
                ):
                    user_input["text"] = "No, that's all. Thank you."
                curated_steps.append(step)
                continue

            expectation = step.get("expectation")
            if not isinstance(expectation, dict):
                curated_steps.append(step)
                continue
            tool_response = expectation.get("toolResponse")
            if isinstance(tool_response, dict):
                tool = _tool_resource_id(tool_response)
                tool_response["response"] = {
                    "output": json.dumps(
                        _managed_fake_output(tool), separators=(",", ":")
                    )
                }
                curated_steps.append(step)
                continue
            updated_variables = expectation.get("updatedVariables")
            if isinstance(updated_variables, dict):
                replacements = {
                    "active_fraud_alert_id": "eval-alert-1",
                    "active_fraud_authorization_ids": ",".join(
                        f"eval-auth-{index}" for index in range(1, 6)
                    ),
                    "active_fraud_transaction_ids": "",
                    "proposal_id": "eval-proposal-1",
                }
                expectation["updatedVariables"] = {
                    key: replacements.get(key, value)
                    for key, value in updated_variables.items()
                    if key
                    not in {
                        "session_capability",
                        "customer_ref",
                        "support_session_id",
                        "runtime_session_id",
                    }
                }
                curated_steps.append(step)
                continue
            tool_call = expectation.get("toolCall")
            if isinstance(tool_call, dict):
                tool_call["args"] = {}
            curated_steps.append(step)
        turn["steps"] = curated_steps
    return golden


def _tool_resource_id(payload: dict[str, Any]) -> str:
    toolset_tool = payload.get("toolsetTool") or {}
    return str(toolset_tool.get("toolId") or payload.get("tool") or "").rsplit(
        "/", 1
    )[-1]


def _managed_evaluation(
    api: CesApi,
    *,
    app: str,
    app_version: str,
    conversation_name: str,
    dataset_id: str,
    display_name: str,
) -> dict[str, Any]:
    generated_operation = api.wait_operation(
        api.request(
            "POST",
            f"{conversation_name}:generateEvaluation",
            {"source": "LIVE", "evaluationType": "GOLDEN"},
        )
    )
    generated = {
        key: value
        for key, value in (generated_operation.get("response") or {}).items()
        if key != "@type"
    }
    if not generated.get("golden"):
        raise RuntimeError(
            "CES generated a response without a golden evaluation."
        )
    evaluation_id = f"{dataset_id}-golden"
    evaluation_path = f"{app}/evaluations/{evaluation_id}"
    evaluation_body = {
        "displayName": f"{display_name} golden",
        "description": "Generated from the bounded, locally qualified live CES trace.",
        "tags": ["bounded-qualification", "fraud", "work-item-1"],
        "golden": _curate_generated_golden(generated["golden"]),
        "evaluationMetricsThresholdOverride": {
            "goldenHallucinationMetricBehavior": "DISABLED",
            "goldenEvaluationMetricsThresholds": {
                "turnLevelMetricsThresholds": {
                    "semanticSimilaritySuccessThreshold": 0,
                    "overallToolInvocationCorrectnessThreshold": 1,
                    "semanticSimilarityChannel": "TEXT",
                },
                "expectationLevelMetricsThresholds": {
                    "toolInvocationParameterCorrectnessThreshold": 1
                },
            },
        },
    }
    try:
        existing_evaluation = api.request("GET", evaluation_path)
        evaluation = api.request(
            "PATCH",
            evaluation_path,
            {"name": existing_evaluation["name"], **evaluation_body},
            {
                "updateMask": (
                    "display_name,description,tags,golden,"
                    "evaluation_metrics_threshold_override"
                )
            },
        )
    except RuntimeError as error:
        if "HTTP 404" not in str(error):
            raise
        evaluation = api.request(
            "POST",
            f"{app}/evaluations",
            evaluation_body,
            {"evaluationId": evaluation_id},
        )
    evaluation_name = evaluation["name"]

    dataset_path = f"{app}/evaluationDatasets/{dataset_id}"
    try:
        dataset = api.request("GET", dataset_path)
        dataset = api.request(
            "PATCH",
            dataset_path,
            {
                "name": dataset["name"],
                "displayName": display_name,
                "evaluations": [evaluation_name],
            },
            {"updateMask": "display_name,evaluations"},
        )
    except RuntimeError as error:
        if "HTTP 404" not in str(error):
            raise
        dataset = api.request(
            "POST",
            f"{app}/evaluationDatasets",
            {"displayName": display_name, "evaluations": [evaluation_name]},
            {"evaluationDatasetId": dataset_id},
        )

    run_operation = api.wait_operation(
        api.request(
            "POST",
            f"{app}:runEvaluation",
            {
                "evaluationDataset": dataset["name"],
                "displayName": (
                    f"{display_name} managed replay "
                    f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                ),
                "appVersion": app_version,
                "goldenRunMethod": "STABLE",
                "runCount": 1,
                "config": {
                    "evaluationChannel": "TEXT",
                    "toolCallBehaviour": "FAKE",
                },
            },
        )
    )
    run_response = run_operation.get("response") or {}
    run_name = run_response.get("name") or run_response.get("evaluationRun")
    if not run_name:
        raise RuntimeError("CES completed the run operation without a run resource name.")
    run = api.request("GET", run_name)
    results: list[dict[str, Any]] = []
    for result_name in run.get("evaluationResults") or []:
        result = api.request("GET", result_name)
        replay_turns = (result.get("goldenResult") or {}).get(
            "turnReplayResults"
        ) or []
        expectation_outcomes = [
            expectation.get("outcome")
            for turn in replay_turns
            for expectation in turn.get("expectationOutcome") or []
            if expectation.get("outcome")
        ]
        results.append(
            {
                "name": result.get("name"),
                "execution_state": result.get("executionState"),
                "evaluation_status": result.get("evaluationStatus"),
                "app_version": result.get("appVersion"),
                "turn_count": len(replay_turns),
                "failed_expectation_count": expectation_outcomes.count("FAIL"),
            }
        )
    return {
        "evaluation": evaluation_name,
        "evaluation_id": _resource_id(evaluation_name),
        "dataset": dataset.get("name"),
        "dataset_id": _resource_id(dataset.get("name")),
        "run": run.get("name"),
        "run_id": _resource_id(run.get("name")),
        "run_state": run.get("state"),
        "evaluation_type": run.get("evaluationType"),
        "golden_run_method": run.get("goldenRunMethod"),
        "app_version": run.get("appVersion"),
        "results": results,
        "passed": bool(results)
        and all(
            result.get("execution_state") == "COMPLETED"
            and result.get("evaluation_status") == "PASS"
            for result in results
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--conversation", required=True)
    parser.add_argument("--app-version")
    parser.add_argument("--account")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--scenario", default="fraud-golden")
    parser.add_argument("--managed", action="store_true")
    parser.add_argument("--dataset-id", default="bounded-ces-work-item-1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    matrix = json.loads(args.matrix.read_text())
    scenario = _scenario(matrix, args.scenario)
    api = CesApi(project=args.project, account=args.account)
    conversation = api.request(
        "GET", args.conversation, query={"source": "LIVE"}
    )
    events = normalize_ces_conversation(conversation)
    result = evaluate_trajectory(events, _expectation(scenario["expectation"]))

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "qualification_id": matrix.get("qualification_id"),
        "scenario": args.scenario,
        "conversation": safe_conversation_identity(conversation),
        "trajectory": {
            "passed": result.passed,
            "failures": list(result.failures),
            "metrics": result.metrics,
        },
    }
    if args.managed:
        app_version = args.app_version or conversation.get("appVersion")
        if not app_version:
            raise ValueError("--app-version is required when the conversation omits it.")
        report["managed_evaluation"] = _managed_evaluation(
            api,
            app=args.app,
            app_version=app_version,
            conversation_name=args.conversation,
            dataset_id=args.dataset_id,
            display_name="Bounded CES fraud qualification work item 1",
        )

    report["passed"] = result.passed and (
        not args.managed or report["managed_evaluation"]["passed"]
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
