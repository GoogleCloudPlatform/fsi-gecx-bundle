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

"""Allowlisted numeric CES timings; never forward provider arguments or responses."""
import math


def ces_diagnostics(info):
    metrics = {"type": "VOICE_DIAGNOSTICS", "tool_ms": None, "provider_first_chunk_ms": None}
    def number(value):
        return (float(value) if isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0 else None)
    def visit(span, depth=0):
        if not isinstance(span, dict) or depth > 20:
            return
        if span.get("name") == "LLM":
            attributes = span.get("attributes")
            value = number(attributes.get("time to first chunk (ms)")) if isinstance(attributes, dict) else None
            if value is not None:
                metrics["provider_first_chunk_ms"] = value
        if span.get("name") == "Tool":
            duration = span.get("duration")
            if isinstance(duration, str) and duration.endswith("s"):
                try:
                    value = number(float(duration[:-1]) * 1000)
                    if value is not None:
                        metrics["tool_ms"] = value
                except ValueError:
                    pass
        children = span.get("childSpans")
        for child in (children[:200] if isinstance(children, list) else []):
            visit(child, depth + 1)
    if isinstance(info, dict):
        visit(info.get("rootSpan"))
    return metrics
