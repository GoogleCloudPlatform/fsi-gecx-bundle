#!/usr/bin/env python3
"""Bounded audio/avatar capacity probe for the credit-support agent.

Dry-run is the default. A live probe requires explicit confirmation and direct
LiveKit and agent-start credentials; it never discovers or prints secrets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import uuid

import httpx
import numpy as np
from livekit import api, rtc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.session_capacity import SessionCapacity  # noqa: E402


def capacity_matrix(max_units: int, audio_units: int, video_units: int) -> dict:
    return {
        "max_capacity_units": max_units,
        "audio_session_units": audio_units,
        "video_session_units": video_units,
        "audio_only_sessions": max_units // audio_units,
        "video_only_sessions": max_units // video_units,
        "mixed_examples": [
            {
                "video_sessions": videos,
                "remaining_audio_sessions": max(
                    0, (max_units - videos * video_units) // audio_units
                ),
            }
            for videos in range((max_units // video_units) + 1)
        ],
    }


def _token(api_key: str, api_secret: str, room_name: str, identity: str) -> str:
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )


async def _open_probe_session(args, index: int) -> dict:
    room_name = f"capacity-probe-{uuid.uuid4()}"
    customer_id = args.customer_id
    room = rtc.Room()
    agent_joined = asyncio.Event()

    @room.on("participant_connected")
    def participant_connected(participant: rtc.RemoteParticipant) -> None:
        if participant.identity.startswith("agent-voice-"):
            agent_joined.set()

    started = time.monotonic()
    try:
        await room.connect(
            args.livekit_url,
            _token(args.api_key, args.api_secret, room_name, f"user-{customer_id}"),
        )
        source = rtc.AudioSource(48000, 1)
        track = rtc.LocalAudioTrack.create_audio_track("capacity-probe", source)
        await room.local_participant.publish_track(track)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                args.agent_start_url,
                json={
                    "room_name": room_name,
                    "customer_id": customer_id,
                    "session_id": str(uuid.uuid4()),
                    "mode": args.mode,
                },
            )
        admission_latency_ms = round((time.monotonic() - started) * 1000, 2)
        if response.status_code != 200:
            return {
                "index": index,
                "success": False,
                "admitted": False,
                "agent_joined": False,
                "status_code": response.status_code,
                "admission_latency_ms": admission_latency_ms,
            }
        try:
            await asyncio.wait_for(agent_joined.wait(), timeout=args.join_timeout_seconds)
        except TimeoutError:
            return {
                "index": index,
                "success": False,
                "admitted": True,
                "agent_joined": False,
                "status_code": response.status_code,
                "admission_latency_ms": admission_latency_ms,
                "error_type": "AgentJoinTimeout",
            }
        samples = np.array(
            [int(600 * math.sin(2 * math.pi * 220 * n / 48000)) for n in range(480)],
            dtype=np.int16,
        ).tobytes()
        deadline = time.monotonic() + args.duration_seconds
        while time.monotonic() < deadline:
            await source.capture_frame(
                rtc.AudioFrame(
                    data=samples,
                    sample_rate=48000,
                    num_channels=1,
                    samples_per_channel=480,
                )
            )
            await asyncio.sleep(0.01)
        return {
            "index": index,
            "success": True,
            "admitted": True,
            "agent_joined": True,
            "status_code": response.status_code,
            "admission_latency_ms": admission_latency_ms,
            "observed_duration_seconds": round(time.monotonic() - started, 3),
        }
    except Exception as error:
        return {
            "index": index,
            "success": False,
            "admitted": False,
            "agent_joined": agent_joined.is_set(),
            "error_type": type(error).__name__,
            "observed_duration_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        await room.disconnect()


async def _run_live(args) -> list[dict]:
    if args.sessions > args.max_live_sessions:
        raise ValueError("Requested sessions exceed the explicit live-probe safety bound.")
    return await asyncio.gather(
        *(_open_probe_session(args, index) for index in range(args.sessions))
    )


def summarize_live_results(results: list[dict]) -> dict:
    latencies = sorted(
        float(item["admission_latency_ms"])
        for item in results
        if item.get("admission_latency_ms") is not None
    )
    p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
    return {
        "requested": len(results),
        "admitted": sum(bool(item.get("admitted")) for item in results),
        "agent_joined": sum(bool(item.get("agent_joined")) for item in results),
        "successful": sum(bool(item.get("success")) for item in results),
        "admission_latency_ms_median": (
            round(statistics.median(latencies), 2) if latencies else None
        ),
        "admission_latency_ms_p95": latencies[p95_index] if latencies else None,
        "errors": sorted(
            str(item["error_type"])
            for item in results
            if item.get("error_type")
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-units", type=int, default=4)
    parser.add_argument("--audio-units", type=int, default=1)
    parser.add_argument("--video-units", type=int, default=4)
    parser.add_argument("--confirm-live-load", action="store_true")
    parser.add_argument("--mode", choices=("audio", "video"), default="audio")
    parser.add_argument("--sessions", type=int, default=1)
    parser.add_argument("--max-live-sessions", type=int, default=4)
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--join-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--livekit-url", default=os.getenv("LIVEKIT_URL"))
    parser.add_argument("--api-key", default=os.getenv("LIVEKIT_API_KEY"))
    parser.add_argument("--api-secret", default=os.getenv("LIVEKIT_API_SECRET"))
    parser.add_argument("--agent-start-url")
    parser.add_argument(
        "--customer-id",
        help="Existing non-production test customer used by each live probe room.",
    )
    args = parser.parse_args()

    # Validate the same invariants used by the runtime even for a dry run.
    SessionCapacity(
        max_units=args.max_units,
        audio_units=args.audio_units,
        video_units=args.video_units,
    )
    output = {"capacity": capacity_matrix(args.max_units, args.audio_units, args.video_units)}
    if args.confirm_live_load:
        missing = [
            name
            for name in (
                "livekit_url",
                "api_key",
                "api_secret",
                "agent_start_url",
                "customer_id",
            )
            if not getattr(args, name)
        ]
        if missing:
            parser.error(f"live probe requires: {', '.join(missing)}")
        output["sessions"] = asyncio.run(_run_live(args))
        output["summary"] = summarize_live_results(output["sessions"])
    print(json.dumps(output, indent=2, sort_keys=True))
    return (
        0
        if not args.confirm_live_load
        or output["summary"]["successful"] == args.sessions
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
