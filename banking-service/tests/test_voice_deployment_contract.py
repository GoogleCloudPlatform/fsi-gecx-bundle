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

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cloud_run_retains_shutdown_headroom_beyond_voice_session_timeout():
    variables = (ROOT / "deployment/terraform/variables.tf").read_text()
    cloud_run = (ROOT / "deployment/terraform/cloud_run_v2.tf").read_text()

    assert 'variable "banking_service_timeout_seconds"' in variables
    assert "default = 720" in variables
    assert 'variable "banking_service_voice_session_timeout_seconds"' in variables
    assert "default     = 600" in variables
    assert "var.banking_service_voice_session_timeout_seconds + 60" in cloud_run
    assert 'name  = "VOICE_BIDI_SESSION_TIMEOUT_SECONDS"' in cloud_run
    assert (
        "value = tostring(var.banking_service_voice_session_timeout_seconds)"
        in cloud_run
    )
