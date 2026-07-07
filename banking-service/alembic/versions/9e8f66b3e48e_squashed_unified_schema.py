"""squashed unified schema

Revision ID: 9e8f66b3e48e
Revises: 
Create Date: 2026-07-07 09:36:38.513747

"""
from typing import Sequence, Union
from pathlib import Path
import datetime
import os
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import utils.database


# revision identifiers, used by Alembic.
revision: str = '9e8f66b3e48e'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RESOURCE_DATA_DIR = Path(__file__).resolve().parents[2] / "resources" / "data"


def _load_json_resource(filename: str):
    with (RESOURCE_DATA_DIR / filename).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_jsonl_resource(filename: str) -> list[dict]:
    with (RESOURCE_DATA_DIR / filename).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _seed_reference_tables() -> None:
    credit_products = sa.table(
        "credit_products",
        sa.column("product_code", sa.String),
        sa.column("product_name", sa.String),
        sa.column("min_credit_limit_cents", sa.BigInteger),
        sa.column("max_credit_limit_cents", sa.BigInteger),
        sa.column("purchase_apr", sa.Numeric),
        sa.column("cashback_rate", sa.Numeric),
        sa.column("travel_multiplier", sa.Integer),
        sa.column("dining_multiplier", sa.Integer),
        sa.column("annual_fee_cents", sa.BigInteger),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        schema="catalog",
    )
    deposit_products = sa.table(
        "deposit_products",
        sa.column("product_code", sa.String),
        sa.column("product_name", sa.String),
        sa.column("annual_percentage_yield", sa.Numeric),
        sa.column("monthly_maintenance_fee_cents", sa.BigInteger),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        schema="catalog",
    )
    merchant_category_codes = sa.table(
        "merchant_category_codes",
        sa.column("mcc", sa.String),
        sa.column("primary_category", sa.String),
        sa.column("detailed_category", sa.String),
        sa.column("updated_at", sa.DateTime),
        schema="merchants",
    )
    merchant_master = sa.table(
        "merchant_master",
        sa.column("id", utils.database.UniversalUUID()),
        sa.column("merchant_id", sa.String),
        sa.column("clean_name", sa.String),
        sa.column("default_mcc", sa.String),
        sa.column("merchant_domain", sa.String),
        sa.column("logo_url", sa.String),
        sa.column("is_subscription", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
        schema="merchants",
    )
    merchant_stores = sa.table(
        "merchant_stores",
        sa.column("id", utils.database.UniversalUUID()),
        sa.column("merchant_id", sa.String),
        sa.column("location_name", sa.String),
        sa.column("raw_descriptor", sa.String),
        sa.column("country_code", sa.String),
        sa.column("is_international", sa.Boolean),
        sa.column("risk_score", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
        schema="merchants",
    )
    system_settings = sa.table(
        "system_settings",
        sa.column("key", sa.String),
        sa.column("value", sa.String),
        schema="admin",
    )
    retail_locations = sa.table(
        "retail_locations",
        sa.column("id", utils.database.UniversalUUID()),
        sa.column("name", sa.String),
        sa.column("type", sa.String),
        sa.column("address", sa.String),
        sa.column("latitude", sa.Float),
        sa.column("longitude", sa.Float),
        sa.column("hours", sa.String),
        sa.column("phone_number", sa.String),
        schema="operations",
    )

    now = datetime.datetime.now(datetime.timezone.utc)

    op.bulk_insert(
        credit_products,
        [
            {
                **item,
                "is_active": item.get("is_active", True),
                "created_at": now,
            }
            for item in _load_json_resource("credit_products.json")
        ],
    )
    op.bulk_insert(
        deposit_products,
        [
            {
                **item,
                "is_active": item.get("is_active", True),
                "created_at": now,
            }
            for item in _load_json_resource("deposit_products.json")
        ],
    )
    op.bulk_insert(
        merchant_category_codes,
        [
            {
                **item,
                "updated_at": now,
            }
            for item in _load_json_resource("merchant_category_codes.json")
        ],
    )

    merchant_catalog = _load_json_resource("merchant_catalog.json")
    op.bulk_insert(
        merchant_master,
        [
            {
                "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"merchant-master:{item['merchant_id']}"),
                "merchant_id": item["merchant_id"],
                "clean_name": item["clean_name"],
                "default_mcc": item["default_mcc"],
                "merchant_domain": item.get("merchant_domain"),
                "logo_url": item.get("logo_url"),
                "is_subscription": item.get("is_subscription", False),
                "created_at": now,
                "updated_at": now,
            }
            for item in merchant_catalog
        ],
    )

    store_rows = []
    for item in merchant_catalog:
        stores = item.get("stores", [])
        legacy_vars = item.get("store_variations", [])
        if stores:
            for store in stores:
                store_rows.append(
                    {
                        "id": uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"merchant-store:{item['merchant_id']}:{store['raw_descriptor']}",
                        ),
                        "merchant_id": item["merchant_id"],
                        "location_name": store["location_name"],
                        "raw_descriptor": store["raw_descriptor"],
                        "country_code": store.get("country_code", "USA"),
                        "is_international": store.get("is_international", False),
                        "risk_score": store.get("risk_score", 0),
                        "created_at": now,
                        "updated_at": now,
                    }
                )
        elif legacy_vars:
            for idx, descriptor in enumerate(legacy_vars, start=1):
                store_rows.append(
                    {
                        "id": uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            f"merchant-store:{item['merchant_id']}:{descriptor}",
                        ),
                        "merchant_id": item["merchant_id"],
                        "location_name": f"{item['clean_name']} #{idx}",
                        "raw_descriptor": descriptor,
                        "country_code": "USA",
                        "is_international": False,
                        "risk_score": 0,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
        else:
            store_rows.append(
                {
                    "id": uuid.uuid5(
                        uuid.NAMESPACE_DNS,
                        f"merchant-store:{item['merchant_id']}:{item['clean_name'].upper()}",
                    ),
                    "merchant_id": item["merchant_id"],
                    "location_name": item["clean_name"],
                    "raw_descriptor": item["clean_name"].upper(),
                    "country_code": "USA",
                    "is_international": False,
                    "risk_score": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    op.bulk_insert(merchant_stores, store_rows)

    op.bulk_insert(
        system_settings,
        [{"key": key, "value": value} for key, value in _load_json_resource("system_settings.json").items()],
    )
    op.bulk_insert(
        retail_locations,
        [
            {
                "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"retail-location:{item['id']}"),
                "name": item["name"],
                "type": item["type"],
                "address": item["address"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "hours": item.get("hours"),
                "phone_number": item.get("phone_number"),
            }
            for item in _load_jsonl_resource("retail_locations.jsonl")
        ],
    )


def upgrade() -> None:
    """Upgrade schema."""
    schemas = ["admin", "audit", "catalog", "identity", "merchants", "operations", "cards", "kyc", "ledger", "origination", "ref_data"]
    for s in schemas:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
        
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('system_settings',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('key'),
    schema='admin'
    )
    op.create_index(op.f('ix_admin_system_settings_key'), 'system_settings', ['key'], unique=False, schema='admin')
    op.create_table('audit_outbox',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('event_id', sa.String(length=128), nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id'),
    schema='audit'
    )
    op.create_index('idx_audit_outbox_created_at', 'audit_outbox', ['created_at'], unique=False, schema='audit')
    op.create_index('idx_audit_outbox_event_type', 'audit_outbox', ['event_type'], unique=False, schema='audit')
    op.create_table('credit_products',
    sa.Column('product_code', sa.String(length=50), nullable=False),
    sa.Column('product_name', sa.String(length=100), nullable=False),
    sa.Column('min_credit_limit_cents', sa.BigInteger(), nullable=False),
    sa.Column('max_credit_limit_cents', sa.BigInteger(), nullable=False),
    sa.Column('purchase_apr', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('cashback_rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('travel_multiplier', sa.Integer(), nullable=False),
    sa.Column('dining_multiplier', sa.Integer(), nullable=False),
    sa.Column('annual_fee_cents', sa.BigInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('product_code'),
    schema='catalog'
    )
    op.create_table('deposit_products',
    sa.Column('product_code', sa.String(length=50), nullable=False),
    sa.Column('product_name', sa.String(length=100), nullable=False),
    sa.Column('annual_percentage_yield', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('monthly_maintenance_fee_cents', sa.BigInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('product_code'),
    schema='catalog'
    )
    op.create_table('users',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('auth_provider_uid', sa.String(length=128), nullable=False),
    sa.Column('first_name', sa.String(length=100), nullable=True),
    sa.Column('last_name', sa.String(length=100), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone_number', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='identity'
    )
    op.create_index(op.f('ix_identity_users_auth_provider_uid'), 'users', ['auth_provider_uid'], unique=True, schema='identity')
    op.create_index(op.f('ix_identity_users_email'), 'users', ['email'], unique=False, schema='identity')
    op.create_table('merchant_category_codes',
    sa.Column('mcc', sa.String(length=10), nullable=False),
    sa.Column('primary_category', sa.String(length=50), nullable=False),
    sa.Column('detailed_category', sa.String(length=100), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('mcc'),
    schema='merchants'
    )
    op.create_index(op.f('ix_merchants_merchant_category_codes_mcc'), 'merchant_category_codes', ['mcc'], unique=False, schema='merchants')
    op.create_table('merchant_master',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('merchant_id', sa.String(length=100), nullable=False),
    sa.Column('clean_name', sa.String(length=100), nullable=False),
    sa.Column('default_mcc', sa.String(length=10), nullable=False),
    sa.Column('merchant_domain', sa.String(length=100), nullable=True),
    sa.Column('logo_url', sa.String(length=255), nullable=True),
    sa.Column('is_subscription', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='merchants'
    )
    op.create_index('idx_merchants_domain', 'merchant_master', ['merchant_domain'], unique=False, schema='merchants')
    op.create_index('idx_merchants_mcc', 'merchant_master', ['default_mcc'], unique=False, schema='merchants')
    op.create_index(op.f('ix_merchants_merchant_master_merchant_id'), 'merchant_master', ['merchant_id'], unique=True, schema='merchants')
    op.create_table('retail_locations',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('address', sa.String(length=255), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('hours', sa.String(length=255), nullable=True),
    sa.Column('phone_number', sa.String(length=50), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='operations'
    )
    op.create_table('support_escalations',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('room_name', sa.String(), nullable=False),
    sa.Column('customer_id', sa.String(), nullable=False),
    sa.Column('reason', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('transcript', sa.JSON(), nullable=True),
    sa.Column('assigned_to', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='operations'
    )
    op.create_table('credit_accounts',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('customer_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('product_code', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('credit_limit_cents', sa.BigInteger(), nullable=False),
    sa.Column('cleared_balance_cents', sa.BigInteger(), nullable=False),
    sa.Column('available_credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('payment_due_date', sa.DateTime(), nullable=True),
    sa.Column('statement_close_date', sa.DateTime(), nullable=True),
    sa.Column('last_payment_date', sa.DateTime(), nullable=True),
    sa.Column('last_payment_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['customer_id'], ['identity.users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_code'], ['catalog.credit_products.product_code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    schema='cards'
    )
    op.create_index('idx_credit_accounts_customer_id', 'credit_accounts', ['customer_id'], unique=False, schema='cards')
    op.create_index('idx_credit_accounts_product_code', 'credit_accounts', ['product_code'], unique=False, schema='cards')
    op.create_table('user_addresses',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('address_type', sa.String(length=50), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('street_line_1', sa.String(length=255), nullable=False),
    sa.Column('street_line_2', sa.String(length=255), nullable=True),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('state', sa.String(length=50), nullable=False),
    sa.Column('postal_code', sa.String(length=20), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('verified_by_doc_ai', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='identity'
    )
    op.create_index('idx_user_addresses_user_id', 'user_addresses', ['user_id'], unique=False, schema='identity')
    op.create_index(op.f('ix_identity_user_addresses_city'), 'user_addresses', ['city'], unique=False, schema='identity')
    op.create_table('user_devices',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('device_token', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='identity'
    )
    op.create_index('idx_user_devices_user_id', 'user_devices', ['user_id'], unique=False, schema='identity')
    op.create_table('user_secure_messages',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('message_id', sa.String(length=128), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('sender', sa.String(length=50), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('thread_id', sa.String(length=128), nullable=False),
    sa.Column('is_user_read', sa.Boolean(), nullable=True),
    sa.Column('is_agent_read', sa.Boolean(), nullable=True),
    sa.Column('deleted', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='identity'
    )
    op.create_index('idx_secure_msgs_thread_id', 'user_secure_messages', ['thread_id'], unique=False, schema='identity')
    op.create_index('idx_secure_msgs_user_id', 'user_secure_messages', ['user_id'], unique=False, schema='identity')
    op.create_index(op.f('ix_identity_user_secure_messages_message_id'), 'user_secure_messages', ['message_id'], unique=True, schema='identity')
    op.create_table('kyc_records',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('encrypted_pii', sa.LargeBinary(), nullable=False),
    sa.Column('wrapped_dek', sa.LargeBinary(), nullable=False),
    sa.Column('encryption_iv', sa.LargeBinary(), nullable=False),
    sa.Column('auth_tag', sa.LargeBinary(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    schema='kyc'
    )
    op.create_index('idx_kyc_records_user_id', 'kyc_records', ['user_id'], unique=False, schema='kyc')
    op.create_table('user_credit_profiles',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('credit_score', sa.Integer(), nullable=False),
    sa.Column('credit_tier', sa.String(length=50), nullable=False),
    sa.Column('stated_annual_income_cents', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id'),
    schema='kyc'
    )
    op.create_table('accounts',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=True),
    sa.Column('account_number', sa.String(length=50), nullable=False),
    sa.Column('account_type', sa.String(length=30), nullable=False),
    sa.Column('product_name', sa.String(length=100), nullable=False),
    sa.Column('product_code', sa.String(length=50), nullable=False),
    sa.Column('routing_number', sa.String(length=9), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('credit_limit_cents', sa.BigInteger(), nullable=False),
    sa.Column('cleared_balance_cents', sa.BigInteger(), nullable=False),
    sa.Column('available_credit_cents', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['product_code'], ['catalog.deposit_products.product_code'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_number'),
    schema='ledger'
    )
    op.create_index('idx_accounts_product_code', 'accounts', ['product_code'], unique=False, schema='ledger')
    op.create_index('idx_accounts_user_id', 'accounts', ['user_id'], unique=False, schema='ledger')
    op.create_table('transactions',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=128), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=True),
    sa.Column('response_payload', sa.Text(), nullable=True),
    sa.Column('response_status', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key'),
    schema='ledger'
    )
    op.create_index('idx_transactions_user_id', 'transactions', ['user_id'], unique=False, schema='ledger')
    op.create_table('merchant_stores',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('merchant_id', sa.String(length=100), nullable=False),
    sa.Column('location_name', sa.String(length=100), nullable=False),
    sa.Column('raw_descriptor', sa.String(length=150), nullable=False),
    sa.Column('country_code', sa.String(length=3), nullable=False),
    sa.Column('is_international', sa.Boolean(), nullable=False),
    sa.Column('risk_score', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['merchant_id'], ['merchants.merchant_master.merchant_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    schema='merchants'
    )
    op.create_index('idx_stores_country', 'merchant_stores', ['country_code', 'is_international'], unique=False, schema='merchants')
    op.create_index('idx_stores_descriptor', 'merchant_stores', ['raw_descriptor'], unique=False, schema='merchants')
    op.create_index('idx_stores_risk', 'merchant_stores', ['risk_score'], unique=False, schema='merchants')
    op.create_index(op.f('ix_merchants_merchant_stores_merchant_id'), 'merchant_stores', ['merchant_id'], unique=False, schema='merchants')
    op.create_index(op.f('ix_merchants_merchant_stores_raw_descriptor'), 'merchant_stores', ['raw_descriptor'], unique=False, schema='merchants')
    op.create_table('applications',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('application_id', sa.String(length=128), nullable=False),
    sa.Column('user_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('product_category', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('last_updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['identity.users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id'),
    schema='origination'
    )
    op.create_index('idx_applications_user_id', 'applications', ['user_id'], unique=False, schema='origination')
    op.create_table('issued_card',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('account_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('cardholder_name', sa.String(length=150), nullable=False),
    sa.Column('card_token', sa.String(length=255), nullable=False),
    sa.Column('last_four', sa.String(length=4), nullable=False),
    sa.Column('encrypted_pin_block', sa.String(length=255), nullable=True),
    sa.Column('pin_fail_count', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('exp_month', sa.Integer(), nullable=False),
    sa.Column('exp_year', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('is_virtual', sa.Boolean(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['cards.credit_accounts.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('card_token'),
    schema='cards'
    )
    op.create_index('idx_issued_card_token', 'issued_card', ['card_token'], unique=True, schema='cards')
    op.create_table('account_ledger',
    sa.Column('entry_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('transaction_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('account_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('entry_type', sa.String(length=10), nullable=False),
    sa.Column('posted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['ledger.accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['transaction_id'], ['ledger.transactions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('entry_id'),
    schema='ledger'
    )
    op.create_index('idx_ledger_account_id', 'account_ledger', ['account_id'], unique=False, schema='ledger')
    op.create_index('idx_ledger_transaction_id', 'account_ledger', ['transaction_id'], unique=False, schema='ledger')
    op.create_table('application_artifacts',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('artifact_id', sa.String(length=128), nullable=False),
    sa.Column('application_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('customer_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('claimed_artifact_type', sa.String(length=100), nullable=True),
    sa.Column('actual_artifact_type', sa.String(length=100), nullable=True),
    sa.Column('classification_confidence', sa.Float(), nullable=True),
    sa.Column('extraction_payload', sa.Text(), nullable=True),
    sa.Column('audit_metadata', sa.Text(), nullable=True),
    sa.Column('verification_tier', sa.String(length=50), nullable=True),
    sa.Column('gcs_uri', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('version_id', sa.String(length=128), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['origination.applications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['identity.users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('artifact_id'),
    schema='origination'
    )
    op.create_index('idx_artifacts_application_id', 'application_artifacts', ['application_id'], unique=False, schema='origination')
    op.create_index('idx_artifacts_customer_id', 'application_artifacts', ['customer_id'], unique=False, schema='origination')
    op.create_table('credit_card_applications',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('application_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('requested_limit_cents', sa.BigInteger(), nullable=True),
    sa.Column('card_product_id', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['origination.applications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id'),
    schema='origination'
    )
    op.create_table('deposit_applications',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('application_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('deposit_product_name', sa.String(length=100), nullable=True),
    sa.Column('initial_deposit_cents', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['origination.applications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id'),
    schema='origination'
    )
    op.create_table('mortgage_applications',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('application_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('requested_loan_cents', sa.BigInteger(), nullable=True),
    sa.Column('property_address', sa.String(length=255), nullable=True),
    sa.Column('estimated_value_cents', sa.BigInteger(), nullable=True),
    sa.Column('loan_term_months', sa.Integer(), nullable=True),
    sa.Column('down_payment_cents', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['application_id'], ['origination.applications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id'),
    schema='origination'
    )
    op.create_table('transaction_authorization',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('card_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('account_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('transaction_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('transaction_currency', sa.String(length=3), nullable=False),
    sa.Column('billing_amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('billing_currency', sa.String(length=3), nullable=False),
    sa.Column('exchange_rate', sa.Numeric(precision=18, scale=9), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('decline_reason', sa.String(length=50), nullable=False),
    sa.Column('auth_code', sa.String(length=6), nullable=False),
    sa.Column('retrieval_reference_number', sa.String(length=12), nullable=False),
    sa.Column('card_network', sa.String(length=30), nullable=False),
    sa.Column('merchant_category_code', sa.String(length=4), nullable=False),
    sa.Column('merchant_name', sa.String(length=255), nullable=True),
    sa.Column('fraud_risk_score', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['cards.credit_accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['card_id'], ['cards.issued_card.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    schema='cards'
    )
    op.create_index('idx_auth_account_status', 'transaction_authorization', ['account_id', 'status'], unique=False, schema='cards')
    op.create_table('posted_transactions',
    sa.Column('id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('account_id', utils.database.UniversalUUID(), nullable=False),
    sa.Column('authorization_id', utils.database.UniversalUUID(), nullable=True),
    sa.Column('auth_code', sa.String(length=6), nullable=True),
    sa.Column('retrieval_reference_number', sa.String(length=12), nullable=True),
    sa.Column('amount_cents', sa.BigInteger(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('posted_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['account_id'], ['cards.credit_accounts.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['authorization_id'], ['cards.transaction_authorization.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    schema='cards'
    )
    op.create_index('idx_ledger_account', 'posted_transactions', ['account_id'], unique=False, schema='cards')
    op.create_index('idx_ledger_account_posted', 'posted_transactions', ['account_id', 'posted_at'], unique=False, schema='cards')
    # ### end Alembic commands ###

    _seed_reference_tables()

    if op.get_bind().dialect.name == "postgresql" and os.getenv("SKIP_IAM_GRANTS") != "true":
        try:
            from utils.gcp import get_project_id
            project_id = get_project_id()
            if str(project_id) == "None":
                project_id = os.getenv("PROJECT_ID")
        except Exception:
            project_id = os.getenv("PROJECT_ID")

        users_by_schema = {
            "identity": [], "kyc": [], "ledger": [], "cards": [], "operations": [], "ref_data": [], "merchants": []
        }
        if project_id and str(project_id) != "None":
            main_sa = f"banking-service-sa@{project_id}.iam"
            for s in users_by_schema:
                users_by_schema[s].append(main_sa)
            users_by_schema["kyc"].append(f"kyc-service-sa@{project_id}.iam")
            users_by_schema["ledger"].append(f"ledger-service-sa@{project_id}.iam")
            users_by_schema["ref_data"].extend([f"kyc-service-sa@{project_id}.iam", f"ledger-service-sa@{project_id}.iam"])
            users_by_schema["merchants"].extend([f"kyc-service-sa@{project_id}.iam", f"ledger-service-sa@{project_id}.iam"])

        iam_dba_users_env = os.getenv("IAM_DBA_USERS")
        if iam_dba_users_env:
            for user in [u.strip() for u in iam_dba_users_env.split(",") if u.strip()]:
                for s in users_by_schema:
                    users_by_schema[s].append(user)

        all_users = set(u for u_list in users_by_schema.values() for u in u_list)

        iam_viewer_users_env = os.getenv("IAM_DB_VIEWER_USERS")
        viewer_users_by_schema = {s: [] for s in users_by_schema}
        if iam_viewer_users_env:
            for user in [u.strip() for u in iam_viewer_users_env.split(",") if u.strip()]:
                for s in viewer_users_by_schema:
                    viewer_users_by_schema[s].append(user)

        all_viewer_users = set(u for u_list in viewer_users_by_schema.values() for u in u_list)

        for user in all_users | all_viewer_users:
            try:
                op.execute(f'DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = \'{user}\') THEN CREATE ROLE "{user}" NOLOGIN; END IF; END $$;')
            except Exception:
                pass

        for schema_name, users in users_by_schema.items():
            for user in users:
                try:
                    op.execute(f'GRANT USAGE ON SCHEMA {schema_name} TO "{user}";')
                    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_name} TO "{user}";')
                    op.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema_name} TO "{user}";')
                    op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{user}";')
                    op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT ALL PRIVILEGES ON SEQUENCES TO "{user}";')
                except Exception:
                    pass

        for schema_name, users in viewer_users_by_schema.items():
            for user in users:
                try:
                    op.execute(f'GRANT USAGE ON SCHEMA {schema_name} TO "{user}";')
                    op.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA {schema_name} TO "{user}";')
                    op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} GRANT SELECT ON TABLES TO "{user}";')
                except Exception:
                    pass

        db_user = os.getenv("CDC_REPLICATION_USER", "banking_bq_connector")
        conn = op.get_bind()
        try:
            user_exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :username"), {"username": db_user}).scalar()
            if user_exists:
                has_priv = conn.execute(text("""SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = CURRENT_USER AND (rolsuper = true OR rolreplication = true));""")).scalar()
                if has_priv:
                    try:
                        with conn.begin_nested():
                            conn.execute(text(f'ALTER ROLE "{db_user}" WITH REPLICATION;'))
                    except Exception:
                        pass
                for schema_name in ["cards", "origination", "identity"]:
                    try:
                        with conn.begin_nested():
                            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema_name}" TO "{db_user}";'))
                            conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema_name}" TO "{db_user}";'))
                            conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema_name}" GRANT SELECT ON TABLES TO "{db_user}";'))
                    except Exception:
                        pass
            try:
                with conn.begin_nested():
                    pub_exists = conn.execute(text("SELECT 1 FROM pg_publication WHERE pubname = 'datastream_publication'")).scalar()
                    if not pub_exists:
                        conn.execute(text('CREATE PUBLICATION datastream_publication FOR ALL TABLES;'))
            except Exception:
                pass
            try:
                wal_level = conn.execute(text("SHOW wal_level;")).scalar()
                if wal_level == 'logical':
                    has_priv = conn.execute(text("""SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = CURRENT_USER AND (rolsuper = true OR rolreplication = true));""")).scalar()
                    if has_priv:
                        with conn.begin_nested():
                            slot_exists = conn.execute(text("SELECT 1 FROM pg_replication_slots WHERE slot_name = 'datastream_replication_slot'")).scalar()
                            if not slot_exists:
                                conn.execute(text("SELECT pg_create_logical_replication_slot('datastream_replication_slot', 'pgoutput');"))
            except Exception:
                pass
        except Exception:
            pass


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    try:
        if conn.dialect.name == "postgresql":
            wal_level = conn.execute(text("SHOW wal_level;")).scalar()
            if wal_level == 'logical':
                with conn.begin_nested():
                    conn.execute(text("SELECT pg_drop_replication_slot('datastream_replication_slot') WHERE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'datastream_replication_slot');"))
    except Exception:
        pass
        
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('idx_ledger_account_posted', table_name='posted_transactions', schema='cards')
    op.drop_index('idx_ledger_account', table_name='posted_transactions', schema='cards')
    op.drop_table('posted_transactions', schema='cards')
    op.drop_index('idx_auth_account_status', table_name='transaction_authorization', schema='cards')
    op.drop_table('transaction_authorization', schema='cards')
    op.drop_table('mortgage_applications', schema='origination')
    op.drop_table('deposit_applications', schema='origination')
    op.drop_table('credit_card_applications', schema='origination')
    op.drop_index('idx_artifacts_customer_id', table_name='application_artifacts', schema='origination')
    op.drop_index('idx_artifacts_application_id', table_name='application_artifacts', schema='origination')
    op.drop_table('application_artifacts', schema='origination')
    op.drop_index('idx_ledger_transaction_id', table_name='account_ledger', schema='ledger')
    op.drop_index('idx_ledger_account_id', table_name='account_ledger', schema='ledger')
    op.drop_table('account_ledger', schema='ledger')
    op.drop_index('idx_issued_card_token', table_name='issued_card', schema='cards')
    op.drop_table('issued_card', schema='cards')
    op.drop_index('idx_applications_user_id', table_name='applications', schema='origination')
    op.drop_table('applications', schema='origination')
    op.drop_index(op.f('ix_merchants_merchant_stores_raw_descriptor'), table_name='merchant_stores', schema='merchants')
    op.drop_index(op.f('ix_merchants_merchant_stores_merchant_id'), table_name='merchant_stores', schema='merchants')
    op.drop_index('idx_stores_risk', table_name='merchant_stores', schema='merchants')
    op.drop_index('idx_stores_descriptor', table_name='merchant_stores', schema='merchants')
    op.drop_index('idx_stores_country', table_name='merchant_stores', schema='merchants')
    op.drop_table('merchant_stores', schema='merchants')
    op.drop_index('idx_transactions_user_id', table_name='transactions', schema='ledger')
    op.drop_table('transactions', schema='ledger')
    op.drop_index('idx_accounts_user_id', table_name='accounts', schema='ledger')
    op.drop_index('idx_accounts_product_code', table_name='accounts', schema='ledger')
    op.drop_table('accounts', schema='ledger')
    op.drop_table('user_credit_profiles', schema='kyc')
    op.drop_index('idx_kyc_records_user_id', table_name='kyc_records', schema='kyc')
    op.drop_table('kyc_records', schema='kyc')
    op.drop_index(op.f('ix_identity_user_secure_messages_message_id'), table_name='user_secure_messages', schema='identity')
    op.drop_index('idx_secure_msgs_user_id', table_name='user_secure_messages', schema='identity')
    op.drop_index('idx_secure_msgs_thread_id', table_name='user_secure_messages', schema='identity')
    op.drop_table('user_secure_messages', schema='identity')
    op.drop_index('idx_user_devices_user_id', table_name='user_devices', schema='identity')
    op.drop_table('user_devices', schema='identity')
    op.drop_index(op.f('ix_identity_user_addresses_city'), table_name='user_addresses', schema='identity')
    op.drop_index('idx_user_addresses_user_id', table_name='user_addresses', schema='identity')
    op.drop_table('user_addresses', schema='identity')
    op.drop_index('idx_credit_accounts_product_code', table_name='credit_accounts', schema='cards')
    op.drop_index('idx_credit_accounts_customer_id', table_name='credit_accounts', schema='cards')
    op.drop_table('credit_accounts', schema='cards')
    op.drop_table('support_escalations', schema='operations')
    op.drop_table('retail_locations', schema='operations')
    op.drop_index(op.f('ix_merchants_merchant_master_merchant_id'), table_name='merchant_master', schema='merchants')
    op.drop_index('idx_merchants_mcc', table_name='merchant_master', schema='merchants')
    op.drop_index('idx_merchants_domain', table_name='merchant_master', schema='merchants')
    op.drop_table('merchant_master', schema='merchants')
    op.drop_index(op.f('ix_merchants_merchant_category_codes_mcc'), table_name='merchant_category_codes', schema='merchants')
    op.drop_table('merchant_category_codes', schema='merchants')
    op.drop_index(op.f('ix_identity_users_email'), table_name='users', schema='identity')
    op.drop_index(op.f('ix_identity_users_auth_provider_uid'), table_name='users', schema='identity')
    op.drop_table('users', schema='identity')
    op.drop_table('deposit_products', schema='catalog')
    op.drop_table('credit_products', schema='catalog')
    op.drop_index('idx_audit_outbox_event_type', table_name='audit_outbox', schema='audit')
    op.drop_index('idx_audit_outbox_created_at', table_name='audit_outbox', schema='audit')
    op.drop_table('audit_outbox', schema='audit')
    op.drop_index(op.f('ix_admin_system_settings_key'), table_name='system_settings', schema='admin')
    op.drop_table('system_settings', schema='admin')
    # ### end Alembic commands ###
