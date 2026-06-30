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

import os
import uuid
import random
import datetime
import logging
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from utils.database import SessionLocal, generate_uuid
from utils.encryption import encrypt_pii

# Models
from models.identity import User
from models.kyc import KYCRecord, UserCreditProfile
from models.origination import Account, AccountLedgerEntry, Transaction
from models.credit_card import CreditAccount, IssuedCard, PostedTransaction, CreditProduct, TransactionAuthorization
from models.origination import DepositProduct
from models.settings import SystemSetting

logger = logging.getLogger(__name__)

PERSONAS = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "first_name": "Eleanor",
        "last_name": "Vance",
        "email": "eleanor.vance@nova.horizon.test",
        "phone_number": "555-0101",
        "ssn": "900-01-0001",
        "credit_score": 785,
        "credit_tier": "PRIME_EXCELLENT",
        "stated_annual_income_cents": 25000000,  # $250,000.00
        "credit_limit_cents": 2500000,          # $25,000.00
        "credit_product": "PLATINUM_TRAVEL_REWARDS",
        "accounts": [
            {"type": "CHECKING", "balance_cents": 4500000, "product_code": "CHECKING_SIGNATURE", "product_name": "Nova Signature Checking"},
            {"type": "SAVINGS", "balance_cents": 15000000, "product_code": "SAVINGS_HIGH_YIELD", "product_name": "Nova High Yield Savings"},
        ],
        "card_token": "tok_visa_eleanor_vance",
        "cardholder_name": "Eleanor Vance"
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "first_name": "Marcus",
        "last_name": "Vance",
        "email": "marcus.vance@nova.horizon.test",
        "phone_number": "555-0102",
        "ssn": "900-01-0002",
        "credit_score": 720,
        "credit_tier": "PRIME_GOOD",
        "stated_annual_income_cents": 9500000,   # $95,000.00
        "credit_limit_cents": 1000000,          # $10,000.00
        "credit_product": "CASHBACK_EVERYDAY",
        "accounts": [
            {"type": "CHECKING", "balance_cents": 800000, "product_code": "CHECKING_EVERYDAY", "product_name": "Nova Everyday Checking"},
            {"type": "SAVINGS", "balance_cents": 2000000, "product_code": "SAVINGS_HIGH_YIELD", "product_name": "Nova High Yield Savings"},
        ],
        "card_token": "tok_visa_marcus_vance",
        "cardholder_name": "Marcus Vance"
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "first_name": "Chloe",
        "last_name": "Gomez",
        "email": "chloe.gomez@nova.horizon.test",
        "phone_number": "555-0103",
        "ssn": "900-01-0003",
        "credit_score": 680,
        "credit_tier": "NEAR_PRIME",
        "stated_annual_income_cents": 6200000,    # $62,000.00
        "credit_limit_cents": 500000,            # $5,000.00
        "credit_product": "CASHBACK_EVERYDAY",
        "accounts": [
            {"type": "CHECKING", "balance_cents": 300000, "product_code": "CHECKING_EVERYDAY", "product_name": "Nova Everyday Checking"}
        ],
        "card_token": "tok_visa_chloe_gomez",
        "cardholder_name": "Chloe Gomez"
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "first_name": "David",
        "last_name": "Miller",
        "email": "david.miller@nova.horizon.test",
        "phone_number": "555-0104",
        "ssn": "900-01-0004",
        "credit_score": 610,
        "credit_tier": "SUBPRIME",
        "stated_annual_income_cents": 4200000,    # $42,000.00
        "credit_limit_cents": 150000,            # $1,500.00
        "credit_product": "SECURED_STARTER",
        "accounts": [
            {"type": "CHECKING", "balance_cents": 120000, "product_code": "CHECKING_EVERYDAY", "product_name": "Nova Everyday Checking"}
        ],
        "card_token": "tok_visa_david_miller",
        "cardholder_name": "David Miller"
    },
    {
        "id": "55555555-5555-4555-8555-555555555555",
        "first_name": "Sarah",
        "last_name": "Jenkins",
        "email": "sarah.jenkins@nova.horizon.test",
        "phone_number": "555-0105",
        "ssn": "900-01-0005",
        "credit_score": 750,
        "credit_tier": "PRIME_EXCELLENT",
        "stated_annual_income_cents": 18500000,  # $185,000.00
        "credit_limit_cents": 3500000,           # $35,000.00
        "credit_product": "BUSINESS_ADVANTAGE",
        "accounts": [
            {"type": "CHECKING", "balance_cents": 6000000, "product_code": "BUSINESS_CHECKING", "product_name": "Nova Business Checking"}
        ],
        "card_token": "tok_visa_sarah_jenkins",
        "cardholder_name": "Sarah Jenkins"
    },
    {
        "id": "12300000-0000-4000-8000-000000000123",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "customer@example.com",
        "phone_number": "555-0199",
        "ssn": "900-01-0123",
        "credit_score": 730,
        "credit_tier": "PRIME_GOOD",
        "stated_annual_income_cents": 8500000,
        "credit_limit_cents": 1000000,
        "credit_product": "CASHBACK_EVERYDAY",
        "accounts": [
            {"type": "CHECKING", "balance_cents": 150000, "product_code": "CHECKING_EVERYDAY", "product_name": "Nova Everyday Checking"},
            {"type": "SAVINGS", "balance_cents": 500000, "product_code": "SAVINGS_HIGH_YIELD", "product_name": "Nova High Yield Savings"},
        ],
        "card_token": "tok_visa_jane_doe",
        "cardholder_name": "Jane Doe",
        "auth_provider_uid": "cust-123"
    }
]

