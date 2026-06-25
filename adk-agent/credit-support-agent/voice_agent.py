import os
os.environ["NNPACK_DISABLED"] = "1"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"
import sys
import asyncio
import logging
import numpy as np
import torch
from silero_vad import load_silero_vad
from livekit import rtc
from fastapi import FastAPI, HTTPException, Request
import uvicorn

# Prepend the directory to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from agent import root_agent, register_event_callback
from agent.events import DataChannelEvent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.genai import types

# from agent.patch_adk import apply_patch
# apply_patch()

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

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
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

# Initialize Silero VAD
logger.info("Loading Silero VAD model...")
vad_model = load_silero_vad()

class SileroVADTracker:
    def __init__(self, threshold=0.5, silence_seconds=0.4, sample_rate=16000):
        self.threshold = threshold
        self.silence_samples_limit = int(silence_seconds * sample_rate)
        self.sample_rate = sample_rate
        self.speech_active = False
        self.silent_samples = 0
        self.buffer = []

    def process_chunk(self, float32_samples: np.ndarray) -> tuple[bool, bool]:
        """
        Processes audio samples.
        Returns (speech_started_detected, speech_ended_detected)
        """
        self.buffer.extend(float32_samples)
        speech_started = False
        speech_ended = False

        # Silero VAD works on chunks of 512 samples at 16kHz
        chunk_size = 512
        while len(self.buffer) >= chunk_size:
            chunk = np.array(self.buffer[:chunk_size], dtype=np.float32)
            self.buffer = self.buffer[chunk_size:]

            tensor_chunk = torch.from_numpy(chunk)
            prob = vad_model(tensor_chunk, self.sample_rate).item()

            if prob > self.threshold:
                self.silent_samples = 0
                if not self.speech_active:
                    self.speech_active = True
                    speech_started = True
                    logger.info("Speech start detected by VAD")
            else:
                self.silent_samples += chunk_size
                if self.speech_active and self.silent_samples >= self.silence_samples_limit:
                    self.speech_active = False
                    speech_ended = True
                    logger.info("Speech end detected by VAD")

        return speech_started, speech_ended

async def run_stt_worker(client, audio_queue: asyncio.Queue, sample_rate: int, author: str, on_agent_event_fn):
    logger.info(f"Starting async Speech-to-Text worker for {author} (sample_rate={sample_rate}Hz)...")
    try:
        from google.cloud import speech
        
        # Configure the streaming request config
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code="en-US",
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=False
        )
        
        def create_request_generator():
            async def generator():
                yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
                while True:
                    try:
                        chunk = await audio_queue.get()
                        if chunk is None:
                            logger.info(f"STT worker for {author} received poison pill. Exiting generator.")
                            audio_queue.task_done()
                            break
                        yield speech.StreamingRecognizeRequest(audio_content=chunk)
                        audio_queue.task_done()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Error in STT generator for {author}: {e}")
                        break
            return generator()

        # Reconnect loop to handle gRPC / Audio timeouts on silence
        while True:
            try:
                logger.info(f"Connecting to Google Cloud Speech-to-Text for {author}...")
                generator = create_request_generator()
                responses = await client.streaming_recognize(requests=generator)
                async for response in responses:
                    for result in response.results:
                        if result.is_final:
                            transcript = result.alternatives[0].transcript.strip()
                            if transcript:
                                logger.info(f"[{author.upper()} TRANSCRIPT] {transcript}")
                                # Broadcast the transcript to the client room
                                on_agent_event_fn({
                                    "type": "TRANSCRIPT",
                                    "author": author,
                                    "text": transcript
                                })
            except asyncio.CancelledError:
                logger.info(f"STT worker for {author} was cancelled.")
                break
            except Exception as ex:
                # Catch timeout or other gRPC connection closures and attempt recovery
                logger.warning(f"Speech-to-Text stream for {author} closed: {ex}. Reconnecting...")
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        logger.info(f"STT worker for {author} was cancelled.")
    except Exception as e:
        logger.error(f"Fatal exception in STT worker loop for {author}: {e}", exc_info=True)
    finally:
        logger.info(f"Finished STT worker for {author}.")

