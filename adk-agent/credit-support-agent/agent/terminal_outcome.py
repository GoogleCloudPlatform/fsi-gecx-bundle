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

"""Explicit terminal outcomes for voice-session operational telemetry."""

from dataclasses import dataclass, field
from enum import StrEnum


class TerminalOutcome(StrEnum):
    NORMAL_DISCONNECT = "NORMAL_DISCONNECT"
    HANDOFF = "HANDOFF"
    MODEL_FAILURE = "MODEL_FAILURE"
    MEDIA_FAILURE = "MEDIA_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    HARD_TIMEOUT = "HARD_TIMEOUT"
    CANCELLED = "CANCELLED"


@dataclass
class ToolFailureTracker:
    """Track tool failures that were not recovered by a same-tool retry."""

    unresolved: set[str] = field(default_factory=set)

    def record(self, tool_name: str, outcome: str) -> None:
        if not tool_name:
            return
        if outcome == "success":
            self.unresolved.discard(tool_name)
        elif outcome in {"failure", "error"}:
            self.unresolved.add(tool_name)

    def terminal_outcome(self, current: TerminalOutcome) -> TerminalOutcome:
        if current == TerminalOutcome.NORMAL_DISCONNECT and self.unresolved:
            return TerminalOutcome.TOOL_FAILURE
        return current
