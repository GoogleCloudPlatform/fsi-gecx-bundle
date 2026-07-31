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

import pytest

from agent.runtime_config import VoiceRuntimeConfig, validate_session_request
from agent.session_coordinator import _parse_settings


def test_runtime_rejects_unknown_mode():
    config = VoiceRuntimeConfig("audio", "video", "ws://livekit", 10)
    with pytest.raises(ValueError, match="mode must"):
        validate_session_request(config, mode="text")


def test_video_can_fall_back_to_audio_model():
    config = VoiceRuntimeConfig("audio", None, "ws://livekit", 10)
    assert validate_session_request(config, mode="video") == "video"


def test_session_settings_reject_invalid_timeout_order():
    with pytest.raises(ValueError, match="warning duration"):
        _parse_settings(
            {
                "voice_agent_max_duration": 60,
                "voice_agent_warning_duration": 60,
            }
        )
