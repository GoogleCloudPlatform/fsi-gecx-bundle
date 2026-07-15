import asyncio

import numpy as np
import pytest

from agent import media_bridge
from agent.media_bridge import BufferedAudioPlayout, SileroVADTracker, discard_audio_queue


class _AudioSource:
    def __init__(self):
        self.frames = []

    async def capture_frame(self, frame):
        self.frames.append(frame)


@pytest.mark.asyncio
async def test_playout_bridge_accounts_for_buffer_and_drains_queue():
    queue = asyncio.Queue()
    source = _AudioSource()
    bridge = BufferedAudioPlayout(audio_source=source, queue=queue)
    task = asyncio.create_task(bridge.run())
    await queue.put(bytes(7200))
    assert await bridge.wait_for_drain(timeout=1.0) is True
    assert len(source.frames) == 15
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_discard_audio_queue_preserves_join_accounting():
    queue = asyncio.Queue()
    await queue.put(b"one")
    await queue.put(b"two")

    assert discard_audio_queue(queue) == 2
    await asyncio.wait_for(queue.join(), timeout=0.1)


def test_synthetic_streaming_audio_fixture_drives_vad(monkeypatch):
    class Probability:
        def __init__(self, value):
            self.value = value

        def item(self):
            return self.value

    def fake_model(chunk, sample_rate):
        assert sample_rate == 16000
        return Probability(0.95 if float(chunk.abs().mean()) > 0.1 else 0.01)

    monkeypatch.setattr(media_bridge, "_get_vad_model", lambda: fake_model)
    tracker = SileroVADTracker(threshold=0.5, silence_seconds=0.1)

    started, ended = tracker.process_chunk(np.ones(1024, dtype=np.float32))
    assert started is True
    assert ended is False

    started, ended = tracker.process_chunk(np.zeros(2048, dtype=np.float32))
    assert started is False
    assert ended is True
