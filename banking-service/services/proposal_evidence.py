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

"""Self-contained, allowlisted evidence transported separately from audit metadata.

Snapshots are canonical JSON strings: their exact bytes, rather than a query
engine's JSON serialization, define the digest. Unknown fields never propagate.
"""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import uuid

CONTRACT = "proposal-evidence.v1"
EVENT_TYPE = "PROPOSAL_EVIDENCE_SNAPSHOT"

MONEY = {"amount_minor": None, "currency_code": None}
FACT = {
    key: None
    for key in (
        "authorization_id",
        "transaction_id",
        "merchant_name",
        "merchant_category_code",
        "card_network",
        "created_at",
        "pending",
        "source",
    )
} | {"money": MONEY, "billing_money": MONEY}
CARD = {
    key: None
    for key in (
        "account_id",
        "old_card_id",
        "new_card_id",
        "new_last_four",
        "status",
        "replacement_status",
        "is_virtual",
        "fraud_alert_id",
        "compromised_card_id",
    )
}
REMEDIATION = {
    key: None
    for key in (
        "success",
        "account_id",
        "authorization_id",
        "transaction_id",
        "fraud_alert_id",
        "status",
        "authorization_status",
        "ledger_entry_id",
        "provisional_credit_id",
        "provisional_credit_transaction_id",
        "journal_transaction_id",
    )
} | {
    key: MONEY
    for key in (
        "voided_amount",
        "credited_amount",
        "available_credit",
        "cleared_balance",
    )
}
RESULT = {
    key: None
    for key in (
        "success",
        "outcome",
        "status",
        "card_status",
        "wallet_provider",
        "wallet_provisioning_status",
        "account_id",
        "fraud_alert_id",
        "escalated",
    )
} | {
    "replacement_card": CARD,
    "fraud_alert": {
        key: None for key in ("id", "fraud_alert_id", "status", "remediation_status")
    },
    "voided_authorizations": [REMEDIATION],
    "provisional_credits": [REMEDIATION],
    "secure_message": {"thread_id": None, "message_id": None},
}
PAYLOAD = {
    key: None
    for key in (
        "account_id",
        "card_id",
        "compromised_card_id",
        "card_last_four",
        "reason",
        "wallet_provider",
        "fraud_alert_id",
        "issue_replacement",
        "issue_virtual_card",
        "escalate",
    )
} | {
    "disputed_authorization_ids": [None],
    "disputed_transaction_ids": [None],
    "money_facts": [FACT],
}
EVIDENCE = {
    key: None
    for key in (
        "method",
        "source",
        "runtime_name",
        "runtime_session_id",
        "presentation_turn_id",
        "confirmation_turn_id",
        "presentation_acknowledgment",
        "presentation_acknowledgment_source",
        "presentation_artifact_id",
    )
} | {"acknowledged_fact_keys": [None]}


LIMIT_POLICY = {key: None for key in (
    "id", "revision", "digest", "currency_code", "maximum_current_limit_multiple",
    "maximum_minor", "requires_active_account", "requires_active_product",
    "requires_strict_increase", "requires_product_bounds", "approval_semantics",
)}
LIMIT_FACTS = {key: None for key in (
    "account_id", "account_status", "currency_code", "product_code",
    "current_limit_minor", "product_active", "minimum_limit_minor", "maximum_limit_minor",
    "available_credit_minor", "projected_available_credit_minor",
)}
DECISION_POLICY = {key: None for key in ("provider_id", "policy_id", "version", "digest", "approval_ttl_seconds")}
BANK_DECISION = {key: None for key in ("decision_id", "provider_id", "outcome", "evaluated_at", "expires_at", "request_ref", "scope_ref", "input_ref")} | {
    "approved_limit": MONEY, "reason_codes": [None], "policy": DECISION_POLICY, "evidence_references": [None],
}
DECISION_REQUEST = {"request_ref": None, "scope_ref": None, "input_ref": None, "requested_limit": MONEY, "facts": LIMIT_FACTS}
PAYLOAD.update({
    "bank_decision": BANK_DECISION, "decision_request": DECISION_REQUEST,
    "current_limit": MONEY, "proposed_limit": MONEY, "increase_amount": MONEY,
    "credit_limit_policy": LIMIT_POLICY, "eligibility_facts": LIMIT_FACTS,
    "approval_semantics": None,
    "prepared_arithmetic": {"available_credit_minor": None, "projected_available_credit_minor": None},
})
RESULT.update({
    "previous_credit_limit": MONEY, "credit_limit": MONEY,
    "increase_amount": MONEY, "available_credit": MONEY, "approval_semantics": None,
})


