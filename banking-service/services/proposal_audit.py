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

"""Versioned, minimal evidence for governed proposal actions.

Audit metadata contains identifiers, hashes and bounded policy fields. Separate
allowlisted evidence snapshots preserve reconstruction facts without credentials,
free-form model reasoning or conversation text.
"""

import hashlib
import json
import uuid
from functools import wraps
from inspect import signature

from models.audit import AuditOutbox
from services.proposal_evidence import (
    archive,
    artifact_id_for,
    definition_snapshot,
    transition_snapshot,
)
from utils.audit import record_audit_event
from utils.log_safety import stable_log_reference
from utils.version import BUILD_VERSION, BUILD_COMMIT_ID

SCHEMA_VERSION = 2
CONTRACT = "proposal-audit.v2"


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def context_fields(context):
    return {
        "support_session_ref": stable_log_reference(
            context.support_session_id, "session"
        ),
        "runtime_name": context.runtime_name,
        "runtime_session_ref": stable_log_reference(
            context.runtime_session_id, "runtime-session"
        ),
        "customer_turn_ref": stable_log_reference(context.customer_turn_id, "turn"),
        "reset_generation_ref": stable_log_reference(context.reset_generation, "reset"),
        "catalog_snapshot_ref": stable_log_reference(
            context.catalog_snapshot_id, "catalog"
        )
        if context.catalog_snapshot_id
        else None,
    }


def definition_fields(spec):
    handler_definition = getattr(spec.handler, "_definition", {})
    return {
        "id": spec.definition_id,
        "revision": spec.definition_revision,
        "digest": spec.definition_digest,
        "action_type": spec.action_type,
        "contract_version": spec.contract_version,
        "operation": handler_definition.get("operation"),
        "authorization_policy": handler_definition.get("authorization_policy"),
    }


def emit(
    db,
    event_type,
    payload,
    *,
    recorder=record_audit_event,
    event_id=None,
    snapshot=None,
):
    event_id = event_id or str(uuid.uuid4())
    artifact = (
        archive(db, event_id, snapshot, recorder=recorder)
        if snapshot is not None
        else None
    )
    recorder(
        db,
        event_type,
        {
            "audit_contract": CONTRACT,
            "banking_build": {"version": BUILD_VERSION, "commit": BUILD_COMMIT_ID},
            **payload,
            **({"evidence_artifact": artifact} if artifact else {}),
        },
        schema_version=SCHEMA_VERSION,
        event_id=event_id,
    )
    return event_id


def record_transition(
    db, proposal, spec, stage, *, recorder=record_audit_event, reason=None
):
    evidence = proposal.confirmation_evidence or {}
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{CONTRACT}:{proposal.id}:{stage}"))
    # A replay/reconciliation must not append another transition for a state
    # already recorded. The row is locked by the lifecycle caller.
    if (
        db.query(AuditOutbox)
        .filter(AuditOutbox.event_id.in_([event_id, artifact_id_for(event_id)]))
        .first()
        is not None
    ):
        return event_id
    policy = spec.authorization_policy
    return emit(
        db,
        "ACTION_PROPOSAL_" + stage,
        {
            "proposal_ref": stable_log_reference(proposal.id, "proposal"),
            "proposal_id": str(proposal.id),
            "correlation_id": str(proposal.id),
            "action_type": proposal.action_type,
            "contract_version": proposal.contract_version,
            "definition": definition_fields(spec),
            "customer_ref": stable_log_reference(proposal.customer_id, "customer"),
            "account_ref": stable_log_reference(proposal.account_id, "account")
            if proposal.account_id
            else None,
            "support_session_ref": stable_log_reference(
                proposal.support_session_id, "session"
            ),
            "runtime_name": proposal.runtime_name,
            "runtime_session_ref": stable_log_reference(
                proposal.runtime_session_id, "runtime-session"
            ),
            "reset_generation_ref": stable_log_reference(
                proposal.reset_generation, "reset"
            ),
            "originating_turn_ref": stable_log_reference(
                proposal.originating_customer_turn_id, "turn"
            ),
            "catalog_snapshot_ref": stable_log_reference(
                proposal.catalog_snapshot_id, "catalog"
            )
            if proposal.catalog_snapshot_id
            else None,
            "payload_fingerprint": proposal.payload_fingerprint,
            "presentation_fingerprint": fingerprint(proposal.customer_safe_summary),
            "result_fingerprint": fingerprint(proposal.result_payload)
            if proposal.result_payload is not None
            else None,
            "state": proposal.status,
            "reason_code": reason or proposal.invalidation_reason,
            "result_success": (proposal.result_payload or {}).get("success")
            if type((proposal.result_payload or {}).get("success")) is bool
            else None,
            "banking_outcome": next(
                (
                    value
                    for value in [
                        (proposal.result_payload or {}).get("outcome"),
                        (proposal.result_payload or {}).get(
                            "wallet_provisioning_status"
                        ),
                        (proposal.result_payload or {}).get("status"),
                    ]
                    if isinstance(value, str)
                    and len(value) <= 64
                    and value[:1].isascii()
                    and value[:1].isalpha()
                    and value[:1].isupper()
                    and all(
                        c.isascii() and (c.isupper() or c.isdigit() or c == "_")
                        for c in value
                    )
                ),
                None,
            ),
            "policy": {
                "name": policy.name,
                "risk_tier": policy.risk_tier.name,
                "presentation": policy.presentation_policy.value,
                "decision": policy.decision_policy.value,
                "required_fact_keys": sorted(
                    spec.presentation_requirement.required_fact_keys
                ),
                "presentation_quality_gate": spec.presentation_requirement.quality_gate.value,
            },
            "evidence": {
                "presentation_turn_ref": stable_log_reference(
                    proposal.presented_assistant_turn_id, "turn"
                )
                if proposal.presented_assistant_turn_id
                else None,
                "decision_turn_ref": stable_log_reference(
                    proposal.confirmation_customer_turn_id, "turn"
                )
                if proposal.confirmation_customer_turn_id
                else None,
                "source": evidence.get("source"),
                "method": evidence.get("method"),
                "fingerprint": fingerprint(evidence) if evidence else None,
            },
        },
        recorder=recorder,
        event_id=event_id,
        snapshot=transition_snapshot(proposal, spec, stage, reason),
    )