def generate_luhn_card_number(prefix: str, length: int) -> str:
    """Generates a Luhn-valid credit card number string starting with the given prefix."""
    num_str = prefix
    while len(num_str) < length - 1:
        num_str += str(random.randint(0, 9))
    
    digits = [int(ch) for ch in num_str]
    for i in range(len(digits) - 1, -1, -2):
        val = digits[i] * 2
        if val > 9:
            val -= 9
        digits[i] = val
    
    total = sum(digits)
    check_digit = (10 - (total % 10)) % 10
    return num_str + str(check_digit)

def clean_database(db: Session) -> None:
    """Removes all transactional and customer-related tables while preserving catalogs."""
    logger.info("Purging transactional and profile database tables...")
    
    # Bypass engine RBAC constraints during schema cleanup
    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True
        
    # Order matters due to foreign key constraints!
    from models.support import Escalation
    from models.origination import Application, MortgageApplication, CreditCardApplication, DepositApplication, ApplicationArtifact

    db.query(Escalation).delete()
    db.query(PostedTransaction).delete()
    db.query(TransactionAuthorization).delete()
    db.query(IssuedCard).delete()
    db.query(CreditAccount).delete()
    
    db.query(AccountLedgerEntry).delete()
    db.query(Transaction).delete()
    db.query(Account).delete()
    
    db.query(ApplicationArtifact).delete()
    db.query(MortgageApplication).delete()
    db.query(CreditCardApplication).delete()
    db.query(DepositApplication).delete()
    db.query(Application).delete()
    
    db.query(UserCreditProfile).delete()
    db.query(KYCRecord).delete()
    db.query(User).delete()
    
    db.flush()

