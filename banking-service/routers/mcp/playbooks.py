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

"""Generic model-facing discovery and proposal lifecycle entry points."""

import json
import logging
from typing import Literal
from fastmcp import Context
from . import mcp
from .utils import (
    requires_user_assertion,
    verified_customer_id_var,
    proposal_runtime_context_var,
)
from .credit_card import (
    _proposal_idempotency_key,
    _safe_protocol_failure,
    _is_proposal_id,
)
from services.action_proposals import ActionProposalService, ProposalError
from services.action_proposal_context import RuntimeContextError
from services.proposal_audit import (
    record_discovery,
    record_catalog_decision,
    record_rejection,
)
from services.playbook_discovery import discover_playbooks as discover_catalog
from services.voice_bidi import send_session_event
from utils.database import SessionLocal

logger = logging.getLogger(__name__)


async def _run(operation, *, audit_operation="PLAYBOOK_REQUEST", audit_request=None):
    context = proposal_runtime_context_var.get()
    if context is None:
        return {
            "success": False,
            "error": "TRUSTED_RUNTIME_CONTEXT_REQUIRED",
            "message": "Trusted runtime session context is required.",
        }
    db = SessionLocal()
    service = None
    identity = verified_customer_id_var.get()
    try:
        service = ActionProposalService(db)
        return await operation(service, identity, context)
    except Exception as exc:
        db.rollback()
        if not getattr(exc, "proposal_audit_recorded", False):
            if service is None:
                record_rejection(
                    db, identity, context, audit_operation, exc, audit_request or {}
                )
            else:
                service.record_request_rejection(
                    identity, context, audit_operation, exc, audit_request or {}
                )
        if isinstance(exc, (ProposalError, RuntimeContextError)):
            return _safe_protocol_failure(exc, fallback_error="PROPOSAL_REJECTED")
        if isinstance(exc, ValueError):
            return {
                "success": False,
                "error": "INVALID_PLAYBOOK_REQUEST",
                "message": "Use a published playbook revision and its declared business inputs. Discover again if needed.",
            }
        logger.error("Playbook request failed error_type=%s", type(exc).__name__)
        return {
            "success": False,
            "error": "PLAYBOOK_REQUEST_FAILED",
            "message": "The playbook request could not be completed.",
        }
    finally:
        db.close()


@mcp.tool()
@requires_user_assertion
async def discover_playbooks(customer_need: str, ctx: Context = None) -> dict:
    """Discover published actions for a customer's expressed need, including indirect requests.

    Use when deciding how to help or when a new concern emerges. Returns the small
    published catalog with intent, exclusions, prerequisites and input contracts.
    Compare meaning with trusted session context; no keyword matching is required.
    This tool does not prepare, authorize, execute, or establish eligibility.
    """

    async def run(service, identity, context):
        context.require_customer_turn()
        service._resolve_customer_id(identity)
        result = discover_catalog(service.registry, customer_need)
        return record_discovery(service, identity, context, result)

    return await _run(
        run, audit_operation="DISCOVER", audit_request={"customer_need": customer_need}
    )


@mcp.tool()
@requires_user_assertion
async def prepare_action_proposal(
    playbook_id: str,
    revision: int,
    digest: str,
    inputs_json: str,
    ctx: Context = None,
) -> dict:
    """Check eligibility and prepare a discovered playbook's immutable offer.

    Use the exact identity and input schema from discover_playbooks. Supply only
    business inputs as a JSON object serialized in inputs_json (use "{}" when empty).
    Authenticated customer and session context come from runtime.
    No preliminary permission is needed to prepare an offer for a clear need.
    Present the returned summary and wait for a later explicit confirmation.
    Preparation does not perform the proposed banking action.
    """

    async def run(service, identity, context):
        inputs = json.loads(inputs_json)
        payload = {
            "playbook_id": playbook_id,
            "revision": revision,
            "digest": digest,
            "inputs": inputs,
        }
        return service.prepare_playbook_for_identity(
            **payload,
            customer_identity=identity,
            runtime_context=context,
            idempotency_key=_proposal_idempotency_key(context, payload),
        )

    return await _run(
        run,
        audit_operation="PREPARE",
        audit_request={
            "playbook_id": playbook_id,
            "revision": revision,
            "digest": digest,
            "inputs_json": inputs_json,
        },
    )


