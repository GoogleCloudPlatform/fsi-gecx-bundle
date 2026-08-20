#!/usr/bin/env python3
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

"""Evaluate a CES conversation and optionally run contract and quality replays."""

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
DEFAULT_CONVERSATIONAL_REFERENCE = (
    ROOT
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "evaluations"
    / "ces_fraud_conversational_reference.json"
)
SESSION_CLOSEOUT_AGENT_ID = "43201fe7-1b16-48fe-9f96-ab57528b729e"
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


def _app_version_for_app(app: str, app_version: str | None) -> str | None:
    """Bind CES's immutable version id to the caller-selected app parent.

    Conversation resources may return the project-number spelling while the
    evaluation endpoint receives the equivalent project-id spelling. CES
    compares resource parents textually, so preserve the immutable version id
    while normalizing its parent.
    """
    version_id = _resource_id(app_version)
    return f"{app}/versions/{version_id}" if version_id else None


def _latest_live_conversation(api: CesApi, app: str) -> str:
    """Return the newest completed LIVE conversation, following all list pages."""
    candidates: list[dict[str, Any]] = []
    page_token = ""
    seen_tokens: set[str] = set()
    while True:
        query = {"pageSize": "100"}
        if page_token:
            query["pageToken"] = page_token
        response = api.request("GET", f"{app}/conversations", query=query)
        candidates.extend(
            conversation
            for conversation in response.get("conversations") or []
            if conversation.get("source") == "LIVE"
            and conversation.get("name")
            and conversation.get("endTime")
        )
        next_token = str(response.get("nextPageToken") or "")
        if not next_token:
            break
        if next_token in seen_tokens:
            raise RuntimeError("CES returned a repeated conversations page token.")
        seen_tokens.add(next_token)
        page_token = next_token

    if not candidates:
        raise ValueError(f"No completed LIVE conversations were found for {app}.")
    latest = max(
        candidates,
        key=lambda conversation: (
            str(conversation.get("endTime") or ""),
            str(conversation.get("startTime") or ""),
            str(conversation["name"]),
        ),
    )
    return str(latest["name"])


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
                "summary": (
                    "Customer has an active fraud alert on card ending in 0001. "
                    "Flagged transactions are $4.99 at GAME*TEST TOKEN ONLINE, "
                    "$1,499.00 at APPLE.COM*ONLINE, $2,150.00 at BEST "
                    "BUY*MKTPLACE, $1,250.00 at RAZER GOLD GIFT CARD, and "
                    "$950.00 at TARGET.COM GIFT CARDS."
                ),
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
                "Confirm that you want to dispute $4.99 at GAME*TEST TOKEN ONLINE, "
                "$1,499.00 at APPLE.COM*ONLINE, $2,150.00 at BEST BUY*MKTPLACE, "
                "$1,250.00 at RAZER GOLD GIFT CARD, and $950.00 at TARGET.COM "
                "GIFT CARDS on card ending 0001, block the current card, and issue "
                "a replacement."
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
    if tool == "propose_wallet_provisioning":
        return {
            "success": True,
            "status": "PROPOSED",
            "action_type": "PROVISION_GOOGLE_WALLET",
            "contract_version": "wallet-provisioning.v1",
            "proposal_id": "eval-wallet-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to queue the virtual card ending 0002 "
                "for Google Wallet."
            ),
        }
    if tool == "commit_wallet_provisioning":
        return {
            "success": True,
            "status": "COMMITTED",
            "action_type": "PROVISION_GOOGLE_WALLET",
            "contract_version": "wallet-provisioning.v1",
            "proposal_id": "eval-wallet-proposal-1",
            "message": "Virtual card provisioning is queued for Google Wallet.",
            "card_token": "eval-replacement-token",
            "wallet_provider": "GOOGLE_WALLET",
            "wallet_provisioning_status": "QUEUED",
        }
    if tool == "decide_action_proposal":
        return {
            "success": True,
            "status": "DECLINED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "decision": "DECLINE",
            "invalidation_reason": "CUSTOMER_DECLINED",
        }
    if tool == "request_credit_limit_increase":
        return {
            "success": True,
            "new_limit": 11250,
            "message": "Credit limit increase approved.",
        }
    return {}


def _curate_generated_golden(golden: dict[str, Any]) -> dict[str, Any]:
    """Sanitize a generated CES Golden fixture used only for contract replay."""
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


