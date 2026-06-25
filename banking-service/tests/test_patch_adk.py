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

import sys
import os

# Set dummy model environment variable to bypass Pydantic import-time validation
os.environ["VOICE_AGENT_AUDIO_MODEL"] = "gemini-2.0-flash-exp"

# Add credit-support-agent directory to sys.path to resolve imports correctly
agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../adk-agent/credit-support-agent"))
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)

def test_monkeypatch_application():
    """Verifies that the ADK monkeypatch loads and applies receive method correctly without signature mismatch."""
    from agent.patch_adk import apply_patch
    from google.adk.models.gemini_llm_connection import GeminiLlmConnection

    original_receive = GeminiLlmConnection.receive
    try:
        # Apply the monkeypatch
        apply_patch()
        
        # Check that the method was replaced
        assert GeminiLlmConnection.receive != original_receive
        
        # Verify that it is callable
        assert callable(GeminiLlmConnection.receive)
    finally:
        # Restore original method to avoid polluting other test states
        GeminiLlmConnection.receive = original_receive
