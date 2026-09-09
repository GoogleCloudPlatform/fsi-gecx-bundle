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

"""Switch only session language; retain the banking proposal and require a new turn."""
import json


def set_conversation_language(locale: str) -> dict:
    """Switch session language only on an explicit customer request, never on language detection alone.

    Args:
        locale: The explicitly requested locale: en-US, es-MX, es-ES, es-US, fr-CA, fr-FR, de-DE, pt-BR.
    """
    if locale not in ("en-US", "es-MX", "es-ES", "es-US", "fr-CA", "fr-FR", "de-DE", "pt-BR"):
        return {"success": False, "error": "UNSUPPORTED_LANGUAGE"}
    variables = context.variables
    if variables.get("proposal_commit_attempted"):
        return {"success": False, "error": "COMMIT_RESULT_PENDING",
                "message": "Resolve the same pending commit before switching language."}
    invocation_id = str(context.invocation_id or "")
    if not invocation_id or not any(part.text_or_transcript() for part in context.get_last_user_input() or []):
        return {"success": False, "error": "CUSTOMER_TURN_REQUIRED"}
    try:
        facts = json.loads(variables.get("proposal_facts_json") or "{}")
        if not isinstance(facts, dict):
            raise ValueError("Invalid proposal context")
    except (ValueError, TypeError):
        return {"success": False, "error": "INVALID_PROPOSAL_CONTEXT"}
    summary = str(variables.get("proposal_customer_safe_summary") or "")
    if variables.get("proposal_id"):
        # The language request cannot authorize the existing proposal, even if
        # the customer also says yes in this same turn.
        variables["proposal_presentation_turn_id"] = invocation_id
        for key in ("proposal_confirmation_turn_id", "proposal_confirmation_method",
                    "proposal_confirmation_source", "proposal_decision_type"):
            variables[key] = ""
        variables["proposal_customer_safe_summary"] = summary
    variables["runtime_language_code"] = locale
    variables["language_code"] = locale.split("-")[0]
    variables["language_selection_source"] = "conversation"
    return {"success": True, "locale": locale,
            "requires_reconfirmation": bool(variables.get("proposal_id")),
            "customer_safe_summary": summary,
            "proposal_facts": facts,
            "instruction": "Continue in the selected language. If a proposal is pending, present it again and wait for a later customer confirmation. Do not commit in this turn."}
