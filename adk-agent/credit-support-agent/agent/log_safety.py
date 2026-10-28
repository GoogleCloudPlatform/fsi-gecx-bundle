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

"""Bounded, non-sensitive summaries for voice workflow telemetry."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any


class CloudRunJsonFormatter(logging.Formatter):
    """Single-line JSON formatter so Cloud Run keeps multi-line tracebacks together."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            exc_text = record.exc_text or self.formatException(record.exc_info)
            if exc_text:
                message = f"{message}\n{exc_text}"
        if record.stack_info:
            stack_text = self.formatStack(record.stack_info)
            if stack_text:
                message = f"{message}\n{stack_text}"
        payload = {
            "severity": record.levelname,
            "logger": record.name,
            "message": message,
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_runtime_logging(level: int = logging.INFO) -> None:
    """Configure single-entry JSON logging on Cloud Run and plain text locally."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    handler = logging.StreamHandler()
    if os.getenv("K_SERVICE"):
        handler.setFormatter(CloudRunJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    root_logger.handlers = [handler]


EXPECTED_TOOL_CHECKPOINT_STATUSES = {
    "AUTHORIZATION_REQUIRED",
    "SESSION_CLOSE_CONFIRMATION_REQUIRED",
    "PLAYBOOK_DECISION_REQUIRED",
    "PROPOSAL_ALREADY_RESOLVED",
}


def stable_log_reference(value: Any, *, prefix: str = "ref") -> str | None:
    """Return a stable, non-reversible reference suitable for correlation logs."""
    if value in (None, ""):
        return None
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def banking_trace_reference(value: Any, *, prefix: str) -> str | None:
    """Match banking-service's salted, non-reversible trace reference."""
    if value in (None, ""):
        return None
    salt = os.getenv("LOG_REFERENCE_SALT", "fsi-gecx-log-reference")
    digest = hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:12]
    return f"{prefix}:{digest}"


def tool_args_log_summary(tool_name: str, args: dict | None) -> dict[str, Any]:
    args = args or {}
    summary: dict[str, Any] = {"keys": sorted(args.keys())}
    if "disputed_authorization_ids" in args:
        summary["disputed_authorization_count"] = len(
            args.get("disputed_authorization_ids") or []
        )
    if "disputed_transaction_ids" in args:
        summary["disputed_transaction_count"] = len(
            args.get("disputed_transaction_ids") or []
        )
    for key in ("issue_replacement", "escalate", "wallet_provider"):
        if key in args:
            summary[key] = args[key]
    if tool_name == "push_card_to_google_wallet":
        summary["trusted_card_token_present"] = bool(args.get("card_token"))
    return summary


def tool_result_log_summary(tool_response: Any) -> dict[str, Any]:
    if not isinstance(tool_response, dict):
        return {"response_type": type(tool_response).__name__}
    structured = tool_response.get("structuredContent")
    summary: dict[str, Any] = {
        "is_error": bool(tool_response.get("isError")),
        "status": tool_response.get("status"),
        "structured": isinstance(structured, dict),
    }
    if isinstance(structured, dict):
        summary.update(
            {
                "success": structured.get("success"),
                "outcome": structured.get("outcome"),
                "voided_authorization_count": len(
                    structured.get("voided_authorizations") or []
                ),
                "provisional_credit_count": len(
                    structured.get("provisional_credits") or []
                ),
                "replacement_card_issued": bool(
                    structured.get("replacement_card")
                ),
                "secure_message_sent": bool(structured.get("secure_message")),
                "wallet_provisioning_status": structured.get(
                    "wallet_provisioning_status"
                ),
            }
        )
    elif tool_response.get("error"):
        # MCP error strings are provider-controlled and can include request
        # values. Preserve only the failure signal in operational logs.
        summary["error_present"] = True
    return {key: value for key, value in summary.items() if value is not None}


