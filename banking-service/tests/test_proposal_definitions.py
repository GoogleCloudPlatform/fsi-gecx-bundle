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

"""Configuration boundaries and version pinning for declarative actions."""

from copy import deepcopy
import datetime
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from services.decisioning import (
    BankDecision,
    DecisionRequest,
    load_decisioning_provider,
)
from services.proposal_definitions import (
    CATALOG_PATH,
    DECISION_CONTRACTS_PATH,
    CreditInquiryConsentPayload,
    CreditLimitCounterofferPayload,
    bundled_documents,
    definition_digest,
    load_action_registry,
    load_decision_proposal_contracts,
    ServiceActionHandler,
    validate_counteroffer_origin,
)


def documents():
    return [
        json.loads(path.read_text()) for path in sorted(CATALOG_PATH.glob("*.json"))
    ]


def test_fourth_action_requires_only_a_definition():
    docs = documents()
    fourth = deepcopy(docs[0])
    fourth.update(id="replacement-followup", action_type="REPLACEMENT_FOLLOWUP")
    registry = load_action_registry(None, [*docs, fourth])
    assert len(registry.action_types) == 5
    assert {type(registry.require(key).handler) for key in registry.action_types} == {
        ServiceActionHandler
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(extra=True),
        lambda d: d.update(type="python"),
        lambda d: d.update(revision=True),
        lambda d: d.update(operation="os.system"),
        lambda d: d.update(authorization_policy="none"),
        lambda d: d["presentation"].update(public_payload_fields=["card_token"]),
        lambda d: d["presentation"].update(required_facts=[]),
        lambda d: d["presentation"].update(template="{card_last_four.__class__}"),
        lambda d: d["payload"].update(compromised_card_id={"literal": "another-card"}),
        lambda d: d["parameters"].update(require_virtual=0),
    ],
)
def test_invalid_definitions_rejected_before_execution(mutation):
    d = documents()[0]
    mutation(d)
    with pytest.raises(ValueError):
        load_action_registry(None, [d])


def test_pinned_revision_and_digest_survive_activation():
    first = documents()[0]
    old = load_action_registry(None, [first]).require(first["action_type"])
    second = deepcopy(first)
    second["revision"] = 2
    second["presentation"]["template"] += " Please confirm."
    registry = load_action_registry(None, [first, second])
    proposal = SimpleNamespace(
        definition_id=old.definition_id,
        definition_revision=old.definition_revision,
        definition_digest=old.definition_digest,
        action_type=old.action_type,
        contract_version=old.contract_version,
    )
    assert registry.require(old.action_type).definition_revision == 2
    assert registry.for_proposal(proposal).definition_revision == 1
    with pytest.raises(ValueError, match="Unknown or changed"):
        load_action_registry(None, [second]).for_proposal(proposal)
    modified = deepcopy(first)
    modified["presentation"]["template"] += " Changed."
    with pytest.raises(ValueError, match="Unknown or changed"):
        load_action_registry(None, [modified]).for_proposal(proposal)


def test_duplicate_revisions_rejected():
    d = documents()[0]
    with pytest.raises(ValueError, match="exactly once"):
        load_action_registry(None, [d, d])


def test_reset_migration_requires_definition_identity_and_preserves_other_data():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text, inspect

    path = (
        Path(__file__).parents[1]
        / "alembic/versions/f7e0f4a9c306_proposal_definition_identity.py"
    )
    spec = importlib.util.spec_from_file_location("definition_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        if "operations" in {
            row[1] for row in connection.execute(text("PRAGMA database_list"))
        }:
            connection.execute(text("DETACH DATABASE operations"))
        connection.execute(text("ATTACH DATABASE ':memory:' AS operations"))
        connection.execute(
            text("CREATE TABLE operations.action_proposals (id TEXT PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO operations.action_proposals VALUES ('old')")
        )
        connection.execute(text("CREATE TABLE operations.other_data (id TEXT)"))
        connection.execute(text("INSERT INTO operations.other_data VALUES ('keep')"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM operations.action_proposals")
            ).scalar()
            == 0
        )
        assert (
            connection.execute(text("SELECT id FROM operations.other_data")).scalar()
            == "keep"
        )
        columns = {
            c["name"]: c
            for c in inspect(connection).get_columns(
                "action_proposals", schema="operations"
            )
        }
        assert all(
            not columns[key]["nullable"]
            for key in ("definition_id", "definition_revision", "definition_digest")
        )


