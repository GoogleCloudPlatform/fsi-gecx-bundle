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

"""Validated declarative catalog and the single service-action handler."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from string import Formatter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.money import Money
from services.decisioning import (
    BankDecision,
    ConsentedInquiryType,
    CounterofferOrigin,
    DecisionRequest,
    DisclosureVersion,
    Fingerprint,
    validate_decision,
)
from services.proposal_capabilities import OPERATIONS, validate_inputs
from services.proposal_protocol import (
    ActionRegistry,
    ActionSpecification,
    GENERAL_ACKNOWLEDGMENT_POLICY,
    PresentationQualityGate,
    PresentationRequirement,
)

CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "action_definitions"


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(
            f"Definition requires exactly these fields: {sorted(expected)}"
        )


def validate_definition(document):
    d = deepcopy(document)
    _keys(
        d,
        (
            "schema_version",
            "id",
            "revision",
            "action_type",
            "contract_version",
            "type",
            "operation",
            "authorization_policy",
            "parameters",
            "payload",
            "presentation",
            *(("discovery",) if d.get("schema_version") == 2 else ()),
        ),
    )
    if (
        type(d["schema_version"]) is not int
        or d["schema_version"] not in {1, 2}
        or d["type"] != "service_action"
    ):
        raise ValueError("Unsupported definition schema or execution type.")
    if type(d["revision"]) is not int or d["revision"] < 1:
        raise ValueError("Definition revision must be a positive integer.")
    for field, limit in [("id", 128), ("action_type", 64), ("contract_version", 32)]:
        if (
            not isinstance(d[field], str)
            or not d[field].strip()
            or len(d[field]) > limit
        ):
            raise ValueError(f"Invalid definition {field}.")
    if d["authorization_policy"] != "general_acknowledgment.v1":
        raise ValueError("Unsupported authorization policy.")
    if not isinstance(d["operation"], str) or d["operation"] not in OPERATIONS:
        raise ValueError("Unknown registered operation.")
    op = OPERATIONS[d["operation"]]
    if d["parameters"] != op.parameters:
        raise ValueError("Parameters do not match the operation contract.")
    _keys(d["parameters"], op.parameters)
    for key, value in op.parameters.items():
        if type(d["parameters"][key]) is not type(value):
            raise ValueError("Invalid parameter type.")
    _keys(d["payload"], op.payload_schema)
    for key, binding in d["payload"].items():
        expected = (
            {"literal": op.literal_bindings[key]}
            if key in op.literal_bindings
            else {"from": key}
        )
        if binding != expected:
            raise ValueError("Payload binding does not match the operation contract.")
        if (
            "literal" in expected
            and type(binding["literal"]) is not op.payload_schema[key]
        ):
            raise ValueError("Invalid literal type.")
    p = d["presentation"]
    _keys(
        p, ("required_facts", "display_selection", "public_payload_fields", "template")
    )
    for key in ("required_facts", "display_selection", "public_payload_fields"):
        if (
            not isinstance(p[key], list)
            or any(not isinstance(v, str) for v in p[key])
            or len(set(p[key])) != len(p[key])
        ):
            raise ValueError("Presentation fields must be unique string lists.")
    if set(p["required_facts"]) != op.required_facts:
        raise ValueError("Presentation must include the operation required facts.")
    if not set(p["display_selection"] + p["public_payload_fields"]) <= op.public_fields:
        raise ValueError("Presentation projects private or unknown fields.")
    if op.template_fields:
        if not isinstance(p["template"], str) or not p["template"].strip():
            raise ValueError("This operation requires a presentation template.")
        parts = list(Formatter().parse(p["template"]))
        if any(
            field is not None
            and (field not in op.template_fields or spec or conversion)
            for _, field, spec, conversion in parts
        ):
            raise ValueError("Template references an unsupported public fact.")
        if not op.template_fields <= {field for _, field, _, _ in parts}:
            raise ValueError("Template must include all required template facts.")
    elif p["template"] is not None:
        raise ValueError("This operation uses its registered money renderer.")
    if d["schema_version"] == 2:
        discovery = d["discovery"]
        _keys(
            discovery,
            (
                "title",
                "purpose",
                "when_to_use",
                "when_not_to_use",
                "prerequisites",
                "input_guidance",
                "examples",
            ),
        )
        for key in ("title", "purpose", "input_guidance"):
            if (
                not isinstance(discovery[key], str)
                or not discovery[key].strip()
                or len(discovery[key]) > 2000
            ):
                raise ValueError("Discovery text must be nonempty and bounded.")
        for key in ("when_to_use", "when_not_to_use", "prerequisites", "examples"):
            values = discovery[key]
            if (
                not isinstance(values, list)
                or not 1 <= len(values) <= 12
                or any(
                    not isinstance(value, str) or not value.strip() or len(value) > 1000
                    for value in values
                )
            ):
                raise ValueError("Discovery lists must contain bounded nonempty text.")
    return d


class ServiceActionHandler:
    def __init__(self, db, definition, decisioning_provider=None):
        self.db = db
        self.decisioning_provider = decisioning_provider
        self._definition = deepcopy(definition)
        self.operation = OPERATIONS[definition["operation"]]

    def discovery_view(self):
        """Public catalog metadata only; never payload bindings or private facts."""
        d = self._definition
        if "discovery" not in d:
            return None
        return deepcopy(d["discovery"])

    def prepare(self, customer_id, inputs, *, preparation_context=None):
        inputs = deepcopy(inputs)
        validate_inputs(inputs, self.operation.input_schema)
        d = self._definition
        account_id, facts, summary = self.operation.prepare(
            self.db, customer_id, inputs, d["parameters"],
            provider=self.decisioning_provider, preparation_context=preparation_context,
        )
        payload = {
            key: deepcopy(
                binding["literal"] if "literal" in binding else facts[binding["from"]]
            )
            for key, binding in d["payload"].items()
        }
        if d["presentation"]["template"] is not None:
            summary = d["presentation"]["template"].format(
                **{field: facts[field] for field in self.operation.template_fields}
            )
        return account_id, payload, summary

    def display_selection(self, proposal):
        return {
            key: proposal.action_payload[key]
            for key in self._definition["presentation"]["display_selection"]
        }

    def public_projection(self, proposal):
        return {
            key: proposal.action_payload[key]
            for key in self._definition["presentation"]["public_payload_fields"]
        }

    def execute(self, proposal):
        return self.operation.execute(self.db, proposal)

    def validate_current_preconditions(self, proposal):
        return self.operation.validate(self.db, proposal, provider=self.decisioning_provider)

    def reconcile(self, proposal):
        return self.operation.reconcile(self.db, proposal)

    def commit_pending_message(self, proposal):
        return self.operation.pending(self.db, proposal)

    def record_commit_started(self, proposal):
        return self.operation.started(self.db, proposal)

    def record_committed(self, proposal, result):
        return self.operation.committed(self.db, proposal, result)

    def record_reconciled(self, proposal, result):
        return self.operation.reconciled(self.db, proposal, result)


def definition_digest(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def bundled_documents():
    return [json.loads(path.read_text()) for path in sorted(CATALOG_PATH.glob("*.json"))]


def load_action_registry(db, documents=None, *, decisioning_provider=None):
    repository_catalog = documents is None
    published = None
    if documents is None:
        if db is None:
            documents = bundled_documents()
        else:
            from services.playbook_repository import SqlPlaybookRepository
            snapshot = SqlPlaybookRepository(db).snapshot()
            documents, published = snapshot.documents, snapshot.published
    specifications = []
    for document in documents:
        d = validate_definition(document)
        operation = OPERATIONS[d["operation"]]
        specifications.append(
            ActionSpecification(
                action_type=d["action_type"],
                contract_version=d["contract_version"],
                definition_id=d["id"],
                definition_revision=d["revision"],
                definition_digest=definition_digest(d),
                payload_schema=operation.payload_schema,
                scope_resolver=lambda proposal: (
                    str(proposal.customer_id),
                    str(proposal.account_id) if proposal.account_id else None,
                ),
                authorization_policy=GENERAL_ACKNOWLEDGMENT_POLICY,
                presentation_requirement=PresentationRequirement(
                    required_fact_keys=frozenset(d["presentation"]["required_facts"]),
                    quality_gate=PresentationQualityGate.RELEASE_EVALUATION,
                    natural_language_allowed=True,
                ),
                handler=ServiceActionHandler(db, d, decisioning_provider),
                result_schema={"success": bool},
            )
        )
    if not specifications:
        raise ValueError("Action catalog is empty.")
    registry = ActionRegistry(tuple(specifications), published=published)
    if repository_catalog and any(
        registry.require(key).handler.discovery_view() is None
        for key in registry.action_types
    ):
        raise ValueError(
            "Every published repository playbook requires discovery metadata."
        )
    return registry


def action_contract(definition_id):
    """Bind a typed public entry point to its catalog-owned wire identifiers."""
    registry = load_action_registry(None)
    matches = [
        registry.require(key)
        for key in registry.action_types
        if registry.require(key).definition_id == definition_id
    ]
    if len(matches) != 1:
        raise ValueError(f"No active action for definition {definition_id}.")
    specification = matches[0]
    return specification.action_type, specification.contract_version


# --- Contract-only decision proposal types ----------------------------------
# Declared identity and payload shape for the tiered credit-limit flow. These
# are deliberately NOT loaded into ActionRegistry or discovery: they have no
# registered operation yet, so no runtime can prepare or execute them.

DECISION_CONTRACTS_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "decision_proposal_contracts"
)
_ACCOUNT_ID = r"^[A-Fa-f0-9-]{36}$"


class DecisionProposalContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9-]{1,128}$")
    revision: int = Field(ge=1)
    action_type: str = Field(pattern=r"^[A-Z_]{1,64}$")
    contract_version: str = Field(
        max_length=32, pattern=r"^[a-z0-9-]+\.v[1-9][0-9]{0,3}$"
    )
    status: Literal["CONTRACT_ONLY"]
    authorization_policy: Literal["general_acknowledgment.v1"]
    payload_fields: tuple[str, ...] = Field(min_length=1, max_length=32)
    public_payload_fields: tuple[str, ...] = Field(min_length=1, max_length=32)
    required_facts: tuple[str, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def coherent_projection(self):
        payload = DECISION_PAYLOAD_MODELS.get(self.action_type)
        if payload is None or set(self.payload_fields) != set(payload.model_fields):
            raise ValueError("Contract payload must match its typed payload model.")
        fields = (self.payload_fields, self.public_payload_fields, self.required_facts)
        if any(len(set(v)) != len(v) for v in fields):
            raise ValueError("Contract field lists must be unique.")
        if not set(self.required_facts) <= set(self.public_payload_fields) <= set(
            self.payload_fields
        ):
            raise ValueError("Required facts must be public payload fields.")
        if not self.contract_version.startswith(f"{self.id}.v"):
            raise ValueError("Contract version must be namespaced by its id.")
        return self

    @property
    def digest(self):
        return definition_digest(self.model_dump(mode="json"))


class CreditInquiryConsentPayload(BaseModel):
    """Consent proposal for one bank-selected SOFT or HARD inquiry."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: str = Field(pattern=_ACCOUNT_ID)
    inquiry_type: ConsentedInquiryType
    disclosure_version: DisclosureVersion
    score_impact: Literal["NONE", "MAY_AFFECT_SCORE"]
    origin_request_ref: Fingerprint

    @model_validator(mode="after")
    def disclosure_matches_tier(self):
        expected = {"SOFT": "NONE", "HARD": "MAY_AFFECT_SCORE"}[self.inquiry_type]
        if self.score_impact != expected or not self.disclosure_version.startswith(
            f"{self.inquiry_type.lower()}-"
        ):
            raise ValueError("Consent disclosure and score impact must match the tier.")
        return self


