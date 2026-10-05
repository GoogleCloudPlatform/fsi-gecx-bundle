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

"""Public lifecycle conformance for the bounded demo credit-limit capability."""

import datetime
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.playbook import Playbook, PlaybookRevision
from models.action_proposal import ActionProposal
from models.audit import AuditOutbox
from models.credit_card import CreditAccount, CreditProduct
from models.identity import User
from models.money import MAX_MINOR
from services.action_proposal_context import ProposalRuntimeContext
from services.action_proposals import ActionProposalService
from services.proposal_lifecycle import (
    ActionPreconditionError,
    ProposalError,
    ProposalPolicyError,
    ProposalScopeError,
)
from services.playbook_discovery import discover_playbooks

TABLES = (
    Playbook.__table__,
    PlaybookRevision.__table__,
    User.__table__,
    CreditProduct.__table__,
    CreditAccount.__table__,
    ActionProposal.__table__,
    AuditOutbox.__table__,
)


@pytest.fixture
def credit_db():
    engine = create_engine("sqlite:///:memory:")
    for table in TABLES:
        table.create(engine, checkfirst=True)
    with Session(engine) as db:
        user, account, product = seed_credit(db)
        yield db, user, account, product
    for table in reversed(TABLES):
        table.drop(engine, checkfirst=True)
    engine.dispose()


def seed_credit(db):
    user = User(
        id=uuid.uuid4(),
        auth_provider_uid=f"limit-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@example.com",
    )
    product = CreditProduct(
        product_code=f"TEST-{uuid.uuid4()}",
        product_name="Demo",
        min_credit_limit_cents=100000,
        max_credit_limit_cents=3000000,
        purchase_apr=0.1,
    )
    account = CreditAccount(
        id=uuid.uuid4(),
        customer_id=user.id,
        product_code=product.product_code,
        status="ACTIVE",
        currency="USD",
        credit_limit_cents=1000000,
        available_credit_cents=950000,
    )
    db.add_all([user, product])
    db.flush()
    db.add(account)
    db.commit()
    return user, account, product


def context(*, session="support-limit", confirm=False, turn=None):
    return ProposalRuntimeContext(
        support_session_id=session,
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id=f"runtime-{session}",
        customer_turn_id=turn or ("turn-2" if confirm else "turn-1"),
        reset_generation="reset-1",
        catalog_snapshot_id="guidance-2.9",
        presentation_turn_id="assistant-1" if confirm else None,
        confirmation_turn_id=(turn or "turn-2") if confirm else None,
        confirmation_method="EXPLICIT_VERBAL" if confirm else None,
        confirmation_source="MODEL_TOOL_INTENT" if confirm else None,
    )


def prepare(db, user, *, inputs=None, ctx=None, key="prepare-1", provider=None):
    service = ActionProposalService(db, decisioning_provider=provider)
    spec = service.registry.published("credit-limit-increase")
    return service.prepare_playbook_for_identity(
        playbook_id=spec.definition_id,
        revision=spec.definition_revision,
        digest=spec.definition_digest,
        inputs=inputs
        if inputs is not None
        else {"requested_limit_minor": 1500000, "currency_code": "USD"},
        customer_identity=user.auth_provider_uid,
        runtime_context=ctx or context(),
        idempotency_key=key,
    )


def commit(db, user, view, ctx=None, provider=None):
    return ActionProposalService(
        db, decisioning_provider=provider
    ).commit_action_for_identity(
        view["proposal_id"],
        customer_identity=user.auth_provider_uid,
        runtime_context=ctx or context(confirm=True),
    )


def snapshots(db):
    return [
        json.loads(json.loads(row.payload)["snapshot_json"])
        for row in db.query(AuditOutbox).filter_by(
            event_type="PROPOSAL_EVIDENCE_SNAPSHOT"
        )
    ]


def test_discovery_four_playbooks_and_integer_contract(credit_db):
    db, user, account, product = credit_db
    result = discover_playbooks(
        ActionProposalService(db).registry, "I need more room on my card"
    )
    assert len(result["playbooks"]) == 4
    entry = next(
        p for p in result["playbooks"] if p["playbook_id"] == "credit-limit-increase"
    )
    assert entry["input_schema"]["properties"]["requested_limit_minor"] == {
        "type": "integer"
    }
    assert entry["eligibility"] == "NOT_CHECKED"