def tool_response_succeeded(tool_name: str, tool_response: Any) -> bool:
    """Classify execution success without confusing an empty domain result."""
    if not isinstance(tool_response, dict):
        return False
    if tool_response.get("isError") is True or tool_response.get("error"):
        return False
    if tool_response.get("status") == "SUCCESS":
        return True
    if "success" in tool_response:
        return tool_response.get("success") is True
    structured = tool_response.get("structuredContent")
    if not isinstance(structured, dict):
        return False
    if structured.get("isError") is True or structured.get("error"):
        return False
    if tool_name == "get_open_fraud_alert" and "fraud_alert" in structured:
        # No alert is a valid read result and is the entry condition for the
        # customer-reported fraud workflow.
        return True
    if "success" in structured:
        return structured.get("success") is True
    return True


def tool_response_is_expected_checkpoint(tool_response: Any) -> bool:
    """Return whether a blocked local tool call is an expected control checkpoint."""
    return bool(
        isinstance(tool_response, dict)
        and tool_response.get("status") in EXPECTED_TOOL_CHECKPOINT_STATUSES
        and tool_response.get("isError") is not True
    )


# Transient banking failures the runtime retries; unrecovered, they remain a
# tool failure rather than a policy answer.
TRANSIENT_RECOVERY_CLASSES = {"RETRY_SAME_PROPOSAL"}


def tool_response_is_domain_refusal(tool_response: Any) -> bool:
    """Return whether banking refused the request as an expected domain outcome.

    A refusal is a structured ``success: false`` result that carries a bank
    ``recovery_class``. Transport errors, MCP ``isError`` results, and
    transient retry classes are not refusals.
    """
    if not isinstance(tool_response, dict):
        return False
    if tool_response.get("isError") is True:
        return False
    structured = tool_response.get("structuredContent")
    result = structured if isinstance(structured, dict) else tool_response
    if result.get("isError") is True or result.get("success") is not False:
        return False
    recovery_class = result.get("recovery_class")
    return (
        isinstance(recovery_class, str)
        and bool(recovery_class.strip())
        and recovery_class not in TRANSIENT_RECOVERY_CLASSES
    )


KNOWLEDGE_LOOKUP_MAX_CITE_KEYS = 5
KNOWLEDGE_LOOKUP_MAX_FIELD_CHARS = 128


def knowledge_lookup_summary(tool_response: Any) -> dict[str, Any]:
    """Project a search_knowledge result onto audit-safe corpus identifiers.

    Only corpus identifiers (snapshot and cite keys) and a bounded outcome are
    kept. Snippet text and the customer's query are never read.
    """
    if not isinstance(tool_response, dict) or tool_response.get("isError") is True:
        return _knowledge_summary("UNAVAILABLE")
    structured = tool_response.get("structuredContent")
    result = structured if isinstance(structured, dict) else tool_response
    if result.get("success") is not True:
        outcome = (
            "INVALID_QUERY" if result.get("error") == "INVALID_QUERY" else "UNAVAILABLE"
        )
        return _knowledge_summary(outcome)
    snippets = result.get("snippets")
    if not isinstance(snippets, list):
        return _knowledge_summary("UNAVAILABLE")
    cite_keys = [
        str(snippet.get("cite_key"))[:KNOWLEDGE_LOOKUP_MAX_FIELD_CHARS]
        for snippet in snippets[:KNOWLEDGE_LOOKUP_MAX_CITE_KEYS]
        if isinstance(snippet, dict) and snippet.get("cite_key")
    ]
    return _knowledge_summary(
        "MATCHED" if snippets else "NO_MATCH",
        snapshot_id=str(result.get("snapshot_id") or "")[
            :KNOWLEDGE_LOOKUP_MAX_FIELD_CHARS
        ]
        or None,
        cite_keys=cite_keys,
        result_count=len(snippets),
    )


def _knowledge_summary(
    outcome: str,
    *,
    snapshot_id: str | None = None,
    cite_keys: list[str] | None = None,
    result_count: int = 0,
) -> dict[str, Any]:
    return {
        "outcome": outcome,
        "snapshot_id": snapshot_id,
        "cite_keys": cite_keys or [],
        "result_count": result_count,
    }
