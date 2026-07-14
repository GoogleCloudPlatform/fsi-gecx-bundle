"""Audio boundary helpers kept independent from ADK workflow coordination."""

from __future__ import annotations

import asyncio
import logging

import numpy as np
import torch
from silero_vad import load_silero_vad

logger = logging.getLogger("voice_agent")
_vad_model = None


def discard_audio_queue(queue: asyncio.Queue) -> int:
    """Discard queued playout while preserving Queue.join accounting."""
    discarded = 0
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        else:
            queue.task_done()
            discarded += 1
    return discarded


def _get_vad_model():
    global _vad_model
    if _vad_model is None:
        _vad_model = load_silero_vad()
    return _vad_model


class SileroVADTracker:
    def __init__(self, threshold=0.5, silence_seconds=0.4, sample_rate=16000):
        self.threshold = threshold
        self.silence_samples_limit = int(silence_seconds * sample_rate)
        self.sample_rate = sample_rate
        self.speech_active = False
        self.silent_samples = 0
        self.buffer = []

    def process_chunk(self, float32_samples: np.ndarray) -> tuple[bool, bool]:
        self.buffer.extend(float32_samples)
        speech_started = False
        speech_ended = False
        chunk_size = 512
        while len(self.buffer) >= chunk_size:
            chunk = np.array(self.buffer[:chunk_size], dtype=np.float32)
            self.buffer = self.buffer[chunk_size:]
            probability = _get_vad_model()(
                torch.from_numpy(chunk), self.sample_rate
            ).item()
            if probability > self.threshold:
                self.silent_samples = 0
                if not self.speech_active:
                    self.speech_active = True
                    speech_started = True
                    logger.info("Speech start detected by VAD")
            else:
                self.silent_samples += chunk_size
                if (
                    self.speech_active
                    and self.silent_samples >= self.silence_samples_limit
                ):
                    self.speech_active = False
                    speech_ended = True
                    logger.info("Speech end detected by VAD")
        return speech_started, speech_ended


class BufferedAudioPlayout:
    """Own jitter buffering, pacing, queue accounting, and drain semantics."""

    def __init__(self, *, audio_source, queue: asyncio.Queue):
        self.audio_source = audio_source
        self.queue = queue

    async def run(self) -> None:
        from livekit import rtc

        accumulator = b""
        chunk_size = 480
        start_time = None
        frame_count = 0
        buffering = True
        loop = asyncio.get_running_loop()
        while True:
            pcm_bytes = await self.queue.get()
            try:
                accumulator += pcm_bytes
                if buffering:
                    if len(accumulator) < 7200:
                        continue
                    buffering = False
                    start_time = loop.time()
                    frame_count = 0
                while len(accumulator) >= chunk_size:
                    chunk = accumulator[:chunk_size]
                    accumulator = accumulator[chunk_size:]
                    await self.audio_source.capture_frame(
                        rtc.AudioFrame(
                            data=chunk,
                            sample_rate=24000,
                            num_channels=1,
                            samples_per_channel=240,
                        )
                    )
                    frame_count += 1
                    delay = start_time + (frame_count * 0.010) - loop.time()
                    if delay > 0:
                        await asyncio.sleep(delay)
                if not accumulator:
                    buffering = True
            finally:
                self.queue.task_done()

    async def wait_for_drain(self, timeout: float = 8.0) -> bool:
        try:
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
