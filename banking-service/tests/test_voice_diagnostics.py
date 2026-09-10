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

from services.voice_diagnostics import ces_diagnostics


def test_only_safe_numeric_provider_metrics_are_forwarded():
    info = {"rootSpan": {"childSpans": [
        {"name": "LLM", "attributes": {"time to first chunk (ms)": 123, "prompt": "private"}},
        {"name": "Tool", "duration": "0.04s", "attributes": {"args": {"secret": "private"}}},
        {"name": "LLM", "attributes": {"time to first chunk (ms)": 98}},
    ]}}
    assert ces_diagnostics(info) == {"type": "VOICE_DIAGNOSTICS", "tool_ms": 40, "provider_first_chunk_ms": 98}


def test_missing_or_invalid_metrics_are_unavailable_not_zero():
    for info in [None, {}, {"rootSpan": {"name": "Tool", "duration": "nans"}},
                 {"rootSpan": {"name": "LLM", "attributes": {"time to first chunk (ms)": -1}}}]:
        assert ces_diagnostics(info) == {"type": "VOICE_DIAGNOSTICS", "tool_ms": None, "provider_first_chunk_ms": None}
