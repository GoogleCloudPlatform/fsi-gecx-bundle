import asyncio

import pytest

from agent.avatar_runtime import run_with_avatar_fallback


@pytest.mark.asyncio
async def test_decoder_failure_switches_to_audio_fallback() -> None:
    fallback_activated = []

    async def primary():
        await asyncio.Event().wait()

    async def decoder():
        return None

    async def activate():
        fallback_activated.append(True)

    async def prepare():
        fallback_activated.append("prepared")

    async def fallback():
        return "audio-complete"

    result = await run_with_avatar_fallback(
        primary_factory=primary,
        decoder_task=asyncio.create_task(decoder()),
        fallback_factory=fallback,
        prepare_fallback=prepare,
        activate_fallback=activate,
        stop_requested=lambda: False,
    )

    assert result == "audio-complete"
    assert fallback_activated == ["prepared", True]


@pytest.mark.asyncio
async def test_primary_completion_does_not_activate_fallback() -> None:
    activated = []

    async def primary():
        return "video-complete"

    async def decoder():
        await asyncio.Event().wait()

    async def activate():
        activated.append(True)

    async def prepare():
        activated.append("prepared")

    decoder_task = asyncio.create_task(decoder())
    try:
        result = await run_with_avatar_fallback(
            primary_factory=primary,
            decoder_task=decoder_task,
            fallback_factory=primary,
            prepare_fallback=prepare,
            activate_fallback=activate,
            stop_requested=lambda: False,
        )
    finally:
        decoder_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await decoder_task

    assert result == "video-complete"
    assert activated == []


@pytest.mark.asyncio
async def test_decoder_stop_during_session_shutdown_does_not_restart_model() -> None:
    activated = []

    async def primary():
        await asyncio.Event().wait()

    async def decoder():
        return None

    async def activate():
        activated.append(True)

    async def prepare():
        activated.append("prepared")

    result = await run_with_avatar_fallback(
        primary_factory=primary,
        decoder_task=asyncio.create_task(decoder()),
        fallback_factory=primary,
        prepare_fallback=prepare,
        activate_fallback=activate,
        stop_requested=lambda: True,
    )

    assert result is None
    assert activated == []
