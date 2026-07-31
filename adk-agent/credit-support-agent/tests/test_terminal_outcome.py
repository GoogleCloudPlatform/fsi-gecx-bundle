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

from agent.terminal_outcome import TerminalOutcome, ToolFailureTracker


def test_unresolved_tool_failure_has_distinct_terminal_outcome() -> None:
    tracker = ToolFailureTracker()
    tracker.record("push_card_to_google_wallet", "failure")

    assert (
        tracker.terminal_outcome(TerminalOutcome.NORMAL_DISCONNECT)
        == TerminalOutcome.TOOL_FAILURE
    )


def test_successful_same_tool_retry_resolves_failure() -> None:
    tracker = ToolFailureTracker()
    tracker.record("push_card_to_google_wallet", "error")
    tracker.record("push_card_to_google_wallet", "success")

    assert (
        tracker.terminal_outcome(TerminalOutcome.NORMAL_DISCONNECT)
        == TerminalOutcome.NORMAL_DISCONNECT
    )


def test_handoff_remains_primary_terminal_outcome() -> None:
    tracker = ToolFailureTracker()
    tracker.record("triage_fraud_case", "failure")

    assert (
        tracker.terminal_outcome(TerminalOutcome.HANDOFF)
        == TerminalOutcome.HANDOFF
    )