def test_discovery_uses_only_published_revisions_and_excludes_private_bindings():
    from services.playbook_discovery import discover_playbooks

    result = discover_playbooks(
        load_action_registry(None), "How will I pay for dinner?"
    )
    assert result["retrieval_mode"] == "FULL_PUBLISHED_CATALOG"
    assert len(result["playbooks"]) == 4
    assert all(
        p["revision"] == (1 if p["playbook_id"] == "credit-limit-increase" else 2)
        and p["eligibility"] == "NOT_CHECKED"
        for p in result["playbooks"]
    )
    assert "card_token" not in json.dumps(result)
    assert "authorization_policy" not in json.dumps(result)
    for candidate in result["playbooks"]:
        spec = load_action_registry(None).resolve(
            candidate["playbook_id"], candidate["revision"], candidate["digest"]
        )
        assert spec.handler.discovery_view()["purpose"] == candidate["purpose"]


def test_fourth_definition_is_discoverable_without_tool_or_engine_changes():
    from services.playbook_discovery import discover_playbooks

    docs = documents()
    fourth = deepcopy(
        next(d for d in docs if d["id"] == "card-reissue" and d["revision"] == 2)
    )
    fourth.update(id="new-replacement", action_type="NEW_REPLACEMENT")
    result = discover_playbooks(
        load_action_registry(None, [*docs, fourth]), "Replace my card"
    )
    assert len(result["playbooks"]) == 5
    assert next(
        p for p in result["playbooks"] if p["playbook_id"] == "new-replacement"
    )["input_schema"]["required"] == ["reason"]


@pytest.mark.parametrize(
    "field,value", [("purpose", ""), ("examples", []), ("prerequisites", "text")]
)
def test_discovery_metadata_is_validated_with_executable_definition(field, value):
    d = next(d for d in documents() if d["revision"] == 2)
    d["discovery"][field] = value
    with pytest.raises(ValueError, match="Discovery"):
        load_action_registry(None, [d])


def test_repository_publication_rejects_executable_without_discovery(
    tmp_path, monkeypatch
):
    first = next(d for d in documents() if d["revision"] == 1)
    (tmp_path / "incomplete.json").write_text(json.dumps(first))
    monkeypatch.setattr("services.proposal_definitions.CATALOG_PATH", tmp_path)
    with pytest.raises(ValueError, match="requires discovery metadata"):
        load_action_registry(None)


# --- Contract-only decision proposal types ----------------------------------

NOW = datetime.datetime(2026, 10, 2, tzinfo=datetime.timezone.utc)
ACCOUNT = "4b0b3f4e-7c1a-4d55-9a37-1d2f0e6a9b11"


def usd(amount):
    return {"amount_minor": amount, "currency_code": "USD"}


def limit_request(requested, **extra):
    return DecisionRequest.model_validate(
        {
            "request_ref": extra.pop("request_ref", "a" * 64),
            "scope_ref": "b" * 64,
            "input_ref": "c" * 64,
            "requested_limit": usd(requested),
            "facts": {
                "account_id": ACCOUNT,
                "account_status": "ACTIVE",
                "currency_code": "USD",
                "product_code": "DEMO",
                "current_limit_minor": 1000000,
                "product_active": True,
                "minimum_limit_minor": 100000,
                "maximum_limit_minor": 3000000,
            },
            **extra,
        }
    )


def counteroffer_case():
    provider = load_decisioning_provider(clock=lambda: NOW)
    origin_request = limit_request(1500000)
    origin_decision = BankDecision.model_validate(
        {
            **provider.evaluate(origin_request).model_dump(mode="json"),
            "outcome": "COUNTEROFFER",
            "approved_limit": usd(1200000),
            "reason_codes": ["COUNTEROFFER_AVAILABLE"],
            "inquiry_type": "NONE",
            "counteroffer": {
                "origin_request_ref": origin_request.request_ref,
                "requested_limit": usd(1500000),
            },
            "refusal": {
                "reason_code": "COUNTEROFFER_AVAILABLE",
                "retryable": False,
                "current_limit": usd(1000000),
                "product_maximum": usd(3000000),
                "max_instantly_approvable": usd(1200000),
                "soft_tier_cap": usd(1500000),
                "product_name": "Demo",
                "next_steps": ["ACCEPT_COUNTEROFFER"],
            },
        }
    )
    origin = {
        "origin_request_ref": origin_request.request_ref,
        "origin_decision_ref": origin_decision.binding_ref,
        "origin_requested_limit": usd(1500000),
    }
    request = limit_request(1200000, request_ref="d" * 64, origin=origin)
    payload = {
        "account_id": ACCOUNT,
        "current_limit": usd(1000000),
        "proposed_limit": usd(1200000),
        "increase_amount": usd(200000),
        "origin": origin,
        "bank_decision": provider.evaluate(request).model_dump(mode="json"),
        "decision_request": request.model_dump(mode="json"),
        "approval_semantics": "DEMO_APPROVED_ON_CONFIRMATION",
    }
    return payload, origin_decision


