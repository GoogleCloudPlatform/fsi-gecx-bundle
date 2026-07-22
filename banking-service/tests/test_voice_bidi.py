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
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from main import app
from services.ces_session_bootstrap import CesSessionBootstrap
from services.voice_bidi import _PcmFrameBuffer, _configured_frame_duration_ms

client = TestClient(app)


def test_pcm_frame_buffer_pads_input_underruns_with_silence():
    buffer = _PcmFrameBuffer(frame_bytes=8)
    buffer.append(b"voice")

    frame, silence_bytes = buffer.next_frame()

    assert frame == b"voice\x00\x00\x00"
    assert silence_bytes == 3


def test_pcm_frame_buffer_drops_stale_audio_from_front():
    buffer = _PcmFrameBuffer(frame_bytes=4, max_buffered_frames=2)
    buffer.append(b"0123456789")

    first_frame, first_silence_bytes = buffer.next_frame()
    second_frame, second_silence_bytes = buffer.next_frame()

    assert first_frame == b"2345"
    assert second_frame == b"6789"
    assert first_silence_bytes == 0
    assert second_silence_bytes == 0
    assert buffer.dropped_bytes == 2


def test_ces_input_frame_duration_is_configurable(monkeypatch):
    monkeypatch.setenv("CES_INPUT_FRAME_DURATION_MS", "80")
    assert _configured_frame_duration_ms() == 80


def test_ces_input_frame_duration_rejects_unsafe_values(monkeypatch):
    monkeypatch.setenv("CES_INPUT_FRAME_DURATION_MS", "500")
    with pytest.raises(ValueError, match="between 20 and 200"):
        _configured_frame_duration_ms()


@pytest.fixture
def mock_firebase_app():
    """Mock firebase_admin initialize_app to prevent actual connection attempts."""
    with patch("firebase_admin.initialize_app") as mock_init:
        yield mock_init


@patch("routers.voice_bidi.validate_firebase_token")
@patch("services.voice_bidi.token_manager.get_token")
@patch("services.voice_bidi.build_ces_session_bootstrap")
@patch("websockets.connect")
@patch("services.voice_bidi.get_project_id")
def test_gecx_voice_stream_success(
    mock_get_project_id,
    mock_ws_connect,
    mock_build_bootstrap,
    mock_get_token,
    mock_validate_token,
    mock_firebase_app,
    monkeypatch,
):
    """Verify GECX WebSocket proxy successfully authenticates first-frame and forwards messages."""
    monkeypatch.setenv("GECX_APP_ID", "42345105-29cb-492d-8a60-07171bb72190")
    monkeypatch.setattr(
        "services.voice_bidi.mint_ces_session_capability",
        lambda _bootstrap: "opaque-session-capability",
    )

    # 1. Setup Mock user validation claims
    mock_get_project_id.return_value = "evo-genai-workspace"
    mock_validate_token.return_value = MagicMock(claims={"sub": "borrower-123"})
    mock_get_token.return_value = "mock-gcp-bearer-token"
    mock_build_bootstrap.side_effect = lambda _db, **kwargs: CesSessionBootstrap(
        support_session_id="support-session-1",
        runtime_name="CES_GEMINI_LIVE",
        runtime_session_id=kwargs["runtime_session_id"],
        customer_identity="borrower-123",
        customer_id="11111111-1111-1111-1111-111111111111",
        customer_ref="customer:abc123",
        reset_generation="0:7",
        catalog_snapshot_id="catalog-snapshot-1",
        catalog_content_version="2.1",
        entry_reason="fraud_alert",
        has_active_fraud_alert=True,
        guidance_summary="Use the active fraud workflow.",
        ces_app_id="42345105-29cb-492d-8a60-07171bb72190",
        ces_version_or_deployment_id="UNPINNED_APP",
    )

    # 2. Setup GECX Mock server WebSocket connection instance
    mock_gecx_ws = AsyncMock()
    # Mock the GECX response: Yield a single transcript json frame, then exit loop
    mock_gecx_ws.__aiter__.return_value = [
        json.dumps(
            {"sessionOutput": {"text": "Welcome to Horizon Financial support."}}
        ),
        json.dumps({"interruptionSignal": {"bargeIn": True}}),
    ]
    mock_ws_connect.return_value.__aenter__.return_value = mock_gecx_ws

    # 3. Trigger WebSocket connection using FastAPI TestClient
    with client.websocket_connect("/voice/gecx-stream") as websocket:
        # A. Send FIRST-FRAME auth packet
        websocket.send_text(
            json.dumps({"type": "AUTH", "token": "valid-firebase-session-token"})
        )

        # B. The server advertises the exact audio contract it negotiated.
        audio_config = websocket.receive_json()
        assert audio_config == {
            "type": "AUDIO_CONFIG",
            "input_sample_rate_hz": 16000,
            "output_sample_rate_hz": 16000,
            "encoding": "LINEAR16",
        }

        # C. Await response message forwarded from GECX
        response = websocket.receive_json()

        # D. Verify forwarded transcript properties
        assert response["type"] == "TRANSCRIPT"
        assert response["text"] == "Welcome to Horizon Financial support."
        assert response["author"] == "agent"

        # D2. Await second response, which should be the INTERRUPT event
        interrupt_response = websocket.receive_json()
        assert interrupt_response["type"] == "INTERRUPT"

        # E. Verify backend handshake call payload parameters
        sent_messages = [json.loads(c[0][0]) for c in mock_gecx_ws.send.call_args_list]
        config_msg = next((msg for msg in sent_messages if "config" in msg), None)
        assert config_msg is not None
        assert config_msg["config"]["session"].startswith(
            "projects/evo-genai-workspace/locations/us/apps/"
            "42345105-29cb-492d-8a60-07171bb72190/sessions/ces-"
        )

        variables_msg = next(
            (
                msg
                for msg in sent_messages
                if "realtimeInput" in msg and "variables" in msg["realtimeInput"]
            ),
            None,
        )
        assert variables_msg is not None
        variables = variables_msg["realtimeInput"]["variables"]
        assert variables["session_capability"] == "opaque-session-capability"
        assert "user_token" not in variables
        assert "access_token" not in variables
        assert variables["support_session_id"] == "support-session-1"
        assert variables["runtime_name"] == "CES_GEMINI_LIVE"
        assert variables["reset_generation"] == "0:7"
        assert variables["catalog_snapshot_id"] == "catalog-snapshot-1"
        assert variables["language_code"] == "en"
        assert variables["runtime_language_code"] == "en-US"
        assert variables["language_selection_source"] == "default"

        welcome_msg = next(
            (
                msg
                for msg in sent_messages
                if "realtimeInput" in msg and "event" in msg["realtimeInput"]
            ),
            None,
        )
        assert welcome_msg is not None
        assert welcome_msg["realtimeInput"]["event"]["event"] == "sys.welcome"
        assert sent_messages.index(variables_msg) < sent_messages.index(welcome_msg)

    runtime_session_id = mock_build_bootstrap.call_args.kwargs["runtime_session_id"]
    assert runtime_session_id.startswith("ces-")
    assert mock_build_bootstrap.call_args.kwargs["auth_provider_uid"] == (
        "borrower-123"
    )


