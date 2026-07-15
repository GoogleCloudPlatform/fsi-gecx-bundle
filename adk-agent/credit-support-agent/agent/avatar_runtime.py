"""Supervise optional avatar media without sacrificing the audio workflow."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


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
