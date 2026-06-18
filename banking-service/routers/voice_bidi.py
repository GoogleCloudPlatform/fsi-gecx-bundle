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
import logging
import asyncio
from fastapi import APIRouter, WebSocket

from utils.auth import validate_firebase_token
from utils.env import is_running_locally
from services.voice_bidi import VoiceBidiSession

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/voice/gecx-stream")
async def gecx_voice_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket proxy connection accepted. Awaiting first-frame authorization...")

    user_id = None
    session_id = None
    
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
                fb_token = "mock-local-token"
            else:
                validated_token = validate_firebase_token(auth_frame["token"])
                user_id = validated_token.claims.get("sub")
                fb_token = auth_frame["token"]
                # Append a timestamp to GECx session ID to force a fresh session context on every connect
                session_id = f"session-{user_id}-{int(time.time())}"
                
            logger.info(f"First-frame authentication succeeded. Session: {session_id} (User: {user_id})")
        except asyncio.TimeoutError:
            logger.warning("Auth timeout: First-frame auth token not received within 5 seconds.")
            await websocket.close(code=4001, reason="Authentication timeout.")
            return
        except Exception as auth_err:
            logger.warning(f"Auth failed: Invalid Firebase token details. {auth_err}")
            await websocket.close(code=4001, reason="Authentication failed.")
            return

        # 2. Delegate real-time session execution to service
        gecx_app_id = os.getenv("GECX_APP_ID", "42345105-29cb-492d-8a60-07171bb72190")
        location = os.getenv("GECX_LOCATION", "us")
        
        session = VoiceBidiSession(
            user_id=user_id,
            session_id=session_id,
            fb_token=fb_token,
            websocket=websocket,
            gecx_app_id=gecx_app_id,
            location=location
        )
        await session.start()
        
    except Exception as e:
        logger.error(f"Session failure for session {session_id}: {e}")
    finally:
        logger.info(f"WebSocket session clean-up completed.")
