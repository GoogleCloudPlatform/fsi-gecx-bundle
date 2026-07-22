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


def _configured_noise_suppression_level() -> str:
    value = os.getenv("CES_INPUT_NOISE_SUPPRESSION_LEVEL", "moderate").strip().lower()
    if value not in {"low", "moderate", "high", "very_high"}:
        raise ValueError(
            "CES_INPUT_NOISE_SUPPRESSION_LEVEL must be low, moderate, high, or very_high."
        )
    return value


def _pcm_peak(chunk: bytes) -> int:
    """Return the absolute peak of little-endian LINEAR16 PCM for diagnostics."""
    if not chunk or len(chunk) % 2:
        return 0
    return max((abs(sample) for sample in memoryview(chunk).cast("h")), default=0)


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
        noise_suppression_level = _configured_noise_suppression_level()
        transport_stats = {
            "input_frames": 0,
            "input_bytes": 0,
            "browser_input_frames": 0,
            "browser_input_bytes": 0,
            "input_speech_like_frames": 0,
            "input_speech_bursts": 0,
            "input_peak": 0,
            "first_browser_input_at": None,
            "last_browser_input_at": None,
            "output_frames": 0,
            "output_bytes": 0,
            "output_gap_over_250ms": 0,
            "max_output_gap_ms": 0,
            "last_output_at": None,
            "recognition_results": 0,
            "interruption_signals": 0,
            "completed_turns": 0,
            "provider_end_signal": "none",
        }
        transport_started_at = time.monotonic()

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
                    "noiseSuppressionLevel": noise_suppression_level,
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
                            received_at = time.monotonic()
                            transport_stats["browser_input_frames"] += 1
                            transport_stats["browser_input_bytes"] += len(message)
                            if transport_stats["first_browser_input_at"] is None:
                                transport_stats["first_browser_input_at"] = received_at
                            transport_stats["last_browser_input_at"] = received_at
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
                            elif payload.get("type") == "AUDIO_DIAGNOSTICS":
                                logger.info(
                                    "CES browser audio settings sample_rate_hz=%s "
                                    "channel_count=%s echo_cancellation=%s "
                                    "noise_suppression=%s auto_gain_control=%s "
                                    "latency_seconds=%s",
                                    payload.get("sample_rate_hz"),
                                    payload.get("channel_count"),
                                    payload.get("echo_cancellation"),
                                    payload.get("noise_suppression"),
                                    payload.get("auto_gain_control"),
                                    payload.get("latency_seconds"),
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

            # Task B: Forward browser AudioWorklet PCM at the negotiated rate.
            # Re-clocking here creates a second timing loop and can discard valid
            # microphone audio when provider sends are backpressured.
            async def send_to_gecx():
                speech_active = False
                quiet_frames = 0
                try:
                    while True:
                        chunk = await self.client_to_gecx_queue.get()
                        self.client_to_gecx_queue.task_done()
                        if chunk is None:
                            break
                        b64_audio = base64.b64encode(chunk).decode("utf-8")
                        realtime_input = {"realtimeInput": {"audio": b64_audio}}
                        await gecx_ws.send(json.dumps(realtime_input))
                        transport_stats["input_frames"] += 1
                        transport_stats["input_bytes"] += len(chunk)
                        peak = _pcm_peak(chunk)
                        transport_stats["input_peak"] = max(
                            transport_stats["input_peak"], peak
                        )
                        if peak >= 512:
                            transport_stats["input_speech_like_frames"] += 1
                            quiet_frames = 0
                            if not speech_active:
                                speech_active = True
                                transport_stats["input_speech_bursts"] += 1
                        elif speech_active:
                            quiet_frames += 1
                            if quiet_frames >= 4:
                                speech_active = False
                                quiet_frames = 0
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
                                received_at = time.monotonic()
                                last_output_at = transport_stats["last_output_at"]
                                if last_output_at is not None:
                                    output_gap_ms = round(
                                        (received_at - last_output_at) * 1000
                                    )
                                    transport_stats["max_output_gap_ms"] = max(
                                        transport_stats["max_output_gap_ms"],
                                        output_gap_ms,
                                    )
                                    if output_gap_ms > 250:
                                        transport_stats["output_gap_over_250ms"] += 1
                                transport_stats["last_output_at"] = received_at
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
                            if session_output.get(
                                "turnCompleted"
                            ) or session_output.get("turn_completed"):
                                transport_stats["completed_turns"] += 1

                        recognition_result = response.get("recognitionResult", {})
                        if recognition_result:
                            transport_stats["recognition_results"] += 1
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
                            transport_stats["interruption_signals"] += 1
                            logger.info(
                                f"Barge-in interruption signal received from GECX: {interruption_signal}"
                            )
                            await self.gecx_to_client_queue.put({"type": "INTERRUPT"})

                        if "endSession" in response or "end_session" in response:
                            transport_stats["provider_end_signal"] = "end_session"
                            logger.info("CES end-session signal received.")
                            await self.gecx_to_client_queue.put(
                                {"type": "SESSION_END", "reason": "CES_END_SESSION"}
                            )
                            break
                        if "goAway" in response or "go_away" in response:
                            transport_stats["provider_end_signal"] = "go_away"
                            logger.info("CES go-away signal received.")
                            await self.gecx_to_client_queue.put(
                                {"type": "SESSION_END", "reason": "CES_GO_AWAY"}
                            )
                            break
                except Exception as ex:
                    logger.error(f"Error in read_from_gecx: {ex}")
                finally:
                    finished_at = time.monotonic()
                    first_input_at = transport_stats["first_browser_input_at"]
                    last_input_at = transport_stats["last_browser_input_at"]
                    logger.info(
                        "CES audio transport summary input_frames=%d input_bytes=%d "
                        "browser_input_frames=%d browser_input_bytes=%d "
                        "input_speech_like_frames=%d input_speech_bursts=%d "
                        "input_peak=%d "
                        "first_browser_input_delay_ms=%s "
                        "last_browser_input_gap_ms=%s "
                        "output_frames=%d output_bytes=%d input_rate_hz=%d "
                        "output_rate_hz=%d output_gap_over_250ms=%d "
                        "max_output_gap_ms=%d recognition_results=%d "
                        "interruption_signals=%d completed_turns=%d "
                        "provider_end_signal=%s",
                        transport_stats["input_frames"],
                        transport_stats["input_bytes"],
                        transport_stats["browser_input_frames"],
                        transport_stats["browser_input_bytes"],
                        transport_stats["input_speech_like_frames"],
                        transport_stats["input_speech_bursts"],
                        transport_stats["input_peak"],
                        (
                            round((first_input_at - transport_started_at) * 1000)
                            if first_input_at is not None
                            else "none"
                        ),
                        (
                            round((finished_at - last_input_at) * 1000)
                            if last_input_at is not None
                            else "none"
                        ),
                        transport_stats["output_frames"],
                        transport_stats["output_bytes"],
                        input_sample_rate_hz,
                        output_sample_rate_hz,
                        transport_stats["output_gap_over_250ms"],
                        transport_stats["max_output_gap_ms"],
                        transport_stats["recognition_results"],
                        transport_stats["interruption_signals"],
                        transport_stats["completed_turns"],
                        transport_stats["provider_end_signal"],
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

            # End the provider session as soon as either endpoint disconnects.
            # The prior gather waited for every loop, including the perpetual
            # ping loop, and could leak CES sessions after a browser closed.
            tasks = {
                "read_client": asyncio.create_task(read_client()),
                "send_to_gecx": asyncio.create_task(send_to_gecx()),
                "read_from_gecx": asyncio.create_task(read_from_gecx()),
                "send_to_client": asyncio.create_task(send_to_client()),
                "send_pings": asyncio.create_task(send_pings()),
            }

            async def wait_for_endpoint_close():
                done, _ = await asyncio.wait(
                    (tasks["read_client"], tasks["read_from_gecx"]),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if tasks["read_from_gecx"] in done:
                    # read_from_gecx queues its sentinel only after all CES audio
                    # has been queued. Let the client writer flush that buffer.
                    await tasks["send_to_client"]

            try:
                await asyncio.wait_for(wait_for_endpoint_close(), timeout=600.0)
            except asyncio.TimeoutError:
                logger.warning(f"Session {self.session_id} timed out after 10 minutes.")
                await self.client_ws.send_json(
                    {
                        "type": "ERROR",
                        "message": "Maximum session duration (10 minutes) exceeded.",
                    }
                )
            finally:
                for task in tasks.values():
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks.values(), return_exceptions=True)