class CreditLimitCounterofferPayload(BaseModel):
    """A NEW amount-bound proposal linked to the decision that offered it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    account_id: str = Field(pattern=_ACCOUNT_ID)
    current_limit: Money
    proposed_limit: Money
    increase_amount: Money
    origin: CounterofferOrigin
    bank_decision: BankDecision
    decision_request: DecisionRequest
    approval_semantics: Literal["DEMO_APPROVED_ON_CONFIRMATION"]

    @model_validator(mode="after")
    def bound_to_origin_and_own_decision(self):
        request, decision = self.decision_request, self.bank_decision
        moneys = (self.current_limit, self.proposed_limit, self.increase_amount)
        if len({m.currency_code for m in moneys}) != 1 or (
            self.increase_amount.amount_minor
            != self.proposed_limit.amount_minor - self.current_limit.amount_minor
            or self.increase_amount.amount_minor <= 0
        ):
            raise ValueError("Counteroffer arithmetic is inconsistent.")
        if (
            request.origin != self.origin
            or request.requested_limit != self.proposed_limit
            or request.facts.account_id != self.account_id
            or request.facts.current_limit_minor != self.current_limit.amount_minor
        ):
            raise ValueError("Counteroffer request is not bound to this proposal.")
        if (
            decision.outcome != "APPROVED"
            or decision.approved_limit != self.proposed_limit
            or decision.request_ref != request.request_ref
        ):
            raise ValueError("Counteroffer must carry its own exact-amount approval.")
        return self


def validate_counteroffer_origin(
    payload, origin_decision, *, origin_request, policy, now, tier_config=None
):
    """Bind a counteroffer proposal to the COUNTEROFFER decision that offered it.

    The origin decision is fully revalidated against its own bank-owned request
    (policy identity, scope and freshness) via ``validate_decision``, then bound
    to this proposal: same decision ref, request ref, original amount, offered
    amount, scope and account. The counteroffer's ``DecisionRequest`` therefore
    inherits the origin's ``scope_ref``. Raises ``ValueError`` on any mismatch.
    """
    payload = CreditLimitCounterofferPayload.model_validate(payload)
    origin_request = DecisionRequest.model_validate(
        origin_request.model_dump(mode="json")
        if isinstance(origin_request, DecisionRequest)
        else origin_request
    )
    decision = validate_decision(
        origin_decision, origin_request, policy, now, tier_config=tier_config
    )
    origin, request = payload.origin, payload.decision_request
    if (
        decision.outcome != "COUNTEROFFER"
        or decision.binding_ref != origin.origin_decision_ref
        or origin_request.request_ref != origin.origin_request_ref
        or origin_request.requested_limit != origin.origin_requested_limit
        or decision.approved_limit != payload.proposed_limit
    ):
        raise ValueError("Counteroffer is not linked to its originating decision.")
    if (
        origin_request.scope_ref != request.scope_ref
        or origin_request.facts.account_id != payload.account_id
    ):
        raise ValueError("Counteroffer origin belongs to another scope or account.")
    return payload


DECISION_PAYLOAD_MODELS = {
    "CREDIT_INQUIRY_CONSENT": CreditInquiryConsentPayload,
    "CREDIT_LIMIT_COUNTEROFFER": CreditLimitCounterofferPayload,
}


def load_decision_proposal_contracts(path=None):
    """Return {id: contract}; file names must be ``<id>.v<revision>.json``."""
    contracts = {}
    for file in sorted(Path(path or DECISION_CONTRACTS_PATH).glob("*.json")):
        contract = DecisionProposalContract.model_validate_json(file.read_text())
        if file.name != f"{contract.id}.v{contract.revision}.json":
            raise ValueError("Contract file name must match its identity.")
        if contract.id in contracts:
            raise ValueError("Each contract id must be declared exactly once.")
        contracts[contract.id] = contract
    return contracts