def seed_catalogs_if_missing(db: Session) -> None:
    """Ensures CreditProduct and DepositProduct catalogs are seeded in the database."""
    if db.query(CreditProduct).count() == 0:
        logger.info("Seeding CreditProduct catalog...")
        products = [
            CreditProduct(product_code="PLATINUM_TRAVEL_REWARDS", product_name="Nova Platinum Travel", min_credit_limit_cents=1500000, max_credit_limit_cents=10000000, purchase_apr=0.1899, cashback_rate=0.0000, travel_multiplier=3, dining_multiplier=3, annual_fee_cents=9500),
            CreditProduct(product_code="CASHBACK_EVERYDAY", product_name="Nova Cashback Everyday", min_credit_limit_cents=300000, max_credit_limit_cents=1500000, purchase_apr=0.2199, cashback_rate=0.0150, travel_multiplier=1, dining_multiplier=1, annual_fee_cents=0),
            CreditProduct(product_code="BUSINESS_ADVANTAGE", product_name="Executive Business Advantage", min_credit_limit_cents=2000000, max_credit_limit_cents=15000000, purchase_apr=0.1799, cashback_rate=0.0200, travel_multiplier=2, dining_multiplier=2, annual_fee_cents=0),
            CreditProduct(product_code="SECURED_STARTER", product_name="Nova Secured Rebuilder", min_credit_limit_cents=50000, max_credit_limit_cents=250000, purchase_apr=0.2799, cashback_rate=0.0100, travel_multiplier=1, dining_multiplier=1, annual_fee_cents=0)
        ]
        db.add_all(products)

    if db.query(DepositProduct).count() == 0:
        logger.info("Seeding DepositProduct catalog...")
        deposits = [
            DepositProduct(product_code="CHECKING_SIGNATURE", product_name="Nova Signature Checking", annual_percentage_yield=0.0005, monthly_maintenance_fee_cents=1500),
            DepositProduct(product_code="CHECKING_EVERYDAY", product_name="Nova Everyday Checking", annual_percentage_yield=0.0000, monthly_maintenance_fee_cents=0),
            DepositProduct(product_code="SAVINGS_HIGH_YIELD", product_name="Nova High Yield Savings", annual_percentage_yield=0.0450, monthly_maintenance_fee_cents=0),
            DepositProduct(product_code="BUSINESS_CHECKING", product_name="Nova Business Checking", annual_percentage_yield=0.0010, monthly_maintenance_fee_cents=1000)
        ]
        db.add_all(deposits)
        
    db.flush()

def seed_system_settings_if_missing(db: Session) -> None:
    """Ensures default voice and live avatar system settings are seeded."""
    default_keys = {
        "voice_agent_hard_timeout_enabled": "false",
        "voice_agent_max_duration": "300",
        "voice_agent_warning_duration": "240",
        "voice_agent_avatar_selection": "random",
        "voice_agent_mock_avatar_enabled": "false"
    }
    for k, v in default_keys.items():
        existing = db.query(SystemSetting).filter(SystemSetting.key == k).first()
        if not existing:
            db.add(SystemSetting(key=k, value=v))
    db.flush()