def _managed_contract_evaluation(
    api: CesApi,
    *,
    app: str,
    app_version: str,
    reference: dict[str, Any],
    dataset_id: str,
    display_name: str,
    golden: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    run_count: int = 1,
    required_agent_response_role: str | None = None,
) -> dict[str, Any]:
    evaluation_id = f"{dataset_id}-reviewed"
    evaluation_path = f"{app}/evaluations/{evaluation_id}"
    evaluation_body = {
        "displayName": f"{display_name} reviewed contract",
        "description": (
            "Reviewed synthetic trajectory for typed tool and workflow invariants. "
            "Live traces are canary evidence and never become golden implicitly."
        ),
        "tags": tags
        or [
            "bounded-qualification",
            "reviewed-contract",
            "fraud",
            "work-item-1",
        ],
        "golden": golden or _conversational_golden(app, reference),
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
                    f"{display_name} reviewed contract "
                    f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                ),
                "appVersion": app_version,
                "goldenRunMethod": "STABLE",
                "runCount": run_count,
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
        required_agent_response_observed = (
            required_agent_response_role is None
            or any(
                str(
                    (expectation.get("observedAgentResponse") or {}).get("role")
                    or ""
                )
                == required_agent_response_role
                and any(
                    str(chunk.get("text") or "").strip()
                    for chunk in (
                        expectation.get("observedAgentResponse") or {}
                    ).get("chunks")
                    or []
                    if isinstance(chunk, dict)
                )
                for turn in replay_turns
                for expectation in turn.get("expectationOutcome") or []
            )
        )
        results.append(
            {
                "name": result.get("name"),
                "execution_state": result.get("executionState"),
                "evaluation_status": result.get("evaluationStatus"),
                "app_version": result.get("appVersion"),
                "turn_count": len(replay_turns),
                "failed_expectation_count": expectation_outcomes.count("FAIL"),
                "required_agent_response_role": required_agent_response_role,
                "required_agent_response_observed": (
                    required_agent_response_observed
                ),
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
            and result.get("required_agent_response_observed") is True
            for result in results
        ),
    }


