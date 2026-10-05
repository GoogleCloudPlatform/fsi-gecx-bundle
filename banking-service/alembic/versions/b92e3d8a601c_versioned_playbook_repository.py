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

"""Operational versioned playbook catalog, immutable publications and fixed bootstrap."""

import datetime
import hashlib
import json
from alembic import op
import sqlalchemy as sa

revision = "b92e3d8a601c"
down_revision = "a81d2c7f490b"
branch_labels = None
depends_on = None

BOOTSTRAP = json.loads(
    '[{"schema_version":1,"id":"card-reissue","revision":1,"action_type":"REISSUE_CARD","contract_version":"card-reissue.v1","type":"service_action","operation":"cards.issue_replacement.v1","authorization_policy":"general_acknowledgment.v1","parameters":{"require_virtual":false},"payload":{"account_id":{"from":"account_id"},"compromised_card_id":{"from":"compromised_card_id"},"reason":{"from":"reason"},"issue_virtual_card":{"literal":true}},"presentation":{"required_facts":["card_last_four","current_card_blocking","replacement_card_form"],"display_selection":["reason","issue_virtual_card"],"public_payload_fields":[],"template":"Confirm that you want to block the card ending {card_last_four} and issue a replacement virtual card."}},{"schema_version":2,"id":"card-reissue","revision":2,"action_type":"REISSUE_CARD","contract_version":"card-reissue.v1","type":"service_action","operation":"cards.issue_replacement.v1","authorization_policy":"general_acknowledgment.v1","parameters":{"require_virtual":false},"payload":{"account_id":{"from":"account_id"},"compromised_card_id":{"from":"compromised_card_id"},"reason":{"from":"reason"},"issue_virtual_card":{"literal":true}},"presentation":{"required_facts":["card_last_four","current_card_blocking","replacement_card_form"],"display_selection":["reason","issue_virtual_card"],"public_payload_fields":[],"template":"Confirm that you want to block the card ending {card_last_four} and issue a replacement virtual card."},"discovery":{"title":"Replace a lost, stolen, or damaged card","purpose":"Block the affected active card and issue a virtual replacement.","when_to_use":["The customer reports a lost, stolen, or damaged card and needs a replacement."],"when_not_to_use":["A replacement already exists and the customer needs help using it.","An open fraud alert needs review and triage first."],"prerequisites":["An owned active card eligible for replacement."],"input_guidance":"Provide reason LOST, STOLEN, or DAMAGED based on the customer request.","examples":["My card went missing.","The chip on my card is damaged."]}},{"schema_version":2,"id":"credit-limit-increase","revision":1,"action_type":"CREDIT_LIMIT_INCREASE","contract_version":"credit-limit-increase.v1","type":"service_action","operation":"credit.adjust_limit.v1","authorization_policy":"general_acknowledgment.v1","parameters":{},"payload":{"account_id":{"from":"account_id"},"current_limit":{"from":"current_limit"},"proposed_limit":{"from":"proposed_limit"},"increase_amount":{"from":"increase_amount"},"credit_limit_policy":{"from":"credit_limit_policy"},"eligibility_facts":{"from":"eligibility_facts"},"approval_semantics":{"from":"approval_semantics"},"prepared_arithmetic":{"from":"prepared_arithmetic"},"bank_decision":{"from":"bank_decision"},"decision_request":{"from":"decision_request"}},"presentation":{"required_facts":["current_limit","proposed_limit","increase_amount","approval_semantics"],"display_selection":["current_limit","proposed_limit","increase_amount","approval_semantics"],"public_payload_fields":["current_limit","proposed_limit","increase_amount","approval_semantics"],"template":null},"discovery":{"title":"Increase an eligible credit-card limit","purpose":"Apply a bounded demo credit-limit increase after presentation and later explicit confirmation. This is not real underwriting or a review submission.","when_to_use":["The customer asks to raise their credit-card limit to a specified new total.","The customer needs more credit capacity and wants to request a higher limit; clarify the desired new total first."],"when_not_to_use":["The customer asks only about their current limit or available balance.","The customer wants to decrease a limit or increase a deposit balance.","The customer asks for a loan, underwriting review or unsupported currency."],"prerequisites":["Exactly one owned active USD credit-card account and an active credit product with valid limit bounds.","An explicit requested new total limit and currency; an increase amount alone requires clarification."],"input_guidance":"Provide requested_limit_minor as an integer new total in USD cents, and currency_code as USD. For $7,500.00 use 750000. Do not send floats, assume a percentage or select an amount. Preparation evaluates product bounds and the demo ceiling of twice the current limit. Present returned current/proposed limits and increase amount, explain confirmation applies an eligible demo increase, then await later explicit confirmation.","examples":["Can you raise my credit limit to $7,500.00?","I need more room on my card for a purchase."]}},{"schema_version":1,"id":"fraud-triage","revision":1,"action_type":"TRIAGE_FRAUD_CASE","contract_version":"fraud-triage.v1","type":"service_action","operation":"fraud.triage.v1","authorization_policy":"general_acknowledgment.v1","parameters":{},"payload":{"fraud_alert_id":{"from":"fraud_alert_id"},"disputed_authorization_ids":{"from":"disputed_authorization_ids"},"disputed_transaction_ids":{"from":"disputed_transaction_ids"},"issue_replacement":{"from":"issue_replacement"},"escalate":{"from":"escalate"},"money_facts":{"from":"money_facts"},"card_last_four":{"from":"card_last_four"}},"presentation":{"required_facts":["card_last_four","proposed_disposition","replacement_and_escalation_consequences","reviewed_activity_selection"],"display_selection":["fraud_alert_id","disputed_authorization_ids","disputed_transaction_ids","issue_replacement","escalate"],"public_payload_fields":["money_facts","card_last_four","issue_replacement","escalate"],"template":null}},{"schema_version":2,"id":"fraud-triage","revision":2,"action_type":"TRIAGE_FRAUD_CASE","contract_version":"fraud-triage.v1","type":"service_action","operation":"fraud.triage.v1","authorization_policy":"general_acknowledgment.v1","parameters":{},"payload":{"fraud_alert_id":{"from":"fraud_alert_id"},"disputed_authorization_ids":{"from":"disputed_authorization_ids"},"disputed_transaction_ids":{"from":"disputed_transaction_ids"},"issue_replacement":{"from":"issue_replacement"},"escalate":{"from":"escalate"},"money_facts":{"from":"money_facts"},"card_last_four":{"from":"card_last_four"}},"presentation":{"required_facts":["card_last_four","proposed_disposition","replacement_and_escalation_consequences","reviewed_activity_selection"],"display_selection":["fraud_alert_id","disputed_authorization_ids","disputed_transaction_ids","issue_replacement","escalate"],"public_payload_fields":["money_facts","card_last_four","issue_replacement","escalate"],"template":null},"discovery":{"title":"Review and resolve fraud-alert activity","purpose":"Resolve a reviewed fraud alert: close recognized activity or release eligible disputed holds, credit eligible posted charges, and optionally replace the affected card.","when_to_use":["The customer disputes specific transactions from an open fraud alert after reviewing all flagged activity.","The customer explicitly recognizes all flagged activity and wants the alert resolved without card action."],"when_not_to_use":["There is no open alert; use the customer-reported fraud intake flow.","The selection is uncertain or incomplete."],"prerequisites":["An owned open fraud alert.","Every flagged item explicitly classified as disputed or recognized."],"input_guidance":"Use exact IDs from get_open_fraud_alert and review_fraud_selection. Include selection_status COMPLETE, all four disputed/recognized ID lists, issue_replacement and escalate. Never infer a disputed selection. If all activity is recognized, disputed lists are empty and issue_replacement is false.","examples":["I do not recognize any of those five charges.","The first one is mine, but the other two are not.","Those are all mine; please close the alert."]}},{"schema_version":1,"id":"google-wallet-provisioning","revision":1,"action_type":"PROVISION_GOOGLE_WALLET","contract_version":"wallet-provisioning.v1","type":"service_action","operation":"cards.queue_wallet.v1","authorization_policy":"general_acknowledgment.v1","parameters":{"require_virtual":true},"payload":{"account_id":{"from":"account_id"},"card_id":{"from":"card_id"},"card_token":{"from":"card_token"},"wallet_provider":{"literal":"GOOGLE_WALLET"}},"presentation":{"required_facts":["card_last_four","provisioning_is_queued","wallet_provider"],"display_selection":["wallet_provider"],"public_payload_fields":[],"template":"Confirm that you want to queue the virtual card ending {card_last_four} for Google Wallet."}},{"schema_version":2,"id":"google-wallet-provisioning","revision":2,"action_type":"PROVISION_GOOGLE_WALLET","contract_version":"wallet-provisioning.v1","type":"service_action","operation":"cards.queue_wallet.v1","authorization_policy":"general_acknowledgment.v1","parameters":{"require_virtual":true},"payload":{"account_id":{"from":"account_id"},"card_id":{"from":"card_id"},"card_token":{"from":"card_token"},"wallet_provider":{"literal":"GOOGLE_WALLET"}},"presentation":{"required_facts":["card_last_four","provisioning_is_queued","wallet_provider"],"display_selection":["wallet_provider"],"public_payload_fields":[],"template":"Confirm that you want to queue the virtual card ending {card_last_four} for Google Wallet."},"discovery":{"title":"Enable replacement-card access through Google Wallet","purpose":"Queue an eligible active virtual card for Google Wallet so the customer can continue using their card.","when_to_use":["The customer needs to pay with a replacement virtual card, including an upcoming in-person expense, without needing to name a wallet.","The customer asks to add their eligible virtual card to Google Wallet."],"when_not_to_use":["Provisioning is already pending or completed for this card.","The customer is only asking about existing wallet status.","A replacement exists but the customer has expressed no payment or wallet need.","The customer needs an unsupported wallet provider."],"prerequisites":["An owned active virtual card.","Google Wallet is appropriate for the customer; clarify the provider if uncertain."],"input_guidance":"No business inputs: use an empty object. Preparing checks card eligibility and creates an offer; it does not queue provisioning. Present the offer before seeking later confirmation. Queued does not mean installed or ready for contactless payment.","examples":["I have an important client dinner tonight. How am I going to pay now?","Can you add the new card to Google Wallet?"]}}]'
)


