import os
os.environ["NNPACK_DISABLED"] = "1"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"
import sys
import asyncio
import logging
import time
import numpy as np
from livekit import rtc
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# Prepend the directory to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agent.agent import (
    bind_session_context,
    clear_session_end_request,
    create_voice_agent,
    is_session_end_requested,
    is_tool_processing,
    record_customer_authorization_decision,
    record_customer_turn,
    reset_session_context,
)
from agent.avatar_runtime import run_with_avatar_fallback
from agent.instructions import compose_session_instruction
from agent.live_runtime import build_live_run_config, env_flag, normalize_live_event
from agent.guidance_snapshot import guidance_observability_payload
from agent.media_bridge import BufferedAudioPlayout, SileroVADTracker, discard_audio_queue
from agent.log_safety import stable_log_reference
from agent.session_coordinator import (
    default_session_bootstrap,
    load_session_bootstrap,
    should_abandon_escalation,
)
from agent.runtime_config import load_runtime_config, validate_session_request
from agent.session_capacity import SessionCapacity
from agent.readiness import build_readiness_report
from agent.terminal_outcome import TerminalOutcome, ToolFailureTracker
from agent.session_store import (
    cleanup_expired_sessions,
    get_session_service,
    open_or_resume_session,
)
from agent.workflow_plugin import FraudWorkflowStatePlugin
from agent.version import BUILD_VERSION, BUILD_COMMIT_ID, BUILD_TIME
from agent.events import DataChannelEvent, INTERNAL_TOOL_RUNTIME_STATUS
from agent.typed_input import (
    TypedInputError,
    parse_customer_text_packet,
    typed_input_ack,
    validate_typed_turn_availability,
)
from agent.telemetry import (
    record_avatar_fallback,
    record_interruption,
    record_session_completed,
    record_session_started,
    record_typed_turn,
)
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
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)


