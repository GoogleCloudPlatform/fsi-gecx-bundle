#!/usr/bin/env python3
"""Run non-mutating readiness and evaluate a deployed voice trajectory."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.trajectory_eval import TrajectoryExpectation, evaluate_trajectory  # noqa: E402
from agent.log_safety import stable_log_reference  # noqa: E402


SESSION_PATTERN = re.compile(r"session_ref=(session_[0-9a-f]{12})")
TOOL_PATTERN = re.compile(r"tool_name=([a-z0-9_]+)")
EVENT_PATTERN = re.compile(r"event_type=([A-Z0-9_]+)")
RESET_PATTERN = re.compile(r"reset_generation=([^ ]+)")
OUTCOME_PATTERN = re.compile(r"terminal_outcome=([A-Z_]+)")


SCENARIOS = {
    "fraud": TrajectoryExpectation(
        required_tools={"get_open_fraud_alert": 1, "triage_fraud_case": 1},
        required_ui_events=("FRAUD_ALERT_RESOLVED",),
    ),
    "fraud-wallet": TrajectoryExpectation(
        required_tools={
            "get_open_fraud_alert": 1,
            "triage_fraud_case": 1,
            "push_card_to_google_wallet": 1,
        },
        required_ui_events=("FRAUD_ALERT_RESOLVED", "WALLET_PROVISIONING_QUEUED"),
    ),
    "wallet-decline": TrajectoryExpectation(
        required_tools={"get_open_fraud_alert": 1, "triage_fraud_case": 1},
        forbidden_tools=("push_card_to_google_wallet",),
        required_ui_events=("FRAUD_ALERT_RESOLVED",),
    ),
    "customer-reported": TrajectoryExpectation(
        required_tools={
            "get_open_fraud_alert": 1,
            "get_transaction_history": 1,
            "triage_customer_reported_fraud": 1,
        },
        required_ui_events=("FRAUD_ALERT_RESOLVED",),
    ),
}


def _message(entry: dict[str, Any]) -> str:
    return str(entry.get("textPayload") or (entry.get("jsonPayload") or {}).get("message") or "")


def _elapsed_ms(timestamp: str, start: datetime) -> float:
    current = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return round((current - start).total_seconds() * 1000, 3)


def extract_trajectory(
    entries: list[dict[str, Any]], session_selector: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    ordered = sorted(entries, key=lambda entry: entry.get("timestamp", ""))
    session_ref = None
    if session_selector:
        session_ref = (
            session_selector
            if session_selector.startswith("session_")
            else stable_log_reference(session_selector, prefix="session")
        )
    if session_ref is None:
        candidates = []
        for entry in ordered:
            message = _message(entry)
            if "Opened ADK session state" not in message:
                continue
            match = SESSION_PATTERN.search(message)
            if match:
                candidates.append(match.group(1))
        if not candidates:
            raise ValueError("No deployed voice session was found in the requested window.")
        session_ref = candidates[-1]

    selected = [
        entry
        for entry in ordered
        if f"session_ref={session_ref}" in _message(entry)
    ]
    if not selected:
        raise ValueError(f"No log entries found for session reference {session_ref}.")
    start = datetime.fromisoformat(selected[0]["timestamp"].replace("Z", "+00:00"))
    events: list[dict[str, Any]] = []
    for entry in selected:
        message = _message(entry)
        elapsed_ms = _elapsed_ms(entry["timestamp"], start)
        if "Opened ADK session state" in message:
            match = RESET_PATTERN.search(message)
            events.append(
                {
                    "type": "SESSION_STARTED",
                    "reset_generation": match.group(1) if match else None,
                    "elapsed_ms": elapsed_ms,
                }
            )
        elif "Loaded voice bootstrap" in message and "guidance_snapshot=" in message:
            source = re.search(r"['\"]source['\"]:\s*['\"]([^'\"]+)", message)
            topics = re.search(r"['\"]topic_ids['\"]:\s*\[([^]]*)\]", message)
            topic_ids = re.findall(r"['\"]([^'\"]+)['\"]", topics.group(1)) if topics else []
            events.append(
                {
                    "type": "GUIDANCE_SNAPSHOT",
                    "source": source.group(1) if source else None,
                    "topic_ids": topic_ids,
                    "elapsed_ms": elapsed_ms,
                }
            )
        elif "[CALLBACK] before_tool_callback triggered" in message:
            match = TOOL_PATTERN.search(message)
            if match:
                events.append(
                    {"type": "TOOL_CALL", "tool": match.group(1), "elapsed_ms": elapsed_ms}
                )
        elif "[CALLBACK] after_tool_callback triggered" in message:
            match = TOOL_PATTERN.search(message)
            if match:
                success = any(
                    marker in message
                    for marker in (
                        "'success': True",
                        '"success": true',
                        "'status': 'SUCCESS'",
                    )
                )
                events.append(
                    {
                        "type": "TOOL_RESULT",
                        "tool": match.group(1),
                        "success": success,
                        "elapsed_ms": elapsed_ms,
                    }
                )
        elif "Broadcasting event to LiveKit data channel" in message:
            match = EVENT_PATTERN.search(message)
            if match and match.group(1) != "TRANSCRIPT":
                events.append(
                    {"type": "UI_EVENT", "event": match.group(1), "elapsed_ms": elapsed_ms}
                )
        elif "ADK Live response interrupted" in message:
            events.append({"type": "INTERRUPTION", "elapsed_ms": elapsed_ms})
        elif "terminal_outcome=" in message:
            match = OUTCOME_PATTERN.search(message)
            events.append(
                {
                    "type": "SESSION_ENDED",
                    "outcome": match.group(1) if match else "UNKNOWN",
                    "elapsed_ms": elapsed_ms,
                }
            )
    return session_ref, events


def load_deployed_logs(project: str, region: str, freshness: str) -> list[dict[str, Any]]:
    command = [
        "gcloud",
        "logging",
        "read",
        'resource.type="cloud_run_revision" AND resource.labels.service_name="credit-support-agent"',
        f"--project={project}",
        f"--freshness={freshness}",
        "--limit=2000",
        "--order=desc",
        "--format=json",
    ]
    return json.loads(subprocess.check_output(command, text=True))


def run_readiness_proxy(
    *, project: str, region: str, customer_id: str | None, port: int
) -> dict[str, Any]:
    process = subprocess.Popen(
        [
            "gcloud",
            "run",
            "services",
            "proxy",
            "credit-support-agent",
            f"--project={project}",
            f"--region={region}",
            f"--port={port}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/internal/readiness"
        headers = {"x-target-customer-id": customer_id} if customer_id else None
        last_error: Exception | None = None
        for _ in range(30):
            try:
                response = httpx.get(url, headers=headers, timeout=10.0)
                return response.json()
            except Exception as error:
                last_error = error
                time.sleep(1)
        raise RuntimeError("Readiness proxy did not become available.") from last_error
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="fraud-wallet")
    parser.add_argument("--session-id")
    parser.add_argument("--customer-id")
    parser.add_argument("--freshness", default="2h")
    parser.add_argument("--readiness-only", action="store_true")
    parser.add_argument("--skip-readiness", action="store_true")
    parser.add_argument("--proxy-port", type=int, default=18080)
    args = parser.parse_args()

    output: dict[str, Any] = {}
    if not args.skip_readiness:
        output["readiness"] = run_readiness_proxy(
            project=args.project,
            region=args.region,
            customer_id=args.customer_id,
            port=args.proxy_port,
        )
    if not args.readiness_only:
        session_ref, events = extract_trajectory(
            load_deployed_logs(args.project, args.region, args.freshness),
            session_selector=args.session_id,
        )
        result = evaluate_trajectory(events, SCENARIOS[args.scenario])
        output["trajectory"] = {
            "session_ref": session_ref,
            "scenario": args.scenario,
            "passed": result.passed,
            "failures": result.failures,
            "metrics": result.metrics,
        }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if all(
        item.get("status") == "ready" or item.get("passed") is True
        for item in output.values()
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
