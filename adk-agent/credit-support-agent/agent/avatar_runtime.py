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

"""Supervise optional avatar media without sacrificing the audio workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AvatarVideoFormat:
    """Raw RGBA frame format published to LiveKit from the avatar decoder."""

    width: int
    height: int
    fps: int

    @property
    def frame_bytes(self) -> int:
        return self.width * self.height * 4

    @property
    def frame_interval_us(self) -> int:
        return 1_000_000 // self.fps

    def decoder_args(self, audio_port: int) -> list[str]:
        """FFmpeg args: MP4 on stdin, RGBA frames on stdout, PCM to a socket.

        Scaling to this fixed format keeps every frame exactly
        ``frame_bytes`` long whatever resolution the model streams.
        """
        return [
            "-threads", "1",
            "-f", "mp4",
            "-i", "pipe:0",
            "-vf", f"scale={self.width}:{self.height}",
            "-map", "0:v", "-f", "rawvideo", "-pix_fmt", "rgba", "-",
            "-map", "0:a", "-f", "s16le", "-ar", "24000", "-ac", "1",
            f"tcp://127.0.0.1:{audio_port}",
        ]


# Gemini 3.8 Live Avatar streams 24 FPS MP4 at a minimum of 704x1280 portrait.
LIVE_AVATAR_VIDEO_FORMAT = AvatarVideoFormat(width=704, height=1280, fps=24)


async def run_with_avatar_fallback(
    *,
    primary_factory: Callable[[], Awaitable[Any]],
    decoder_task: asyncio.Task | None,
    fallback_factory: Callable[[], Awaitable[Any]],
    prepare_fallback: Callable[[], Awaitable[None]],
    activate_fallback: Callable[[], Awaitable[None]],
    stop_requested: Callable[[], bool],
) -> Any:
    """Run the primary model and switch once if optional avatar decoding dies."""
    primary_task = asyncio.create_task(primary_factory())
    fallback_task: asyncio.Task | None = None
    try:
        if decoder_task is None:
            return await primary_task

        done, _ = await asyncio.wait(
            {primary_task, decoder_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if primary_task in done:
            return primary_task.result()

        # Retrieve a decoder exception so asyncio does not report it as
        # unhandled. Any decoder termination is a fallback signal.
        try:
            decoder_task.result()
        except (asyncio.CancelledError, Exception):
            pass

        if stop_requested():
            primary_task.cancel()
            try:
                await primary_task
            except asyncio.CancelledError:
                pass
            return None

        await prepare_fallback()
        primary_task.cancel()
        try:
            await primary_task
        except asyncio.CancelledError:
            pass

        await activate_fallback()
        fallback_task = asyncio.create_task(fallback_factory())
        return await fallback_task
    finally:
        for task in (primary_task, fallback_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
