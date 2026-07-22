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

import base64
import json
import logging
import os
import time
import asyncio
import websockets
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect

from utils.gcp import get_project_id
from utils.log_safety import stable_log_reference
from services.ces_session_bootstrap import build_ces_session_bootstrap
from services.ces_session_capability import mint_ces_session_capability
import google.auth
import google.auth.transport.requests

logger = logging.getLogger(__name__)

# Registry of active session queues for out-of-band updates (e.g. card locking sync)
# Keyed by user_id
active_sessions: Dict[str, asyncio.Queue] = {}


def _configured_sample_rate(name: str, default: int = 16_000) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 8_000 or value > 48_000:
        raise ValueError(f"{name} must be between 8000 and 48000 Hz.")
    return value


async def send_session_event(session_key: str, event_payload: dict):
    """Pushes out-of-band events (like tool-driven card lock) directly into the WebSocket playout loop."""
    user_id = session_key.replace("session-", "")
    queue = active_sessions.get(user_id)
    if queue:
        await queue.put(event_payload)
        logger.info(
            "CES OOB event queued customer_ref=%s event_type=%s",
            stable_log_reference(user_id, "customer"),
            event_payload.get("type"),
        )
    else:
        logger.debug(
            "CES OOB event discarded customer_ref=%s reason=offline",
            stable_log_reference(user_id, "customer"),
        )


class GCPTokenManager:
    """Cached OAuth2 access token manager for GECX API connectivity."""

    def __init__(self):
        self._token = None
        self._expiry = 0.0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            now = time.time()
            if not self._token or (self._expiry - now) < 300.0:
                await self._refresh_token()
            return self._token

    async def _refresh_token(self):
        logger.info("Refreshing Google OAuth2 Access Token for GECX stream...")
        credentials, _ = await asyncio.to_thread(
            google.auth.default,
            scopes=[
                "https://www.googleapis.com/auth/ces",
                "https://www.googleapis.com/auth/cloud-platform",
            ],
        )
        auth_req = google.auth.transport.requests.Request()
        await asyncio.to_thread(credentials.refresh, auth_req)
        self._token = credentials.token
        self._expiry = (
            credentials.expiry.timestamp()
            if credentials.expiry
            else (time.time() + 3600.0)
        )


token_manager = GCPTokenManager()