def audited_request(operation):
    """Preserve failed authenticated requests after rolling back their mutations.

    The caller owns a dedicated proposal session. Audit failure is surfaced rather
    than silently allowing an unaudited operation. Successes remain atomic with
    lifecycle events; rejection events are committed in a new transaction.
    """

    def decorate(method):
        binding = signature(method)

        @wraps(method)
        def wrapped(self, *args, **kwargs):
            values = binding.bind(self, *args, **kwargs).arguments
            context = values.get("runtime_context") or values.get("context")
            identity = values.get("customer_identity") or values.get("identity")
            try:
                return method(self, *args, **kwargs)
            except Exception as exc:
                self.db.rollback()
                if context is not None and identity:
                    self.record_request_rejection(
                        identity,
                        context,
                        operation,
                        exc,
                        {
                            key: value
                            for key, value in values.items()
                            if key
                            not in {
                                "self",
                                "runtime_context",
                                "context",
                                "customer_identity",
                                "identity",
                            }
                        },
                    )
                    exc.proposal_audit_recorded = True
                raise

        return wrapped

    return decorate


def record_rejection(
    db, identity, context, operation, exc, request, *, customer_id=None
):
    from dataclasses import replace
    from services.proposal_lifecycle import ProposalPolicyError, ActionPreconditionError
    from services.proposal_evidence import policy_evaluation_snapshot
    from services.proposal_protocol import PolicyEvaluationEvidence

    snapshot = None
    evaluation = exc.policy_evidence if isinstance(exc, (ProposalPolicyError, ActionPreconditionError)) else None
    if isinstance(evaluation, PolicyEvaluationEvidence) and customer_id:
        if isinstance(exc, ActionPreconditionError) and exc.proposal is not None:
            proposal = exc.proposal
            if (str(proposal.customer_id) == str(customer_id)
                and proposal.support_session_id == context.support_session_id
                and proposal.runtime_session_id == context.runtime_session_id
                and proposal.runtime_name == context.runtime_name):
                # The caller pinned this proposal after authenticated scope validation.
                from services.proposal_definitions import load_action_registry
                spec = load_action_registry(db).for_proposal(proposal)
                evaluation = replace(evaluation, definition=definition_snapshot(spec))
        if evaluation.definition is not None:
            snapshot = policy_evaluation_snapshot(evaluation)
    # Never resolve an attempted proposal ID: it may belong to another customer.
    emit(
        db,
        "ACTION_PROPOSAL_REQUEST_REJECTED"
        if isinstance(exc, ValueError)
        else "ACTION_PROPOSAL_REQUEST_FAILED",
        {
            **context_fields(context),
            "customer_ref": stable_log_reference(customer_id, "customer")
            if customer_id
            else None,
            "identity_ref": stable_log_reference(identity, "identity"),
            "operation": operation,
            "reason_code": getattr(exc, "code", None)
            or (
                "INVALID_REQUEST" if isinstance(exc, ValueError) else "INTERNAL_FAILURE"
            ),
            "request_fingerprint": fingerprint(request),
            "attempted_proposal_ref": stable_log_reference(
                request.get("proposal_id"), "proposal"
            )
            if request.get("proposal_id")
            else None,
            "evidence_validated": None,
            "outcome_certainty": "REJECTED_REQUEST"
            if isinstance(exc, ValueError)
            else "UNKNOWN",
        },
        snapshot=snapshot,
    )
    db.commit()


