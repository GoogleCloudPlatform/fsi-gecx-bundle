#!/usr/bin/env python3
"""Local-only banking API and LiveKit fixture for voice UI browser checks."""

from __future__ import annotations

import argparse
import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api, rtc
import uvicorn


app = FastAPI(title="Voice UI fixture")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:4174", "http://localhost:4174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOM_NAME = "voice-ui-fixture"
LIVEKIT_URL = "ws://127.0.0.1:7880"
API_KEY = "devkey"
API_SECRET = "secret"
fixture_tasks: set[asyncio.Task] = set()
fixture_agent_tasks: dict[str, asyncio.Task] = {}
fixture_agent_rooms: dict[str, rtc.Room] = {}
fixture_human_tasks: dict[str, asyncio.Task] = {}
replacement_issued = False


def _token(identity: str, room_name: str = ROOM_NAME) -> str:
    return (
        api.AccessToken(API_KEY, API_SECRET)
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )


def _account() -> dict:
    cards = [
        {
            "card_id": "card-physical-8950",
            "card_token": "fixture-physical-token",
            "last_four": "8950",
            "status": "BLOCKED" if replacement_issued else "ACTIVE",
            "is_virtual": False,
            "cardholder_name": "Demo Customer",
            "exp_month": 7,
            "exp_year": 2029,
        }
    ]
    if replacement_issued:
        cards.append(
            {
                "card_id": "card-virtual-4337",
                "card_token": "fixture-virtual-token",
                "last_four": "4337",
                "status": "ACTIVE",
                "is_virtual": True,
                "cardholder_name": "Demo Customer",
                "exp_month": 7,
                "exp_year": 2029,
            }
        )
    return {
        "customer_id": "fixture-customer",
        "cardholder_name": "Demo Customer",
        "credit_limit_cents": 1_000_000,
        "available_credit_cents": 687_746,
        "cleared_balance_cents": 293_432,
        "cards": cards,
    }


TRANSACTIONS = [
    {
        "id": "fixture-txn-0001",
        "authorization_id": "fixture-auth-0001",
        "description": "GAME*TEST TOKEN ONLINE",
        "amount_cents": 499,
        "posted_at": "2026-07-14T12:00:00Z",
        "pending": True,
    },
    {
        "id": "fixture-txn-0002",
        "authorization_id": "fixture-auth-0002",
        "description": "APPLE.COM*ONLINE",
        "amount_cents": 149_900,
        "posted_at": "2026-07-14T12:01:00Z",
        "pending": True,
    },
]


async def _publish(room: rtc.Room, payload: dict, destination: str | None = None) -> None:
    await room.local_participant.publish_data(
        json.dumps(payload),
        reliable=True,
        destination_identities=[destination] if destination else [],
        topic="voice-support",
    )


async def _run_fixture_agent(room_name: str = ROOM_NAME, mode: str = "audio") -> None:
    global replacement_issued
    room = rtc.Room()

    @room.on("participant_connected")
    def participant_connected(participant: rtc.RemoteParticipant):
        async def greet() -> None:
            await _publish(room, {"type": "agent_mode", "mode": mode})
            await _publish(
                room,
                {
                    "type": "GUIDANCE_SNAPSHOT",
                    "source": "knowledge_catalog",
                    "topic_ids": ["fraud_golden_path"],
                    "content_version": "fixture",
                },
            )
            await _publish(
                room,
                {
                    "type": "FRAUD_ALERT_INSPECTED",
                    "status": "OPEN",
                    "suspicious_transactions_count": 2,
                },
            )
            await _publish(
                room,
                {
                    "type": "TRANSCRIPT",
                    "author": "agent",
                    "text": "I found two suspicious charges. Do you recognize them?",
                },
            )

        task = asyncio.create_task(greet())
        fixture_tasks.add(task)
        task.add_done_callback(fixture_tasks.discard)

    @room.on("data_received")
    def data_received(packet: rtc.DataPacket):
        async def respond() -> None:
            global replacement_issued
            payload = json.loads(packet.data.decode("utf-8"))
            if payload.get("type") != "CUSTOMER_TEXT_INPUT" or packet.participant is None:
                return
            destination = packet.participant.identity
            await _publish(
                room,
                {
                    "type": "CUSTOMER_TEXT_ACCEPTED",
                    "message_id": payload.get("message_id"),
                    "code": None,
                    "message": None,
                    "retryable": False,
                },
                destination,
            )
            await _publish(
                room,
                {"type": "TRANSCRIPT", "author": "user", "text": payload.get("text")},
            )
            replacement_issued = True
            await _publish(
                room,
                {
                    "type": "FRAUD_ALERT_RESOLVED",
                    "status": "RESOLVED",
                    "resolution": "CUSTOMER_DISPUTED",
                    "outcome": "PENDING_SPECIALIST_REVIEW",
                    "voided_authorizations": [{"authorization_id": "fixture-auth-0001"}],
                    "provisional_credits": [],
                    "replacement_card": {
                        "new_card_id": "card-virtual-4337",
                        "card_token": "fixture-virtual-token",
                        "new_last_four": "4337",
                        "status": "ACTIVE",
                        "is_virtual": True,
                        "cardholder_name": "Demo Customer",
                        "exp_month": 7,
                        "exp_year": 2029,
                    },
                    "secure_message": {"thread_id": "fixture-thread", "message_id": "fixture-message"},
                    "escalated": True,
                },
            )
            await _publish(
                room,
                {
                    "type": "TRANSCRIPT",
                    "author": "agent",
                    "text": "The card is blocked and your replacement virtual card is active.",
                },
            )

        task = asyncio.create_task(respond())
        fixture_tasks.add(task)
        task.add_done_callback(fixture_tasks.discard)

    await room.connect(
        LIVEKIT_URL,
        _token(f"agent-voice-ui-fixture-{room_name[-8:]}", room_name),
    )
    fixture_agent_rooms[room_name] = room
    try:
        await asyncio.Event().wait()
    finally:
        if fixture_agent_rooms.get(room_name) is room:
            fixture_agent_rooms.pop(room_name, None)
        await room.disconnect()