class VoiceBidiSession:
    """Manages a single bi-directional voice streaming session with Google GECX."""

    def __init__(
        self,
        user_id: str,
        session_id: str,
        websocket: WebSocket,
        gecx_app_id: str,
        location: str,
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.client_ws = websocket
        self.gecx_app_id = gecx_app_id
        self.location = location
        self.client_to_gecx_queue = asyncio.Queue(maxsize=100)
        self.gecx_to_client_queue = asyncio.Queue(maxsize=100)
        self.bootstrap = None
        self._active_session_keys: set[str] = set()

    async def start(self):
        """Starts the active session streaming loops."""
        from utils.database import SessionLocal

        def load_bootstrap():
            db = SessionLocal()
            try:
                return build_ces_session_bootstrap(
                    db,
                    auth_provider_uid=self.user_id,
                    runtime_session_id=self.session_id,
                    gecx_app_id=self.gecx_app_id,
                )
            finally:
                db.close()

        self.bootstrap = await asyncio.to_thread(load_bootstrap)

        self.customer_id = self.bootstrap.customer_id
        self._active_session_keys = {self.user_id, self.customer_id}
        for key in self._active_session_keys:
            active_sessions[key] = self.gecx_to_client_queue
        logger.info(
            "CES session bootstrap established customer_ref=%s "
            "support_session_ref=%s runtime_session_ref=%s runtime=%s "
            "catalog_snapshot_ref=%s ces_app_id=%s ces_version_or_deployment_id=%s "
            "language_code=%s runtime_language_code=%s",
            self.bootstrap.customer_ref,
            stable_log_reference(self.bootstrap.support_session_id, "support-session"),
            stable_log_reference(self.bootstrap.runtime_session_id, "runtime-session"),
            self.bootstrap.runtime_name,
            stable_log_reference(
                self.bootstrap.catalog_snapshot_id, "catalog-snapshot"
            ),
            self.bootstrap.ces_app_id,
            self.bootstrap.ces_version_or_deployment_id,
            self.bootstrap.language_code,
            self.bootstrap.runtime_language_code,
        )

        try:
            await self._run_pipeline()
        finally:
            for key in self._active_session_keys:
                if active_sessions.get(key) is self.gecx_to_client_queue:
                    active_sessions.pop(key, None)

    async def _run_pipeline(self):
        project_id = get_project_id()
        input_sample_rate_hz = _configured_sample_rate("CES_INPUT_SAMPLE_RATE_HZ")
        output_sample_rate_hz = _configured_sample_rate("CES_OUTPUT_SAMPLE_RATE_HZ")
        transport_stats = {
            "input_frames": 0,
            "input_bytes": 0,
            "output_frames": 0,
            "output_bytes": 0,
        }

        app_id = self.bootstrap.ces_app_id
        deployment_path = None
        if "deployments/" in self.gecx_app_id:
            deployment_path = self.gecx_app_id
            parts = self.gecx_app_id.split("/")
            app_id = parts[parts.index("apps") + 1]

        session_name = (
            f"projects/{project_id}/locations/{self.location}/apps/{app_id}/"
            f"sessions/{self.session_id}"
        )
        gecx_uri = f"wss://ces.googleapis.com/ws/google.cloud.ces.v1.SessionService/BidiRunSession/locations/{self.location}"

        gcp_token = await token_manager.get_token()
        headers = {"Authorization": f"Bearer {gcp_token}"}

        logger.info(
            "Opening CES Bidi session runtime_session_ref=%s",
            stable_log_reference(self.session_id, "runtime-session"),
        )
        async with websockets.connect(gecx_uri, additional_headers=headers) as gecx_ws:
            logger.info("Connected to GECX. Performing handshake...")

            # Send GECX config header payload
            config = {
                "session": session_name,
                "inputAudioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": input_sample_rate_hz,
                },
                "outputAudioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": output_sample_rate_hz,
                },
            }
            if deployment_path:
                config["deployment"] = deployment_path

            config_msg = {"config": config}
            await gecx_ws.send(json.dumps(config_msg))
            logger.info("Handshake configurations transmitted.")
            await self.client_ws.send_json(
                {
                    "type": "AUDIO_CONFIG",
                    "input_sample_rate_hz": input_sample_rate_hz,
                    "output_sample_rate_hz": output_sample_rate_hz,
                    "encoding": "LINEAR16",
                }
            )

            # Send initial session variables to populate context before triggering agent
            variables_msg = {
                "realtimeInput": {
                    "variables": self.bootstrap.ces_variables(
                        session_capability=mint_ces_session_capability(self.bootstrap)
                    )
                }
            }
            await gecx_ws.send(json.dumps(variables_msg))
            logger.info("Session context variables transmitted.")

            # Send initial trigger event to prompt the agent's welcome greeting immediately
            welcome_msg = {"realtimeInput": {"event": {"event": "sys.welcome"}}}
            await gecx_ws.send(json.dumps(welcome_msg))
            logger.info("Initial greeting trigger query transmitted.")

            # Task A: Read frames from browser WebSocket client
            async def read_client():
                try:
                    while True:
                        data = await self.client_ws.receive()
                        if "bytes" in data:
                            message = data["bytes"]
                            if len(message) > 65536:
                                logger.error(
                                    "Security warning: Client sent binary frame exceeding 64KB limit."
                                )
                                break
                            await self.client_to_gecx_queue.put(message)
                        elif "text" in data:
                            payload = json.loads(data["text"])
                            if payload.get("type") == "PING":
                                await self.client_ws.send_json(
                                    {
                                        "type": "PONG",
                                        "timestamp": payload.get("timestamp"),
                                    }
                                )
                except (WebSocketDisconnect, RuntimeError) as ex:
                    if (
                        isinstance(ex, RuntimeError)
                        and "disconnect" not in str(ex)
                        and "receive" not in str(ex)
                    ):
                        logger.error(f"RuntimeError in WebSocket read_client: {ex}")
                    else:
                        logger.debug("Client browser disconnected.")
                except Exception as ex:
                    logger.error(f"Error in WebSocket read_client: {ex}")
                finally:
                    await self.client_to_gecx_queue.put(None)

            # Task B: Base64-encode and forward audio frames to GECX WebSocket
            async def send_to_gecx():
                try:
                    while True:
                        chunk = await self.client_to_gecx_queue.get()
                        if chunk is None:
                            break

                        b64_audio = base64.b64encode(chunk).decode("utf-8")
                        realtime_input = {"realtimeInput": {"audio": b64_audio}}
                        await gecx_ws.send(json.dumps(realtime_input))
                        transport_stats["input_frames"] += 1
                        transport_stats["input_bytes"] += len(chunk)
                        self.client_to_gecx_queue.task_done()
                except Exception as ex:
                    logger.error(f"Error in send_to_gecx: {ex}")

            # Task C: Read text and audio frames from Google GECX API
            async def read_from_gecx():
                try:
                    async for message in gecx_ws:
                        response = json.loads(message)
                        session_output = response.get("sessionOutput", {})
                        if session_output:
                            b64_audio = session_output.get("audio", "")
                            if b64_audio:
                                raw_pcm = base64.b64decode(b64_audio)
                                transport_stats["output_frames"] += 1
                                transport_stats["output_bytes"] += len(raw_pcm)
                                await self.gecx_to_client_queue.put(
                                    {"type": "AUDIO", "data": raw_pcm}
                                )

                            text = session_output.get("text", "")
                            if text:
                                await self.gecx_to_client_queue.put(
                                    {
                                        "type": "TRANSCRIPT",
                                        "text": text,
                                        "author": "agent",
                                    }
                                )

                        recognition_result = response.get("recognitionResult", {})
                        if recognition_result:
                            user_transcript = recognition_result.get("transcript", "")
                            if user_transcript:
                                await self.gecx_to_client_queue.put(
                                    {
                                        "type": "TRANSCRIPT",
                                        "text": user_transcript,
                                        "author": "user",
                                    }
                                )

                        interruption_signal = response.get(
                            "interruptionSignal"
                        ) or response.get("interruption_signal")
                        if interruption_signal:
                            logger.info(
                                f"Barge-in interruption signal received from GECX: {interruption_signal}"
                            )
                            await self.gecx_to_client_queue.put({"type": "INTERRUPT"})
                except Exception as ex:
                    logger.error(f"Error in read_from_gecx: {ex}")
                finally:
                    logger.info(
                        "CES audio transport summary input_frames=%d input_bytes=%d "
                        "output_frames=%d output_bytes=%d input_rate_hz=%d "
                        "output_rate_hz=%d",
                        transport_stats["input_frames"],
                        transport_stats["input_bytes"],
                        transport_stats["output_frames"],
                        transport_stats["output_bytes"],
                        input_sample_rate_hz,
                        output_sample_rate_hz,
                    )
                    await self.gecx_to_client_queue.put(None)

            # Task D: Forward payloads back to client browser WebSocket
            async def send_to_client():
                try:
                    while True:
                        payload = await self.gecx_to_client_queue.get()
                        if payload is None:
                            break

                        if isinstance(payload, dict) and payload.get("type") != "AUDIO":
                            await self.client_ws.send_json(payload)
                        elif (
                            isinstance(payload, dict) and payload.get("type") == "AUDIO"
                        ):
                            await self.client_ws.send_bytes(payload["data"])
                        else:
                            await self.client_ws.send_bytes(payload)

                        self.gecx_to_client_queue.task_done()
                except Exception as ex:
                    logger.error(f"Error in send_to_client: {ex}")

            # Task E: Send keep-alive heartbeats to client
            async def send_pings():
                try:
                    while True:
                        await asyncio.sleep(20)
                        await self.client_ws.send_json({"type": "PING"})
                except Exception:
                    pass

            # Gather all loops with a 10-minute timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_client(),
                        send_to_gecx(),
                        read_from_gecx(),
                        send_to_client(),
                        send_pings(),
                    ),
                    timeout=600.0,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Session {self.session_id} timed out after 10 minutes.")
                await self.client_ws.send_json(
                    {
                        "type": "ERROR",
                        "message": "Maximum session duration (10 minutes) exceeded.",
                    }
                )
