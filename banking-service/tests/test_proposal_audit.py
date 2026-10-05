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

import json
import datetime
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.audit import AuditOutbox
from models.playbook import Playbook, PlaybookRevision
from models.action_proposal import ActionProposal
from models.identity import User
from services.action_proposals import ActionProposalService, ProposalError
from services.action_proposal_context import ProposalRuntimeContext
from services.playbook_discovery import discover_playbooks
from services.proposal_audit import record_discovery, record_catalog_decision


@pytest.fixture
def audit_service(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        execution_options={
            "schema_translate_map": {
                "identity": None,
                "operations": None,
                "audit": None,
            }
        },
    )
    for model in (Playbook, PlaybookRevision, User, ActionProposal, AuditOutbox):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        user = User(
            id=uuid.uuid4(),
            auth_provider_uid="audit-customer",
            email="audit@example.com",
        )
        db.add(user)
        db.commit()
        account = SimpleNamespace(id=uuid.uuid4())
        card = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=account.id,
            status="ACTIVE",
            is_virtual=True,
            is_active=True,
            last_four="4242",
            card_token="SECRET-CARD-TOKEN",
        )
        monkeypatch.setattr(
            "services.proposal_capabilities.CreditCardRepository",
            lambda _: SimpleNamespace(
                get_account_by_customer=lambda _: account,
                list_cards_by_account=lambda _: [card],
            ),
        )
        monkeypatch.setattr(
            "services.proposal_capabilities.issue_replacement_card",
            lambda *a, **k: {
                "success": True,
                "status": "ISSUED",
                "message": "PRIVATE RESULT TEXT",
                "new_card_token": "SECRET-NEW-TOKEN",
            },
        )
        yield ActionProposalService(db)
        db.rollback()
    PlaybookRevision.__table__.drop(engine, checkfirst=True)
    Playbook.__table__.drop(engine, checkfirst=True)
    engine.dispose()


def context(**changes):
    return replace(
        ProposalRuntimeContext(
            "audit-session",
            "ADK_GEMINI_LIVE",
            "runtime-session",
            "customer-1",
            "reset-1",
        ),
        **changes,
    )


def prepare(service):
    spec = service.registry.published("card-reissue")
    return service.prepare_playbook_for_identity(
        playbook_id=spec.definition_id,
        revision=spec.definition_revision,
        digest=spec.definition_digest,
        inputs={"reason": "LOST"},
        customer_identity="audit-customer",
        runtime_context=context(),
        idempotency_key="prepare-1",
    )


def rows(service, event_type=None):
    query = service.db.query(AuditOutbox)
    if event_type:
        query = query.filter_by(event_type=event_type)
    return query.all()


def confirm_context():
    return context(
        customer_turn_id="customer-2",
        presentation_turn_id="assistant-1",
        confirmation_turn_id="customer-2",
        confirmation_method="EXPLICIT_VERBAL",
        confirmation_source="MODEL_TOOL_INTENT",
    )


def test_atomic_lifecycle_carries_pins_policy_and_evidence_without_private_facts(
    audit_service,
):
    service = audit_service
    result = prepare(service)
    service.commit_action_for_identity(
        result["proposal_id"],
        customer_identity="audit-customer",
        runtime_context=confirm_context(),
    )
    events = [e for e in rows(service) if e.event_type != "PROPOSAL_EVIDENCE_SNAPSHOT"]
    assert {e.event_type for e in events} == {
        "ACTION_PROPOSAL_" + s
        for s in ["PROPOSED", "PRESENTED", "CONFIRMED", "COMMIT_STARTED", "COMMITTED"]
    }
    spec = service.registry.published("card-reissue")
    for event in events:
        payload = json.loads(event.payload)
        assert event.schema_version == 2
        assert payload["definition"]["digest"] == spec.definition_digest
        assert payload["definition"]["revision"] == 2
        assert payload["policy"]["decision"] == "EXPLICIT_VERBAL"
        assert payload["policy"]["presentation_quality_gate"] == "RELEASE_EVALUATION"
        assert payload["payload_fingerprint"]
        assert payload["presentation_fingerprint"]
        assert "SECRET" not in event.payload
        assert "PRIVATE RESULT TEXT" not in event.payload
        assert "audit@example.com" not in event.payload
    committed = json.loads(rows(service, "ACTION_PROPOSAL_COMMITTED")[0].payload)
    assert committed["evidence"]["source"] == "MODEL_TOOL_INTENT"
    assert committed["evidence"]["fingerprint"]
    assert committed["result_fingerprint"]
    assert (
        committed["banking_outcome"] is None
    )  # Private nested results remain in the artifact.
    assert committed["result_success"] is True
    service.commit_action_for_identity(
        result["proposal_id"],
        customer_identity="audit-customer",
        runtime_context=confirm_context(),
    )
    assert len(rows(service, "ACTION_PROPOSAL_COMMITTED")) == 1
    assert len(rows(service, "ACTION_PROPOSAL_CONFIRMED")) == 1