def _ensure_fixture_agent(room_name: str, mode: str = "audio") -> None:
    existing = fixture_agent_tasks.get(room_name)
    if existing is not None and not existing.done():
        return
    task = asyncio.create_task(_run_fixture_agent(room_name, mode))
    fixture_agent_tasks[room_name] = task

    def cleanup(completed: asyncio.Task) -> None:
        if fixture_agent_tasks.get(room_name) is completed:
            fixture_agent_tasks.pop(room_name, None)

    task.add_done_callback(cleanup)


async def _run_fixture_human(room_name: str) -> None:
    room = rtc.Room()
    await room.connect(
        LIVEKIT_URL,
        _token("agent-human-fixture@example.invalid", room_name),
    )
    try:
        await asyncio.Event().wait()
    finally:
        await room.disconnect()


def _ensure_fixture_human(room_name: str) -> None:
    existing = fixture_human_tasks.get(room_name)
    if existing is not None and not existing.done():
        return
    task = asyncio.create_task(_run_fixture_human(room_name))
    fixture_human_tasks[room_name] = task

    def cleanup(completed: asyncio.Task) -> None:
        if fixture_human_tasks.get(room_name) is completed:
            fixture_human_tasks.pop(room_name, None)

    task.add_done_callback(cleanup)


@app.get("/profile")
async def profile():
    return {
        "user_id": "fixture-customer",
        "email": "fixture@example.invalid",
        "first_name": "Demo",
        "last_name": "Customer",
    }


@app.post("/cxas/auth/token")
async def cxas_token():
    return {"token": "fixture-token"}


@app.get("/secure-messaging")
async def secure_messaging():
    return []


@app.get("/v1/accounts/summary")
async def accounts_summary():
    return {"accounts": []}


@app.get("/credit-card/account")
async def credit_card_account():
    return _account()


@app.get("/credit-card/transactions")
async def credit_card_transactions():
    return TRANSACTIONS


@app.get("/credit-card/voice/token")
async def voice_token(mode: str = "audio"):
    _ensure_fixture_agent(ROOM_NAME, mode)
    return {
        "token": _token("user-jane.doe@example.com"),
        "room_name": ROOM_NAME,
        "fraud_context": {
            "has_active_fraud_alert": True,
            "fraud_alert": {
                "fraud_alert_id": "fixture-alert",
                "card_id": "card-physical-8950",
                "card_last_four": "8950",
                "status": "OPEN",
                "suspicious_transactions": TRANSACTIONS,
            },
        },
    }


@app.post("/internal/comms/voice/start")
async def fixture_start(room_name: str, mode: str = "audio"):
    """Exercise the capacity probe transport without launching Gemini or MCP."""
    _ensure_fixture_agent(room_name, mode)
    return {"status": "LAUNCHED", "room_name": room_name, "mode": mode}


@app.post("/fixture/handoff")
async def fixture_handoff(room_name: str = ROOM_NAME):
    _ensure_fixture_human(room_name)
    return {"status": "HUMAN_JOINING", "room_name": room_name}


@app.post("/fixture/avatar-fallback")
async def fixture_avatar_fallback(room_name: str = ROOM_NAME):
    room = fixture_agent_rooms.get(room_name)
    if room is None:
        raise HTTPException(status_code=409, detail="Fixture agent is not connected")
    await _publish(room, {"type": "AVATAR_FALLBACK", "mode": "audio"})
    return {"status": "AUDIO_FALLBACK", "room_name": room_name}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