def upgrade():
    op.create_table(
        "playbooks",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("action_type", sa.String(64), nullable=False, unique=True),
        sa.Column("contract_version", sa.String(32), nullable=False),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.Column("published_revision", sa.Integer(), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        schema="admin",
    )
    table = op.create_table(
        "playbook_revisions",
        sa.Column("playbook_id", sa.String(128), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64)),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["playbook_id"], ["admin.playbooks.id"]),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED')", name="ck_playbook_revision_status"
        ),
        sa.CheckConstraint(
            "revision > 0 AND draft_version > 0", name="ck_playbook_revision_versions"
        ),
        sa.CheckConstraint(
            "status != 'PUBLISHED' OR (digest IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_playbook_published_identity",
        ),
        schema="admin",
    )
    heads = sa.table(
        "playbooks",
        sa.column("id"),
        sa.column("action_type"),
        sa.column("contract_version"),
        sa.column("operation"),
        sa.column("published_revision"),
        sa.column("generation"),
        schema="admin",
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    groups = {}
    for document in BOOTSTRAP:
        groups.setdefault(document["id"], []).append(document)
    for playbook_id, versions in groups.items():
        latest = max(versions, key=lambda d: d["revision"])
        op.get_bind().execute(
            heads.insert().values(
                id=playbook_id,
                action_type=latest["action_type"],
                contract_version=latest["contract_version"],
                operation=latest["operation"],
                published_revision=latest["revision"],
                generation=1,
            )
        )
        for document in versions:
            digest = hashlib.sha256(
                json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            op.get_bind().execute(
                table.insert().values(
                    playbook_id=playbook_id,
                    revision=document["revision"],
                    status="PUBLISHED",
                    document=document,
                    digest=digest,
                    draft_version=1,
                    created_by="bundle-bootstrap",
                    updated_by="bundle-bootstrap",
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
            )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION admin.reject_published_playbook_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.status = 'PUBLISHED' THEN RAISE EXCEPTION 'Published playbook revisions are immutable'; END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END $$""")
        op.execute("""CREATE TRIGGER playbook_revision_immutable BEFORE UPDATE OR DELETE ON admin.playbook_revisions
        FOR EACH ROW EXECUTE FUNCTION admin.reject_published_playbook_mutation()""")
    else:
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER admin.playbook_revision_immutable_{action.lower()}
            BEFORE {action} ON playbook_revisions WHEN OLD.status = 'PUBLISHED'
            BEGIN SELECT RAISE(ABORT, 'Published playbook revisions are immutable'); END""")


def downgrade():
    op.drop_table("playbook_revisions", schema="admin")
    op.drop_table("playbooks", schema="admin")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION admin.reject_published_playbook_mutation()")
