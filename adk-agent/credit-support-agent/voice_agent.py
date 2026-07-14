import os
os.environ["NNPACK_DISABLED"] = "1"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"
import sys
import asyncio
import logging
import numpy as np
from livekit import rtc
from fastapi import FastAPI, HTTPException, Request
import uvicorn

# Prepend the directory to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agent.agent import (
    bind_session_context,
    clear_session_end_request,
    create_voice_agent,
    is_session_end_requested,
    is_tool_processing,
    reset_session_context,
)
from agent.instructions import compose_session_instruction
from agent.live_runtime import build_live_run_config, env_flag, normalize_live_event
from agent.guidance_snapshot import guidance_observability_payload
from agent.media_bridge import BufferedAudioPlayout, SileroVADTracker
from agent.session_coordinator import default_session_bootstrap, load_session_bootstrap
from agent.runtime_config import load_runtime_config, validate_session_request
from agent.terminal_outcome import TerminalOutcome
from agent.session_store import (
    cleanup_expired_sessions,
    get_session_service,
    open_or_resume_session,
)
from agent.workflow_plugin import FraudWorkflowStatePlugin
from agent.version import BUILD_VERSION, BUILD_COMMIT_ID, BUILD_TIME
from agent.events import DataChannelEvent
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types

class HandoffException(Exception):
    pass

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("voice_agent")
# Enable verbose debug logs for ADK and GenAI SDK conditionally to trace tool calling packets
if os.getenv("VERBOSE_LOGGING") == "true":
    logging.getLogger("google_adk").setLevel(logging.DEBUG)
    logging.getLogger("google_genai").setLevel(logging.DEBUG)
else:
    logging.getLogger("google_adk").setLevel(logging.ERROR)
    logging.getLogger("google_genai").setLevel(logging.ERROR)


def session_log_context(room_name: str, customer_id: str, session_id: str, mode: str, **extra) -> str:
    context = {
        "room_name": room_name,
        "customer_id": customer_id,
        "session_id": session_id,
        "mode": mode,
    }
    context.update({key: value for key, value in extra.items() if value is not None})
    return " ".join(f"{key}={value}" for key, value in context.items())

runtime_config = load_runtime_config()
LIVEKIT_URL = runtime_config.livekit_url
def get_livekit_token(room_name: str) -> str:
    token_from_env = os.getenv("LIVEKIT_TOKEN")
    if token_from_env:
        return token_from_env

    api_key = os.getenv("LIVEKIT_API_KEY", "devkey")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "secret")
    logger.info(f"Generating fresh LiveKit token for room: {room_name}")
    try:
        from livekit import api as lk_api
        token = lk_api.AccessToken(api_key, api_secret)
        import time
        token.with_identity(f"agent-voice-{int(time.time())}")
        token.with_grants(lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True
        ))
        return token.to_jwt()
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token dynamically: {e}")
        raise e