def session_log_context(room_name: str, customer_id: str, session_id: str, mode: str, **extra) -> str:
    context = {
        "room_ref": stable_log_reference(room_name, prefix="room"),
        "customer_ref": stable_log_reference(customer_id, prefix="customer"),
        "session_ref": stable_log_reference(session_id, prefix="session"),
        "mode": mode,
    }
    for identifier in ("fraud_alert_id", "active_escalation_id"):
        if identifier in extra:
            value = extra.pop(identifier)
            extra[identifier.removesuffix("_id") + "_ref"] = stable_log_reference(
                value,
                prefix=identifier.removesuffix("_id"),
            )
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
    logger.info(
        "Generating fresh LiveKit token room_ref=%s",
        stable_log_reference(room_name, prefix="room"),
    )
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
    requested_mode = mode
    session_started_at = time.monotonic()
    record_session_started(mode)
    logger.info("Initializing voice agent session %s", session_log_context(room_name, customer_id, session_id, mode))
    import agent.agent as agent_module
    session_context_tokens = bind_session_context(
        customer_id,
        None,
        support_session_id=session_id,
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id=session_id,
    )
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
    agent_module.configure_proposal_runtime_context(
        reset_generation=str(reset_generation.get("token") or ""),
        catalog_snapshot_id=support_guidance.get("snapshot_id"),
    )
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
            "- An AUTHORIZATION_REQUIRED tool result is an expected checkpoint, not a technical failure. Never apologize or escalate for it; ask for the required explicit confirmation and wait.\n"
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
            plugins=[FraudWorkflowStatePlugin(
                customer_turn_observer=record_customer_turn,
                authorization_observer=record_customer_authorization_decision,
            )],
        ),
        session_service=session_service,
    )
    loop = asyncio.get_running_loop()
    live_queue = LiveRequestQueue()

    conversation_transcript = []
    tool_failure_tracker = ToolFailureTracker()

    # Define tool event callback to broadcast over LiveKit data channel
    def on_agent_event(event_dict):
        if event_dict.get("type") == INTERNAL_TOOL_RUNTIME_STATUS:
            tool_failure_tracker.record(
                str(event_dict.get("tool") or ""),
                str(event_dict.get("outcome") or ""),
            )
            return
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
                                "Successfully synced support escalation via API %s",
                                session_log_context(
                                    room_name,
                                    customer_id,
                                    session_id,
                                    mode,
                                    active_escalation_id=active_escalation_id,
                                ),
                            )
                        else:
                            logger.error("Failed to sync support escalation via API %s status=%s", session_log_context(room_name, customer_id, session_id, mode), resp.status_code)
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
    typed_turn_lock = asyncio.Lock()
    typed_turn_active = asyncio.Event()
    runtime_transition_active = asyncio.Event()
    voice_input_active = asyncio.Event()
    seen_typed_message_ids: set[str] = set()
    typed_message_order: list[str] = []
    pending_typed_transcripts: list[str] = []
    typed_turn_watchdog_task = None
    greeting_task = None
    greeting_sent = False

    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            if not participant.identity.startswith("agent-human"):
                asyncio.create_task(handle_incoming_audio(track))
            else:
                logger.info(
                    "Ignoring audio track subscription from human supervisor %s "
                    "participant_ref=%s",
                    session_log_context(room_name, customer_id, session_id, mode),
                    stable_log_reference(participant.identity, prefix="participant"),
                )

    disconnect_event = asyncio.Event()

    @room.on("disconnected")
    def on_disconnected(reason: rtc.DisconnectReason):
        # The customer ending a call and our graceful terminal path both land
        # here. Actual media/model failures are logged at their failure site.
        logger.info("Disconnected from LiveKit room %s reason=%s", session_log_context(room_name, customer_id, session_id, mode), reason)
        disconnect_event.set()

    handoff_event = asyncio.Event()

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        if participant.identity.startswith("agent-human"):
            logger.info(
                "Human agent connected %s participant_ref=%s",
                session_log_context(room_name, customer_id, session_id, mode),
                stable_log_reference(participant.identity, prefix="participant"),
            )
            handoff_event.set()

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(
            "Participant disconnected %s participant_ref=%s",
            session_log_context(room_name, customer_id, session_id, mode),
            stable_log_reference(participant.identity, prefix="participant"),
        )
        if not participant.identity.startswith("agent-human"):
            logger.info("Customer disconnected; initiating voice agent session shutdown %s", session_log_context(room_name, customer_id, session_id, mode))
            disconnect_event.set()

    async def publish_typed_ack(
        participant_identity: str | None,
        *,
        message_id: str | None,
        accepted: bool,
        code: str | None = None,
        message: str | None = None,
        retryable: bool = False,
    ) -> None:
        if not participant_identity:
            return
        await room.local_participant.publish_data(
            typed_input_ack(
                message_id=message_id,
                accepted=accepted,
                code=code,
                message=message,
                retryable=retryable,
            ),
            reliable=True,
            destination_identities=[participant_identity],
            topic="voice-support",
        )

    async def handle_typed_input(packet: rtc.DataPacket) -> None:
        nonlocal typed_turn_watchdog_task
        participant_identity = (
            packet.participant.identity if packet.participant is not None else None
        )
        message_id = None
        delivered_to_adk = False
        try:
            import json

            raw_payload = json.loads(packet.data.decode("utf-8"))
            message_id = str(raw_payload.get("message_id") or "") or None
        except Exception:
            pass
        try:
            message = parse_customer_text_packet(
                packet.data,
                participant_identity=participant_identity,
                expected_identity=f"user-{customer_id}",
                seen_message_ids=seen_typed_message_ids,
            )
            if message is None:
                return
            validate_typed_turn_availability(
                tool_processing=is_tool_processing(),
                voice_input_active=voice_input_active.is_set(),
                typed_turn_active=typed_turn_active.is_set(),
                runtime_transition_active=runtime_transition_active.is_set(),
                session_ending=(
                    is_session_end_requested() or disconnect_event.is_set()
                ),
                human_handoff_active=handoff_event.is_set(),
            )
            async with typed_turn_lock:
                validate_typed_turn_availability(
                    tool_processing=is_tool_processing(),
                    voice_input_active=voice_input_active.is_set(),
                    typed_turn_active=typed_turn_active.is_set(),
                    runtime_transition_active=runtime_transition_active.is_set(),
                    session_ending=(
                        is_session_end_requested() or disconnect_event.is_set()
                    ),
                    human_handoff_active=handoff_event.is_set(),
                )
                discard_audio_queue(playout_queue)
                seen_typed_message_ids.add(message.message_id)
                typed_message_order.append(message.message_id)
                if len(typed_message_order) > 200:
                    seen_typed_message_ids.discard(typed_message_order.pop(0))
                pending_typed_transcripts.append(message.text)
                typed_turn_active.set()
                record_customer_turn(
                    message.text,
                    event_id=f"typed-{message.message_id}",
                    pending_ingress=True,
                )

                async def release_stalled_typed_turn() -> None:
                    await asyncio.sleep(30.0)
                    if typed_turn_active.is_set():
                        typed_turn_active.clear()
                        if message.text in pending_typed_transcripts:
                            pending_typed_transcripts.remove(message.text)
                        logger.warning(
                            "Released stalled typed-turn microphone gate %s "
                            "message_ref=%s",
                            session_log_context(room_name, customer_id, session_id, mode),
                            stable_log_reference(
                                message.message_id, prefix="typed_message"
                            ),
                        )

                if typed_turn_watchdog_task and not typed_turn_watchdog_task.done():
                    typed_turn_watchdog_task.cancel()
                typed_turn_watchdog_task = asyncio.create_task(
                    release_stalled_typed_turn()
                )
                live_queue.send_content(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=message.text)],
                    )
                )
                delivered_to_adk = True
                on_agent_event(
                    {
                        "type": DataChannelEvent.TRANSCRIPT.value,
                        "author": "user",
                        "text": message.text,
                    }
                )
                await publish_typed_ack(
                    participant_identity,
                    message_id=message.message_id,
                    accepted=True,
                )
                logger.info(
                    "Accepted typed customer turn %s message_ref=%s "
                    "character_count=%s",
                    session_log_context(room_name, customer_id, session_id, mode),
                    stable_log_reference(message.message_id, prefix="typed_message"),
                    len(message.text),
                )
                record_typed_turn(mode, "accepted")
        except TypedInputError as error:
            if error.code == "DUPLICATE_MESSAGE":
                await publish_typed_ack(
                    participant_identity,
                    message_id=message_id,
                    accepted=True,
                )
                record_typed_turn(mode, "duplicate")
                return
            await publish_typed_ack(
                participant_identity,
                message_id=message_id,
                accepted=False,
                code=error.code,
                message=str(error),
                retryable=error.retryable,
            )
            logger.warning(
                "Rejected typed customer turn %s code=%s retryable=%s",
                session_log_context(room_name, customer_id, session_id, mode),
                error.code,
                error.retryable,
            )
            record_typed_turn(mode, "rejected")
        except Exception as error:
            # If ADK did not accept the turn, roll back deduplication so a
            # client retry can safely deliver it. If only the acknowledgement
            # failed, retain the id: the client's same-id retry will receive a
            # duplicate acceptance without creating a second model turn.
            if not delivered_to_adk and message_id:
                seen_typed_message_ids.discard(message_id)
                if message_id in typed_message_order:
                    typed_message_order.remove(message_id)
                if "message" in locals() and message.text in pending_typed_transcripts:
                    pending_typed_transcripts.remove(message.text)
                typed_turn_active.clear()
                if typed_turn_watchdog_task and not typed_turn_watchdog_task.done():
                    typed_turn_watchdog_task.cancel()
                try:
                    await publish_typed_ack(
                        participant_identity,
                        message_id=message_id,
                        accepted=False,
                        code="DELIVERY_FAILED",
                        message="The message could not be delivered. Please try again.",
                        retryable=True,
                    )
                except Exception:
                    pass
            logger.warning(
                "Typed customer turn delivery failed %s delivered_to_adk=%s error_type=%s",
                session_log_context(room_name, customer_id, session_id, mode),
                delivered_to_adk,
                type(error).__name__,
            )
            record_typed_turn(
                mode,
                "ack_failed" if delivered_to_adk else "delivery_failed",
            )

    @room.on("data_received")
    def on_data_received(packet: rtc.DataPacket):
        asyncio.create_task(handle_typed_input(packet))

    async def handle_incoming_audio(track: rtc.Track):
        nonlocal terminal_outcome, greeting_task, greeting_sent
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
                        if disconnect_event.is_set():
                            return
                        logger.info("Media path is active. Triggering assistant greeting...")
                        greeting_text = initial_greeting_prompt
                        live_queue.send_content(
                            types.Content(
                                parts=[types.Part(text=greeting_text)]
                            )
                        )
                    if not greeting_sent:
                        greeting_sent = True
                        greeting_task = asyncio.create_task(send_delayed_greeting())
                    resampler = rtc.AudioResampler(
                        input_rate=frame.sample_rate,
                        output_rate=16000,
                        num_channels=1
                    )
                # Resample the incoming frame
                resampled_frames = resampler.push(frame)
                for res_frame in resampled_frames:
                    # Check if the agent is currently processing a tool call or shutting down to drop user mic buffers
                    if is_tool_processing() or typed_turn_active.is_set() or is_session_end_requested() or session_end_disconnect_task:
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
                        voice_input_active.set()
                        if video_manual_activity_enabled:
                            live_queue.send_activity_start()
                        # Clear agent's playout queue to immediately interrupt speaking
                        logger.info("User speaking, interrupting agent voice output...")
                        discard_audio_queue(playout_queue)

                    # Always send the audio blob to the model to allow server-side silence detection
                    live_queue.send_realtime(audio_blob)
                    if speech_ended and video_manual_activity_enabled:
                        live_queue.send_activity_end()
                    if speech_ended:
                        voice_input_active.clear()
        except Exception as err:
            terminal_outcome = TerminalOutcome.MEDIA_FAILURE
            logger.error(
                "Incoming audio path failed %s error_type=%s",
                session_log_context(room_name, customer_id, session_id, mode),
                type(err).__name__,
                exc_info=True,
            )
            disconnect_event.set()
        finally:
            voice_input_active.clear()
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
                    if live_event.input_transcript in pending_typed_transcripts:
                        pending_typed_transcripts.remove(live_event.input_transcript)
                    else:
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
                    typed_turn_active.clear()
                    if typed_turn_watchdog_task and not typed_turn_watchdog_task.done():
                        typed_turn_watchdog_task.cancel()
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
                    record_interruption(mode)
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
            # Session-level cleanup owns the shared queue and LiveKit room so
            # an avatar decoder failure can restart only the model stream.

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
                video_manual_activity_enabled = False
                record_avatar_fallback("decoder_start_failed")
                on_agent_event(
                    {
                        "type": DataChannelEvent.AVATAR_FALLBACK.value,
                        "mode": "audio",
                    }
                )
            
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
            
        async def prepare_audio_fallback() -> None:
            runtime_transition_active.set()
            deadline = asyncio.get_running_loop().time() + 30.0
            while (
                typed_turn_active.is_set()
                and not disconnect_event.is_set()
                and not handoff_event.is_set()
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.05)

        async def activate_audio_fallback() -> None:
            nonlocal live_queue, mode, run_config, video_manual_activity_enabled
            nonlocal terminal_outcome
            audio_model = os.getenv("VOICE_AGENT_AUDIO_MODEL")
            if not audio_model:
                terminal_outcome = TerminalOutcome.MEDIA_FAILURE
                raise RuntimeError(
                    "Avatar decoder stopped and no audio fallback model is configured"
                )
            live_queue.close()
            live_queue = LiveRequestQueue()
            mode = "audio"
            session_agent.model = Gemini(model=audio_model)
            run_config = build_live_run_config(
                mode="audio",
                avatar_name=None,
                voice_name=voice_name,
                language_code=lang_code,
            )
            video_manual_activity_enabled = False
            runtime_transition_active.clear()
            record_avatar_fallback("decoder_stopped")
            logger.warning(
                "Live Avatar decoder stopped; continuing with audio %s",
                session_log_context(room_name, customer_id, session_id, mode),
            )
            on_agent_event(
                {
                    "type": DataChannelEvent.AVATAR_FALLBACK.value,
                    "mode": "audio",
                }
            )

        playout_task = asyncio.create_task(playout_loop())
        gemini_task = asyncio.create_task(
            run_with_avatar_fallback(
                primary_factory=run_gemini_loop,
                decoder_task=ffmpeg_task,
                fallback_factory=run_gemini_loop,
                prepare_fallback=prepare_audio_fallback,
                activate_fallback=activate_audio_fallback,
                stop_requested=lambda: (
                    disconnect_event.is_set()
                    or handoff_event.is_set()
                    or session_end_disconnect_task is not None
                ),
            )
        )
        
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
        for task in [playout_task, gemini_task, disconnect_task, handoff_task, watchdog_task, mock_video_task, ffmpeg_task, user_stt_task, agent_stt_task, typed_turn_watchdog_task, greeting_task]:
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
        terminal_outcome = tool_failure_tracker.terminal_outcome(terminal_outcome)
        record_session_completed(
            requested_mode,
            terminal_outcome.value,
            time.monotonic() - session_started_at,
        )
        logger.info("Cleaning up connections and tasks %s", session_log_context(room_name, customer_id, session_id, mode, active_escalation_id=active_escalation_id, terminal_outcome=terminal_outcome.value))
        # Cancel any pending tasks
        for task in [playout_task, gemini_task, disconnect_task, handoff_task, watchdog_task, mock_video_task, ffmpeg_task, user_stt_task, agent_stt_task, typed_turn_watchdog_task, greeting_task]:
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
        if should_abandon_escalation(active_escalation_id, terminal_outcome):
            try:
                import httpx
                headers = agent_module.get_auth_headers()
                async with httpx.AsyncClient(timeout=10.0) as client:
                    abandon_url = f"{agent_module.BANKING_SERVICE_URL}/support/escalations/{active_escalation_id}/abandon"
                    resp = await client.post(abandon_url, headers=headers)
                    if resp.status_code == 200:
                        logger.info(
                            "Active escalation marked as ABANDONED via API %s",
                            session_log_context(
                                room_name,
                                customer_id,
                                session_id,
                                mode,
                                active_escalation_id=active_escalation_id,
                            ),
                        )
                        active_escalation_id = None
                    else:
                        logger.error("Failed to mark escalation as ABANDONED via API %s status=%s", session_log_context(room_name, customer_id, session_id, mode, active_escalation_id=active_escalation_id), resp.status_code)
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
session_capacity = SessionCapacity(
    max_units=runtime_config.max_concurrent_sessions,
    audio_units=runtime_config.audio_session_capacity_units,
    video_units=runtime_config.video_session_capacity_units,
)
session_registry_lock = asyncio.Lock()