def test_rejected_confirmation_survives_rollback_without_false_transitions(
    audit_service,
):
    service = audit_service
    result = prepare(service)
    with pytest.raises(ProposalError):
        service.commit_action_for_identity(
            result["proposal_id"],
            customer_identity="audit-customer",
            runtime_context=context(),
        )
    assert (
        service.db.get(ActionProposal, uuid.UUID(result["proposal_id"])).status
        == "PROPOSED"
    )
    assert not rows(service, "ACTION_PROPOSAL_CONFIRMED")
    rejected = json.loads(rows(service, "ACTION_PROPOSAL_REQUEST_REJECTED")[0].payload)
    assert rejected["operation"] == "COMMIT"
    assert rejected["reason_code"] == "PRESENTATION_EVIDENCE_REQUIRED"
    assert rejected["evidence_validated"] is None
    assert "definition" not in rejected  # Never resolve attempted proposal IDs.


def test_domain_failure_rolls_back_success_events_and_preserves_rejection(
    audit_service, monkeypatch
):
    service = audit_service
    result = prepare(service)

    def fail(*args, **kwargs):
        raise RuntimeError("SECRET FAILURE TEXT")

    monkeypatch.setattr("services.proposal_capabilities.issue_replacement_card", fail)
    with pytest.raises(RuntimeError):
        service.commit_action_for_identity(
            result["proposal_id"],
            customer_identity="audit-customer",
            runtime_context=confirm_context(),
        )
    assert (
        service.db.get(ActionProposal, uuid.UUID(result["proposal_id"])).status
        == "PROPOSED"
    )
    assert not rows(service, "ACTION_PROPOSAL_COMMITTED")
    assert not rows(service, "ACTION_PROPOSAL_COMMIT_STARTED")
    assert not rows(service, "ACTION_PROPOSAL_PRESENTED")
    assert (
        "SECRET FAILURE TEXT"
        not in rows(service, "ACTION_PROPOSAL_REQUEST_FAILED")[0].payload
    )


@pytest.mark.parametrize(
    "decision,stage",
    [("DECLINE", "DECLINED"), ("REVISE", "INVALIDATED"), ("CANCEL", "INVALIDATED")],
)
def test_non_commit_decisions_are_audited_once_with_validated_evidence(
    audit_service, decision, stage
):
    service = audit_service
    result = prepare(service)
    for _ in range(2):
        service.decide_for_identity(
            result["proposal_id"],
            decision=decision,
            customer_identity="audit-customer",
            runtime_context=confirm_context(),
        )
    assert len(rows(service, "ACTION_PROPOSAL_" + stage)) == 1
    event = json.loads(rows(service, "ACTION_PROPOSAL_" + stage)[0].payload)
    assert event["evidence"]["source"] == "MODEL_TOOL_INTENT"
    assert event["evidence"]["fingerprint"]
    assert (
        event["reason_code"]
        == {
            "DECLINE": "CUSTOMER_DECLINED",
            "REVISE": "CUSTOMER_REVISED",
            "CANCEL": "CUSTOMER_CANCELLED",
        }[decision]
    )
    assert not rows(service, "ACTION_PROPOSAL_COMMITTED")