@mcp.tool()
@requires_user_assertion
async def record_playbook_decision(
    discovery_id: str,
    decision: Literal["SELECT", "CLARIFY", "NO_ACTION"],
    reason_code: Literal[
        "APPLICABLE",
        "AMBIGUOUS_INTENT",
        "MISSING_INPUT",
        "UNCERTAIN_PREREQUISITE",
        "NO_MATCH",
        "UNSUPPORTED_REQUEST",
        "ALREADY_SATISFIED",
        "INFORMATION_ONLY",
    ],
    playbook_id: str = "",
    criterion_index: int = -1,
    ctx: Context = None,
) -> dict:
    """Record a bounded catalog decision before acting, clarifying or choosing no action.

    Use the discovery_id returned by discover_playbooks. SELECT uses APPLICABLE
    and a playbook when_to_use criterion index (zero-based). CLARIFY reasons:
    AMBIGUOUS_INTENT, MISSING_INPUT, UNCERTAIN_PREREQUISITE. NO_ACTION reasons:
    NO_MATCH, UNSUPPORTED_REQUEST, ALREADY_SATISFIED, INFORMATION_ONLY.
    When naming a playbook, supply the zero-based criterion_index in prerequisites
    for CLARIFY or when_not_to_use for NO_ACTION. Banking derives the field from
    the decision. With no particular playbook omit playbook_id
    and leave criterion_index=-1. Do not submit customer text or private reasoning.
    This records a model-declared decision; it neither checks eligibility nor
    prepares or authorizes a banking action.
    """
    request = dict(
        discovery_id=discovery_id,
        decision=decision,
        reason_code=reason_code,
        playbook_id=playbook_id,
        criterion_index=criterion_index,
    )

    async def run(service, identity, context):
        return record_catalog_decision(service, identity, context, **request)

    return await _run(run, audit_operation="CATALOG_DECISION", audit_request=request)


async def _publish_committed_event(identity, result):
    # Domain result projections are independent of catalog IDs/tool names.
    if result.get("fraud_alert"):
        event = {
            "type": "FRAUD_CASE_TRIAGED",
            **{
                key: result.get(key)
                for key in (
                    "outcome",
                    "fraud_alert",
                    "voided_authorizations",
                    "provisional_credits",
                    "replacement_card",
                    "secure_message",
                    "escalated",
                )
            },
        }
    elif result.get("replacement_card"):
        replacement = result["replacement_card"]
        event = {
            "type": "CARD_REPLACED",
            **{
                key: replacement.get(key)
                for key in (
                    "old_card_id",
                    "new_card_id",
                    "new_last_four",
                    "replacement_status",
                    "is_virtual",
                )
            },
        }
    elif result.get("wallet_provisioning_status"):
        event = {
            "type": "WALLET_PROVISIONING_QUEUED",
            **{
                key: result.get(key)
                for key in (
                    "card_token",
                    "wallet_provider",
                    "wallet_provisioning_status",
                )
            },
        }
    else:
        return
    event["proposal_id"] = result["proposal_id"]
    try:
        await send_session_event(f"session-{identity}", event)
    except Exception as exc:
        logger.warning(
            "Committed proposal UI event failed error_type=%s", type(exc).__name__
        )


@mcp.tool()
@requires_user_assertion
async def commit_action_proposal(proposal_id: str, ctx: Context = None) -> dict:
    """Commit the presented proposal only after explicit confirmation in a later customer turn.

    Use only the opaque proposal ID returned by preparation. Questions or uncertain
    responses do not authorize commit. Never change inputs while committing.
    """

    async def run(service, identity, context):
        if not _is_proposal_id(proposal_id):
            raise ProposalError("Invalid proposal ID.", code="INVALID_PROPOSAL_ID")
        result = service.commit_action_for_identity(
            proposal_id, customer_identity=identity, runtime_context=context
        )
        if result.get("success"):
            await _publish_committed_event(identity, result)
        return result

    return await _run(
        run, audit_operation="COMMIT", audit_request={"proposal_id": proposal_id}
    )