def perform_algorithmic_seeding(db: Session) -> Dict[str, Any]:
    """Generates user profiles, deposit accounts, credit lines, and cards from persona config."""
    # Seed deterministic generator so results are consistent
    random.seed(42)
    
    clean_database(db)
    seed_catalogs_if_missing(db)
    seed_system_settings_if_missing(db)
    
    cards_manifest = {}
    
    logger.info(f"Initializing {len(PERSONAS)} user profiles and bank accounts...")
    
    for p in PERSONAS:
        user_uuid = uuid.UUID(p["id"])
        auth_uid = p.get("auth_provider_uid") or f"auth-{p['first_name'].lower()}"
        
        # 1. Create User
        user = User(
            id=user_uuid,
            auth_provider_uid=auth_uid,
            first_name=p["first_name"],
            last_name=p["last_name"],
            email=p["email"],
            phone_number=p["phone_number"]
        )
        db.add(user)
        db.flush()
        
        # 2. Create KYCRecord (Envelope encrypted)
        kyc_record_id = uuid.uuid4()
        enc_pii, wrapped_dek, iv, tag = encrypt_pii(
            plaintext_pii=json.dumps({"ssn": p["ssn"], "dob": "1985-06-15"}),
            user_id=str(user_uuid),
            record_id=str(kyc_record_id)
        )
        kyc_rec = KYCRecord(
            id=kyc_record_id,
            user_id=user_uuid,
            encrypted_pii=enc_pii,
            wrapped_dek=wrapped_dek,
            encryption_iv=iv,
            auth_tag=tag
        )
        db.add(kyc_rec)
        
        # 3. Create UserCreditProfile
        credit_prof = UserCreditProfile(
            id=uuid.uuid4(),
            user_id=user_uuid,
            credit_score=p["credit_score"],
            credit_tier=p["credit_tier"],
            stated_annual_income_cents=p["stated_annual_income_cents"]
        )
        db.add(credit_prof)
        db.flush()
        
        # 4. Provision checking/savings deposit accounts
        for acc_conf in p["accounts"]:
            prefix = "CHK" if acc_conf["type"] == "CHECKING" else "SAV"
            acc_num = f"{prefix}-{random.randint(10000000, 99999999)}"
            while db.query(Account).filter_by(account_number=acc_num).first():
                acc_num = f"{prefix}-{random.randint(10000000, 99999999)}"
                
            dep_acc = Account(
                id=uuid.uuid4(),
                user_id=user_uuid,
                account_number=acc_num,
                account_type=acc_conf["type"],
                product_name=acc_conf["product_name"],
                product_code=acc_conf["product_code"],
                cleared_balance_cents=acc_conf["balance_cents"],
                routing_number="021000021",
                status="ACTIVE"
            )
            db.add(dep_acc)
            
        # 5. Create Credit Line Account
        cred_acc_id = uuid.uuid4()
        # Set cleared balance to a minor randomized seed value (e.g. Eleanor has some initial debt)
        debt = random.randint(5000, 20000) if p["first_name"] == "Eleanor" else 0
        cred_acc = CreditAccount(
            id=cred_acc_id,
            customer_id=user_uuid,
            product_code=p["credit_product"],
            status="ACTIVE",
            credit_limit_cents=p["credit_limit_cents"],
            cleared_balance_cents=debt,
            available_credit_cents=p["credit_limit_cents"] - debt,
            payment_due_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=15),
            statement_close_date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=15)
        )
        db.add(cred_acc)
        db.flush()
        
        # 6. Issue Card
        card_id = uuid.uuid4()
        card_num = generate_luhn_card_number(prefix="4111", length=16)
        cvv = str(random.randint(100, 999))
        exp_month = datetime.datetime.now(datetime.timezone.utc).month
        exp_year = datetime.datetime.now(datetime.timezone.utc).year + 3
        
        card = IssuedCard(
            id=card_id,
            account_id=cred_acc_id,
            cardholder_name=p["cardholder_name"],
            card_token=p["card_token"],
            last_four=card_num[-4:],
            exp_month=exp_month,
            exp_year=exp_year,
            status="ACTIVE",
            is_active=True
        )
        db.add(card)
        
        # Add card to manifest
        cards_manifest[p["first_name"].lower()] = {
            "cardholder_name": p["cardholder_name"],
            "card_number": card_num,
            "token": p["card_token"],
            "cvv": cvv,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "credit_limit_dollars": round(p["credit_limit_cents"] / 100.0, 2),
            "email": p["email"],
            "user_id": str(user_uuid),
            "credit_account_id": str(cred_acc_id)
        }
        
    # 7. Store manifest in SystemSetting
    manifest_setting = db.query(SystemSetting).filter(SystemSetting.key == "simulation_cards_manifest").first()
    if manifest_setting:
        manifest_setting.value = json.dumps(cards_manifest)
    else:
        db.add(SystemSetting(key="simulation_cards_manifest", value=json.dumps(cards_manifest)))
        
    db.commit()
    logger.info("Algorithmic persona and card seeding completed successfully.")
    return cards_manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Invoking Seeding Service from command-line...")
    db_session = SessionLocal()
    try:
        manifest = perform_algorithmic_seeding(db_session)
        print("\n=== SEEDED CARDS MANIFEST ===")
        print(json.dumps(manifest, indent=2))
        print("===============================\n")
    finally:
        db_session.close()
