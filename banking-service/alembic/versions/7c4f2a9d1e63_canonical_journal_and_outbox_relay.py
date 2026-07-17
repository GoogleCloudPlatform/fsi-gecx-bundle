"""Canonical journal, statement projection, and outbox relay state.

Revision ID: 7c4f2a9d1e63
Revises: 2ea57c78ba89
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import utils.database


revision: str = "7c4f2a9d1e63"
down_revision: Union[str, Sequence[str], None] = "2ea57c78ba89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_outbox",
        sa.Column("schema_version", sa.BigInteger(), nullable=False, server_default="1"),
        schema="audit",
    )
    op.create_table(
        "outbox_relay_checkpoint",
        sa.Column("relay_name", sa.String(length=100), nullable=False),
        sa.Column("last_created_at", sa.DateTime(), nullable=True),
        sa.Column("last_event_id", sa.String(length=128), nullable=True),
        sa.Column("published_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("relay_name"),
        schema="audit",
    )

    op.alter_column(
        "accounts",
        "product_code",
        existing_type=sa.String(length=50),
        nullable=True,
        schema="ledger",
    )
    op.add_column(
        "accounts",
        sa.Column("credit_account_id", utils.database.UniversalUUID(), nullable=True),
        schema="ledger",
    )
    op.create_foreign_key(
        "fk_ledger_accounts_credit_account_id",
        "accounts",
        "credit_accounts",
        ["credit_account_id"],
        ["id"],
        source_schema="ledger",
        referent_schema="cards",
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_accounts_credit_account_id",
        "accounts",
        ["credit_account_id"],
        unique=True,
        schema="ledger",
    )

    op.add_column(
        "posted_transactions",
        sa.Column("journal_transaction_id", utils.database.UniversalUUID(), nullable=True),
        schema="cards",
    )
    op.create_foreign_key(
        "fk_posted_transactions_journal_transaction_id",
        "posted_transactions",
        "transactions",
        ["journal_transaction_id"],
        ["id"],
        source_schema="cards",
        referent_schema="ledger",
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_posted_transactions_journal_transaction_id",
        "posted_transactions",
        ["journal_transaction_id"],
        unique=True,
        schema="cards",
    )

    # Normalize legacy signed rows, then create one balancing split for any
    # historical one-sided transaction. A controlled reset after deployment
    # replaces these legacy classifications with the current semantic mapping.
    op.execute("UPDATE ledger.account_ledger SET amount_cents = ABS(amount_cents), entry_type = UPPER(entry_type)")
    op.execute(
        """
        INSERT INTO ledger.accounts (
          id, user_id, account_number, account_type, product_name, product_code,
          routing_number, status, credit_limit_cents, cleared_balance_cents,
          available_credit_cents, currency, opened_at
        ) VALUES (
          '00000000-0000-4000-8000-000000000901', NULL,
          'SYSTEM_LEGACY_JOURNAL_CLEARING', 'SYSTEM',
          'Legacy journal normalization clearing', NULL, '021000021', 'ACTIVE',
          0, 0, 0, 'USD', CURRENT_TIMESTAMP
        ) ON CONFLICT (account_number) DO NOTHING
        """
    )
    op.execute(
        """
        WITH imbalances AS (
          SELECT transaction_id,
                 SUM(CASE WHEN entry_type = 'DEBIT' THEN amount_cents ELSE -amount_cents END) AS net
          FROM ledger.account_ledger
          GROUP BY transaction_id
        )
        INSERT INTO ledger.account_ledger (
          entry_id, transaction_id, account_id, amount_cents, entry_type, posted_at
        )
        SELECT (
          substr(md5('legacy-balance:' || transaction_id::text), 1, 8) || '-' ||
          substr(md5('legacy-balance:' || transaction_id::text), 9, 4) || '-' ||
          substr(md5('legacy-balance:' || transaction_id::text), 13, 4) || '-' ||
          substr(md5('legacy-balance:' || transaction_id::text), 17, 4) || '-' ||
          substr(md5('legacy-balance:' || transaction_id::text), 21, 12)
        )::uuid,
        transaction_id,
        '00000000-0000-4000-8000-000000000901'::uuid,
        ABS(net),
        CASE WHEN net > 0 THEN 'CREDIT' ELSE 'DEBIT' END,
        CURRENT_TIMESTAMP
        FROM imbalances
        WHERE net <> 0
        ON CONFLICT (entry_id) DO NOTHING
        """
    )

    # Establish journal receivable accounts and balanced transactions for
    # pre-migration card statement rows, then link the projection.
    op.execute(
        """
        INSERT INTO ledger.accounts (
          id, user_id, account_number, account_type, product_name, product_code,
          credit_account_id, routing_number, status, credit_limit_cents,
          cleared_balance_cents, available_credit_cents, currency, opened_at
        )
        SELECT (
          substr(md5('credit-journal:' || c.id::text), 1, 8) || '-' ||
          substr(md5('credit-journal:' || c.id::text), 9, 4) || '-' ||
          substr(md5('credit-journal:' || c.id::text), 13, 4) || '-' ||
          substr(md5('credit-journal:' || c.id::text), 17, 4) || '-' ||
          substr(md5('credit-journal:' || c.id::text), 21, 12)
        )::uuid,
        c.customer_id, 'CARD-' || c.id::text, 'CREDIT_CARD',
        'Card receivable (' || c.product_code || ')', NULL, c.id,
        '021000021', c.status, c.credit_limit_cents, c.cleared_balance_cents,
        c.available_credit_cents, COALESCE(c.currency, 'USD'), c.opened_at
        FROM cards.credit_accounts c
        ON CONFLICT (credit_account_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO ledger.accounts (
          id, user_id, account_number, account_type, product_name, product_code,
          routing_number, status, credit_limit_cents, cleared_balance_cents,
          available_credit_cents, currency, opened_at
        ) VALUES (
          '00000000-0000-4000-8000-000000000902', NULL,
          'SYSTEM_CARD_MERCHANT_CLEARING', 'SYSTEM',
          'Card network merchant settlement clearing', NULL, '021000021',
          'ACTIVE', 0, 0, 0, 'USD', CURRENT_TIMESTAMP
        ) ON CONFLICT (account_number) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO ledger.transactions (
          id, idempotency_key, user_id, status, description, created_at
        )
        SELECT (
          substr(md5('statement-journal:' || p.id::text), 1, 8) || '-' ||
          substr(md5('statement-journal:' || p.id::text), 9, 4) || '-' ||
          substr(md5('statement-journal:' || p.id::text), 13, 4) || '-' ||
          substr(md5('statement-journal:' || p.id::text), 17, 4) || '-' ||
          substr(md5('statement-journal:' || p.id::text), 21, 12)
        )::uuid,
        'backfill-card-statement:' || p.id::text,
        c.customer_id, 'COMPLETED', p.description, p.posted_at
        FROM cards.posted_transactions p
        JOIN cards.credit_accounts c ON c.id = p.account_id
        WHERE p.amount_cents <> 0 AND p.journal_transaction_id IS NULL
        ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    op.execute(
        """
        WITH statement_posts AS (
          SELECT p.*, a.id AS journal_account_id, t.id AS transaction_id
          FROM cards.posted_transactions p
          JOIN ledger.accounts a ON a.credit_account_id = p.account_id
          JOIN ledger.transactions t ON t.idempotency_key = 'backfill-card-statement:' || p.id::text
          WHERE p.amount_cents <> 0
        ), splits AS (
          SELECT p.id AS statement_id, p.transaction_id, p.journal_account_id AS account_id,
                 ABS(p.amount_cents) AS amount_cents,
                 CASE WHEN p.amount_cents < 0 THEN 'DEBIT' ELSE 'CREDIT' END AS entry_type,
                 p.posted_at, 'card' AS split_name
          FROM statement_posts p
          UNION ALL
          SELECT p.id, p.transaction_id, '00000000-0000-4000-8000-000000000902'::uuid,
                 ABS(p.amount_cents),
                 CASE WHEN p.amount_cents < 0 THEN 'CREDIT' ELSE 'DEBIT' END,
                 p.posted_at, 'counterparty'
          FROM statement_posts p
        )
        INSERT INTO ledger.account_ledger (
          entry_id, transaction_id, account_id, amount_cents, entry_type, posted_at
        )
        SELECT (
          substr(md5('statement-split:' || statement_id::text || ':' || split_name), 1, 8) || '-' ||
          substr(md5('statement-split:' || statement_id::text || ':' || split_name), 9, 4) || '-' ||
          substr(md5('statement-split:' || statement_id::text || ':' || split_name), 13, 4) || '-' ||
          substr(md5('statement-split:' || statement_id::text || ':' || split_name), 17, 4) || '-' ||
          substr(md5('statement-split:' || statement_id::text || ':' || split_name), 21, 12)
        )::uuid,
        transaction_id, account_id, amount_cents, entry_type, posted_at
        FROM splits
        ON CONFLICT (entry_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE cards.posted_transactions p
        SET journal_transaction_id = t.id
        FROM ledger.transactions t
        WHERE t.idempotency_key = 'backfill-card-statement:' || p.id::text
          AND p.journal_transaction_id IS NULL
        """
    )

    # Every historical journal transaction receives a deterministic version-1
    # financial event. Fresh application posts create the same shape directly.
    op.execute(
        """
        WITH event_rows AS (
          SELECT t.id AS transaction_id, t.description, MIN(e.posted_at) AS posted_at,
                 COALESCE(MIN(a.currency), 'USD') AS currency,
                 jsonb_agg(jsonb_build_object(
                   'entry_id', e.entry_id::text,
                   'account_id', e.account_id::text,
                   'direction', e.entry_type,
                   'amount_cents', e.amount_cents
                 ) ORDER BY e.entry_id) AS entries
          FROM ledger.transactions t
          JOIN ledger.account_ledger e ON e.transaction_id = t.id
          LEFT JOIN ledger.accounts a ON a.id = e.account_id
          GROUP BY t.id, t.description
        )
        INSERT INTO audit.audit_outbox (
          id, event_id, event_type, schema_version, payload, created_at
        )
        SELECT deterministic_id, deterministic_id::text,
               'FINANCIAL_TRANSACTION_POSTED', 1,
               jsonb_build_object(
                 'event_id', deterministic_id::text,
                 'schema_version', 1,
                 'transaction_id', transaction_id::text,
                 'event_time', posted_at,
                 'posted_at', posted_at,
                 'currency', currency,
                 'source_type', 'HISTORICAL_LEDGER_BACKFILL',
                 'source_references', jsonb_build_object(),
                 'description', description,
                 'entries', entries
               )::text,
               CURRENT_TIMESTAMP
        FROM (
          SELECT event_rows.*, (
            substr(md5('financial-event:' || transaction_id::text), 1, 8) || '-' ||
            substr(md5('financial-event:' || transaction_id::text), 9, 4) || '-' ||
            substr(md5('financial-event:' || transaction_id::text), 13, 4) || '-' ||
            substr(md5('financial-event:' || transaction_id::text), 17, 4) || '-' ||
            substr(md5('financial-event:' || transaction_id::text), 21, 12)
          )::uuid AS deterministic_id
          FROM event_rows
        ) q
        ON CONFLICT (event_id) DO NOTHING
        """
    )

    op.create_check_constraint(
        "ck_account_ledger_positive_amount",
        "account_ledger",
        "amount_cents > 0",
        schema="ledger",
    )
    op.create_check_constraint(
        "ck_account_ledger_entry_type",
        "account_ledger",
        "entry_type IN ('DEBIT', 'CREDIT')",
        schema="ledger",
    )


def downgrade() -> None:
    op.drop_constraint("ck_account_ledger_entry_type", "account_ledger", schema="ledger", type_="check")
    op.drop_constraint("ck_account_ledger_positive_amount", "account_ledger", schema="ledger", type_="check")
    # Nullable product codes are reserved for the system and card-receivable
    # journal accounts introduced here. Remove their splits before restoring
    # the baseline NOT NULL deposit-account model.
    op.execute("UPDATE cards.posted_transactions SET journal_transaction_id = NULL")
    op.execute(
        """
        DELETE FROM ledger.account_ledger
        WHERE account_id IN (SELECT id FROM ledger.accounts WHERE product_code IS NULL)
        """
    )
    op.execute(
        """
        DELETE FROM ledger.transactions t
        WHERE NOT EXISTS (
          SELECT 1 FROM ledger.account_ledger e WHERE e.transaction_id = t.id
        )
        """
    )
    op.execute("DELETE FROM ledger.accounts WHERE product_code IS NULL")
    op.drop_index("uq_posted_transactions_journal_transaction_id", table_name="posted_transactions", schema="cards")
    op.drop_constraint(
        "fk_posted_transactions_journal_transaction_id",
        "posted_transactions",
        schema="cards",
        type_="foreignkey",
    )
    op.drop_column("posted_transactions", "journal_transaction_id", schema="cards")
    op.drop_index("idx_accounts_credit_account_id", table_name="accounts", schema="ledger")
    op.drop_constraint("fk_ledger_accounts_credit_account_id", "accounts", schema="ledger", type_="foreignkey")
    op.drop_column("accounts", "credit_account_id", schema="ledger")
    op.alter_column(
        "accounts",
        "product_code",
        existing_type=sa.String(length=50),
        nullable=False,
        schema="ledger",
    )
    op.drop_table("outbox_relay_checkpoint", schema="audit")
    op.drop_column("audit_outbox", "schema_version", schema="audit")