class VoiceSessionStartRequest(BaseModel):
    room_name: str
    customer_id: str
    session_id: str
    mode: str = "audio"

@app.get("/healthz")
@app.get("/")
def health_check():
    return {
        "status": "healthy",
        **session_capacity.snapshot(),
        "build_version": BUILD_VERSION,
        "build_commit_id": BUILD_COMMIT_ID,
        "build_time": BUILD_TIME,
    }


@app.get("/internal/readiness")
async def readiness_check(request: Request, customer_id: str | None = None):
    """Verify runtime dependencies without performing a banking mutation."""
    import agent.agent as agent_module

    customer_id = request.headers.get("x-target-customer-id") or customer_id

    authorization = None
    try:
        token = agent_module.get_auth_token_for_audience(
            agent_module.BANKING_SERVICE_URL
        )
        authorization = f"Bearer {token}"
    except Exception:
        logger.exception("Unable to create banking-service readiness credential")

    customer_probe = None
    if customer_id:
        async def probe_customer_context():
            return await load_session_bootstrap(
                banking_service_url=agent_module.BANKING_SERVICE_URL,
                headers={
                    "Authorization": authorization or "",
                    "x-target-customer-id": customer_id,
                },
            )

        customer_probe = probe_customer_context

    report = await build_readiness_report(
        runtime_config=runtime_config,
        banking_service_url=agent_module.BANKING_SERVICE_URL,
        banking_service_mcp_url=agent_module.get_banking_service_mcp_url(),
        authorization_header=authorization,
        customer_probe=customer_probe,
        deployment_metadata={
            "version": BUILD_VERSION,
            "commit": BUILD_COMMIT_ID,
            "revision": os.getenv("K_REVISION"),
        },
    )
    return JSONResponse(
        status_code=200 if report["status"] == "ready" else 503,
        content=report,
    )

