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

import json

from agent import telemetry


def test_structured_metric_is_low_cardinality_and_machine_readable(capsys) -> None:
    telemetry.record_tool_completed("triage_fraud_case", "success", 0.125)

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert [event["metric"] for event in events] == [
        "voice.tool.calls",
        "voice.tool.duration",
    ]
    assert events[1]["value"] == 0.125
    assert events[1]["attributes"] == {
        "tool": "triage_fraud_case",
        "outcome": "success",
    }
    assert "customer" not in str(events)


def test_avatar_fallback_metric_has_bounded_reason(capsys) -> None:
    telemetry.record_avatar_fallback("decoder_stopped")

    event = json.loads(capsys.readouterr().out)

    assert event["metric"] == "voice.avatar.fallbacks"
    assert event["attributes"] == {"reason": "decoder_stopped"}


def test_action_proposal_event_is_correlatable_without_raw_ids(capsys) -> None:
    telemetry.record_action_proposal_event(
        runtime="ADK_GEMINI_LIVE",
        support_session_id="support-session-secret",
        proposal_id="proposal-secret",
        contract_version="fraud-triage.v1",
        catalog_snapshot_id="catalog-7",
        tool="commit_fraud_triage",
        outcome="COMMITTED",
        latency_ms=125.5,
        banking_outcome="CONFIRMED_FRAUD_REMEDIATED",
    )

    event = json.loads(capsys.readouterr().out)

    assert event["message"] == "voice_action_proposal_event"
    assert event["runtime"] == "ADK_GEMINI_LIVE"
    assert event["runtime_version"]
    assert event["support_session_ref"].startswith("session_")
    assert event["proposal_ref"].startswith("proposal_")
    assert event["contract_version"] == "fraud-triage.v1"
    assert event["catalog_snapshot_id"] == "catalog-7"
    assert event["tool"] == "commit_fraud_triage"
    assert event["outcome"] == "COMMITTED"
    assert event["banking_outcome"] == "CONFIRMED_FRAUD_REMEDIATED"
    assert event["latency_ms"] == 125.5
    assert "support-session-secret" not in str(event)
    assert "proposal-secret" not in str(event)
