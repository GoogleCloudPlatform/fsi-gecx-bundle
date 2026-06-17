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
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.fixture
def mock_firebase_app():
    """Mock firebase_admin initialize_app to prevent actual connection attempts."""
    with patch("firebase_admin.initialize_app") as mock_init:
        yield mock_init

@patch("routers.mcp.voice_bidi.validate_firebase_token")
@patch("routers.mcp.voice_bidi.token_manager.get_token")
@patch("websockets.connect")
def test_gecx_voice_stream_success(mock_ws_connect, mock_get_token, mock_validate_token, mock_firebase_app):
    """Verify GECX WebSocket proxy successfully authenticates first-frame and forwards messages."""
    
    # 1. Setup Mock user validation claims
    mock_validate_token.return_value = MagicMock(claims={"sub": "borrower-123"})
    mock_get_token.return_value = "mock-gcp-bearer-token"
    
    # 2. Setup GECX Mock server WebSocket connection instance
    mock_gecx_ws = AsyncMock()
    # Mock the GECX response: Yield a single transcript json frame, then exit loop
    mock_gecx_ws.__aiter__.return_value = [
        json.dumps({
            "sessionOutput": {
                "text": "Welcome to Horizon Financial support."
            }
        })
    ]
    mock_ws_connect.return_value.__aenter__.return_value = mock_gecx_ws
    
    # 3. Trigger WebSocket connection using FastAPI TestClient
    with client.websocket_connect("/voice/gecx-stream") as websocket:
        # A. Send FIRST-FRAME auth packet
        websocket.send_text(json.dumps({
            "type": "AUTH",
            "token": "valid-firebase-session-token"
        }))
        
        # B. Await response message forwarded from GECX
        response = websocket.receive_json()
        
        # C. Verify forwarded transcript properties
        assert response["type"] == "TRANSCRIPT"
        assert response["text"] == "Welcome to Horizon Financial support."
        assert response["author"] == "agent"
        
        # D. Verify backend handshake call payload parameters
        mock_gecx_ws.send.assert_any_call(json.dumps({
            "config": {
                "session": "projects/evo-genai-workspace/locations/us/apps/42345105-29cb-492d-8a60-07171bb72190/sessions/session-borrower-123",
                "inputAudioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": 16000
                },
                "outputAudioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": 16000
                }
            }
        }))

def test_gecx_voice_stream_auth_missing(mock_firebase_app):
    """Verify that client is rejected with code 4001 if authentication fails or is malformed."""
    with client.websocket_connect("/voice/gecx-stream") as websocket:
        # Send malformed AUTH frame (missing token)
        websocket.send_text(json.dumps({
            "type": "AUTH"
        }))
        
        # Client connection should be instantly closed
        with pytest.raises(Exception):
            websocket.receive_json()
