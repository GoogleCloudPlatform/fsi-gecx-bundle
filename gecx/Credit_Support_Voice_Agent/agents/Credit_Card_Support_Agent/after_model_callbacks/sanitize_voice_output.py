from __future__ import annotations

import re

# CES injects LlmResponse and Part into callback globals.
# ruff: noqa: F821


STANDALONE_PUNCTUATION = re.compile(r"(?m)^\s*[.,!?;:]+\s*$")


def after_model_callback(callback_context, llm_response):
    """Remove punctuation-only lines that voice synthesis would read aloud."""
    if llm_response.partial is True:
        return None
    content = llm_response.content
    parts = content.parts if content and content.parts else []
    values = [str(part.text_or_transcript() or "") for part in parts]
    output = " ".join(value for value in values if value)
    if not output or not STANDALONE_PUNCTUATION.search(output):
        return None

    cleaned = STANDALONE_PUNCTUATION.sub("", output)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        return None
    return LlmResponse.from_parts(parts=[Part.from_text(text=cleaned)])
