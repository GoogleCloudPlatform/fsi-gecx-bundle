import asyncio

import pytest

from agent.media_bridge import BufferedAudioPlayout


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