def test_gecx_voice_stream_auth_missing(mock_firebase_app):
    """Verify that client is rejected with code 4001 if authentication fails or is malformed."""
    with client.websocket_connect("/voice/gecx-stream") as websocket:
        # Send malformed AUTH frame (missing token)
        websocket.send_text(json.dumps({"type": "AUTH"}))

        # Client connection should be instantly closed
        with pytest.raises(Exception):
            websocket.receive_json()


@patch("routers.voice_bidi.validate_firebase_token")
def test_gecx_voice_stream_rejects_missing_subject(
    mock_validate_token, mock_firebase_app, monkeypatch
):
    monkeypatch.setenv("GECX_APP_ID", "app-1")
    mock_validate_token.return_value = SimpleNamespace(claims={})

    with client.websocket_connect("/voice/gecx-stream") as websocket:
        websocket.send_text(json.dumps({"type": "AUTH", "token": "valid-token"}))
        with pytest.raises(Exception):
            websocket.receive_json()


@patch("routers.voice_bidi.VoiceBidiSession")
@patch("routers.voice_bidi.validate_firebase_token")
def test_gecx_voice_stream_fails_closed_when_bootstrap_rejects_session(
    mock_validate_token,
    mock_voice_session,
    mock_firebase_app,
    monkeypatch,
):
    monkeypatch.setenv("GECX_APP_ID", "app-1")
    mock_validate_token.return_value = SimpleNamespace(claims={"sub": "unknown-user"})
    mock_voice_session.return_value.start = AsyncMock(
        side_effect=ValueError("unknown identity")
    )

    with client.websocket_connect("/voice/gecx-stream") as websocket:
        websocket.send_text(json.dumps({"type": "AUTH", "token": "valid-token"}))
        assert websocket.receive_json() == {
            "type": "ERROR",
            "message": "Unable to start voice consultation.",
        }
        with pytest.raises(WebSocketDisconnect) as disconnect:
            websocket.receive_json()

    assert disconnect.value.code == 1011