def _tool_expectation(
    app: str,
    tool: str,
    invocation_id: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if tool == "end_session":
        tool_call = {
            "id": invocation_id,
            "tool": f"{app}/tools/end_session",
            "args": args or {},
            "displayName": "end_session",
        }
    else:
        tool_call = {
            "id": invocation_id,
            "args": args or {},
            "displayName": "banking_service_mcp_toolset",
            "toolsetTool": {
                "toolset": f"{app}/toolsets/banking-service-mcp",
                "toolId": tool,
            },
        }
    return {"expectation": {"toolCall": tool_call}}


def _tool_response_expectation(
    app: str,
    tool: str,
    invocation_id: str,
) -> dict[str, Any]:
    return {
        "expectation": {
            "toolResponse": {
                "id": invocation_id,
                "response": {
                    "output": json.dumps(
                        _managed_fake_output(tool), separators=(",", ":")
                    )
                },
                "displayName": "banking_service_mcp_toolset",
                "toolsetTool": {
                    "toolset": f"{app}/toolsets/banking-service-mcp",
                    "toolId": tool,
                },
            }
        }
    }


def _agent_response_expectation(
    text: str,
    *,
    role: str = "Credit Card Support Agent",
) -> dict[str, Any]:
    return {
        "expectation": {
            "agentResponse": {
                "role": role,
                "chunks": [{"text": text}],
            }
        }
    }


def _conversational_golden(
    app: str,
    reference: dict[str, Any],
) -> dict[str, Any]:
    """Build a stable CES Golden fixture from the reviewed reference dialogue."""
    turns_by_id = {
        str(turn["id"]): turn for turn in reference.get("turns") or []
    }
    required_ids = (
        "alert-readout",
        "proposal",
        "commit",
        "recovery-question",
        "wallet-provisioning",
        "close",
    )
    missing = [turn_id for turn_id in required_ids if turn_id not in turns_by_id]
    if missing:
        raise ValueError(
            "Conversational reference is missing required turns: "
            + ", ".join(missing)
        )

    alert = turns_by_id["alert-readout"]
    proposal = turns_by_id["proposal"]
    commit = turns_by_id["commit"]
    recovery = turns_by_id["recovery-question"]
    wallet = turns_by_id["wallet-provisioning"]
    close = turns_by_id["close"]
    proposal_summary = _managed_fake_output("propose_fraud_triage")[
        "customer_safe_summary"
    ]

    return {
        "turns": [
            {
                "steps": [
                    {
                        "userInput": {
                            "variables": {
                                "has_active_fraud_alert": True,
                                "entry_reason": "fraud_alert",
                                "runtime_name": "CES_GEMINI_LIVE",
                                "catalog_content_version": "2.2+2.4+2.5",
                                "catalog_snapshot_id": "eval-catalog-snapshot",
                                "reset_generation": "eval-reset-1",
                                "language_code": "en",
                                "runtime_language_code": "en-US",
                                "language_selection_source": "default",
                                "ces_app_id": _resource_id(app),
                                "ces_version_or_deployment_id": "eval-version",
                                "fraud_support_guidance_summary": (
                                    "Enumerate every flagged merchant and exact amount. "
                                    "Use one proposal confirmation. After commit, continue "
                                    "helping and offer Google Wallet only when requested."
                                ),
                            }
                        }
                    },
                    {"userInput": {"event": {"event": str(alert["event"])}}},
                    _tool_expectation(
                        app, "get_open_fraud_alert", "eval-alert-read"
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "active_fraud_alert_id": "eval-alert-1",
                                "active_fraud_authorization_ids": (
                                    "eval-auth-1,eval-auth-2,eval-auth-3,"
                                    "eval-auth-4,eval-auth-5"
                                ),
                                "active_fraud_transaction_ids": "",
                            }
                        }
                    },
                    _tool_response_expectation(
                        app, "get_open_fraud_alert", "eval-alert-read"
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "fraud_selection_prompt_turn_id": "eval-turn-alert",
                                "fraud_selection_pending": True,
                            }
                        }
                    },
                    _agent_response_expectation(str(alert["expected_agent"])),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": str(proposal["user"])}},
                    _tool_expectation(
                        app, "propose_fraud_triage", "eval-proposal"
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "customer_turn_id": "eval-turn-proposal",
                                "proposal_originating_turn_id": "eval-turn-proposal",
                                "proposal_action_type": "TRIAGE_FRAUD_CASE",
                                "proposal_id": "eval-proposal-1",
                                "proposal_customer_safe_summary": proposal_summary,
                                "proposal_presentation_turn_id": "",
                                "proposal_confirmation_turn_id": "",
                                "proposal_confirmation_method": "",
                                "proposal_confirmation_source": "",
                                "fraud_selection_pending": False,
                                "fraud_review_stage": "AWAITING_ACTION_CONFIRMATION",
                                "fraud_review_status": "COMPLETE",
                                "fraud_review_ready": True,
                            }
                        }
                    },
                    _tool_response_expectation(
                        app, "propose_fraud_triage", "eval-proposal"
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "proposal_presentation_turn_id": "eval-turn-proposal"
                            }
                        }
                    },
                    _agent_response_expectation(str(proposal["expected_agent"])),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": str(commit["user"])}},
                    {
                        "expectation": {
                            "updatedVariables": {
                                "customer_turn_id": "eval-turn-confirmation",
                                "proposal_confirmation_turn_id": (
                                    "eval-turn-confirmation"
                                ),
                                "proposal_confirmation_method": "EXPLICIT_VERBAL",
                                "proposal_confirmation_source": "MODEL_TOOL_INTENT",
                            }
                        }
                    },
                    _tool_expectation(
                        app,
                        "commit_fraud_triage",
                        "eval-commit",
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "fraud_review_stage": "COMMITTED"
                            }
                        }
                    },
                    _tool_response_expectation(
                        app, "commit_fraud_triage", "eval-commit"
                    ),
                    _agent_response_expectation(str(commit["expected_agent"])),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": str(recovery["user"])}},
                    _tool_expectation(
                        app,
                        "propose_wallet_provisioning",
                        "eval-wallet-proposal",
                    ),
                    _tool_response_expectation(
                        app,
                        "propose_wallet_provisioning",
                        "eval-wallet-proposal",
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "customer_turn_id": "eval-turn-wallet-proposal",
                                "proposal_originating_turn_id": (
                                    "eval-turn-wallet-proposal"
                                ),
                                "proposal_action_type": (
                                    "PROVISION_GOOGLE_WALLET"
                                ),
                                "proposal_id": "eval-wallet-proposal-1",
                                "proposal_customer_safe_summary": (
                                    _managed_fake_output(
                                        "propose_wallet_provisioning"
                                    )["customer_safe_summary"]
                                ),
                                "proposal_presentation_turn_id": (
                                    "eval-turn-wallet-proposal"
                                ),
                                "proposal_confirmation_turn_id": "",
                                "proposal_confirmation_method": "",
                                "proposal_confirmation_source": "",
                                "closeout_originating_turn_id": "",
                            }
                        }
                    },
                    _agent_response_expectation(str(recovery["expected_agent"])),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": str(wallet["user"])}},
                    _tool_expectation(
                        app,
                        "commit_wallet_provisioning",
                        "eval-wallet-provisioning",
                    ),
                    _tool_response_expectation(
                        app,
                        "commit_wallet_provisioning",
                        "eval-wallet-provisioning",
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "proposal_id": "",
                                "proposal_customer_safe_summary": "",
                                "proposal_action_type": "",
                                "proposal_originating_turn_id": "",
                                "proposal_presentation_turn_id": "",
                                "proposal_confirmation_turn_id": "",
                                "proposal_confirmation_method": "",
                                "proposal_confirmation_source": "",
                                "proposal_decision_type": "",
                                "proposal_commit_attempted": False,
                                "closeout_checkpoint_state": "OFFERED",
                                "closeout_originating_turn_id": (
                                    "eval-wallet-provisioning"
                                ),
                                "closeout_originating_input_fingerprint": "",
                                "closeout_delegation_authorized": False,
                            }
                        }
                    },
                    _agent_response_expectation(str(wallet["expected_agent"])),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": str(close["user"])}},
                    {
                        "expectation": {
                            "agentTransfer": {
                                "targetAgent": (
                                    f"{app}/agents/{SESSION_CLOSEOUT_AGENT_ID}"
                                ),
                                "displayName": "Session Closeout Agent",
                            }
                        }
                    },
                    # The wording is illustrative rather than fixed; the
                    # zero semantic threshold leaves phrasing to the model,
                    # while the response expectation requires a farewell text
                    # chunk to exist before the terminal tool executes.
                    _agent_response_expectation(
                        "You're very welcome.",
                        role="Session Closeout Agent",
                    ),
                    # The first transfer intent is consumed as typed
                    # authorization. The after-model callback then emits the
                    # second structural transfer that activates the child in
                    # the same customer turn.
                    {
                        "expectation": {
                            "agentTransfer": {
                                "targetAgent": (
                                    f"{app}/agents/{SESSION_CLOSEOUT_AGENT_ID}"
                                ),
                                "displayName": "Session Closeout Agent",
                            }
                        }
                    },
                    # CES terminates the streaming turn as soon as the system
                    # tool executes, so post-tool farewell audio is not a
                    # stable managed-replay surface. The terminal tool is the
                    # deterministic assertion; live canaries cover playout.
                    _tool_expectation(
                        app,
                        "end_session",
                        "eval-end-session",
                        {
                            "reason": "customer_query_ended",
                        },
                    ),
                ]
            },
        ]
    }


