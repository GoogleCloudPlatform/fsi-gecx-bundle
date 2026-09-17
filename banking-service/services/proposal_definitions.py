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
        ),
    )
    if (
        type(d["schema_version"]) is not int
        or d["schema_version"] != 1
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
    return d


class ServiceActionHandler:
    def __init__(self, db, definition):
        self.db = db
        self._definition = deepcopy(definition)
        self.operation = OPERATIONS[definition["operation"]]

    def prepare(self, customer_id, inputs):
        inputs = deepcopy(inputs)
        validate_inputs(inputs, self.operation.input_schema)
        d = self._definition
        account_id, facts, summary = self.operation.prepare(
            self.db, customer_id, inputs, d["parameters"]
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
        return self.operation.validate(self.db, proposal)

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


def load_action_registry(db, documents=None):
    if documents is None:
        documents = [
            json.loads(path.read_text()) for path in sorted(CATALOG_PATH.glob("*.json"))
        ]
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
                definition_digest=hashlib.sha256(
                    json.dumps(d, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
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
                handler=ServiceActionHandler(db, d),
                result_schema={"success": bool},
            )
        )
    if not specifications:
        raise ValueError("Action catalog is empty.")
    return ActionRegistry(tuple(specifications))


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