def test_offer_preserves_money_policy_and_changes_no_financial_state(credit_db):
    db, user, account, product = credit_db
    view = prepare(db, user)
    assert view["proposed_limit"] == {"amount_minor": 1500000, "currency_code": "USD"}
    assert "$15,000.00" in view["customer_safe_summary"]
    assert "after you confirm" in view["customer_safe_summary"]
    assert account.credit_limit_cents == 1000000
    assert account.available_credit_cents == 950000
    facts = snapshots(db)[0]["offer"]["facts"]
    assert facts["credit_limit_policy"]["digest"]
    assert facts["eligibility_facts"]["maximum_limit_minor"] == 3000000


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {"requested_limit_minor": True, "currency_code": "USD"},
        {"requested_limit_minor": 1500000.0, "currency_code": "USD"},
        {"requested_limit_minor": "1500000", "currency_code": "USD"},
        {
            "requested_limit_minor": 1500000,
            "currency_code": "USD",
            "account_id": "foreign",
        },
    ],
)
def test_malformed_inputs_archive_no_untrusted_facts(credit_db, inputs):
    db, user, account, product = credit_db
    with pytest.raises(ProposalError):
        prepare(db, user, inputs=inputs)
    assert not db.query(ActionProposal).count()
    assert not snapshots(db)
    assert account.credit_limit_cents == 1000000


@pytest.mark.parametrize(
    "amount,reason",
    [
        (0, "REQUESTED_LIMIT_INVALID"),
        (-1, "REQUESTED_LIMIT_INVALID"),
        (MAX_MINOR + 1, "REQUESTED_LIMIT_INVALID"),
        (1000000, "LIMIT_NOT_INCREASED"),
        (500000, "LIMIT_NOT_INCREASED"),
        (2500000, "DEMO_LIMIT_CEILING_EXCEEDED"),
        (3500000, "PRODUCT_LIMIT_OUT_OF_BOUNDS"),
    ],
)
def test_denials_preserve_owned_policy_evidence(credit_db, amount, reason):
    db, user, account, product = credit_db
    with pytest.raises(ProposalPolicyError) as error:
        prepare(
            db, user, inputs={"requested_limit_minor": amount, "currency_code": "USD"}
        )
    assert error.value.code == reason
    archived = snapshots(db)[0]
    assert archived["kind"] == (
        "BANK_DECISION"
        if reason == "DEMO_LIMIT_CEILING_EXCEEDED"
        else "POLICY_EVALUATION"
    )
    assert archived["definition"]["id"] == "credit-limit-increase"
    assert archived["reason_code"] == reason
    assert archived["evaluated_facts"]["account_id"] == str(account.id)
    assert archived["requested_limit"]["amount_minor"] == amount
    assert account.credit_limit_cents == 1000000
    assert not db.query(ActionProposal).count()


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("currency", "MXN", "UNSUPPORTED_CURRENCY"),
        ("status", "FROZEN", "ACCOUNT_INACTIVE"),
        ("active", False, "PRODUCT_POLICY_UNAVAILABLE"),
        ("maximum", 0, "PRODUCT_POLICY_INVALID"),
        ("available", MAX_MINOR, "AVAILABLE_CREDIT_OUT_OF_RANGE"),
        ("available", -MAX_MINOR - 1, "AVAILABLE_CREDIT_OUT_OF_RANGE"),
    ],
)
def test_authoritative_refusals(credit_db, field, value, reason):
    db, user, account, product = credit_db
    if field == "currency":
        account.currency = value
    elif field == "status":
        account.status = value
    elif field == "active":
        product.is_active = value
    elif field == "available":
        account.available_credit_cents = value
    else:
        product.max_credit_limit_cents = value
    db.commit()
    with pytest.raises(ProposalPolicyError) as error:
        prepare(db, user)
    assert error.value.code == reason
    assert snapshots(db)[0]["reason_code"] == reason


def test_missing_product_is_refusal(credit_db):
    db, user, account, product = credit_db
    db.delete(product)
    db.commit()
    with pytest.raises(ProposalPolicyError):
        prepare(db, user)
    assert snapshots(db)[0]["evaluated_facts"]["product_active"] is None


