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

from agent.session_coordinator import should_abandon_escalation
from agent.terminal_outcome import TerminalOutcome


def test_successful_handoff_does_not_abandon_escalation() -> None:
    assert not should_abandon_escalation(
        "escalation-1", TerminalOutcome.HANDOFF
    )


def test_disconnect_before_handoff_abandons_escalation() -> None:
    assert should_abandon_escalation(
        "escalation-1", TerminalOutcome.NORMAL_DISCONNECT
    )


def test_no_active_escalation_needs_no_cleanup() -> None:
    assert not should_abandon_escalation(None, TerminalOutcome.MODEL_FAILURE)
