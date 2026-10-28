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

"""Single owner of the credit product catalog (catalog.credit_products).

Guarantees:
- ``sync_credit_product_catalog`` makes the table match credit_products.json:
  it validates every row, inserts missing products and overwrites changed
  terms. It is idempotent and never deletes (credit accounts reference
  products with ON DELETE RESTRICT); retire a product with ``is_active: false``.
- ``list_active_credit_products`` returns active products ordered by
  ``display_order`` then ``product_code``.
- ``find_active_credit_product`` returns None for unknown and inactive codes
  alike, so callers have one refusal path.
"""
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from models.credit_card import CreditProduct
from models.credit_product_catalog import (
    CreditProductResponse,
    CreditProductSeed,
    IntroAprPresentation,
    MoneyPresentation,
    RatePresentation,
    RewardsPresentation,
)
from models.money import Money
from services.money_presentation import project_money

CREDIT_PRODUCTS_SEED_PATH = (
    Path(__file__).resolve().parents[1] / "resources" / "data" / "credit_products.json"
)
_RATE_QUANTUM = Decimal("0.0001")


def load_credit_product_seed(path: Path = CREDIT_PRODUCTS_SEED_PATH) -> list[CreditProductSeed]:
    """Parse and validate the catalog seed; raises on any invalid or duplicate row."""
    with path.open("r", encoding="utf-8") as handle:
        rows = [CreditProductSeed.model_validate(item) for item in json.load(handle)]
    codes = [row.product_code for row in rows]
    duplicates = sorted({code for code in codes if codes.count(code) > 1})
    if duplicates:
        raise ValueError(f"Duplicate credit product codes in seed: {duplicates}")
    return rows


def sync_credit_product_catalog(
    db: Session, seed: list[CreditProductSeed] | None = None
) -> None:
    """Upsert the catalog from its seed. Unchanged rows produce no UPDATE."""
    rows = load_credit_product_seed() if seed is None else seed
    existing = {
        product.product_code: product
        for product in db.query(CreditProduct).filter(
            CreditProduct.product_code.in_([row.product_code for row in rows])
        )
    }
    for row in rows:
        values = row.model_dump()
        product = existing.get(row.product_code)
        if product is None:
            db.add(CreditProduct(**values))
            continue
        for column, value in values.items():
            if getattr(product, column) != value:
                setattr(product, column, value)
    db.flush()


def list_active_credit_products(db: Session) -> list[CreditProduct]:
    return (
        db.query(CreditProduct)
        .filter(CreditProduct.is_active.is_(True))
        .order_by(CreditProduct.display_order, CreditProduct.product_code)
        .all()
    )


def find_active_credit_product(db: Session, product_code: str) -> CreditProduct | None:
    return (
        db.query(CreditProduct)
        .filter(
            CreditProduct.product_code == product_code,
            CreditProduct.is_active.is_(True),
        )
        .one_or_none()
    )


def _money(amount_minor: int, currency_code: str) -> MoneyPresentation:
    return MoneyPresentation.model_validate(
        project_money(Money(amount_minor=int(amount_minor), currency_code=currency_code))
    )


def _rate(value) -> RatePresentation:
    rate = Decimal(str(value)).quantize(_RATE_QUANTUM)
    percent = (rate * 100).normalize()
    return RatePresentation(rate=str(rate), display_text=f"{percent:f}%")


def _intro(apr, months) -> IntroAprPresentation | None:
    if apr is None:
        return None
    rate = _rate(apr)
    return IntroAprPresentation(
        apr=rate, months=months, display_text=f"{rate.display_text} intro APR for {months} months"
    )


def _rewards(product: CreditProduct) -> RewardsPresentation:
    cashback = _rate(product.cashback_rate)
    travel, dining = product.travel_multiplier, product.dining_multiplier
    if Decimal(cashback.rate) > 0:
        kind, text = "CASHBACK", f"{cashback.display_text} cash back on all purchases"
    elif travel > 1 or dining > 1:
        kind = "POINTS"
        text = f"{travel}x points on travel, {dining}x points on dining, 1x points on everything else"
    else:
        kind, text = "NONE", "No rewards program"
    return RewardsPresentation(
        type=kind,
        cashback_rate=cashback,
        travel_multiplier=travel,
        dining_multiplier=dining,
        display_text=text,
    )


def present_credit_product(product: CreditProduct) -> CreditProductResponse:
    currency = product.currency_code
    return CreditProductResponse(
        product_code=product.product_code,
        product_name=product.product_name,
        display_order=product.display_order,
        tagline=product.tagline,
        best_for=product.best_for,
        is_secured=product.is_secured,
        currency_code=currency,
        features=list(product.features or []),
        min_credit_limit=_money(product.min_credit_limit_cents, currency),
        max_credit_limit=_money(product.max_credit_limit_cents, currency),
        annual_fee=_money(product.annual_fee_cents, currency),
        purchase_apr=_rate(product.purchase_apr),
        intro_purchase_apr=_intro(product.intro_purchase_apr, product.intro_purchase_apr_months),
        intro_balance_transfer_apr=_intro(
            product.intro_balance_transfer_apr, product.intro_balance_transfer_apr_months
        ),
        penalty_apr=_rate(product.penalty_apr) if product.penalty_apr is not None else None,
        balance_transfer_fee_rate=_rate(product.balance_transfer_fee_rate),
        balance_transfer_fee_minimum=_money(product.balance_transfer_fee_minimum_minor, currency),
        cash_advance_apr=_rate(product.cash_advance_apr),
        cash_advance_fee_rate=_rate(product.cash_advance_fee_rate),
        cash_advance_fee_minimum=_money(product.cash_advance_fee_minimum_minor, currency),
        foreign_transaction_fee_rate=_rate(product.foreign_transaction_fee_rate),
        late_fee_maximum=_money(product.late_fee_maximum_minor, currency),
        returned_payment_fee_maximum=_money(product.returned_payment_fee_maximum_minor, currency),
        rewards=_rewards(product),
    )