def test_discovery_and_no_action_are_durable_without_customer_text(audit_service):
    service = audit_service
    result = record_discovery(
        service,
        "audit-customer",
        context(),
        discover_playbooks(service.registry, "PRIVATE CUSTOMER DINNER CONCERN"),
    )
    event = json.loads(rows(service, "PLAYBOOK_DISCOVERED")[0].payload)
    assert "PRIVATE CUSTOMER DINNER CONCERN" not in json.dumps(event)
    assert len(event["catalog"]) == 4
    assert event["need_fingerprint"]
    assert event["customer_ref"]
    recorded = record_catalog_decision(
        service,
        "audit-customer",
        context(),
        discovery_id=result["discovery_id"],
        decision="NO_ACTION",
        reason_code="UNSUPPORTED_REQUEST",
    )
    assert recorded["authorizes_execution"] is False
    assert service.db.query(ActionProposal).count() == 0
    decision = json.loads(rows(service, "PLAYBOOK_DECISION_RECORDED")[0].payload)
    assert decision["discovery_id"] == result["discovery_id"]
    assert decision["claim_source"] == "MODEL_TOOL_SELECTION"


def test_selection_references_real_published_criteria_and_cannot_cross_scope(
    audit_service,
):
    service = audit_service
    result = record_discovery(
        service,
        "audit-customer",
        context(),
        discover_playbooks(service.registry, "lost card"),
    )
    args = dict(
        discovery_id=result["discovery_id"],
        decision="SELECT",
        reason_code="APPLICABLE",
        playbook_id="card-reissue",
        criterion_index=0,
    )
    recorded = record_catalog_decision(service, "audit-customer", context(), **args)
    assert recorded["success"]
    for changed in [
        dict(criterion_index=999),
        dict(reason_code="UNSUPPORTED_REQUEST"),
        dict(playbook_id="nonexistent"),
    ]:
        with pytest.raises(ValueError):
            record_catalog_decision(
                service, "audit-customer", context(), **{**args, **changed}
            )
    for identity, ctx in [
        ("other-customer", context()),
        ("audit-customer", context(support_session_id="another-session")),
        ("audit-customer", context(reset_generation="reset-2")),
    ]:
        with pytest.raises((ValueError, ProposalError)):
            record_catalog_decision(service, identity, ctx, **args)
    assert len(rows(service, "PLAYBOOK_DECISION_RECORDED")) == 1


def test_audit_failure_prevents_preparation(audit_service, monkeypatch):
    service = audit_service

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    service.audit_recorder = fail
    with pytest.raises(RuntimeError, match="audit unavailable"):
        prepare(service)
    assert service.db.query(ActionProposal).count() == 0
    assert not rows(service, "ACTION_PROPOSAL_PROPOSED")
    assert len(rows(service, "ACTION_PROPOSAL_REQUEST_FAILED")) == 1


def test_commit_audit_failure_rolls_back_domain_mutation(audit_service, monkeypatch):
    service = audit_service
    result = prepare(service)
    user_id = service._resolve_customer_id("audit-customer")

    def execute(*args, **kwargs):
        service.db.get(User, user_id).first_name = "MUTATION"
        service.db.flush()
        return {"success": True}

    monkeypatch.setattr(
        "services.proposal_capabilities.issue_replacement_card", execute
    )
    original = service.audit_recorder

    def fail_completed(db, event_type, payload, **kwargs):
        if event_type == "ACTION_PROPOSAL_COMMITTED":
            raise RuntimeError("audit write failed")
        return original(db, event_type, payload, **kwargs)

    service.audit_recorder = fail_completed
    with pytest.raises(RuntimeError, match="audit write failed"):
        service.commit_action_for_identity(
            result["proposal_id"],
            customer_identity="audit-customer",
            runtime_context=confirm_context(),
        )
    assert service.db.get(User, user_id).first_name is None
    assert (
        service.db.get(ActionProposal, uuid.UUID(result["proposal_id"])).status
        == "PROPOSED"
    )
    assert not rows(service, "ACTION_PROPOSAL_COMMITTED")
    assert len(rows(service, "ACTION_PROPOSAL_REQUEST_FAILED")) == 1


