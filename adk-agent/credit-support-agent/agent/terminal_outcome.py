"""Explicit terminal outcomes for voice-session operational telemetry."""

from enum import StrEnum


class TerminalOutcome(StrEnum):
    NORMAL_DISCONNECT = "NORMAL_DISCONNECT"
    HANDOFF = "HANDOFF"
    MODEL_FAILURE = "MODEL_FAILURE"
    MEDIA_FAILURE = "MEDIA_FAILURE"
    HARD_TIMEOUT = "HARD_TIMEOUT"
    CANCELLED = "CANCELLED"
