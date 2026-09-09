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

"""Locale-only voice state; banking retains proposal and Money authority."""

from copy import deepcopy
from agent.proposal_evidence import COMMIT_IN_FLIGHT, COMMIT_RETRY, require_re_presentation
from agent.workflow_authorization import invalidate_workflow_authorization


def effective_voice_locale(requested: str, content: dict) -> str:
    if (requested == "es-MX" and content.get("review_status") == "APPROVED"
            and content.get("es-MX")):
        return "es-MX"
    return "en-US"


def select_banking_presentation(value, locale: str):
    """Select precomputed text, without translating or calculating Money."""
    if isinstance(value, list):
        return [select_banking_presentation(item, locale) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: select_banking_presentation(item, locale)
              for key, item in value.items() if key != "presentations"}
    if "presentations" in value:
        selected = value["presentations"].get(locale)
        if selected is None:
            raise ValueError("Banking presentation is unavailable in the selected language")
        result["presentation"] = deepcopy(selected)
    return result


def change_voice_language(state, requested_locale: str) -> dict:
    content = state.get("money_voice_content") or {}
    selected = effective_voice_locale(requested_locale, content)
    playbook = dict(state.get("fraud_playbook") or {})
    pending = playbook.get("pending_proposal") or {}
    if pending.get("evidence_state") in {COMMIT_IN_FLIGHT, COMMIT_RETRY}:
        return {"success": False, "effective_locale": state.get("voice_locale", "en-US"),
                "message": "Resolve the pending action result before changing language."}
    changed = selected != state.get("voice_locale", "en-US")
    fallback = selected != requested_locale
    if changed or fallback:
        if pending: playbook["pending_proposal"] = require_re_presentation(pending)
        if playbook.get("workflow_authorization"):
            playbook["workflow_authorization"] = invalidate_workflow_authorization(
                playbook["workflow_authorization"], reason="LANGUAGE_CHANGED")
        state["fraud_playbook"] = playbook
        state["voice_locale"] = selected
    copy = content.get(selected) or {}
    result = {"success": True, "effective_locale": selected, "fallback": fallback,
              "requires_fresh_confirmation": bool(pending and (changed or fallback)),
              "message": copy.get("fallback" if fallback else "language_changed") if changed or fallback else "Language unchanged.",
              "model_instruction": f"Continue in {selected}. Use banking speech_text exactly. Never translate amounts or infer currency. Present the complete proposal and wait for a later customer turn before committing."}
    cached = state.get("banking_proposal_presentation") or {}
    if pending and cached.get("proposal_id") == pending.get("proposal_id"):
        result["proposal"] = select_banking_presentation(cached, selected)
    return result


async def stream_with_language_changes(*, stream_factory, current_locale, restart):
    """Restart Live only after ADK has persisted a trusted locale state delta."""
    from contextlib import aclosing
    while True:
        selected = None
        async with aclosing(stream_factory()) as stream:
            async for event in stream:
                actions = getattr(event, "actions", None)
                delta = getattr(actions, "state_delta", None) or {}
                requested = delta.get("voice_locale")
                if requested in {"en-US", "es-MX"} and requested != current_locale():
                    selected = requested
                    break
                yield event
        if selected is None:
            return
        await restart(selected)