@app.post("/internal/comms/voice/start")
async def start_session(
    request: Request,
    payload: VoiceSessionStartRequest | None = None,
    room_name: str | None = None,
    customer_id: str | None = None,
    session_id: str | None = None,
    mode: str = "audio",
):
    if payload is not None:
        room_name = payload.room_name
        customer_id = payload.customer_id
        session_id = payload.session_id
        mode = payload.mode
    if not room_name or not customer_id or not session_id:
        raise HTTPException(status_code=422, detail="Missing voice session dispatch fields.")
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

    async with session_registry_lock:
        # Release a prior reservation before checking capacity so reconnecting a
        # room cannot be rejected merely because its old task occupies the slot.
        old_task = active_sessions.pop(room_name, None)
        if old_task is not None:
            session_capacity.release(room_name)
            logger.info("Cancelling existing session to allow replacement %s", session_log_context(room_name, customer_id, session_id, mode))
            old_task.cancel()
            try:
                await asyncio.wait_for(old_task, timeout=3.0)
            except (asyncio.CancelledError, TimeoutError):
                logger.info("Old task cleanup complete or timed out %s", session_log_context(room_name, customer_id, session_id, mode))
            except Exception as error:
                logger.warning(
                    "Old task ended with an error during replacement %s error_type=%s",
                    session_log_context(room_name, customer_id, session_id, mode),
                    type(error).__name__,
                )

        try:
            reservation = session_capacity.reserve(room_name, mode)
        except OverflowError as error:
            logger.warning(
                "Rejecting start request %s capacity=%s",
                session_log_context(room_name, customer_id, session_id, mode),
                session_capacity.snapshot(),
            )
            raise HTTPException(status_code=429, detail="Container session capacity reached.") from error

        task = None

        async def run_session_wrapper():
            try:
                await run_voice_agent_session(room_name, customer_id, session_id, mode)
            finally:
                # An older cancelled task must never delete a newer replacement.
                if active_sessions.get(room_name) is task:
                    active_sessions.pop(room_name, None)
                    session_capacity.release(room_name)
                    logger.info("Cleaned up room registry %s", session_log_context(room_name, customer_id, session_id, mode))

        task = asyncio.create_task(run_session_wrapper())
        active_sessions[room_name] = task
        logger.info(
            "Reserved voice capacity %s mode_units=%s capacity=%s",
            session_log_context(room_name, customer_id, session_id, mode),
            reservation.units,
            session_capacity.snapshot(),
        )
    
    return {"status": "LAUNCHED", "room_name": room_name}

if __name__ == "__main__":
    logger.info(f"Starting Credit Support Voice Agent version: {app_version}")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False)