def test_scoped_expiry_is_retained_with_rejection_after_rollback(audit_service):
    service = audit_service
    result = prepare(service)
    proposal = service.db.get(ActionProposal, uuid.UUID(result["proposal_id"]))
    proposal.expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(seconds=1)
    service.db.commit()
    with pytest.raises(ProposalError):
        service.commit_action_for_identity(
            result["proposal_id"],
            customer_identity="audit-customer",
            runtime_context=confirm_context(),
        )
    assert service.db.get(ActionProposal, proposal.id).status == "EXPIRED"
    assert len(rows(service, "ACTION_PROPOSAL_EXPIRED")) == 1
    assert len(rows(service, "ACTION_PROPOSAL_REQUEST_REJECTED")) == 1
    assert not rows(service, "ACTION_PROPOSAL_COMMIT_STARTED")


def test_foreign_commit_rejection_contains_requester_scope_only(audit_service):
    service = audit_service
    result = prepare(service)
    other = User(
        id=uuid.uuid4(), auth_provider_uid="other-customer", email="other@example.com"
    )
    service.db.add(other)
    service.db.commit()
    with pytest.raises(ProposalError):
        service.commit_action_for_identity(
            result["proposal_id"],
            customer_identity="other-customer",
            runtime_context=confirm_context(),
        )
    event = json.loads(rows(service, "ACTION_PROPOSAL_REQUEST_REJECTED")[0].payload)
    assert event["reason_code"] == "PROPOSAL_SCOPE_MISMATCH"
    assert "definition" not in event and "payload_fingerprint" not in event
    assert event["attempted_proposal_ref"]
    assert (
        service.db.get(ActionProposal, uuid.UUID(result["proposal_id"])).status
        == "PROPOSED"
    )


def snapshot_for(service, audit_event):
    from services.proposal_audit import fingerprint

    data = json.loads(audit_event.payload)
    ref = data["evidence_artifact"]
    artifact = service.db.query(AuditOutbox).filter_by(event_id=ref["id"]).one()
    archived = json.loads(artifact.payload)
    snapshot = json.loads(archived["snapshot_json"])
    assert fingerprint(snapshot) == ref["digest"] == archived["snapshot_digest"]
    assert archived["audit_event_id"] == audit_event.event_id
    return snapshot


def test_reconstructs_from_archive_after_proposals_and_catalog_are_gone(audit_service):
    service = audit_service
    prepared = prepare(service)
    service.commit_action_for_identity(
        prepared["proposal_id"],
        customer_identity="audit-customer",
        runtime_context=confirm_context(),
    )
    event = rows(service, "ACTION_PROPOSAL_COMMITTED")[0]
    expected_definition = service.registry.published("card-reissue").handler._definition
    service.db.query(ActionProposal).delete()
    service.db.commit()
    service.registry = None
    snapshot = snapshot_for(service, event)
    assert snapshot["definition"] == expected_definition
    assert snapshot["policy"]["authorization"]["evidence_policy"][
        "accepted_sources"
    ] == ["MODEL_TOOL_INTENT"]
    assert snapshot["offer"]["facts"]["reason"] == "LOST"
    assert "4242" in snapshot["offer"]["summary"]
    assert snapshot["accepted_evidence"]["confirmation_turn_id"] == "customer-2"
    assert snapshot["outcome"]["replacement_card"]["status"] == "ISSUED"
    assert snapshot["outcome"]["success"] is True
    assert "SECRET" not in json.dumps(snapshot)
    assert "PRIVATE RESULT TEXT" not in json.dumps(snapshot)