def _closeout_contract_golden(app: str) -> dict[str, Any]:
    """Build a focused servicing-to-closeout trajectory."""
    return {
        "turns": [
            {
                "steps": [
                    {
                        "userInput": {
                            "variables": {
                                "has_active_fraud_alert": False,
                                "entry_reason": "general_support",
                                "runtime_name": "CES_GEMINI_LIVE",
                                "reset_generation": "eval-reset-1",
                                "language_code": "en",
                                "runtime_language_code": "en-US",
                                "language_selection_source": "default",
                                "ces_app_id": _resource_id(app),
                                "ces_version_or_deployment_id": "eval-version",
                            }
                        }
                    },
                    {"userInput": {"event": {"event": "sys.welcome"}}},
                    _agent_response_expectation(
                        "Hi, I'm Nova with Nova Horizon Bank. How can I help you?"
                    ),
                ]
            },
            {
                "steps": [
                    {
                        "userInput": {
                            "text": "Please raise my credit limit to $11,250."
                        }
                    },
                    _agent_response_expectation(
                        "To confirm, you want a new credit limit of $11,250. "
                        "Is that correct?"
                    ),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": "That's correct."}},
                    _tool_expectation(
                        app,
                        "request_credit_limit_increase",
                        "eval-limit-increase",
                    ),
                    _tool_response_expectation(
                        app,
                        "request_credit_limit_increase",
                        "eval-limit-increase",
                    ),
                    {
                        "expectation": {
                            "updatedVariables": {
                                "closeout_checkpoint_state": "OFFERED",
                                "closeout_originating_turn_id": (
                                    "eval-limit-increase"
                                ),
                                "closeout_originating_input_fingerprint": "",
                                "closeout_delegation_authorized": False,
                                "proposal_id": "",
                                "proposal_commit_attempted": False,
                            }
                        }
                    },
                    _agent_response_expectation(
                        "Your credit limit increase was approved. Your new limit "
                        "is $11,250. Is there anything else I can help you with?"
                    ),
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": "No, that's all."}},
                    {
                        "expectation": {
                            "agentTransfer": {
                                "targetAgent": (
                                    f"{app}/agents/{SESSION_CLOSEOUT_AGENT_ID}"
                                ),
                                "displayName": "Session Closeout Agent",
                            }
                        }
                    },
                    # The authorization attempt and the structural handoff are
                    # both observable agent-transfer events in managed replay.
                    {
                        "expectation": {
                            "agentTransfer": {
                                "targetAgent": (
                                    f"{app}/agents/{SESSION_CLOSEOUT_AGENT_ID}"
                                ),
                                "displayName": "Session Closeout Agent",
                            }
                        }
                    },
                    _agent_response_expectation(
                        "You're very welcome.",
                        role="Session Closeout Agent",
                    ),
                    _tool_expectation(
                        app,
                        "end_session",
                        "eval-end-session",
                        {
                            "reason": "customer_query_ended",
                        },
                    ),
                ]
            },
        ]
    }