def resolve_discovery(db, discovery_id, customer_id, context):
    row = (
        db.query(AuditOutbox)
        .filter_by(event_id=discovery_id, event_type="PLAYBOOK_DISCOVERED")
        .one_or_none()
    )
    if row is None:
        raise ValueError("Discover playbooks before recording a catalog decision.")
    data = json.loads(row.payload)
    expected = context_fields(context)
    # A discovery can inform a later clarification turn, but never another
    # customer, runtime session, reset generation or support session.
    if data.get("customer_ref") != stable_log_reference(customer_id, "customer") or any(
        data.get(key) != expected[key]
        for key in (
            "support_session_ref",
            "runtime_name",
            "runtime_session_ref",
            "reset_generation_ref",
        )
    ):
        raise ValueError("Discovery does not belong to this trusted session.")
    return data


DECISION_REASONS = {
    "SELECT": {"APPLICABLE"},
    "CLARIFY": {"AMBIGUOUS_INTENT", "MISSING_INPUT", "UNCERTAIN_PREREQUISITE"},
    "NO_ACTION": {
        "NO_MATCH",
        "UNSUPPORTED_REQUEST",
        "ALREADY_SATISFIED",
        "INFORMATION_ONLY",
    },
}


def record_discovery(service, identity, context, result):
    context.require_customer_turn()
    customer_id = service._resolve_customer_id(identity)
    catalog = [
        {"id": p["playbook_id"], "revision": p["revision"], "digest": p["digest"]}
        for p in result["playbooks"]
    ]
    event_id = emit(
        service.db,
        "PLAYBOOK_DISCOVERED",
        {
            **context_fields(context),
            "customer_ref": stable_log_reference(customer_id, "customer"),
            "need_fingerprint": fingerprint(result["customer_need"]),
            "retrieval_mode": result["retrieval_mode"],
            "catalog": catalog,
            "catalog_fingerprint": fingerprint(catalog),
            "eligibility": "NOT_CHECKED",
        },
        snapshot={
            "kind": "PLAYBOOK_CATALOG",
            "catalog": [
                definition_snapshot(
                    service.registry.resolve(p["id"], p["revision"], p["digest"])
                )
                for p in catalog
            ],
        },
    )
    service.db.commit()
    return {**result, "discovery_id": event_id}


def record_catalog_decision(
    service,
    identity,
    context,
    *,
    discovery_id,
    decision,
    reason_code,
    playbook_id="",
    criterion_index=-1,
):
    context.require_customer_turn()
    customer_id = service._resolve_customer_id(identity)
    if reason_code not in DECISION_REASONS.get(decision, set()):
        raise ValueError("Use a supported decision and reason code.")
    discovery = resolve_discovery(service.db, discovery_id, customer_id, context)
    selected = None
    reference = None
    if playbook_id:
        candidate = next(
            (p for p in discovery["catalog"] if p["id"] == playbook_id), None
        )
        if candidate is None:
            raise ValueError("Choose only from the discovered catalog.")
        spec = service.registry.resolve(
            candidate["id"], candidate["revision"], candidate["digest"]
        )
        fields = {
            "SELECT": "when_to_use",
            "CLARIFY": "prerequisites",
            "NO_ACTION": "when_not_to_use",
        }
        criterion = fields[decision]
        metadata = spec.handler.discovery_view()
        if type(criterion_index) is not int or not 0 <= criterion_index < len(
            metadata[criterion]
        ):
            raise ValueError("Reference the published criterion for this decision.")
        selected = definition_fields(spec)
        reference = {
            "field": criterion,
            "index": criterion_index,
            "fingerprint": fingerprint(metadata[criterion][criterion_index]),
        }
    elif decision == "SELECT" or criterion_index != -1:
        raise ValueError("A selection requires a discovered playbook and criterion.")
    event_id = emit(
        service.db,
        "PLAYBOOK_DECISION_RECORDED",
        {
            **context_fields(context),
            "customer_ref": stable_log_reference(customer_id, "customer"),
            "discovery_id": discovery_id,
            "catalog_fingerprint": discovery["catalog_fingerprint"],
            "decision": decision,
            "reason_code": reason_code,
            "definition": selected,
            "criterion": reference,
            "claim_source": "MODEL_TOOL_SELECTION",
            "eligibility": "NOT_CHECKED",
            "authorizes_execution": False,
        },
        snapshot={
            "kind": "PLAYBOOK_DECISION",
            "discovery_id": discovery_id,
            "discovery_artifact": discovery["evidence_artifact"],
            "decision": decision,
            "reason_code": reason_code,
            "definition": definition_snapshot(spec) if selected else None,
            "criterion": {**reference, "text": metadata[criterion][criterion_index]}
            if reference
            else None,
            "authorizes_execution": False,
        },
    )
    service.db.commit()
    return {
        "success": True,
        "decision": decision,
        "audit_event_id": event_id,
        "authorizes_execution": False,
    }
