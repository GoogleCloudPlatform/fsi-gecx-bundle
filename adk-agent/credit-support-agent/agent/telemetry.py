"""Low-cardinality OpenTelemetry metrics for the voice runtime."""

from __future__ import annotations

import json
import sys
from opentelemetry import metrics


_meter = metrics.get_meter("credit-support-agent", "1.0")
_sessions_started = _meter.create_counter("voice.sessions.started")
_sessions_completed = _meter.create_counter("voice.sessions.completed")
_session_duration = _meter.create_histogram("voice.session.duration", unit="s")
_interruptions = _meter.create_counter("voice.session.interruptions")
_typed_turns = _meter.create_counter("voice.typed_turns")
_avatar_fallbacks = _meter.create_counter("voice.avatar.fallbacks")
_tool_calls = _meter.create_counter("voice.tool.calls")
_tool_duration = _meter.create_histogram("voice.tool.duration", unit="s")


def _emit_structured_metric(name: str, value: float, attributes: dict[str, str]) -> None:
    """Emit an exporter-independent Cloud Run structured-log metric event."""
    sys.stdout.write(
        json.dumps(
            {
                "severity": "INFO",
                "message": "voice_runtime_metric",
                "component": "credit-support-agent",
                "metric": name,
                "value": round(value, 6),
                "attributes": attributes,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    sys.stdout.flush()


def record_session_started(mode: str) -> None:
    attributes = {"mode": mode}
    _sessions_started.add(1, attributes)
    _emit_structured_metric("voice.sessions.started", 1, attributes)


def record_session_completed(mode: str, outcome: str, duration_seconds: float) -> None:
    attributes = {"mode": mode, "outcome": outcome}
    _sessions_completed.add(1, attributes)
    _session_duration.record(duration_seconds, attributes)
    _emit_structured_metric("voice.sessions.completed", 1, attributes)
    _emit_structured_metric("voice.session.duration", duration_seconds, attributes)


def record_interruption(mode: str) -> None:
    attributes = {"mode": mode}
    _interruptions.add(1, attributes)
    _emit_structured_metric("voice.session.interruptions", 1, attributes)


def record_typed_turn(mode: str, outcome: str) -> None:
    attributes = {"mode": mode, "outcome": outcome}
    _typed_turns.add(1, attributes)
    _emit_structured_metric("voice.typed_turns", 1, attributes)


def record_avatar_fallback(reason: str) -> None:
    attributes = {"reason": reason}
    _avatar_fallbacks.add(1, attributes)
    _emit_structured_metric("voice.avatar.fallbacks", 1, attributes)


def record_tool_completed(tool_name: str, outcome: str, duration_seconds: float) -> None:
    attributes = {"tool": tool_name, "outcome": outcome}
    _tool_calls.add(1, attributes)
    _tool_duration.record(max(0.0, duration_seconds), attributes)
    _emit_structured_metric("voice.tool.calls", 1, attributes)
    _emit_structured_metric("voice.tool.duration", max(0.0, duration_seconds), attributes)