def test_evidence_write_failure_rolls_back_action_and_both_audit_branches(
    audit_service, monkeypatch
):
    service = audit_service
    result = prepare(service)
    original = service.audit_recorder
    user_id = service._resolve_customer_id("audit-customer")

    def execute(*args, **kwargs):
        service.db.get(User, user_id).first_name = "MUTATION"
        return {"success": True, "status": "ISSUED"}

    def fail_archive(db, event_type, payload, **kwargs):
        if (
            event_type == "PROPOSAL_EVIDENCE_SNAPSHOT"
            and json.loads(payload["snapshot_json"]).get("stage") == "COMMITTED"
        ):
            raise RuntimeError("archive unavailable")
        return original(db, event_type, payload, **kwargs)

    monkeypatch.setattr(
        "services.proposal_capabilities.issue_replacement_card", execute
    )
    service.audit_recorder = fail_archive
    with pytest.raises(RuntimeError, match="archive unavailable"):
        service.commit_action_for_identity(
            result["proposal_id"],
            customer_identity="audit-customer",
            runtime_context=confirm_context(),
        )
    assert service.db.get(User, user_id).first_name is None
    assert (
        len(rows(service, "PROPOSAL_EVIDENCE_SNAPSHOT")) == 1
    )  # Only durable preparation.
    assert not rows(service, "ACTION_PROPOSAL_COMMITTED")


def test_catalog_choices_reconstruct_without_definition_files(audit_service):
    service = audit_service
    discovered = record_discovery(
        service,
        "audit-customer",
        context(),
        discover_playbooks(service.registry, "lost card"),
    )
    record_catalog_decision(
        service,
        "audit-customer",
        context(),
        discovery_id=discovered["discovery_id"],
        decision="SELECT",
        reason_code="APPLICABLE",
        playbook_id="card-reissue",
        criterion_index=0,
    )
    catalog = snapshot_for(service, rows(service, "PLAYBOOK_DISCOVERED")[0])
    decision = snapshot_for(service, rows(service, "PLAYBOOK_DECISION_RECORDED")[0])
    assert len(catalog["catalog"]) == 4
    assert (
        decision["criterion"]["text"]
        == decision["definition"]["discovery"]["when_to_use"][0]
    )
    assert decision["discovery_artifact"]["id"]


def test_recursive_allowlist_drops_secrets_even_inside_money_and_result_lists():
    from services.proposal_evidence import project, PAYLOAD, RESULT

    payload = project(
        {
            "card_token": "SECRET",
            "money_facts": [
                {
                    "money": {
                        "amount_minor": 499,
                        "currency_code": "USD",
                        "token": "SECRET",
                    },
                    "transaction_id": "tx-1",
                    "private_metadata": {"password": "SECRET"},
                }
            ],
        },
        PAYLOAD,
    )
    result = project(
        {
            "replacement_card": {"new_card_id": "card-1", "new_card_token": "SECRET"},
            "provisional_credits": [
                {
                    "transaction_id": "tx-1",
                    "credited_amount": {
                        "amount_minor": 499,
                        "currency_code": "USD",
                        "token": "SECRET",
                    },
                    "message": "PRIVATE",
                }
            ],
        },
        RESULT,
    )
    assert payload["money_facts"][0]["money"] == {
        "amount_minor": 499,
        "currency_code": "USD",
    }
    assert result["replacement_card"] == {"new_card_id": "card-1"}
    assert "SECRET" not in json.dumps([payload, result])


def test_retained_archive_deduplicates_transition_after_metadata_pruning(audit_service):
    from services.proposal_audit import record_transition

    service = audit_service
    result = prepare(service)
    proposal = service.db.get(ActionProposal, uuid.UUID(result["proposal_id"]))
    event = rows(service, "ACTION_PROPOSAL_PROPOSED")[0]
    event_id = event.event_id
    service.db.delete(event)
    service.db.commit()
    assert (
        record_transition(
            service.db, proposal, service.registry.for_proposal(proposal), "PROPOSED"
        )
        == event_id
    )
    assert len(rows(service, "PROPOSAL_EVIDENCE_SNAPSHOT")) == 1
    assert not rows(service, "ACTION_PROPOSAL_PROPOSED")