async def run_voice_agent_session(room_name: str, customer_id: str, session_id: str, mode: str = "audio"):
    logger.info(f"Initializing voice agent session for room: {room_name} (customer: {customer_id}, mode: {mode})")

    # Load active configurations from banking-service
    mock_avatar_enabled = False
    avatar_name = "Ben" # default fallback
    max_duration = 300
    warning_duration = 240
    hard_timeout_enabled = False

    try:
        import httpx
        import agent.agent as agent_module
        headers = agent_module.get_auth_headers()
        async with httpx.AsyncClient(timeout=10.0) as client:
            settings_url = f"{agent_module.BANKING_SERVICE_URL}/api/settings"
            resp = await client.get(settings_url, headers=headers)
            if resp.status_code == 200:
                settings = resp.json()
                mock_avatar_enabled = settings.get("voice_agent_mock_avatar_enabled") == "true"
                max_duration = int(settings.get("voice_agent_max_duration", 300))
                warning_duration = int(settings.get("voice_agent_warning_duration", 240))
                hard_timeout_enabled = settings.get("voice_agent_hard_timeout_enabled") == "true"
                
                avatar_mode = settings.get("voice_agent_avatar_selection", "random")
                if avatar_mode == "random":
                    import random
                    avatar_name = random.choice(["Ingrid", "Paul", "Sam"])
                else:
                    avatar_name = avatar_mode
                logger.info(f"Loaded voice agent settings via API: mock={mock_avatar_enabled}, avatar={avatar_name}, max_duration={max_duration}, warning={warning_duration}, hard={hard_timeout_enabled}")
            else:
                logger.error(f"Failed to fetch system settings from API: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to query system settings from API: {e}")

    # Set active customer ID for database tools dynamically
    import agent.agent as agent_module
    agent_module.active_customer_id_var.set(customer_id)
    logger.info(f"Set active customer ID for database tools: {agent_module.active_customer_id_var.get()}")

    active_escalation_id = None
    audio_server = None
    audio_port = None

    session_service = InMemorySessionService()
    # Create the session dynamically using the passed IDs
    user_id = f"user-{customer_id}"
    await session_service.create_session(app_name="credit-support-agent", user_id=user_id, session_id=session_id)
    
    import copy
    from google.adk.models import Gemini
    session_agent = copy.copy(root_agent)
    if avatar_name:
        session_agent.instruction = session_agent.instruction.replace("{{avatar_name}}", avatar_name)
    else:
        session_agent.instruction = session_agent.instruction.replace("{{avatar_name}}", "Nova")
    if mode == "video":
        model_name = os.getenv("VOICE_AGENT_VIDEO_MODEL")
        if not model_name:
            logger.warning("VOICE_AGENT_VIDEO_MODEL environment variable is not set. Gracefully falling back to audio mode.")
            mode = "audio"

    if mode == "video":
        logger.info(f"Setting agent model to Publishers Gemini Live video wrapper: {model_name}")
        session_agent.model = Gemini(model=model_name)
    else:
        model_name = os.getenv("VOICE_AGENT_AUDIO_MODEL")
        if not model_name:
            raise ValueError("VOICE_AGENT_AUDIO_MODEL environment variable must be set")
        logger.info(f"Setting agent model to Publishers Gemini Live audio wrapper: {model_name}")
        session_agent.model = Gemini(model=model_name)
        
    runner = Runner(app_name="credit-support-agent", agent=session_agent, session_service=session_service)
    loop = asyncio.get_running_loop()
    live_queue = LiveRequestQueue()

    conversation_transcript = []

    # Define tool event callback to broadcast over LiveKit data channel
    def on_agent_event(event_dict):
        if room and room.local_participant:
            import json
            payload = json.dumps(event_dict)
            logger.info(f"Broadcasting event to LiveKit data channel: {event_dict}")
            def schedule_publish():
                asyncio.create_task(room.local_participant.publish_data(payload))
            loop.call_soon_threadsafe(schedule_publish)

        # Capture transcript events in memory
        if event_dict.get("type") == DataChannelEvent.TRANSCRIPT.value:
            conversation_transcript.append({
                "author": event_dict["author"],
                "text": event_dict["text"]
            })
        
        # Capture session end trigger and disconnect
        elif event_dict.get("type") == DataChannelEvent.SESSION_END.value:
            logger.info("SESSION_END event received from tool. Broadcasting to client.")
        
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
                            logger.info(f"Successfully synced support escalation via API: {active_escalation_id}")
                        else:
                            logger.error(f"Failed to sync support escalation via API: {resp.text}")
                except Exception as ex:
                    logger.error(f"Failed to call support escalation API: {ex}", exc_info=True)

            loop.call_soon_threadsafe(lambda: asyncio.create_task(sync_escalation()))

    register_event_callback(on_agent_event)

    user_stt_queue = None
    agent_stt_queue = None
    user_stt_task = None
    agent_stt_task = None

    # Configure ADK streaming for native audio
    # Configure ADK streaming modalities dynamically
    modalities = ["VIDEO"] if mode == "video" else ["AUDIO"]
    avatar_config = types.AvatarConfig(avatar_name=avatar_name) if mode == "video" else None
    
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

    speech_config = types.SpeechConfig(
        language_code=lang_code,
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
        )
    )

    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=modalities,
        avatar_config=avatar_config,
        speech_config=speech_config,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig()
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
        logger.warning(f"Disconnected from LiveKit room: {reason}")
        disconnect_event.set()

    handoff_event = asyncio.Event()

    @room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        if participant.identity.startswith("agent-human"):
            logger.info(f"Human agent {participant.identity} connected. Triggering handoff event.")
            handoff_event.set()

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"Participant disconnected: {participant.identity}")
        if not participant.identity.startswith("agent-human"):
            logger.info("Customer disconnected. Initiating voice agent session shutdown.")
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
                        live_queue.send_content(
                            types.Content(
                                parts=[types.Part(text="Please introduce yourself as Nova Horizon Bank's Credit Card Support Voice Assistant and ask the customer how you can help them today.")]
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
                    # Check if the agent is currently processing a tool call to drop user mic buffers
                    session = await session_service.get_session(app_name="credit-support-agent", user_id=user_id, session_id=session_id)
                    is_processing_tool = session.state.get("is_processing_tool", False) if session else False
                    if is_processing_tool:
                        logger.debug("Muting microphone audio: tool execution in progress.")
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
                        # Clear agent's playout queue to immediately interrupt speaking
                        logger.info("User speaking, interrupting agent voice output...")
                        while not playout_queue.empty():
                            try:
                                playout_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                    # Always send the audio blob to the model to allow server-side silence detection
                    live_queue.send_realtime(audio_blob)
        except Exception as err:
            logger.error(f"Error handling incoming audio: {err}", exc_info=True)
        finally:
            await audio_stream.aclose()

    video_source = None
    local_video_track = None

    async def run_livekit_connection():
        logger.info(f"Connecting to LiveKit Room at {LIVEKIT_URL}...")
        token = get_livekit_token(room_name)
        await room.connect(LIVEKIT_URL, token)
        logger.info("Connected to LiveKit room!")
        
        # Broadcast agent mode to client
        import json
        event_payload = json.dumps({"type": "agent_mode", "mode": mode})
        logger.info(f"Broadcasting agent mode: {event_payload}")
        await room.local_participant.publish_data(event_payload)

        # Publish our microphone/audio source track
        local_track = rtc.LocalAudioTrack.create_audio_track("agent-audio", audio_source)
        publish_options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(local_track, publish_options)
        logger.info("Published agent voice track to room")
        
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
            logger.info(f"Published agent video track ({vw}x{vh}) to room")
        # Broadcast avatar configuration to client UI
        on_agent_event({
            "type": "AVATAR_CONFIG",
            "avatar_name": avatar_name
        })
        
        pass

    async def playout_loop():
        # Continuously reads frames from playout_queue and captures them into the AudioSource
        # AudioSource expects Int16 PCM audio at 24000Hz (sample_rate=24000, 1 channel)
        # Each capture frame should contain sample data
        accumulator = b""
        chunk_size = 480
        start_time = None
        frame_count = 0
        is_buffering = True
        
        while True:
            try:
                pcm_bytes = await playout_queue.get()
                accumulator += pcm_bytes
                
                # Pre-buffer 150ms of audio (7200 bytes) at the start of a turn to absorb network jitter
                if is_buffering:
                    if len(accumulator) < 7200:
                        playout_queue.task_done()
                        continue
                    else:
                        is_buffering = False
                        start_time = asyncio.get_event_loop().time()
                        frame_count = 0
                
                # Extract and play out all complete 10ms (480-byte) audio frames
                while len(accumulator) >= chunk_size:
                    chunk = accumulator[:chunk_size]
                    accumulator = accumulator[chunk_size:]
                    
                    frame = rtc.AudioFrame(
                        data=chunk,
                        sample_rate=24000,
                        num_channels=1,
                        samples_per_channel=240
                    )
                    await audio_source.capture_frame(frame)
                    frame_count += 1
                    
                    # Calculate target playout time for drift-corrected pacing (10ms per frame)
                    target_time = start_time + (frame_count * 0.010)
                    delay = target_time - asyncio.get_event_loop().time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                
                # Reset buffering for the next response if the buffer has been fully cleared
                if len(accumulator) == 0:
                    is_buffering = True
                    
                playout_queue.task_done()
            except Exception as e:
                logger.error(f"Playout capture error: {e}")

    async def run_gemini_loop():
        logger.info("Starting run_live stream loop...")
        try:
            async for event in runner.run_live(
                user_id=user_id,
                session_id=session_id,
                live_request_queue=live_queue,
                run_config=run_config
            ):
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
                if event.input_transcription and event.input_transcription.finished:
                    on_agent_event({
                        "type": "TRANSCRIPT",
                        "author": "user",
                        "text": event.input_transcription.text
                    })
                if event.output_transcription and event.output_transcription.finished:
                    on_agent_event({
                        "type": "TRANSCRIPT",
                        "author": "agent",
                        "text": event.output_transcription.text
                    })

                # Log any final responses or tool call events for tracking
                if event.is_final_response():
                    logger.debug("Agent turn complete. Finished generation.")

                # Trigger clean shutdown when the model completes the session
                if event.actions and event.actions.end_of_agent:
                    logger.info("Model requested end of session conversation.")
                    on_agent_event({
                        "type": "SESSION_END"
                    })
                    
                    async def delayed_disconnect():
                        await asyncio.sleep(3.5)
                        disconnect_event.set()
                    asyncio.create_task(delayed_disconnect())
        except Exception as e:
            logger.error(f"Error in Gemini run_live loop: {e}", exc_info=True)
        finally:
            logger.info("Gemini stream loop finished. Closing connections.")
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
            elapsed = 0
            warning_sent = False
            while True:
                await asyncio.sleep(1)
                elapsed += 1
                if elapsed >= warning_duration and not warning_sent:
                    warning_sent = True
                    logger.warning(f"Watchdog warning triggered: session running for {elapsed}s")
                    on_agent_event({
                        "type": "WATCHDOG_WARNING",
                        "time_remaining_seconds": max(0, max_duration - elapsed)
                    })
                if hard_timeout_enabled and elapsed >= max_duration:
                    logger.error(f"Watchdog hard timeout reached: terminating session after {elapsed}s")
                    disconnect_event.set()
                    break
        
        watchdog_task = asyncio.create_task(watchdog_task_loop())
        
        if mode == "video" and mock_avatar_enabled:
            mock_video_task = asyncio.create_task(mock_video_loop())
        elif mode == "video" and not mock_avatar_enabled:
            logger.info("Initializing real Live Avatar video pipeline (FFmpeg-based decoder)...")
            
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
                logger.info(f"Local TCP audio server started on port {audio_port}")
            except Exception as e:
                logger.error(f"Failed to start local TCP audio server: {e}")

            ffmpeg_proc = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-threads', '1',        # restrict to single thread for resource-constrained containers
                '-f', 'mp4',
                '-i', 'pipe:0',
                '-vf', 'scale=352:640',
                '-map', '0:v', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-',
                '-map', '0:a', '-f', 's16le', '-ar', '24000', '-ac', '1', f'tcp://127.0.0.1:{audio_port}',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
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
            
            ffmpeg_task = asyncio.create_task(read_ffmpeg_frames_loop())
            
        playout_task = asyncio.create_task(playout_loop())
        gemini_task = asyncio.create_task(run_gemini_loop())
        
        async def wait_for_disconnect():
            await disconnect_event.wait()
            raise Exception("LiveKit room disconnected")
        disconnect_task = asyncio.create_task(wait_for_disconnect())

        async def wait_for_handoff():
            await handoff_event.wait()
            raise HandoffException("Handoff to human supervisor initiated")
        handoff_task = asyncio.create_task(wait_for_handoff())
        
        # Wait for either of them to complete (if run_gemini_loop finishes or crashes, or room disconnects, or handoff triggers, we exit)
        tasks = [playout_task, gemini_task, disconnect_task, handoff_task, watchdog_task]
        if mock_video_task:
            tasks.append(mock_video_task)
        if ffmpeg_task:
            tasks.append(ffmpeg_task)
            
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED
        )
        # Propagate exceptions from completed tasks
        for task in done:
            task.result()
    except KeyboardInterrupt:
        logger.info("Shutting down voice agent...")
    except HandoffException as he:
        logger.info(f"Handoff completed successfully: {he}. Cleaning up connections and tasks...")
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
        logger.info("Voice agent successfully entered handoff standby status and completed the session.")
    except Exception as e:
        logger.error(f"Encountered error in voice agent session: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up connections and tasks...")
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
                        logger.info(f"Active escalation {active_escalation_id} marked as ABANDONED via API due to customer disconnect.")
                        active_escalation_id = None
                    else:
                        logger.error(f"Failed to mark escalation as ABANDONED via API: {resp.text}")
            except Exception as ex:
                logger.error(f"Failed to call abandon escalation API: {ex}")

        if audio_server:
            audio_server.close()
            try:
                await audio_server.wait_closed()
            except Exception:
                pass

        live_queue.close()
        try:
            await room.disconnect()
        except Exception:
            pass

app = FastAPI()
active_sessions = {}
MAX_CONCURRENT_SESSIONS = 10

@app.get("/healthz")
@app.get("/")
def health_check():
    return {"status": "healthy", "active_sessions": len(active_sessions)}

@app.post("/internal/comms/voice/start")
async def start_session(room_name: str, customer_id: str, session_id: str, request: Request, mode: str = "audio"):
    logger.info(f"Request to start voice agent session for room: {room_name} (mode: {mode})")
    
    # Dynamically resolve BANKING_SERVICE_URL from request URL if not explicitly set in env
    import agent.agent as agent_module
    if not os.getenv("BANKING_SERVICE_URL"):
        own_url = str(request.base_url).rstrip("/")
        if "credit-support-agent" in own_url:
            agent_module.BANKING_SERVICE_URL = own_url.replace("credit-support-agent", "banking-service")
            logger.info(f"Dynamically resolved BANKING_SERVICE_URL: {agent_module.BANKING_SERVICE_URL}")
    
    if len(active_sessions) >= MAX_CONCURRENT_SESSIONS:
        logger.warning(f"Rejecting start request for {room_name}: max capacity reached ({MAX_CONCURRENT_SESSIONS})")
        raise HTTPException(status_code=429, detail="Container session capacity reached.")

    # If a session is already active for this room, cancel it to allow the new one to take over
    if room_name in active_sessions:
        logger.info(f"Cancelling existing session for room {room_name} to allow replacement...")
        old_task = active_sessions[room_name]
        old_task.cancel()
        try:
            await asyncio.wait_for(old_task, timeout=3.0)
        except Exception as e:
            logger.info(f"Old task cleanup complete or timed out: {e}")
        active_sessions.pop(room_name, None)

    async def run_session_wrapper():
        try:
            await run_voice_agent_session(room_name, customer_id, session_id, mode)
        finally:
            active_sessions.pop(room_name, None)
            logger.info(f"Cleaned up room registry for: {room_name}")

    # Create the task wrapper and store in active_sessions map
    task = asyncio.create_task(run_session_wrapper())
    active_sessions[room_name] = task
    
    return {"status": "LAUNCHED", "room_name": room_name}

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)