def test_foreign_or_ambiguous_account_has_no_evidence_disclosure(credit_db):
    db, user, account, product = credit_db
    foreign = User(
        id=uuid.uuid4(),
        auth_provider_uid="other-limit",
        email="other-limit@example.com",
    )
    db.add(foreign)
    db.commit()
    with pytest.raises(ProposalScopeError):
        prepare(db, foreign)
    assert not snapshots(db)
    other = CreditAccount(
        id=uuid.uuid4(),
        customer_id=user.id,
        product_code=product.product_code,
        status="ACTIVE",
        currency="USD",
        credit_limit_cents=500000,
        available_credit_cents=500000,
    )
    db.add(other)
    db.commit()
    with pytest.raises(ProposalScopeError):
        prepare(db, user)
    assert not snapshots(db)


def test_confirmation_uses_latest_available_credit_and_replays_once(credit_db):
    db, user, account, product = credit_db
    view = prepare(db, user)
    account.available_credit_cents = 800000
    db.commit()
    result = commit(db, user, view)
    assert result["credit_limit"] == view["proposed_limit"]
    assert result["available_credit"] == {
        "amount_minor": 1300000,
        "currency_code": "USD",
    }
    assert result["status"] == "COMMITTED"
    assert commit(db, user, view)["idempotent_replay"] is True
    assert account.available_credit_cents == 1300000
    assert (
        db.query(AuditOutbox).filter_by(event_type="CREDIT_LIMIT_INCREASED").count()
        == 1
    )
    assert snapshots(db)[-1]["outcome"]["credit_limit"] == view["proposed_limit"]


def test_same_turn_and_decline_never_mutate(credit_db):
    db, user, account, product = credit_db
    view = prepare(db, user)
    with pytest.raises(ValueError):
        commit(db, user, view, context(confirm=True, turn="turn-1"))
    assert account.credit_limit_cents == 1000000
    result = ActionProposalService(db).decide_for_identity(
        view["proposal_id"],
        decision="DECLINE",
        customer_identity=user.auth_provider_uid,
        runtime_context=context(confirm=True),
    )
    assert result["status"] == "DECLINED"
    with pytest.raises(ProposalError):
        commit(db, user, view)
    assert account.credit_limit_cents == 1000000


@pytest.mark.parametrize(
    "field",
    [
        "limit",
        "currency",
        "status",
        "product",
        "bounds",
        "active",
        "policy",
        "available_overflow",
    ],
)
def test_changed_eligibility_invalidates_with_approved_and_observed_evidence(
    credit_db, field, monkeypatch
):
    db, user, account, product = credit_db
    view = prepare(db, user)
    if field == "limit":
        account.credit_limit_cents = 1100000
    elif field == "currency":
        account.currency = "MXN"
    elif field == "status":
        account.status = "FROZEN"
    elif field == "product":
        account.product_code = "missing-product"
    elif field == "bounds":
        product.max_credit_limit_cents = 1400000
    elif field == "active":
        product.is_active = False
    elif field == "available_overflow":
        account.available_credit_cents = MAX_MINOR
    else:
        from services import proposal_capabilities

        monkeypatch.setattr(
            proposal_capabilities,
            "CREDIT_LIMIT_POLICY",
            {**proposal_capabilities.CREDIT_LIMIT_POLICY, "revision": 2},
        )
    db.commit()
    with pytest.raises(ActionPreconditionError):
        commit(db, user, view)
    assert db.get(ActionProposal, view["proposal_id"]).status == "INVALIDATED"
    assert account.credit_limit_cents != 1500000
    evidence = next(p for p in snapshots(db) if p["kind"] == "POLICY_EVALUATION")
    assert evidence["approved_facts"]["current_limit_minor"] == 1000000
    assert evidence["evaluated_facts"]["account_id"] == str(account.id)


