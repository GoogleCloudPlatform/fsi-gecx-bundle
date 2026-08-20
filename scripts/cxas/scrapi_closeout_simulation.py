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

"""Run a SCRAPI audio simulation for the CES closeout contract."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from cxas_scrapi.evals.simulation_evals import SimulationEvals


def _expectations() -> list[str]:
    return [
        (
            "After the final customer utterance, the Session Closeout "
            "Agent emits exactly one short spoken farewell before the "
            "session ends."
        ),
        (
            "The Session Closeout Agent calls native end_session with reason "
            "customer_query_ended after its farewell in the same turn."
        ),
        (
            "The Session Closeout Agent does not transfer control back "
            "to the Credit Card Support Agent."
        ),
        "The agent emits no speech after the native end_session call.",
    ]


def _credit_limit_test_case() -> dict[str, Any]:
    return {
        "name": "credit_limit_closeout_audio",
        "steps": [
            {
                "goal": "Confirm the proposed credit limit increase.",
                "success_criteria": (
                    "The limit increase succeeds and the support agent asks "
                    "whether the customer needs anything else."
                ),
                "static_utterance": "That's correct.",
                "max_turns": 1,
            },
            {
                "goal": "End the consultation after declining more help.",
                "success_criteria": (
                    "The closeout agent speaks one short farewell and then "
                    "calls native end_session with reason customer_query_ended."
                ),
                "max_turns": 1,
            },
        ],
        "expectations": _expectations(),
    }


def _checkpoint_test_case() -> dict[str, Any]:
    return {
        "name": "authorized_closeout_audio",
        "session_parameters": {
            "closeout_checkpoint_state": "OFFERED",
            "closeout_originating_turn_id": "scrapi-closeout-offer",
            "closeout_originating_input_fingerprint": "",
            "closeout_delegation_authorized": False,
            "proposal_id": "",
            "proposal_commit_attempted": False,
        },
        "steps": [
            {
                "goal": "Generate an authorized consultation farewell.",
                "success_criteria": (
                    "The closeout agent speaks one short farewell and then "
                    "calls native end_session with reason customer_query_ended."
                ),
                "static_utterance": "No, that's all.",
                "max_turns": 1,
            },
        ],
        "expectations": _expectations(),
    }


def _strict_closeout_checks(trace_chunks: list[str]) -> dict[str, Any]:
    lines = [
        line.strip()
        for chunk in trace_chunks
        for line in str(chunk).splitlines()
        if line.strip()
    ]
    # SCRAPI exposes the simulated customer's turns with a stable event label.
    # Locate the final turn structurally; its wording is deliberately outside
    # the deterministic evaluation contract.
    customer_turn_indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith("User:")
    ]
    final_user_index = (
        customer_turn_indexes[-1] if customer_turn_indexes else -1
    )
    tail = lines[final_user_index + 1 :] if final_user_index >= 0 else []

    closeout_transfer_indexes = [
        index
        for index, line in enumerate(tail)
        if "Agent Transfer:" in line and "Session Closeout Agent" in line
    ]
    support_return_indexes = [
        index
        for index, line in enumerate(tail)
        if "Agent Transfer:" in line and "Credit Card Support Agent" in line
    ]
    farewell_indexes = [
        index for index, line in enumerate(tail) if line.startswith("Agent Text")
    ]
    end_indexes = [
        index
        for index, line in enumerate(tail)
        if "Tool Call" in line and "end_session" in line
    ]
    farewell_before_end = bool(
        farewell_indexes
        and end_indexes
        and farewell_indexes[0] < end_indexes[0]
    )
    no_speech_after_end = bool(end_indexes) and not any(
        index > end_indexes[-1] for index in farewell_indexes
    )
    correct_reason = any(
        "customer_query_ended" in tail[index] for index in end_indexes
    )
    checks = {
        "final_customer_turn_observed": final_user_index >= 0,
        "closeout_transfer_observed": bool(closeout_transfer_indexes),
        "farewell_observed": bool(farewell_indexes),
        "end_session_observed": bool(end_indexes),
        "farewell_before_end_session": farewell_before_end,
        "end_session_reason_correct": correct_reason,
        "no_return_to_support_agent": not support_return_indexes,
        "no_speech_after_end_session": no_speech_after_end,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "terminal_trace": tail,
    }


def _records(dataframe: Any) -> list[dict[str, Any]]:
    if dataframe is None:
        return []
    return dataframe.to_dict(orient="records")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--app",
        required=True,
        help="Full CES app resource name.",
    )
    parser.add_argument(
        "--deployment-id",
        help=(
            "Optional deployed version to exercise. Omit to test the current "
            "CX Agent Studio draft."
        ),
    )
    parser.add_argument(
        "--modality", choices=("audio", "text"), default="audio"
    )
    parser.add_argument(
        "--scenario",
        choices=("checkpoint", "credit-limit"),
        default="checkpoint",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    session_id = f"scrapi-closeout-{uuid.uuid4().hex[:16]}"
    simulations = SimulationEvals(
        app_name=args.app,
        deployment_id=args.deployment_id,
        expectations_only=True,
    )
    conversation = simulations.simulate_conversation(
        test_case=(
            _checkpoint_test_case()
            if args.scenario == "checkpoint"
            else _credit_limit_test_case()
        ),
        session_id=session_id,
        console_logging=not args.quiet,
        modality=args.modality,
        use_tool_fakes=True,
        single_bidi_stream=args.modality == "audio",
        skip_playback_wait=False,
        sim_user_model="gemini-3.1-flash-lite",
        eval_model="gemini-3.1-flash-lite",
        initial_utterance=(
            "No, that's all."
            if args.scenario == "checkpoint"
            else "Can you raise my credit limit to $11,250, please?"
        ),
    )
    report = conversation.generate_report()
    strict = _strict_closeout_checks(conversation.detailed_trace)
    expectations = _records(report.expectations_df)
    judged_pass = bool(expectations) and all(
        item.get("status") == "Met" for item in expectations
    )
    result = {
        "schema_version": "1.0",
        "app": args.app,
        "deployment_id": args.deployment_id,
        "target": "deployment" if args.deployment_id else "draft",
        "modality": args.modality,
        "scenario": args.scenario,
        "single_bidi_stream": args.modality == "audio",
        "tool_fakes": True,
        "session_id": session_id,
        "passed": strict["passed"] and judged_pass,
        "strict_closeout": strict,
        "goals": _records(report.goals_df),
        "expectations": expectations,
        "transcript": conversation.get_transcript().splitlines(),
        "trace": conversation.detailed_trace,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "passed": result["passed"],
        "strict_closeout": strict,
        "expectations": expectations,
    }, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
