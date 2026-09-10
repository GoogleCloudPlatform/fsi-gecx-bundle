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

from agent.proposal_evidence import COMMIT_IN_FLIGHT, COMMIT_RETRY, require_re_presentation
from agent.workflow_authorization import invalidate_workflow_authorization


SUPPORTED_SUPPORT_LOCALES = ("en-US", "es-MX", "es-ES", "es-US", "fr-CA", "fr-FR", "de-DE", "pt-BR", "it-IT")
# Live documents a smaller regional inventory than CES. Preserve the customer
# locale in state/instructions and map only the speech configuration code.
LIVE_LANGUAGE_CODES = {locale: locale for locale in SUPPORTED_SUPPORT_LOCALES}
LIVE_LANGUAGE_CODES.update({"fr-CA": "fr-FR", "es-MX": "es-US", "es-ES": "es-US"})


def effective_voice_locale(requested: str) -> str:
    return requested if requested in SUPPORTED_SUPPORT_LOCALES else "en-US"


MONEY_LANGUAGE_INSTRUCTION = (
    "Explain banking facts naturally in the selected language. Use concise amounts "
    "such as 'twelve ninety-nine' or 'doce con noventa y nueve' when USD is established. "
    "Use decimal notation in text. Make the currency explicit when ambiguous, when it "
    "changes, or when original and billing currencies differ. Preserve every amount, "
    "currency, merchant, and action consequence. Never perform FX or recalculate amounts. "
    "Reference summaries are facts to explain, not scripts to recite."
)


def select_banking_presentation(value, locale: str):
    """Expose exact display facts and discard legacy scripted speech without mutation."""
    if isinstance(value, list):
        return [select_banking_presentation(item, locale) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: select_banking_presentation(item, locale)
              for key, item in value.items() if key not in {"presentations", "speech_text"}}
    presentations = value.get("presentations") or {}
    selected = presentations.get(locale) or presentations.get("en-US")
    if selected:
        result["presentation"] = select_banking_presentation(selected, locale)
    return result


def change_voice_language(state, requested_locale: str, *, runtime_unavailable=False) -> dict:
    if requested_locale not in SUPPORTED_SUPPORT_LOCALES:
        return {"success": False, "error": "UNSUPPORTED_LANGUAGE",
                "effective_locale": state.get("voice_locale", "en-US")}
    selected = "en-US" if runtime_unavailable else effective_voice_locale(requested_locale)
    playbook = dict(state.get("fraud_playbook") or {})
    pending = playbook.get("pending_proposal") or {}
    if pending.get("evidence_state") in {COMMIT_IN_FLIGHT, COMMIT_RETRY}:
        return {"success": False, "effective_locale": state.get("voice_locale", "en-US"),
                "message": "Resolve the pending action result before changing language."}
    cached = state.get("banking_proposal_presentation") or {}
    selected_proposal = None
    if pending and cached.get("proposal_id") == pending.get("proposal_id"):
        selected_proposal = select_banking_presentation(cached, selected)
    changed = selected != state.get("voice_locale", "en-US")
    fallback = selected != requested_locale
    if changed or fallback:
        if pending: playbook["pending_proposal"] = require_re_presentation(pending)
        if playbook.get("workflow_authorization"):
            playbook["workflow_authorization"] = invalidate_workflow_authorization(
                playbook["workflow_authorization"], reason="LANGUAGE_CHANGED")
        state["fraud_playbook"] = playbook
        state["voice_locale"] = selected
    result = {"success": True, "effective_locale": selected, "fallback": fallback,
              "requires_fresh_confirmation": bool(pending and (changed or fallback)),
              "message": ("The selected language is unavailable. Explain the switch to English." if fallback else "Language changed." if changed else "Language unchanged."),
              "model_instruction": f"Continue in {selected}. {MONEY_LANGUAGE_INSTRUCTION} Explain the complete proposal and wait for a later customer turn before committing."}
    if selected_proposal is not None:
        result["proposal"] = selected_proposal
    return result


def is_language_runtime_rejection(error: Exception) -> bool:
    """Only explicit language-support errors warrant changing locale."""
    message = str(error).lower()
    return (any(term in message for term in ("language", *[locale.lower() for locale in SUPPORTED_SUPPORT_LOCALES]))
            and any(term in message for term in ("unsupported", "not supported", "unavailable")))


async def stream_with_language_changes(*, stream_factory, current_locale, restart,
                                       runtime_fallback=None):
    """Restart Live only after ADK has persisted a trusted locale state delta."""
    from contextlib import aclosing
    while True:
        selected = None
        try:
            async with aclosing(stream_factory()) as stream:
                async for event in stream:
                    actions = getattr(event, "actions", None)
                    delta = getattr(actions, "state_delta", None) or {}
                    requested = delta.get("voice_locale")
                    if requested in SUPPORTED_SUPPORT_LOCALES and requested != current_locale():
                        selected = requested
                        break
                    yield event
        except Exception as error:
            if (current_locale() == "en-US" or runtime_fallback is None
                    or not is_language_runtime_rejection(error)
                    or not await runtime_fallback()):
                raise
            selected = "en-US"
        if selected is None:
            return
        await restart(selected)