def policy_evaluation_snapshot(evaluation):
    return {
        "kind": "BANK_DECISION" if evaluation.bank_decision or evaluation.decision_failure else "POLICY_EVALUATION",
        "decision": (evaluation.bank_decision or {}).get("outcome", "REFUSED"),
        "bank_decision": project(evaluation.bank_decision, BANK_DECISION),
        "decision_failure": evaluation.decision_failure,
        "decision_policy": project(evaluation.decision_policy, DECISION_POLICY),
        "decision_request": project(evaluation.decision_request, DECISION_REQUEST),
        "reason_code": evaluation.reason_code,
        "definition": deepcopy(evaluation.definition),
        "credit_limit_policy": project(evaluation.policy, LIMIT_POLICY),
        "requested_limit": project(evaluation.requested_limit, MONEY),
        "evaluated_facts": project(evaluation.facts, LIMIT_FACTS),
        "approved_facts": project(evaluation.approved_facts, LIMIT_FACTS),
    }


def project(value, schema):
    """Copy only explicit structural fields; reject malformed archive facts."""
    if value is None:
        return None
    if schema is None:
        if type(value) not in (str, int, float, bool):
            raise ValueError("Evidence facts must be scalar values.")
        return value
    if isinstance(schema, list):
        if not isinstance(value, list):
            raise ValueError("Evidence facts must be a list.")
        return [project(item, schema[0]) for item in value]
    if not isinstance(value, dict):
        raise ValueError("Evidence facts must be an object.")
    return {
        key: project(value[key], child) for key, child in schema.items() if key in value
    }


def policy_snapshot(spec):
    policy = asdict(spec.authorization_policy)
    # Enum members and sets need stable wire forms independent of Python repr.
    policy["risk_tier"] = spec.authorization_policy.risk_tier.name
    evidence = policy["evidence_policy"]
    for key in ("accepted_sources", "accepted_presentation_acknowledgment_sources"):
        evidence[key] = sorted(evidence[key])
    presentation = asdict(spec.presentation_requirement)
    presentation["required_fact_keys"] = sorted(presentation["required_fact_keys"])
    return {"authorization": policy, "presentation": presentation}


def definition_snapshot(spec):
    document = getattr(spec.handler, "_definition", None)
    if document is None:
        # Generic kernel specifications have no declarative document.
        return {
            "id": spec.definition_id,
            "revision": spec.definition_revision,
            "digest": spec.definition_digest,
            "action_type": spec.action_type,
            "contract_version": spec.contract_version,
        }
    return deepcopy(document)


def transition_snapshot(proposal, spec, stage, reason=None):
    return {
        "kind": "PROPOSAL_TRANSITION",
        "stage": stage,
        "proposal_id": str(proposal.id),
        "state": proposal.status,
        "reason_code": reason or proposal.invalidation_reason,
        "definition": definition_snapshot(spec),
        "policy": policy_snapshot(spec),
        "scope": {
            "customer_id": str(proposal.customer_id),
            "account_id": str(proposal.account_id) if proposal.account_id else None,
            "support_session_id": proposal.support_session_id,
            "runtime_name": proposal.runtime_name,
            "runtime_session_id": proposal.runtime_session_id,
            "reset_generation": proposal.reset_generation,
            "originating_customer_turn_id": proposal.originating_customer_turn_id,
            "catalog_snapshot_id": proposal.catalog_snapshot_id,
        },
        "offer": {
            "summary": proposal.customer_safe_summary,
            "facts": project(proposal.action_payload, PAYLOAD),
            "payload_fingerprint": proposal.payload_fingerprint,
        },
        "accepted_evidence": project(proposal.confirmation_evidence, EVIDENCE),
        "outcome": project(proposal.result_payload, RESULT),
        "timestamps": {
            key: getattr(proposal, key).isoformat() if getattr(proposal, key) else None
            for key in (
                "created_at",
                "expires_at",
                "presented_at",
                "confirmed_at",
                "commit_started_at",
                "completed_at",
            )
        },
    }


def artifact_id_for(audit_event_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{CONTRACT}:{audit_event_id}"))


def archive(db, audit_event_id, snapshot, *, recorder):
    artifact_id = artifact_id_for(audit_event_id)
    snapshot_json = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256(snapshot_json.encode()).hexdigest()
    recorder(
        db,
        EVENT_TYPE,
        {
            "evidence_contract": CONTRACT,
            "artifact_id": artifact_id,
            "audit_event_id": audit_event_id,
            "snapshot_digest": digest,
            "snapshot_json": snapshot_json,
        },
        schema_version=1,
        event_id=artifact_id,
    )
    return {"id": artifact_id, "digest": digest, "contract": CONTRACT}