def test_decision_contracts_have_stable_identity_and_digest():
    contracts = load_decision_proposal_contracts()
    assert {c.action_type for c in contracts.values()} == {
        "CREDIT_INQUIRY_CONSENT",
        "CREDIT_LIMIT_COUNTEROFFER",
    }
    for contract in contracts.values():
        document = json.loads(
            (DECISION_CONTRACTS_PATH / f"{contract.id}.v{contract.revision}.json").read_text()
        )
        assert contract.digest == definition_digest(document)


def test_decision_contracts_are_not_executable_or_discoverable():
    from services.playbook_discovery import discover_playbooks

    path = Path(__file__).parents[1] / "alembic/versions/b92e3d8a601c_versioned_playbook_repository.py"
    spec = importlib.util.spec_from_file_location("bootstrap_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    registry = load_action_registry(None)
    contracts = load_decision_proposal_contracts().values()
    assert not {c.action_type for c in contracts} & set(registry.action_types)
    listed = json.dumps(discover_playbooks(registry, "raise my credit limit"))
    assert all(c.id not in listed and c.action_type not in listed for c in contracts)
    assert migration.BOOTSTRAP == bundled_documents()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(secret="private"),
        lambda d: d.update(status="PUBLISHED"),
        lambda d: d.update(payload_fields=d["payload_fields"][:-1]),
        lambda d: d.update(payload_fields=d["payload_fields"] + ["card_token"]),
        lambda d: d.update(required_facts=d["required_facts"] + ["origin"]),
        lambda d: d.update(contract_version="other.v1"),
        lambda d: d.update(revision=2),  # file name no longer matches identity
        lambda d: d.update(revision=True),
    ],
)
def test_decision_contract_declarations_are_closed(tmp_path, mutate):
    name = "credit-limit-counteroffer.v1.json"
    document = json.loads((DECISION_CONTRACTS_PATH / name).read_text())
    mutate(document)
    (tmp_path / name).write_text(json.dumps(document))
    with pytest.raises((ValueError, ValidationError)):
        load_decision_proposal_contracts(tmp_path)


def test_counteroffer_without_origin_link_is_rejected():
    payload, origin_decision = counteroffer_case()
    assert validate_counteroffer_origin(payload, origin_decision).origin.origin_decision_ref
    without_origin = {k: v for k, v in payload.items() if k != "origin"}
    with pytest.raises(ValidationError):
        CreditLimitCounterofferPayload.model_validate(without_origin)
    unlinked_request = {
        **payload,
        "decision_request": {
            k: v for k, v in payload["decision_request"].items() if k != "origin"
        },
    }
    with pytest.raises(ValidationError, match="not bound"):
        CreditLimitCounterofferPayload.model_validate(unlinked_request)


@pytest.mark.parametrize(
    "decision_change",
    [
        {"decision_id": "another-decision"},
        {"request_ref": "f" * 64},
        {"approved_limit": usd(1300000)},
    ],
)
def test_counteroffer_is_bound_to_the_decision_that_offered_it(decision_change):
    payload, origin_decision = counteroffer_case()
    forged = {**origin_decision.model_dump(mode="json"), **decision_change}
    if "request_ref" in decision_change:
        forged["counteroffer"]["origin_request_ref"] = decision_change["request_ref"]
    with pytest.raises(ValueError):
        validate_counteroffer_origin(payload, forged)


@pytest.mark.parametrize(
    "change",
    [
        {"increase_amount": usd(300000)},
        {"proposed_limit": usd(1300000), "increase_amount": usd(300000)},
        {"approval_semantics": "APPLIED_IMMEDIATELY"},
        {"account_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_counteroffer_payload_is_amount_bound(change):
    payload, _ = counteroffer_case()
    with pytest.raises(ValidationError):
        CreditLimitCounterofferPayload.model_validate({**payload, **change})


@pytest.mark.parametrize(
    "inquiry_type,disclosure,impact,valid",
    [
        ("SOFT", "soft-inquiry-disclosure.v1", "NONE", True),
        ("HARD", "hard-inquiry-disclosure.v1", "MAY_AFFECT_SCORE", True),
        ("HARD", "hard-inquiry-disclosure.v1", "NONE", False),
        ("SOFT", "soft-inquiry-disclosure.v1", "MAY_AFFECT_SCORE", False),
        ("HARD", "soft-inquiry-disclosure.v1", "MAY_AFFECT_SCORE", False),
        ("NONE", "soft-inquiry-disclosure.v1", "NONE", False),
    ],
)
def test_consent_payload_binds_tier_disclosure_and_score_impact(
    inquiry_type, disclosure, impact, valid
):
    document = {
        "account_id": ACCOUNT,
        "inquiry_type": inquiry_type,
        "disclosure_version": disclosure,
        "score_impact": impact,
        "origin_request_ref": "a" * 64,
    }
    if valid:
        assert CreditInquiryConsentPayload.model_validate(document).inquiry_type == inquiry_type
    else:
        with pytest.raises(ValidationError):
            CreditInquiryConsentPayload.model_validate(document)