async def run_voice_agent_session(room_name: str, customer_id: str, session_id: str, mode: str = "audio"):
    logger.info("Initializing voice agent session %s", session_log_context(room_name, customer_id, session_id, mode))
    import agent.agent as agent_module
    session_context_tokens = bind_session_context(customer_id, None)
    terminal_outcome = TerminalOutcome.NORMAL_DISCONNECT

    # Load typed runtime settings and customer workflow context.
    bootstrap = default_session_bootstrap()
    settings = bootstrap.settings
    voice_context = bootstrap.voice_context
    fraud_alert_state = {}
    fraud_playbook = bootstrap.fraud_playbook
    support_guidance = bootstrap.support_guidance
    initial_greeting_prompt = bootstrap.initial_greeting_prompt

    try:
        headers = agent_module.get_auth_headers()
        bootstrap = await load_session_bootstrap(
            banking_service_url=agent_module.BANKING_SERVICE_URL,
            headers=headers,
        )
        settings = bootstrap.settings
        voice_context = bootstrap.voice_context
        fraud_playbook = bootstrap.fraud_playbook
        support_guidance = bootstrap.support_guidance
        initial_greeting_prompt = bootstrap.initial_greeting_prompt
        logger.info(
            "Loaded voice bootstrap %s avatar=%s max_duration=%s active_fraud=%s guidance_snapshot=%s",
            session_log_context(room_name, customer_id, session_id, mode),
            settings.avatar_name,
            settings.max_duration,
            voice_context.get("has_active_fraud_alert"),
            guidance_observability_payload(support_guidance),
        )
    except Exception as e:
        logger.error("Failed to query system settings from API %s error=%s", session_log_context(room_name, customer_id, session_id, mode), e, exc_info=True)

    mock_avatar_enabled = settings.mock_avatar_enabled
    avatar_name = settings.avatar_name
    max_duration = settings.max_duration
    warning_duration = settings.warning_duration
    hard_timeout_enabled = settings.hard_timeout_enabled

    active_escalation_id = None
    audio_server = None
    audio_port = None

    session_service = await get_session_service()
    if voice_context.get("has_active_fraud_alert") and voice_context.get("fraud_alert"):
        fraud_alert_state = dict(voice_context["fraud_alert"])
    session_state = {
        "room_name": room_name,
        "customer_id": customer_id,
        "session_id": session_id,
        "mode": mode,
        "has_active_fraud_alert": voice_context.get("has_active_fraud_alert", False),
        "entry_reason": voice_context.get("entry_reason", "general_support"),
        "fraud_context": fraud_alert_state,
        "fraud_playbook": fraud_playbook,
        "support_guidance": support_guidance,
        "guidance_source": support_guidance.get("source"),
        "initial_greeting_prompt": initial_greeting_prompt,
    }
    reset_generation = voice_context.get("reset_generation") or {
        "global_epoch": 0,
        "customer_epoch": 0,
        "token": "0:0",
    }
    session_state["reset_generation"] = reset_generation
    # Create the session dynamically using the passed IDs
    user_id = f"user-{customer_id}"
    _, resumed, resume_reason = await open_or_resume_session(
        session_service,
        user_id=user_id,
        session_id=session_id,
        state=session_state,
        reset_generation_token=str(reset_generation.get("token") or ""),
    )
    logger.info(
        "Opened ADK session state %s resumed=%s reason=%s reset_generation=%s",
        session_log_context(
            room_name,
            customer_id,
            session_id,
            mode,
            fraud_alert_id=fraud_playbook.get("fraud_alert_id"),
            entry_mode=fraud_playbook.get("entry_mode"),
        ),
        resumed,
        resume_reason,
        reset_generation.get("token"),
    )
    if not resumed:
        try:
            deleted_sessions = await cleanup_expired_sessions(session_service)
            if deleted_sessions:
                logger.info("Cleaned up %s expired voice sessions", deleted_sessions)
        except Exception as cleanup_error:
            logger.warning("Voice session cleanup failed: %s", cleanup_error)
    logger.debug(
        "ADK session state payload %s state_keys=%s",
        session_log_context(room_name, customer_id, session_id, mode),
        sorted(session_state.keys()),
    )
    
    from google.adk.models import Gemini
    active_flows = []
    session_context_text = None
    if voice_context.get("has_active_fraud_alert") and voice_context.get("fraud_alert"):
        active_flows.append("fraud_alert")
        fraud_alert = voice_context["fraud_alert"]
        suspicious_lines = "\n".join(
            f"- {txn['merchant_name']}: ${txn['amount_cents'] / 100:,.2f}"
            for txn in fraud_alert.get("suspicious_transactions", [])
        )
        session_context_text = (
            "Session-specific customer context:\n"
            f"- The customer has an active fraud alert on card ending in {fraud_alert['card_last_four']}.\n"
            f"- Fraud alert thread id: {fraud_alert['message_thread_id']}.\n"
            f"- Fraud alert id for triage_fraud_case: {fraud_alert['fraud_alert_id']}.\n"
            "- Start the conversation by asking whether the customer recognizes the flagged transactions; do not assume fraud has occurred.\n"
            "- Name each flagged merchant and amount when summarizing what looked suspicious:\n"
            f"{suspicious_lines or '- No suspicious transaction details were provided.'}\n"
            "- Once the disputed selection is clear, call prepare_fraud_triage_confirmation with the exact alert id, disputed authorization ids, disputed transaction ids, and replacement choice. It does not mutate banking state.\n"
            "- Restate the exact prepared selection and ask the customer to confirm it. Stop after asking; do not call triage_fraud_case in the same response.\n"
            "- After the customer explicitly confirms in a later response, call triage_fraud_case once with exactly the prepared payload. Any changed selection requires a new preparation and confirmation.\n"
            "- If the customer recognizes every flagged transaction, call triage_fraud_case with empty disputed id arrays and issue_replacement=false.\n"
            "- If the customer disputes any flagged transaction, tell them any credits are provisional pending the full fraud investigation.\n"
            "- If triage_fraud_case returns a clearly transient technical failure, retry it once with the same arguments before offering human escalation.\n"
            "- Treat this as trusted session context rather than something the customer needs to restate."
        )
    guidance_summary = support_guidance.get("agent_guidance_summary")
    session_instruction = compose_session_instruction(
        avatar_name=avatar_name,
        active_flows=active_flows,
        session_context=session_context_text,
        guidance_summary=guidance_summary,
    )
    session_agent = create_voice_agent(instruction=session_instruction)
    if mode == "video":
        model_name = os.getenv("VOICE_AGENT_VIDEO_MODEL")
        if not model_name:
            logger.warning("VOICE_AGENT_VIDEO_MODEL environment variable is not set %s; gracefully falling back to audio mode.", session_log_context(room_name, customer_id, session_id, mode))
            mode = "audio"

    if mode == "video":
        logger.info("Setting agent model to Publishers Gemini Live video wrapper %s model_name=%s", session_log_context(room_name, customer_id, session_id, mode), model_name)
        session_agent.model = Gemini(model=model_name)
    else:
        model_name = os.getenv("VOICE_AGENT_AUDIO_MODEL")
        if not model_name:
            raise ValueError("VOICE_AGENT_AUDIO_MODEL environment variable must be set")
        logger.info("Setting agent model to Publishers Gemini Live audio wrapper %s model_name=%s", session_log_context(room_name, customer_id, session_id, mode), model_name)
        session_agent.model = Gemini(model=model_name)
        
    runner = Runner(
        app=App(
            name="credit-support-agent",
            root_agent=session_agent,
            plugins=[FraudWorkflowStatePlugin()],
        ),
        session_service=session_service,
    )
    loop = asyncio.get_running_loop()
    live_queue = LiveRequestQueue()

    conversation_transcript = []

    # Define tool event callback to broadcast over LiveKit data channel
    def on_agent_event(event_dict):
        if room and room.local_participant:
            import json
            payload = json.dumps(event_dict)
            logger.info(
                "Broadcasting event to LiveKit data channel %s event_type=%s",
                session_log_context(room_name, customer_id, session_id, mode, fraud_alert_id=fraud_playbook.get("fraud_alert_id")),
                event_dict.get("type"),
            )
            def schedule_publish():
                asyncio.create_task(room.local_participant.publish_data(payload))
            loop.call_soon_threadsafe(schedule_publish)

        # Capture transcript events in memory
        if event_dict.get("type") == DataChannelEvent.TRANSCRIPT.value:
            conversation_transcript.append({
                "author": event_dict["author"],
                "text": event_dict["text"]
            })
        
        # The stream loop schedules the graceful disconnect after final audio playout.
        elif event_dict.get("type") == DataChannelEvent.SESSION_END.value:
            logger.info("SESSION_END event received from tool %s", session_log_context(room_name, customer_id, session_id, mode))
        
        # Capture human handoff trigger and save to DB
        elif event_dict.get("type") == DataChannelEvent.HANDOFF_PENDING.value:
            nonlocal active_escalation_id
            
            async def sync_escalation():
                nonlocal active_escalation_id
                try:
                    import httpx
                    headers = agent_module.get_auth_headers()
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        escalate_url = f"{agent_module.BANKING_SERVICE_URL}/support/escalate"
                        payload = {
                            "room_name": room_name,
                            "customer_id": agent_module.active_customer_id_var.get(),
                            "reason": event_dict.get("reason", "User requested supervisor"),
                            "transcript": conversation_transcript
                        }
                        if active_escalation_id is not None:
                            payload["escalation_id"] = active_escalation_id
                        
                        resp = await client.post(escalate_url, json=payload, headers=headers)
                        if resp.status_code == 200:
                            res_data = resp.json()
                            active_escalation_id = res_data.get("escalation_id")
                            logger.info(
                                "Successfully synced support escalation via API %s escalation_id=%s",
                                session_log_context(room_name, customer_id, session_id, mode),
                                active_escalation_id,
                            )
                        else:
                            logger.error("Failed to sync support escalation via API %s status=%s body=%s", session_log_context(room_name, customer_id, session_id, mode), resp.status_code, resp.text)
                except Exception as ex:
                    logger.error("Failed to call support escalation API %s error=%s", session_log_context(room_name, customer_id, session_id, mode), ex, exc_info=True)

            loop.call_soon_threadsafe(lambda: asyncio.create_task(sync_escalation()))

    session_context_tokens["callback"] = agent_module.session_event_callback_var.set(on_agent_event)
    logger.info("Bound session context %s", session_log_context(room_name, customer_id, session_id, mode))

    user_stt_queue = None
    agent_stt_queue = None
    user_stt_task = None
    agent_stt_task = None

    # User-defined mapping for avatar -> voice name & language code
    AVATAR_METADATA = {
        "ingrid": {"voice": "Despina", "lang": "en-GB"},
        "jay": {"voice": "Puck", "lang": "en-IN"},
        "kira": {"voice": "Kore", "lang": "en-US"},
        "paul": {"voice": "Algenib", "lang": "en-GB"},
        "sam": {"voice": "Sadaltager", "lang": "en-US"},
        "vera": {"voice": "Vindemiatrix", "lang": "en-US"}
    }
    
    voice_name = "Aoede" # Fallback
    lang_code = "en-US" # Fallback
    if avatar_name:
        avatar_lower = avatar_name.lower()
        if avatar_lower in AVATAR_METADATA:
            meta = AVATAR_METADATA[avatar_lower]
            voice_name = meta["voice"]
            lang_code = meta["lang"]
        else:
            if avatar_lower in ['paul', 'sam', 'jay', 'kai', 'leo', 'ben']:
                voice_name = 'Charon'
            else:
                voice_name = 'Aoede'

    run_config = build_live_run_config(
        mode=mode,
        avatar_name=avatar_name,
        voice_name=voice_name,
        language_code=lang_code,
        manual_activity_detection=(
            mode == "video"
            and env_flag("VOICE_AGENT_VIDEO_MANUAL_ACTIVITY_ENABLED", default=True)
        ),
    )
    video_manual_activity_enabled = bool(run_config.realtime_input_config)
    logger.info(
        "Configured Live input activity detection %s manual_activity=%s",
        session_log_context(room_name, customer_id, session_id, mode),
        video_manual_activity_enabled,
    )

    # Initialize LiveKit Room and Audio Source
    # Gemini Live outputs 24kHz, 16-bit PCM mono
    audio_source = rtc.AudioSource(sample_rate=24000, num_channels=1)
    
    # We maintain an output queue for playout frames to handle interruptions
    playout_queue = asyncio.Queue()

    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            if not participant.identity.startswith("agent-human"):
                asyncio.create_task(handle_incoming_audio(track))
            else:
                logger.info(f"Ignoring audio track subscription from human supervisor: {participant.identity}")

    disconnect_event = asyncio.Event()

    @room.on("disconnected")
    def on_disconnected(reason: rtc.DisconnectReason):
        logger.warning("Disconnected from LiveKit room %s reason=%s", session_log_context(room_name, customer_id, session_id, mode), reason)
        disconnect_event.set()

    handoff_event = asyncio.Event()

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        if participant.identity.startswith("agent-human"):
            logger.info("Human agent connected %s participant=%s", session_log_context(room_name, customer_id, session_id, mode), participant.identity)
            handoff_event.set()

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info("Participant disconnected %s participant=%s", session_log_context(room_name, customer_id, session_id, mode), participant.identity)
        if not participant.identity.startswith("agent-human"):
            logger.info("Customer disconnected; initiating voice agent session shutdown %s", session_log_context(room_name, customer_id, session_id, mode))
            disconnect_event.set()

    async def handle_incoming_audio(track: rtc.Track):
        # Read frames from LiveKit incoming track
        audio_stream = rtc.AudioStream(track)
        # Resampler will be initialized dynamically on the first frame to match incoming sample rate
        resampler = None
        vad = SileroVADTracker()

        try:
            async for frame_event in audio_stream:
                frame = frame_event.frame
                if resampler is None:
                    logger.info(f"First audio frame received! sample_rate={frame.sample_rate}, num_channels={frame.num_channels}")
                    # Media path is active. Send initial greeting prompt after a 500ms delay to let the WebRTC connection stabilize.
                    async def send_delayed_greeting():
                        await asyncio.sleep(0.5)
                        logger.info("Media path is active. Triggering assistant greeting...")
                        greeting_text = initial_greeting_prompt
                        live_queue.send_content(
                            types.Content(
                                parts=[types.Part(text=greeting_text)]
                            )
                        )
                    asyncio.create_task(send_delayed_greeting())
                    resampler = rtc.AudioResampler(
                        input_rate=frame.sample_rate,
                        output_rate=16000,
                        num_channels=1
                    )
                # Resample the incoming frame
                resampled_frames = resampler.push(frame)
                for res_frame in resampled_frames:
                    # Check if the agent is currently processing a tool call or shutting down to drop user mic buffers
                    if is_tool_processing() or is_session_end_requested() or session_end_disconnect_task:
                        logger.debug("Muting microphone audio: tool execution or session shutdown in progress.")
                        continue

                    # Convert to Float32 array for VAD
                    int16_data = np.frombuffer(res_frame.data, dtype=np.int16)
                    float32_data = int16_data.astype(np.float32) / 32768.0

                    speech_started, speech_ended = vad.process_chunk(float32_data)

                    pcm_bytes = int16_data.tobytes()
                    audio_blob = types.Blob(mime_type="audio/pcm;rate=16000", data=pcm_bytes)

                    # Feed user Speech-to-Text worker continuously to keep the gRPC stream alive
                    if mode == "video" and user_stt_queue:
                        await user_stt_queue.put(pcm_bytes)

                    if speech_started:
                        if video_manual_activity_enabled:
                            live_queue.send_activity_start()
                        # Clear agent's playout queue to immediately interrupt speaking
                        logger.info("User speaking, interrupting agent voice output...")
                        while not playout_queue.empty():
                            try:
                                playout_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                    # Always send the audio blob to the model to allow server-side silence detection
                    live_queue.send_realtime(audio_blob)
                    if speech_ended and video_manual_activity_enabled:
                        live_queue.send_activity_end()
        except Exception as err:
            logger.error(f"Error handling incoming audio: {err}", exc_info=True)
        finally:
            await audio_stream.aclose()

    video_source = None
    local_video_track = None

    async def run_livekit_connection():
        logger.info("Connecting to LiveKit Room %s livekit_url=%s", session_log_context(room_name, customer_id, session_id, mode), LIVEKIT_URL)
        token = get_livekit_token(room_name)
        await room.connect(LIVEKIT_URL, token)
        logger.info("Connected to LiveKit room %s", session_log_context(room_name, customer_id, session_id, mode))
        
        # Broadcast agent mode to client
        import json
        event_payload = json.dumps({"type": "agent_mode", "mode": mode})
        logger.info("Broadcasting agent mode %s payload=%s", session_log_context(room_name, customer_id, session_id, mode), event_payload)
        await room.local_participant.publish_data(event_payload)
        guidance_payload = {
            "type": DataChannelEvent.GUIDANCE_SNAPSHOT.value,
            **guidance_observability_payload(support_guidance),
        }
        logger.info(
            "Publishing safe guidance snapshot %s guidance_snapshot=%s",
            session_log_context(room_name, customer_id, session_id, mode),
            guidance_payload,
        )
        await room.local_participant.publish_data(json.dumps(guidance_payload))

        # Publish our microphone/audio source track
        local_track = rtc.LocalAudioTrack.create_audio_track("agent-audio", audio_source)
        publish_options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(local_track, publish_options)
        logger.info("Published agent voice track %s", session_log_context(room_name, customer_id, session_id, mode))
        
        # Publish local video track if video mode is enabled
        nonlocal video_source, local_video_track
        if mode == "video":
            if mock_avatar_enabled:
                import cv2
                cap = cv2.VideoCapture("assets/mock_avatar.mp4")
                vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 320
                vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 240
                cap.release()
            else:
                # Google 1P Live Avatar native resolution (scaled for performance and smoothness)
                vw = 352
                vh = 640
            
            video_source = rtc.VideoSource(vw, vh)
            local_video_track = rtc.LocalVideoTrack.create_video_track("agent-video", video_source)
            video_publish_options = rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_CAMERA,
                video_encoding=rtc.VideoEncoding(
                    max_bitrate=1_500_000,
                    max_framerate=30
                )
            )
            await room.local_participant.publish_track(local_video_track, video_publish_options)
            logger.info("Published agent video track %s width=%s height=%s", session_log_context(room_name, customer_id, session_id, mode), vw, vh)
        # Broadcast avatar configuration to client UI
        on_agent_event({
            "type": "AVATAR_CONFIG",
            "avatar_name": avatar_name
        })
        
        pass

    playout_bridge = BufferedAudioPlayout(
        audio_source=audio_source, queue=playout_queue
    )

    async def playout_loop():
        await playout_bridge.run()

    session_end_disconnect_task = None
    session_end_event_published = False

    async def wait_for_playout_drain(reason: str) -> None:
        if not await playout_bridge.wait_for_drain(timeout=8.0):
            logger.warning("Timed out waiting for final agent audio playout %s reason=%s", session_log_context(room_name, customer_id, session_id, mode), reason)
        await asyncio.sleep(1.0)

    def schedule_session_end_disconnect(reason: str) -> None:
        nonlocal session_end_disconnect_task, session_end_event_published
        if session_end_disconnect_task and not session_end_disconnect_task.done():
            return

        async def delayed_disconnect():
            nonlocal session_end_event_published
            logger.info("Scheduling graceful session end %s reason=%s", session_log_context(room_name, customer_id, session_id, mode), reason)
            await wait_for_playout_drain(reason)
            if not session_end_event_published:
                session_end_event_published = True
                on_agent_event({"type": "SESSION_END"})
            await asyncio.sleep(5.0)
            disconnect_event.set()

        session_end_disconnect_task = asyncio.create_task(delayed_disconnect())

    async def run_gemini_loop():
        logger.info("Starting run_live stream loop %s", session_log_context(room_name, customer_id, session_id, mode, fraud_alert_id=fraud_playbook.get("fraud_alert_id")))
        try:
            async for event in runner.run_live(
                user_id=user_id,
                session_id=session_id,
                live_request_queue=live_queue,
                run_config=run_config
            ):
                live_event = normalize_live_event(event)
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        # Extract audio output from the model
                        if part.inline_data:
                            if part.inline_data.mime_type.startswith("audio/pcm"):
                                audio_bytes = part.inline_data.data
                                # Queue it for playout
                                await playout_queue.put(audio_bytes)
                                if mode == "video" and agent_stt_queue:
                                    await agent_stt_queue.put(audio_bytes)
                            else:
                                logger.debug(f"Received video chunk: size={len(part.inline_data.data)} bytes, mime={part.inline_data.mime_type}")
                                # Send video frame/chunk to FFmpeg decoder process stdin
                                if ffmpeg_proc and ffmpeg_proc.stdin:
                                    ffmpeg_proc.stdin.write(part.inline_data.data)
                                    await ffmpeg_proc.stdin.drain()
                                else:
                                    logger.warning("ffmpeg_proc or ffmpeg_proc.stdin is not available!")
                            
                # Broadcast transcriptions over data channel for UI display when complete
                if live_event.input_transcript is not None:
                    on_agent_event({
                        "type": "TRANSCRIPT",
                        "author": "user",
                        "text": live_event.input_transcript
                    })
                if live_event.output_transcript is not None:
                    on_agent_event({
                        "type": "TRANSCRIPT",
                        "author": "agent",
                        "text": live_event.output_transcript
                    })
                    if is_session_end_requested():
                        logger.info("Session end requested via end_consultation tool %s", session_log_context(room_name, customer_id, session_id, mode))
                        clear_session_end_request()
                        schedule_session_end_disconnect("final_output_transcript")

                # Log any final responses or tool call events for tracking
                if live_event.final_response:
                    logger.debug("Agent turn complete. Finished generation.")
                    if is_session_end_requested():
                        logger.info("Session end requested without final output transcript %s", session_log_context(room_name, customer_id, session_id, mode))
                        clear_session_end_request()
                        schedule_session_end_disconnect("final_response")

                # Trigger clean shutdown when the model completes the session
                if live_event.end_of_agent:
                    logger.info("Model requested end of session conversation %s", session_log_context(room_name, customer_id, session_id, mode))
                    schedule_session_end_disconnect("end_of_agent")

                if live_event.interrupted:
                    logger.info("ADK Live response interrupted %s", session_log_context(room_name, customer_id, session_id, mode))

                if live_event.session_resumption_handle:
                    logger.debug("ADK Live session resumption handle updated %s", session_log_context(room_name, customer_id, session_id, mode))

                if is_session_end_requested() and not session_end_disconnect_task:
                    logger.info("Session end requested; using graceful fallback disconnect %s", session_log_context(room_name, customer_id, session_id, mode))
                    clear_session_end_request()
                    schedule_session_end_disconnect("session_end_fallback")
        except Exception as e:
            logger.error("Error in Gemini run_live loop %s error=%s", session_log_context(room_name, customer_id, session_id, mode), e, exc_info=True)
            raise
        finally:
            if session_end_disconnect_task and not disconnect_event.is_set():
                try:
                    await asyncio.wait_for(session_end_disconnect_task, timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning("Timed out waiting for graceful session end %s", session_log_context(room_name, customer_id, session_id, mode))
            logger.info("Gemini stream loop finished; closing connections %s", session_log_context(room_name, customer_id, session_id, mode))
            live_queue.close()
            await room.disconnect()

    async def mock_video_loop():
        logger.info("Starting mock video loop task...")
        import cv2
        video_path = "assets/mock_avatar.mp4"
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error(f"Failed to open mock video file: {video_path}")
            return
        
        try:
            pts_us = 0
            frame_delay = 1.0 / 30.0
            while not disconnect_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                
                rgba_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                fh, fw, _ = rgba_frame.shape
                
                from livekit.rtc._proto import video_frame_pb2 as proto_video
                lk_frame = rtc.VideoFrame(
                    width=fw,
                    height=fh,
                    type=proto_video.VideoBufferType.RGBA,
                    data=rgba_frame.tobytes()
                )
                
                pts_us += int(frame_delay * 1_000_000)
                if video_source:
                    video_source.capture_frame(lk_frame, timestamp_us=pts_us)
                
                await asyncio.sleep(frame_delay)
        except asyncio.CancelledError:
            logger.info("Mock video loop task cancelled.")
        except Exception as ex:
            logger.error(f"Error in mock video loop: {ex}")
        finally:
            cap.release()

    # Launch connection, playout loop, and Gemini loop concurrently in a reconnect loop
    playout_task = None
    gemini_task = None
    disconnect_task = None
    handoff_task = None
    watchdog_task = None
    mock_video_task = None
    ffmpeg_proc = None
    ffmpeg_task = None
    try:
        await run_livekit_connection()
        disconnect_event.clear()
        handoff_event.clear()
        
        # Start the warning & timeout watchdog task
        async def watchdog_task_loop():
            nonlocal terminal_outcome
            elapsed = 0
            warning_sent = False
            while True:
                await asyncio.sleep(1)
                elapsed += 1
                if elapsed >= warning_duration and not warning_sent:
                    warning_sent = True
                    logger.warning("Watchdog warning triggered %s elapsed_seconds=%s", session_log_context(room_name, customer_id, session_id, mode), elapsed)
                    on_agent_event({
                        "type": "WATCHDOG_WARNING",
                        "time_remaining_seconds": max(0, max_duration - elapsed)
                    })
                if hard_timeout_enabled and elapsed >= max_duration:
                    terminal_outcome = TerminalOutcome.HARD_TIMEOUT
                    logger.error("Watchdog hard timeout reached %s elapsed_seconds=%s", session_log_context(room_name, customer_id, session_id, mode), elapsed)
                    disconnect_event.set()
                    break
        
        watchdog_task = asyncio.create_task(watchdog_task_loop())
        
        if mode == "video" and mock_avatar_enabled:
            mock_video_task = asyncio.create_task(mock_video_loop())
        elif mode == "video" and not mock_avatar_enabled:
            logger.info("Initializing real Live Avatar video pipeline %s", session_log_context(room_name, customer_id, session_id, mode))
            
            async def handle_ffmpeg_audio(reader, writer):
                logger.info("FFmpeg audio stream connected to TCP socket")
                try:
                    while not disconnect_event.is_set():
                        data = await reader.read(4096)
                        if not data:
                            break
                        # Queue the raw audio PCM bytes for playout
                        await playout_queue.put(data)
                        if mode == "video" and agent_stt_queue:
                            await agent_stt_queue.put(data)
                except Exception as ex:
                    logger.error(f"Error in FFmpeg audio TCP handler: {ex}")
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    logger.info("FFmpeg audio stream TCP socket closed")

            try:
                audio_server = await asyncio.start_server(handle_ffmpeg_audio, '127.0.0.1', 0)
                audio_port = audio_server.sockets[0].getsockname()[1]
                logger.info("Local TCP audio server started %s audio_port=%s", session_log_context(room_name, customer_id, session_id, mode), audio_port)
            except Exception as e:
                logger.error("Failed to start local TCP audio server %s error=%s", session_log_context(room_name, customer_id, session_id, mode), e)

            if audio_port:
                try:
                    ffmpeg_proc = await asyncio.create_subprocess_exec(
                        'ffmpeg',
                        '-threads', '1',
                        '-f', 'mp4',
                        '-i', 'pipe:0',
                        '-vf', 'scale=352:640',
                        '-map', '0:v', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-',
                        '-map', '0:a', '-f', 's16le', '-ar', '24000', '-ac', '1', f'tcp://127.0.0.1:{audio_port}',
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                except Exception as avatar_error:
                    logger.error("Live Avatar decoder failed; degrading to audio %s error=%s", session_log_context(room_name, customer_id, session_id, mode), avatar_error)

            if ffmpeg_proc is None:
                audio_model = os.getenv("VOICE_AGENT_AUDIO_MODEL")
                if not audio_model:
                    terminal_outcome = TerminalOutcome.MEDIA_FAILURE
                    raise RuntimeError("Live Avatar decoder failed and no audio fallback model is configured")
                mode = "audio"
                session_agent.model = Gemini(model=audio_model)
                run_config = build_live_run_config(
                    mode="audio",
                    avatar_name=None,
                    voice_name=voice_name,
                    language_code=lang_code,
                )
                on_agent_event({"type": "AVATAR_FALLBACK", "mode": "audio"})
            
            async def log_ffmpeg_stderr():
                try:
                    while True:
                        line = await ffmpeg_proc.stderr.readline()
                        if not line:
                            break
                        logger.debug(f"[FFmpeg] {line.decode('utf-8', errors='ignore').strip()}")
                except Exception as ex:
                    logger.error(f"Error reading FFmpeg stderr: {ex}")
            
            if ffmpeg_proc:
                asyncio.create_task(log_ffmpeg_stderr())
            
            async def read_ffmpeg_frames_loop():
                vw, vh = 352, 640
                frame_size = vw * vh * 4
                pts_us = 0
                frame_delay = 1.0 / 30.0
                try:
                    logger.info("FFmpeg frame reader task started.")
                    frame_count = 0
                    while not disconnect_event.is_set():
                        # Native non-blocking read from async subprocess pipe
                        try:
                            raw_frame = await ffmpeg_proc.stdout.readexactly(frame_size)
                        except asyncio.IncompleteReadError:
                            logger.info("FFmpeg decoder stdout closed (incomplete read).")
                            break
                            
                        frame_count += 1
                        if frame_count % 30 == 0 or frame_count <= 5: # log first 5 frames, then every 30th
                            logger.debug(f"Decoded video frame #{frame_count} from FFmpeg stdout (size={len(raw_frame)} bytes)")
                            
                        from livekit.rtc._proto import video_frame_pb2 as proto_video
                        lk_frame = rtc.VideoFrame(
                            width=vw,
                            height=vh,
                            type=proto_video.VideoBufferType.RGBA,
                            data=raw_frame
                        )
                        pts_us += int(frame_delay * 1_000_000)
                        if video_source:
                            video_source.capture_frame(lk_frame, timestamp_us=pts_us)
                            if frame_count % 30 == 0 or frame_count <= 5:
                                logger.debug(f"Captured video frame #{frame_count} to LiveKit VideoSource")
                except asyncio.CancelledError:
                    logger.info("FFmpeg frame reader task cancelled.")
                except Exception as ex:
                    logger.error(f"Error in FFmpeg frame reader: {ex}")
                finally:
                    if ffmpeg_proc:
                        try:
                            ffmpeg_proc.terminate()
                            try:
                                await asyncio.wait_for(ffmpeg_proc.wait(), timeout=1.0)
                            except asyncio.TimeoutError:
                                logger.warning("FFmpeg did not exit gracefully, killing...")
                                ffmpeg_proc.kill()
                        except Exception as ex:
                            logger.error(f"Error terminating FFmpeg reader process: {ex}")
            
            if ffmpeg_proc:
                ffmpeg_task = asyncio.create_task(read_ffmpeg_frames_loop())
            
        playout_task = asyncio.create_task(playout_loop())
        gemini_task = asyncio.create_task(run_gemini_loop())
        
        async def wait_for_disconnect():
            await disconnect_event.wait()
            logger.info(
                "LiveKit room disconnected; ending voice session %s",
                session_log_context(room_name, customer_id, session_id, mode),
            )
        disconnect_task = asyncio.create_task(wait_for_disconnect())

        async def wait_for_handoff():
            await handoff_event.wait()
            raise HandoffException("Handoff to human supervisor initiated")
        handoff_task = asyncio.create_task(wait_for_handoff())
        
        # Wait for either of them to complete (if run_gemini_loop finishes or crashes, or room disconnects, or handoff triggers, we exit)
        tasks = [playout_task, gemini_task, disconnect_task, handoff_task, watchdog_task]
        if mock_video_task:
            tasks.append(mock_video_task)
        # Avatar decoding is optional media. Its termination must not end the
        # ADK workflow or customer audio session.
            
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        # Propagate exceptions from completed tasks
        for task in done:
            task.result()
    except KeyboardInterrupt:
        terminal_outcome = TerminalOutcome.CANCELLED
        logger.info("Shutting down voice agent %s", session_log_context(room_name, customer_id, session_id, mode))
    except HandoffException as he:
        terminal_outcome = TerminalOutcome.HANDOFF
        logger.info("Handoff completed successfully %s reason=%s", session_log_context(room_name, customer_id, session_id, mode), he)
        for task in [playout_task, gemini_task, disconnect_task, handoff_task, watchdog_task, mock_video_task, ffmpeg_task, user_stt_task, agent_stt_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if ffmpeg_proc:
            try:
                ffmpeg_proc.terminate()
                try:
                    await asyncio.wait_for(ffmpeg_proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning("FFmpeg did not exit gracefully, killing...")
                    ffmpeg_proc.kill()
            except Exception as ex:
                logger.error(f"Error terminating FFmpeg reader process: {ex}")
        try:
            await room.disconnect()
        except Exception:
            pass
        logger.info("Voice agent entered handoff standby and completed the session %s", session_log_context(room_name, customer_id, session_id, mode))
    except Exception as e:
        if terminal_outcome not in {
            TerminalOutcome.HARD_TIMEOUT,
            TerminalOutcome.MEDIA_FAILURE,
        }:
            terminal_outcome = TerminalOutcome.MODEL_FAILURE
        logger.error("Encountered error in voice agent session %s error=%s", session_log_context(room_name, customer_id, session_id, mode), e, exc_info=True)
    finally:
        logger.info("Cleaning up connections and tasks %s", session_log_context(room_name, customer_id, session_id, mode, active_escalation_id=active_escalation_id, terminal_outcome=terminal_outcome.value))
        # Cancel any pending tasks
        for task in [playout_task, gemini_task, disconnect_task, handoff_task, watchdog_task, mock_video_task, ffmpeg_task, user_stt_task, agent_stt_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if ffmpeg_proc:
            try:
                ffmpeg_proc.terminate()
                try:
                    await asyncio.wait_for(ffmpeg_proc.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning("FFmpeg did not exit gracefully, killing...")
                    ffmpeg_proc.kill()
            except Exception as ex:
                logger.error(f"Error terminating FFmpeg reader process: {ex}")
        # If the room disconnected before the supervisor took over, mark the escalation as ABANDONED
        # If the room disconnected before the supervisor took over, mark the escalation as ABANDONED
        if active_escalation_id is not None:
            try:
                import httpx
                headers = agent_module.get_auth_headers()
                async with httpx.AsyncClient(timeout=10.0) as client:
                    abandon_url = f"{agent_module.BANKING_SERVICE_URL}/support/escalations/{active_escalation_id}/abandon"
                    resp = await client.post(abandon_url, headers=headers)
                    if resp.status_code == 200:
                        logger.info("Active escalation marked as ABANDONED via API %s escalation_id=%s", session_log_context(room_name, customer_id, session_id, mode), active_escalation_id)
                        active_escalation_id = None
                    else:
                        logger.error("Failed to mark escalation as ABANDONED via API %s status=%s body=%s", session_log_context(room_name, customer_id, session_id, mode, active_escalation_id=active_escalation_id), resp.status_code, resp.text)
            except Exception as ex:
                logger.error("Failed to call abandon escalation API %s error=%s", session_log_context(room_name, customer_id, session_id, mode, active_escalation_id=active_escalation_id), ex, exc_info=True)

        if audio_server:
            audio_server.close()
            try:
                await audio_server.wait_closed()
            except Exception:
                pass

        live_queue.close()
        for tool in getattr(session_agent, "tools", []) or []:
            close = getattr(tool, "close", None)
            if close:
                try:
                    await close()
                except Exception as ex:
                    logger.warning("Failed to close session tool %s error=%s", session_log_context(room_name, customer_id, session_id, mode), ex)
        try:
            await room.disconnect()
        except Exception:
            pass
        reset_session_context(session_context_tokens)

app_version = f"{BUILD_VERSION} ({BUILD_COMMIT_ID})"
app = FastAPI(title="Credit Support Voice Agent API", version=app_version)
active_sessions = {}
MAX_CONCURRENT_SESSIONS = runtime_config.max_concurrent_sessions

@app.get("/healthz")
@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "build_version": BUILD_VERSION,
        "build_commit_id": BUILD_COMMIT_ID,
        "build_time": BUILD_TIME
    }

@app.post("/internal/comms/voice/start")
async def start_session(room_name: str, customer_id: str, session_id: str, request: Request, mode: str = "audio"):
    try:
        mode = validate_session_request(runtime_config, mode=mode)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    logger.info("Request to start voice agent session %s", session_log_context(room_name, customer_id, session_id, mode))
    
    # Dynamically resolve BANKING_SERVICE_URL from request URL if not explicitly set in env
    import agent.agent as agent_module
    if not os.getenv("BANKING_SERVICE_URL"):
        own_url = str(request.base_url).rstrip("/")
        if "credit-support-agent" in own_url:
            agent_module.BANKING_SERVICE_URL = own_url.replace("credit-support-agent", "banking-service")
            logger.info("Dynamically resolved BANKING_SERVICE_URL %s banking_service_url=%s", session_log_context(room_name, customer_id, session_id, mode), agent_module.BANKING_SERVICE_URL)

    if len(active_sessions) >= MAX_CONCURRENT_SESSIONS:
        logger.warning("Rejecting start request %s max_capacity=%s", session_log_context(room_name, customer_id, session_id, mode), MAX_CONCURRENT_SESSIONS)
        raise HTTPException(status_code=429, detail="Container session capacity reached.")

    # If a session is already active for this room, cancel it to allow the new one to take over
    if room_name in active_sessions:
        logger.info("Cancelling existing session to allow replacement %s", session_log_context(room_name, customer_id, session_id, mode))
        old_task = active_sessions[room_name]
        old_task.cancel()
        try:
            await asyncio.wait_for(old_task, timeout=3.0)
        except Exception as e:
            logger.info("Old task cleanup complete or timed out %s error=%s", session_log_context(room_name, customer_id, session_id, mode), e)
        active_sessions.pop(room_name, None)

    async def run_session_wrapper():
        try:
            await run_voice_agent_session(room_name, customer_id, session_id, mode)
        finally:
            active_sessions.pop(room_name, None)
            logger.info("Cleaned up room registry %s", session_log_context(room_name, customer_id, session_id, mode))

    # Create the task wrapper and store in active_sessions map
    task = asyncio.create_task(run_session_wrapper())
    active_sessions[room_name] = task
    
    return {"status": "LAUNCHED", "room_name": room_name}

if __name__ == "__main__":
    logger.info(f"Starting Credit Support Voice Agent version: {app_version}")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
