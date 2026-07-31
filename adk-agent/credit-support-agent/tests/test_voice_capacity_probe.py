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

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "voice_capacity_probe.py"
SPEC = importlib.util.spec_from_file_location("voice_capacity_probe", SCRIPT)
voice_capacity_probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(voice_capacity_probe)


def test_capacity_matrix_separates_audio_and_avatar_costs() -> None:
    result = voice_capacity_probe.capacity_matrix(8, 1, 4)

    assert result["audio_only_sessions"] == 8
    assert result["video_only_sessions"] == 2
    assert result["mixed_examples"][1] == {
        "video_sessions": 1,
        "remaining_audio_sessions": 4,
    }


def test_live_summary_requires_agent_join_not_only_http_admission() -> None:
    summary = voice_capacity_probe.summarize_live_results(
        [
            {
                "success": True,
                "admitted": True,
                "agent_joined": True,
                "admission_latency_ms": 100,
            },
            {
                "success": False,
                "admitted": True,
                "agent_joined": False,
                "admission_latency_ms": 300,
                "error_type": "AgentJoinTimeout",
            },
        ]
    )

    assert summary["admitted"] == 2
    assert summary["agent_joined"] == 1
    assert summary["successful"] == 1
    assert summary["admission_latency_ms_median"] == 200
    assert summary["admission_latency_ms_p95"] == 300
