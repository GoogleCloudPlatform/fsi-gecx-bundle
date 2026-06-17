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

import os
import time
import json
import base64
import asyncio
import logging
import websockets
from typing import Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.auth import validate_firebase_token
from utils.env import is_running_locally
from utils.gcp import get_project_id
import google.auth
import google.auth.transport.requests

router = APIRouter()
logger = logging.getLogger(__name__)

# Registry of active session queues for out-of-band updates (e.g. card locking sync)
active_sessions: Dict[str, asyncio.Queue] = {}

class GCPTokenManager:
    """Thread-safe cached OAuth2 access token manager for GECX API connectivity."""
    def __init__(self):
        self._token = None
        self._expiry = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            now = time.time()
            # Refresh if token is close to expiry (within 5 minutes) or missing
            if not self._token or (self._expiry - now) < 300.0:
                await self._refresh_token()
            return self._token

    async def _refresh_token(self):
        logger.info("Refreshing Google OAuth2 Access Token for GECX stream...")
        credentials, _ = await asyncio.to_thread(
            google.auth.default,
            scopes=["https://www.googleapis.com/auth/ces", "https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        await asyncio.to_thread(credentials.refresh, auth_req)
        self._token = credentials.token
        self._expiry = credentials.expiry.timestamp() if credentials.expiry else (time.time() + 3600.0)

token_manager = GCPTokenManager()

async def send_session_event(session_id: str, event_payload: dict):
    """Pushes out-of-band events (like tool-driven card lock) directly into the WebSocket playout loop."""
    queue = active_sessions.get(session_id)
    if queue:
        await queue.put(event_payload)
        logger.info(f"OOB event queued for GECX session {session_id}: {event_payload}")
    else:
        logger.debug(f"OOB event discarded, GECX session {session_id} is inactive.")

@router.websocket("/voice/gecx-stream")
async def gecx_voice_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket proxy connection accepted. Awaiting first-frame authorization...")

    user_id = None
    session_id = None
    gecx_ws = None
    
    try:
        # 1. First-Frame Authentication Gate (enforces JWT token context)
        try:
            # Enforce strict 5-second timeout for authentication frame
            auth_frame_str = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_frame = json.loads(auth_frame_str)
            
            if auth_frame.get("type") != "AUTH" or not auth_frame.get("token"):
                raise ValueError("Missing type 'AUTH' or 'token' in first-frame.")
                
            if is_running_locally() and auth_frame.get("token") == "mock-local-token":
                user_id = "mock_user_id"
                session_id = "mock_session_id"
            else:
                validated_token = validate_firebase_token(auth_frame["token"])
                user_id = validated_token.claims.get("sub")
                session_id = f"session-{user_id}"
                
            logger.info(f"First-frame authentication succeeded. Session: {session_id} (User: {user_id})")
        except asyncio.TimeoutError:
            logger.warning("Auth timeout: First-frame auth token not received within 5 seconds.")
            await websocket.close(code=4001, reason="Authentication timeout.")
            return
        except Exception as auth_err:
            logger.warning(f"Auth failed: Invalid Firebase token details. {auth_err}")
            await websocket.close(code=4001, reason="Authentication failed.")
            return

        # 2. Establish connection to Google GECx API
        project_id = get_project_id()
        gecx_app_id = os.getenv("GECX_APP_ID", "42345105-29cb-492d-8a60-07171bb72190")
        session_name = f"projects/{project_id}/locations/us/apps/{gecx_app_id}/sessions/{session_id}"
        
        # Determine target region endpoint
        location = os.getenv("GECX_LOCATION", "us")
        gecx_uri = f"wss://ces.googleapis.com/ws/google.cloud.ces.v1.SessionService/BidiRunSession/locations/{location}"
        
        gcp_token = await token_manager.get_token()
        headers = {
            "Authorization": f"Bearer {gcp_token}"
        }
        
        logger.info(f"Opening GECX Bidi Session at {gecx_uri} (Session: {session_name})...")
        async with websockets.connect(gecx_uri, additional_headers=headers) as gecx_ws:
            logger.info("Connected to GECX. Performing handshake...")
            
            # Send GECX config header payload
            config_msg = {
                "config": {
                    "session": session_name,
                    "inputAudioConfig": {
                        "audioEncoding": "LINEAR16",
                        "sampleRateHertz": 16000
                    },
                    "outputAudioConfig": {
                        "audioEncoding": "LINEAR16",
                        "sampleRateHertz": 16000
                    }
                }
            }
            await gecx_ws.send(json.dumps(config_msg))
            logger.info("Handshake configurations transmitted.")
            
            # Initialize queues with strict backpressure sizes
            client_to_gecx_queue = asyncio.Queue(maxsize=100)
            gecx_to_client_queue = asyncio.Queue(maxsize=100)
            
            # Register queue for out-of-band tool events
            active_sessions[session_id] = gecx_to_client_queue
            
            # Task A: Read frames from browser WebSocket client
            async def read_client():
                try:
                    while True:
                        data = await websocket.receive()
                        if "bytes" in data:
                            message = data["bytes"]
                            # DoS protection: limit frame size to 64KB
                            if len(message) > 65536:
                                logger.error("Security warning: Client sent binary frame exceeding 64KB limit.")
                                break
                            logger.info(f"Received binary frame from browser client: {len(message)} bytes")
                            await client_to_gecx_queue.put(message)
                        elif "text" in data:
                            payload = json.loads(data["text"])
                            if payload.get("type") == "PING":
                                await websocket.send_json({
                                    "type": "PONG",
                                    "timestamp": payload.get("timestamp")
                                })
                except (WebSocketDisconnect, RuntimeError) as ex:
                    if isinstance(ex, RuntimeError) and "disconnect" not in str(ex) and "receive" not in str(ex):
                        logger.error(f"RuntimeError in WebSocket read_client: {ex}")
                    else:
                        logger.debug("Client browser disconnected.")
                except Exception as ex:
                    logger.error(f"Error in WebSocket read_client: {ex}")
                finally:
                    await client_to_gecx_queue.put(None)

            # Task B: Base64-encode and forward audio frames to GECx WebSocket
            async def send_to_gecx():
                try:
                    while True:
                        chunk = await client_to_gecx_queue.get()
                        if chunk is None:
                            break
                        
                        b64_audio = base64.b64encode(chunk).decode("utf-8")
                        realtime_input = {
                            "realtimeInput": {
                                "audio": b64_audio
                            }
                        }
                        await gecx_ws.send(json.dumps(realtime_input))
                        logger.info(f"Forwarded {len(chunk)} bytes of audio to GECX.")
                        client_to_gecx_queue.task_done()
                except Exception as ex:
                    logger.error(f"Error in send_to_gecx: {ex}")

            # Task C: Read text and audio frames from Google GECX API
            async def read_from_gecx():
                try:
                    async for message in gecx_ws:
                        response = json.loads(message)
                        logger.info(f"Received frame from GECX: {list(response.keys())}")
                        
                        # GECx SessionOutput (audio and text transcript)
                        session_output = response.get("sessionOutput", {})
                        if session_output:
                            b64_audio = session_output.get("audio", "")
                            if b64_audio:
                                raw_pcm = base64.b64decode(b64_audio)
                                logger.info(f"Received {len(raw_pcm)} bytes of response audio from GECX.")
                                await gecx_to_client_queue.put({"type": "AUDIO", "data": raw_pcm})
                                
                            text = session_output.get("text", "")
                            if text:
                                logger.info(f"Received text transcript from GECX: {len(text)} chars")
                                await gecx_to_client_queue.put({
                                    "type": "TRANSCRIPT",
                                    "text": text,
                                    "author": "agent"
                                })
                                
                        # GECx User Speech Recognition result (for UI transcript display)
                        recognition_result = response.get("recognitionResult", {})
                        if recognition_result:
                            user_transcript = recognition_result.get("transcript", "")
                            if user_transcript:
                                logger.info(f"Received user speech transcript recognition from GECX: {user_transcript}")
                                await gecx_to_client_queue.put({
                                    "type": "TRANSCRIPT",
                                    "text": user_transcript,
                                    "author": "user"
                                })
                except Exception as ex:
                    logger.error(f"Error in read_from_gecx: {ex}")
                finally:
                    await gecx_to_client_queue.put(None)

            # Task D: Forward payloads back to client browser WebSocket
            async def send_to_client():
                try:
                    while True:
                        payload = await gecx_to_client_queue.get()
                        if payload is None:
                            break
                            
                        if isinstance(payload, dict) and payload.get("type") != "AUDIO":
                            await websocket.send_json(payload)
                        elif isinstance(payload, dict) and payload.get("type") == "AUDIO":
                            await websocket.send_bytes(payload["data"])
                        else:
                            # Direct binary frame fallback
                            await websocket.send_bytes(payload)
                            
                        gecx_to_client_queue.task_done()
                except Exception as ex:
                    logger.error(f"Error in send_to_client: {ex}")

            # Task E: Send keep-alive heartbeats to client to prevent load-balancer dropouts
            async def send_pings():
                try:
                    while True:
                        await asyncio.sleep(20)
                        await websocket.send_json({"type": "PING"})
                except Exception:
                    pass

            # Gather all running loops and enforce 10-minute timeout limit
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_client(),
                        send_to_gecx(),
                        read_from_gecx(),
                        send_to_client(),
                        send_pings()
                    ),
                    timeout=600.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"Session {session_id} timed out after 10 minutes.")
                await websocket.send_json({
                    "type": "ERROR",
                    "message": "Maximum session duration (10 minutes) exceeded."
                })
                
    except Exception as e:
        logger.error(f"Session failure for session {session_id}: {e}")
    finally:
        logger.info(f"WebSocket session clean-up initiated for {session_id}...")
        # Deregister session queue
        if session_id:
            active_sessions.pop(session_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