def test_archive_failure_rolls_back_mutation_and_safe_retry(credit_db, monkeypatch):
    db, user, account, product = credit_db
    view = prepare(db, user)
    from services import proposal_audit

    original = proposal_audit.archive

    def fail_commit(db, event_id, snapshot, *, recorder):
        if snapshot.get("stage") == "COMMITTED":
            raise RuntimeError("forced archive failure")
        return original(db, event_id, snapshot, recorder=recorder)

    monkeypatch.setattr(proposal_audit, "archive", fail_commit)
    with pytest.raises(RuntimeError):
        commit(db, user, view)
    db.refresh(account)
    assert account.credit_limit_cents == 1000000
    assert account.available_credit_cents == 950000
    assert db.get(ActionProposal, view["proposal_id"]).status == "PROPOSED"
    assert (
        not db.query(AuditOutbox).filter_by(event_type="CREDIT_LIMIT_INCREASED").count()
    )
    monkeypatch.setattr(proposal_audit, "archive", original)
    assert commit(db, user, view)["success"] is True


@pytest.mark.parametrize("currency", ["secret customer utterance", "usd", "X" * 2000])
def test_unrecognized_currency_never_archives_freeform_inputs(credit_db, currency):
    db, user, account, product = credit_db
    with pytest.raises(ProposalError):
        prepare(
            db,
            user,
            inputs={"requested_limit_minor": 1500000, "currency_code": currency},
        )
    assert not snapshots(db)
    assert all(currency not in row.payload for row in db.query(AuditOutbox))


@pytest.mark.parametrize("amount", [True, 1500000.0, 500000, 2500000, MAX_MINOR + 1])
def test_standalone_domain_service_enforces_same_strict_demo_policy(credit_db, amount):
    db, user, account, product = credit_db
    from services.credit_card import apply_limit_increase

    with pytest.raises(ValueError):
        apply_limit_increase(db, account.id, amount)
    db.refresh(account)
    assert account.credit_limit_cents == 1000000


@pytest.mark.asyncio
async def test_generic_commit_ui_event_uses_canonical_result(credit_db, monkeypatch):
    from routers.mcp import playbooks

    events = []

    async def send(session, event):
        events.append((session, event))

    monkeypatch.setattr(playbooks, "send_session_event", send)
    result = {
        "action_type": "CREDIT_LIMIT_INCREASE",
        "proposal_id": "proposal",
        "credit_limit": {"amount_minor": 1500000, "currency_code": "USD"},
        "available_credit": {"amount_minor": 1450000, "currency_code": "USD"},
    }
    await playbooks._publish_committed_event("owned-user", result)
    assert events == [
        (
            "session-owned-user",
            {
                "type": "LIMIT_UPDATED",
                "proposal_id": "proposal",
                "credit_limit": result["credit_limit"],
                "available_credit": result["available_credit"],
            },
        )
    ]


def test_foreign_customer_cannot_commit_existing_owned_limit_offer(credit_db):
    db, user, account, product = credit_db
    view = prepare(db, user)
    foreign = User(
        id=uuid.uuid4(),
        auth_provider_uid="foreign-commit",
        email="foreign-commit@example.com",
    )
    db.add(foreign)
    db.commit()
    with pytest.raises(ProposalScopeError):
        commit(db, foreign, view)
    assert db.get(ActionProposal, view["proposal_id"]).status == "PROPOSED"
    assert (
        not db.query(AuditOutbox).filter_by(event_type="CREDIT_LIMIT_INCREASED").count()
    )
    assert all(snapshot["kind"] != "POLICY_EVALUATION" for snapshot in snapshots(db))
    assert commit(db, user, view)["success"] is True