def _observed_agent_texts(result: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    replay_turns = (result.get("goldenResult") or {}).get(
        "turnReplayResults"
    ) or []
    for turn in replay_turns:
        for outcome in turn.get("expectationOutcome") or []:
            response = outcome.get("observedAgentResponse") or {}
            text = " ".join(
                str(chunk.get("text") or "")
                for chunk in response.get("chunks") or []
                if isinstance(chunk, dict)
            ).strip()
            if text:
                texts.append(text)
    return texts


def _evaluate_conversational_quality(
    texts: list[str],
    reference: dict[str, Any],
) -> dict[str, Any]:
    rules = reference.get("quality_rules") or {}
    failures: list[str] = []
    if not texts:
        failures.append("No observed agent responses were returned by CES.")
        return {"passed": False, "failures": failures, "observed_turns": 0}

    first = texts[0].lower()
    brand = str(rules.get("required_brand") or "")
    if brand and brand.lower() not in first:
        failures.append(f"Initial readout omitted required brand {brand!r}.")
    for alternatives in rules.get("initial_required_phrases") or []:
        values = [str(value) for value in alternatives]
        if values and not any(value.lower() in first for value in values):
            failures.append(
                "Initial readout omitted required context: "
                + " or ".join(repr(value) for value in values)
                + "."
            )

    def normalized_spoken(value: str) -> str:
        return " ".join(
            value.lower()
            .replace("-", " ")
            .replace(",", "")
            .replace(".", " ")
            .split()
        )

    def numeric_currency_variants(canonical: str) -> set[str]:
        raw = canonical.strip().removeprefix("$").replace(",", "")
        try:
            dollars_text, cents_text = f"{float(raw):.2f}".split(".")
        except ValueError:
            return set()
        variants = {f"{dollars_text} dollars"}
        if cents_text != "00":
            variants.update(
                {
                    f"{dollars_text} dollars {cents_text} cents",
                    f"{dollars_text} dollars and {cents_text} cents",
                }
            )
        return variants

    def check_inventory(label: str, text: str) -> None:
        normalized_text = normalized_spoken(text)
        for item in rules.get("transaction_inventory") or []:
            merchant = str(item.get("merchant") or "")
            canonical_amount = str(item.get("canonical_amount") or "")
            spoken_amounts = [
                normalized_spoken(str(value))
                for value in item.get("spoken_amounts") or []
            ]
            if merchant and merchant.lower() not in text.lower():
                failures.append(f"{label} omitted merchant {merchant!r}.")
            amount_present = (
                canonical_amount
                and canonical_amount.lower() in text.lower()
            ) or any(
                value in normalized_text
                for value in (
                    spoken_amounts
                    + sorted(numeric_currency_variants(canonical_amount))
                )
            )
            if canonical_amount and not amount_present:
                failures.append(
                    f"{label} omitted exact amount {canonical_amount!r}."
                )

    check_inventory("Initial readout", texts[0])
    proposal_turn_index = int(rules.get("proposal_turn_index", 1))
    if proposal_turn_index >= len(texts):
        failures.append("Observed dialogue omitted the proposal turn.")
    else:
        check_inventory("Proposal confirmation", texts[proposal_turn_index])

    commit_turn_index = int(rules.get("commit_turn_index", 2))
    if commit_turn_index >= len(texts):
        failures.append("Observed dialogue omitted the commit-result turn.")
    else:
        commit_text = texts[commit_turn_index].lower()
        for alternatives in rules.get("commit_required_phrases") or []:
            values = [str(value) for value in alternatives]
            if values and not any(value.lower() in commit_text for value in values):
                failures.append(
                    "Commit result omitted required outcome: "
                    + " or ".join(repr(value) for value in values)
                    + "."
                )

    joined = "\n".join(texts).lower()
    for phrase in rules.get("forbidden_phrases") or []:
        if str(phrase).lower() in joined:
            failures.append(f"Observed forbidden phrase {phrase!r}.")

    confirmation_markers = (
        "do you confirm",
        "please confirm",
        "just to confirm",
        "is that correct",
        "does that sound right",
        "does that sound good",
        "do you want to proceed",
    )
    confirmation_turns = sum(
        any(marker in text.lower() for marker in confirmation_markers)
        for text in texts
    )
    expected_confirmation_turns = int(
        rules.get("proposal_confirmation_turns", 1)
    )
    if confirmation_turns != expected_confirmation_turns:
        failures.append(
            "Expected "
            f"{expected_confirmation_turns} proposal confirmation turn(s), "
            f"observed {confirmation_turns}."
        )
    return {
        "passed": not failures,
        "failures": failures,
        "observed_turns": len(texts),
        "proposal_confirmation_turns": confirmation_turns,
    }


def _managed_conversational_evaluation(
    api: CesApi,
    *,
    app: str,
    app_version: str,
    reference: dict[str, Any],
) -> dict[str, Any]:
    reference_id = str(reference["reference_id"])
    display_name = str(reference["display_name"])
    evaluation_path = f"{app}/evaluations/{reference_id}"
    threshold = int(
        (reference.get("quality_rules") or {}).get(
            "semantic_similarity_success_threshold", 3
        )
    )
    evaluation_body = {
        "displayName": display_name,
        "description": str(reference["description"]),
        "tags": ["conversational-reference", "fraud", "customer-experience"],
        "golden": _conversational_golden(app, reference),
        "evaluationMetricsThresholdOverride": {
            "goldenEvaluationMetricsThresholds": {
                "turnLevelMetricsThresholds": {
                    "semanticSimilaritySuccessThreshold": threshold,
                    "overallToolInvocationCorrectnessThreshold": 1,
                    "semanticSimilarityChannel": "TEXT",
                },
                "expectationLevelMetricsThresholds": {
                    "toolInvocationParameterCorrectnessThreshold": 1
                },
            }
        },
    }
    try:
        existing = api.request("GET", evaluation_path)
        evaluation = api.request(
            "PATCH",
            evaluation_path,
            {"name": existing["name"], **evaluation_body},
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
            {"evaluationId": reference_id},
        )

    dataset_id = reference_id
    dataset_path = f"{app}/evaluationDatasets/{dataset_id}"
    try:
        existing_dataset = api.request("GET", dataset_path)
        dataset = api.request(
            "PATCH",
            dataset_path,
            {
                "name": existing_dataset["name"],
                "displayName": display_name,
                "evaluations": [evaluation["name"]],
            },
            {"updateMask": "display_name,evaluations"},
        )
    except RuntimeError as error:
        if "HTTP 404" not in str(error):
            raise
        dataset = api.request(
            "POST",
            f"{app}/evaluationDatasets",
            {
                "displayName": display_name,
                "evaluations": [evaluation["name"]],
            },
            {"evaluationDatasetId": dataset_id},
        )

    operation = api.wait_operation(
        api.request(
            "POST",
            f"{app}:runEvaluation",
            {
                "evaluationDataset": dataset["name"],
                "displayName": (
                    f"{display_name} "
                    f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                ),
                "appVersion": app_version,
                "goldenRunMethod": "STABLE",
                "runCount": int(reference.get("run_count", 3)),
                "config": {
                    "evaluationChannel": "TEXT",
                    "toolCallBehaviour": "FAKE",
                },
            },
        )
    )
    response = operation.get("response") or {}
    run_name = response.get("name") or response.get("evaluationRun")
    if not run_name:
        raise RuntimeError(
            "CES completed the conversational run without a run resource name."
        )
    run = api.request("GET", run_name)
    results: list[dict[str, Any]] = []
    for result_name in run.get("evaluationResults") or []:
        result = api.request("GET", result_name)
        texts = _observed_agent_texts(result)
        quality = _evaluate_conversational_quality(texts, reference)
        results.append(
            {
                "name": result.get("name"),
                "execution_state": result.get("executionState"),
                "evaluation_status": result.get("evaluationStatus"),
                "app_version": result.get("appVersion"),
                "quality": quality,
            }
        )
    return {
        "evaluation": evaluation.get("name"),
        "dataset": dataset.get("name"),
        "run": run.get("name"),
        "run_id": _resource_id(run.get("name")),
        "run_state": run.get("state"),
        "app_version": run.get("appVersion"),
        "results": results,
        "passed": bool(results)
        and all(
            result.get("execution_state") == "COMPLETED"
            and result.get("evaluation_status") == "PASS"
            and (result.get("quality") or {}).get("passed") is True
            for result in results
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--app", required=True)
    conversation_group = parser.add_mutually_exclusive_group(required=True)
    conversation_group.add_argument("--conversation")
    conversation_group.add_argument(
        "--latest",
        action="store_true",
        help="Use the newest completed LIVE conversation for the specified app.",
    )
    parser.add_argument("--app-version")
    parser.add_argument("--account")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--scenario", default="fraud-contract")
    parser.add_argument("--managed", action="store_true")
    parser.add_argument(
        "--managed-suite",
        choices=("all", "closeout"),
        default="all",
        help=(
            "Run the complete managed qualification suite or only the focused "
            "servicing closeout contract."
        ),
    )
    parser.add_argument(
        "--conversational-reference",
        type=Path,
        default=DEFAULT_CONVERSATIONAL_REFERENCE,
    )
    parser.add_argument("--dataset-id", default="ces-fraud-contract-v1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    matrix = json.loads(args.matrix.read_text())
    scenario = _scenario(matrix, args.scenario)
    api = CesApi(project=args.project, account=args.account)
    conversation_name = (
        _latest_live_conversation(api, args.app)
        if args.latest
        else args.conversation
    )
    conversation = api.request(
        "GET", conversation_name, query={"source": "LIVE"}
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
        app_version = _app_version_for_app(
            args.app,
            args.app_version or conversation.get("appVersion"),
        )
        if not app_version:
            raise ValueError("--app-version is required when the conversation omits it.")
        conversational_reference = json.loads(
            args.conversational_reference.read_text()
        )
        if args.managed_suite == "all":
            report["managed_evaluation"] = _managed_contract_evaluation(
                api,
                app=args.app,
                app_version=app_version,
                reference=conversational_reference,
                dataset_id=args.dataset_id,
                display_name="Bounded CES fraud qualification work item 1",
            )
        report["closeout_evaluation"] = _managed_contract_evaluation(
            api,
            app=args.app,
            app_version=app_version,
            reference=conversational_reference,
            dataset_id="ces-servicing-closeout-v1",
            display_name="CES servicing closeout contract",
            golden=_closeout_contract_golden(args.app),
            tags=[
                "bounded-qualification",
                "reviewed-contract",
                "closeout",
                "credit-limit",
            ],
            run_count=3,
            required_agent_response_role="Session Closeout Agent",
        )
        if args.managed_suite == "all":
            report["conversational_evaluation"] = (
                _managed_conversational_evaluation(
                    api,
                    app=args.app,
                    app_version=app_version,
                    reference=conversational_reference,
                )
            )

    if args.managed and args.managed_suite == "closeout":
        report["passed"] = report["closeout_evaluation"]["passed"]
    else:
        report["passed"] = result.passed and (
            not args.managed
            or (
                report["closeout_evaluation"]["passed"]
                and report["managed_evaluation"]["passed"]
                and report["conversational_evaluation"]["passed"]
            )
        )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
