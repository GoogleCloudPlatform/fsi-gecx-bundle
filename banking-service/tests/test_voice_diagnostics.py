from services.voice_diagnostics import ces_diagnostics


def test_only_safe_numeric_provider_metrics_are_forwarded():
    info = {"rootSpan": {"childSpans": [
        {"name": "LLM", "attributes": {"time to first chunk (ms)": 123, "prompt": "private"}},
        {"name": "Tool", "duration": "0.04s", "attributes": {"args": {"secret": "private"}}},
        {"name": "LLM", "attributes": {"time to first chunk (ms)": 98}},
    ]}}
    assert ces_diagnostics(info) == {"type": "VOICE_DIAGNOSTICS", "tool_ms": 40, "provider_first_chunk_ms": 98}


def test_missing_or_invalid_metrics_are_unavailable_not_zero():
    for info in [None, {}, {"rootSpan": {"name": "Tool", "duration": "nans"}},
                 {"rootSpan": {"name": "LLM", "attributes": {"time to first chunk (ms)": -1}}}]:
        assert ces_diagnostics(info) == {"type": "VOICE_DIAGNOSTICS", "tool_ms": None, "provider_first_chunk_ms": None}