class FakeDecisionProvider:
    def __init__(
        self, scenario="STANDARD", *, mutation=None, fail=False, metadata_fail=False
    ):
        from services.decisioning import load_decisioning_provider

        self.delegate = load_decisioning_provider(scenario=scenario)
        self.mutation = mutation
        self.fail = fail
        self.metadata_fail = metadata_fail
        self.calls = 0

    @property
    def current_policy(self):
        if self.metadata_fail:
            raise RuntimeError("SECRET provider config")
        return self.delegate.current_policy

    def evaluate(self, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError("SECRET provider transport")
        result = self.delegate.evaluate(request).model_dump(mode="json")
        return self.mutation(result) if self.mutation else result


@pytest.mark.parametrize(
    "scenario,outcome",
    [
        ("DECLINE", "DECLINED"),
        ("NEEDS_INFORMATION", "NEEDS_INFORMATION"),
        ("REFER_FOR_REVIEW", "REFER_FOR_REVIEW"),
    ],
)
def test_nonapproval_archives_checked_bank_receipt_without_offer(
    credit_db, scenario, outcome
):
    db, user, account, product = credit_db
    provider = FakeDecisionProvider(scenario)
    with pytest.raises(ProposalPolicyError):
        prepare(db, user, provider=provider)
    evidence = snapshots(db)[0]
    assert evidence["kind"] == "BANK_DECISION"
    assert evidence["bank_decision"]["outcome"] == outcome
    assert evidence["decision_request"]["facts"]["account_id"] == str(account.id)
    assert not db.query(ActionProposal).count()
    assert account.credit_limit_cents == 1000000


@pytest.mark.parametrize("mode", ["failure", "metadata", "malformed"])
def test_provider_failure_archives_only_bounded_checked_facts(credit_db, mode):
    db, user, account, product = credit_db
    provider = FakeDecisionProvider(
        fail=mode == "failure",
        metadata_fail=mode == "metadata",
        mutation=(lambda result: {**result, "SECRET": "private response"})
        if mode == "malformed"
        else None,
    )
    with pytest.raises(ProposalPolicyError) as error:
        prepare(db, user, provider=provider)
    evidence = snapshots(db)[0]
    assert evidence["decision_failure"] in {
        "PROVIDER_UNAVAILABLE",
        "INVALID_PROVIDER_RESPONSE",
    }
    assert evidence["decision_request"]["facts"]["account_id"] == str(account.id)
    assert "SECRET" not in json.dumps(evidence)
    assert "SECRET" not in json.dumps(error.value.safe_result())
    assert not db.query(ActionProposal).count()


def test_prepare_retry_returns_pinned_receipt_without_provider_reevaluation(credit_db):
    db, user, account, product = credit_db
    provider = FakeDecisionProvider()
    first = prepare(db, user, provider=provider)
    provider.fail = True
    assert prepare(db, user, provider=provider)["proposal_id"] == first["proposal_id"]
    assert provider.calls == 1
    with pytest.raises(ProposalError):
        prepare(
            db,
            user,
            provider=provider,
            inputs={"requested_limit_minor": 1600000, "currency_code": "USD"},
        )
    assert provider.calls == 1


def test_expired_decision_cannot_commit_even_with_valid_customer_confirmation(
    credit_db, monkeypatch
):
    from services import decisioning

    db, user, account, product = credit_db
    provider = FakeDecisionProvider()
    view = prepare(db, user, provider=provider)
    proposal = db.get(ActionProposal, view["proposal_id"])
    expiry = datetime.datetime.fromisoformat(
        proposal.action_payload["bank_decision"]["expires_at"].replace("Z", "+00:00")
    )
    monkeypatch.setattr(decisioning, "utcnow", lambda: expiry)
    with pytest.raises(ActionPreconditionError):
        commit(db, user, view, provider=provider)
    assert account.credit_limit_cents == 1000000
    assert proposal.status == "INVALIDATED"


def test_changed_operator_policy_invalidates_pinned_approval(credit_db):
    db, user, account, product = credit_db
    view = prepare(db, user, provider=FakeDecisionProvider())
    with pytest.raises(ActionPreconditionError):
        commit(db, user, view, provider=FakeDecisionProvider("DECLINE"))
    assert account.credit_limit_cents == 1000000


def test_bank_decision_binding_cannot_be_reused_in_other_scope(credit_db):
    db, user, account, product = credit_db
    provider = FakeDecisionProvider(
        mutation=lambda result: {**result, "decision_id": "same-id"}
    )
    first = prepare(db, user, provider=provider)
    with pytest.raises(ProposalPolicyError) as error:
        prepare(
            db,
            user,
            provider=provider,
            ctx=context(session="other-scope"),
            key="another",
        )
    assert error.value.code == "BANK_DECISION_ALREADY_BOUND"
    assert db.query(ActionProposal).count() == 1
    assert (
        db.get(ActionProposal, first["proposal_id"]).bank_decision_ref
        == "demo-bank:same-id"
    )
    assert account.credit_limit_cents == 1000000


def test_injected_over_ceiling_approval_never_creates_impossible_offer(credit_db):
    db, user, account, product = credit_db

    def force_approval(result):
        return {
            **result,
            "outcome": "APPROVED",
            "approved_limit": {"amount_minor": 2500000, "currency_code": "USD"},
            "reason_codes": ["APPROVED_BY_POLICY"],
        }

    with pytest.raises(ProposalPolicyError) as error:
        prepare(
            db,
            user,
            provider=FakeDecisionProvider(mutation=force_approval),
            inputs={"requested_limit_minor": 2500000, "currency_code": "USD"},
        )
    assert error.value.code == "DEMO_LIMIT_CEILING_EXCEEDED"
    evidence = snapshots(db)[0]
    assert evidence["bank_decision"]["outcome"] == "APPROVED"
    assert evidence["credit_limit_policy"]["digest"]
    assert not db.query(ActionProposal).count()


def test_cancelled_offer_keeps_bank_decision_reservation(credit_db):
    db, user, account, product = credit_db
    provider = FakeDecisionProvider(
        mutation=lambda result: {**result, "decision_id": "reserved-after-cancel"}
    )
    view = prepare(db, user, provider=provider)
    service = ActionProposalService(db, decisioning_provider=provider)
    cancelled = service.decide_for_identity(
        view["proposal_id"],
        decision="CANCEL",
        customer_identity=user.auth_provider_uid,
        runtime_context=context(confirm=True),
    )
    assert cancelled["status"] == "INVALIDATED"
    with pytest.raises(ProposalPolicyError) as error:
        prepare(
            db,
            user,
            provider=provider,
            ctx=context(session="next-scope"),
            key="new-key",
        )
    assert error.value.code == "BANK_DECISION_ALREADY_BOUND"
    assert (
        db.get(ActionProposal, view["proposal_id"]).bank_decision_ref
        == "demo-bank:reserved-after-cancel"
    )


def test_approved_decision_is_archived_distinct_from_customer_authorization(credit_db):
    db, user, account, product = credit_db
    view = prepare(db, user)
    evidence = snapshots(db)[0]
    receipt = evidence["offer"]["facts"]["bank_decision"]
    assert receipt["outcome"] == "APPROVED"
    assert receipt["approved_limit"] == view["proposed_limit"]
    assert evidence["offer"]["facts"]["decision_request"]["facts"]["account_id"] == str(
        account.id
    )
    assert db.get(ActionProposal, view["proposal_id"]).confirmation_evidence is None


def test_invalid_default_provider_config_does_not_break_catalog_and_fails_closed(
    credit_db, monkeypatch
):
    from services import decisioning

    db, user, account, product = credit_db

    def unavailable():
        raise ValueError("SECRET malformed operator config")

    monkeypatch.setattr(decisioning, "load_decisioning_provider", unavailable)
    assert (
        len(
            discover_playbooks(ActionProposalService(db).registry, "credit limit")[
                "playbooks"
            ]
        )
        == 4
    )
    with pytest.raises(ProposalPolicyError) as error:
        prepare(db, user)
    assert error.value.code == "BANK_DECISION_UNAVAILABLE"
    assert "SECRET" not in json.dumps(snapshots(db))
    assert snapshots(db)[0]["decision_request"]["facts"]["account_id"] == str(
        account.id
    )


def test_valid_negative_available_credit_preserves_delta(credit_db):
    db, user, account, product = credit_db
    account.available_credit_cents = -100000
    db.commit()
    result = commit(db, user, prepare(db, user))
    assert result["available_credit"] == {
        "amount_minor": 400000,
        "currency_code": "USD",
    }


def test_commit_refuses_invalid_current_available_even_if_delta_restores_range(
    credit_db,
):
    db, user, account, product = credit_db
    view = prepare(db, user)
    account.available_credit_cents = -MAX_MINOR - 1
    db.commit()
    with pytest.raises(ActionPreconditionError):
        commit(db, user, view)
    assert account.credit_limit_cents == 1000000


@pytest.mark.parametrize("available,valid", [(-MAX_MINOR - 1, False), (-100000, True)])
def test_standalone_service_available_credit_range(credit_db, available, valid):
    from services.credit_card import apply_limit_increase

    db, user, account, product = credit_db
    account.available_credit_cents = available
    db.commit()
    if valid:
        apply_limit_increase(db, account.id, 1500000)
        assert account.available_credit_cents == 400000
    else:
        with pytest.raises(ValueError, match="Current available credit"):
            apply_limit_increase(db, account.id, 1500000)
        assert account.credit_limit_cents == 1000000
