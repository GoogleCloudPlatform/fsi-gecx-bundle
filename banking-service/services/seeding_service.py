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

import uuid
import random
import datetime
import logging
import json
from typing import Dict, Any
from sqlalchemy.orm import Session

from utils.database import SessionLocal
from utils.encryption import encrypt_pii

# Models
from models.identity import User
from models.kyc import KYCRecord, UserCreditProfile
from models.origination import Account, AccountLedgerEntry, Transaction
from models.credit_card import CreditAccount, IssuedCard, PostedTransaction, CreditProduct, TransactionAuthorization
from models.origination import DepositProduct
from models.settings import SystemSetting

logger = logging.getLogger(__name__)

import os

def load_static_personas():
    path = os.path.join(os.path.dirname(__file__), "..", "resources", "data", "static_personas.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

PERSONAS = load_static_personas()


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
    
    try:
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
            # Set cleared balance to a minor randomized seed value (e.g. Eleanor has initial debt)
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
    except Exception as e:
        db.rollback()
        logger.error(f"Error during algorithmic seeding: {e}")
        raise e


def provision_user_suite(db: Session, email: str, firebase_uid: str) -> Dict[str, Any]:
    """Dynamically provisions a new user, kyc profile, deposit accounts, credit cards, and historical swipes."""
    # Bypass RBAC
    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True

    try:
        # 1. Check if user already exists
        existing_user = db.query(User).filter((User.email == email) | (User.auth_provider_uid == firebase_uid)).first()
        if existing_user:
            has_dep = db.query(Account).filter(Account.user_id == existing_user.id).first()
            has_cc = db.query(CreditAccount).filter(CreditAccount.customer_id == existing_user.id).first()
            if has_dep or has_cc:
                raise ValueError("Profile already provisioned with active accounts.")
            user_uuid = existing_user.id
            first_name = existing_user.first_name
            last_name = existing_user.last_name
        else:
            # 2. Extract first and last names
            name_part = email.split("@")[0]
            if "." in name_part:
                parts = name_part.split(".")
                first_name = parts[0].capitalize()
                last_name = parts[1].capitalize()
            else:
                first_name = name_part.capitalize()
                last_name = "User"

            user_uuid = uuid.uuid4()
            
            # 3. Create User
            user = User(
                id=user_uuid,
                auth_provider_uid=firebase_uid,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number="555-01" + str(random.randint(10, 99))
            )
            db.add(user)
            db.flush()

        # 4. Create KYCRecord (Envelope encrypted) if not exists
        kyc_rec = db.query(KYCRecord).filter(KYCRecord.user_id == user_uuid).first()
        if not kyc_rec:
            kyc_record_id = uuid.uuid4()
            ssn = f"900-{random.randint(10, 99)}-{random.randint(1000, 9999)}"
            enc_pii, wrapped_dek, iv, tag = encrypt_pii(
                plaintext_pii=json.dumps({"ssn": ssn, "dob": "1990-01-01"}),
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

        # 5. Create UserCreditProfile if not exists
        credit_prof = db.query(UserCreditProfile).filter(UserCreditProfile.user_id == user_uuid).first()
        if not credit_prof:
            credit_prof = UserCreditProfile(
                id=uuid.uuid4(),
                user_id=user_uuid,
                credit_score=720,
                credit_tier="PRIME",
                stated_annual_income_cents=9500000  # $95,000.00
            )
            db.add(credit_prof)
        db.flush()

        # 6. Provision checking/savings deposit accounts
        checking_acc = Account(
            id=uuid.uuid4(),
            user_id=user_uuid,
            account_number=f"CHK-{random.randint(10000000, 99999999)}",
            account_type="CHECKING",
            product_name="Nova Signature Checking",
            product_code="CHECKING_SIGNATURE",
            cleared_balance_cents=1000000,  # $10,000.00
            routing_number="021000021",
            status="ACTIVE"
        )
        savings_acc = Account(
            id=uuid.uuid4(),
            user_id=user_uuid,
            account_number=f"SAV-{random.randint(10000000, 99999999)}",
            account_type="SAVINGS",
            product_name="Nova High Yield Savings",
            product_code="SAVINGS_HIGH_YIELD",
            cleared_balance_cents=2000000,  # $20,000.00
            routing_number="021000021",
            status="ACTIVE"
        )
        db.add_all([checking_acc, savings_acc])

        # 7. Create Credit Line Account
        cred_acc_id = uuid.uuid4()
        cred_acc = CreditAccount(
            id=cred_acc_id,
            customer_id=user_uuid,
            product_code="CASHBACK_EVERYDAY",
            status="ACTIVE",
            credit_limit_cents=1000000,  # $10,000.00
            cleared_balance_cents=0,
            available_credit_cents=1000000,
            payment_due_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=15),
            statement_close_date=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=15)
        )
        db.add(cred_acc)
        db.flush()

        # 8. Issue Card
        card_id = uuid.uuid4()
        card_num = generate_luhn_card_number(prefix="4111", length=16)
        card_token = f"tok_visa_{first_name.lower()}_{last_name.lower()}"
        cvv = str(random.randint(100, 999))
        exp_month = datetime.datetime.now(datetime.timezone.utc).month
        exp_year = datetime.datetime.now(datetime.timezone.utc).year + 3
        
        card = IssuedCard(
            id=card_id,
            account_id=cred_acc_id,
            cardholder_name=f"{first_name} {last_name}",
            card_token=card_token,
            last_four=card_num[-4:],
            exp_month=exp_month,
            exp_year=exp_year,
            status="ACTIVE",
            is_active=True
        )
        db.add(card)
        db.flush()

        # 9. Generate 10-15 historical swipes
        swipe_options = [
            {"description": "Starbucks Coffee", "min": 450, "max": 850},
            {"description": "Whole Foods Market", "min": 4500, "max": 12000},
            {"description": "Uber Trip", "min": 1200, "max": 3500},
            {"description": "Amazon Purchase", "min": 1500, "max": 8500},
            {"description": "Netflix Subscription", "min": 1549, "max": 1549},
            {"description": "Chevron Gas Station", "min": 3500, "max": 5500},
            {"description": "McDonald's Fast Food", "min": 850, "max": 1850},
            {"description": "Walmart Superstore", "min": 2500, "max": 9500},
            {"description": "YouTube Premium Subscription", "min": 1399, "max": 1399},
            {"description": "Shell Petrol", "min": 3000, "max": 5000}
        ]
        
        total_swipes_debt_cents = 0
        now = datetime.datetime.now(datetime.timezone.utc)

        # 9a. Seed exactly one LATE_FEE transaction for support escalations CUJ
        late_fee_cents = 3500
        late_fee_tx = PostedTransaction(
            id=uuid.uuid4(),
            account_id=cred_acc_id,
            amount_cents=-late_fee_cents,
            description="LATE_FEE",
            posted_at=now - datetime.timedelta(days=5)
        )
        db.add(late_fee_tx)
        total_swipes_debt_cents += late_fee_cents
        
        for i in range(12):
            swipe_conf = random.choice(swipe_options)
            amount_cents = random.randint(swipe_conf["min"], swipe_conf["max"])
            total_swipes_debt_cents += amount_cents
            
            posted_date = now - datetime.timedelta(days=(14 - i), hours=random.randint(0, 12))
            
            tx = PostedTransaction(
                id=uuid.uuid4(),
                account_id=cred_acc_id,
                amount_cents=-amount_cents,
                description=swipe_conf["description"],
                posted_at=posted_date
            )
            db.add(tx)
            
        cred_acc.cleared_balance_cents = total_swipes_debt_cents
        cred_acc.available_credit_cents = cred_acc.credit_limit_cents - total_swipes_debt_cents
        
        db.commit()
        logger.info(f"Dynamically provisioned personal demo suite for email={email} (user_id={user_uuid}) successfully.")
        
        return {
            "user_id": str(user_uuid),
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "card_token": card_token,
            "card_number": card_num,
            "cvv": cvv,
            "exp_month": exp_month,
            "exp_year": exp_year,
            "checking_account_number": checking_acc.account_number,
            "savings_account_number": savings_acc.account_number,
            "credit_account_id": str(cred_acc_id)
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to provision demo profile for email={email}: {e}")
        raise e

def reset_user_suite(db: Session, user_id: uuid.UUID) -> None:
    """Resets the user's personal checking/savings balances to default and clears credit card transactions."""
    # Bypass RBAC
    if hasattr(db.bind, "engine"):
        db.bind.engine._ignore_rbac = True
    else:
        db.bind._ignore_rbac = True

    # 1. Fetch all checking/savings accounts belonging to user
    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    for acc in accounts:
        db.query(AccountLedgerEntry).filter(AccountLedgerEntry.account_id == acc.id).delete()
        if acc.account_type == "CHECKING":
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.email == "erikvoit@google.com":
                acc.cleared_balance_cents = 4500000
            elif user and user.email == "mservedio@google.com":
                acc.cleared_balance_cents = 6000000
            else:
                acc.cleared_balance_cents = 1000000
        elif acc.account_type == "SAVINGS":
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.email == "erikvoit@google.com":
                acc.cleared_balance_cents = 15000000
            else:
                acc.cleared_balance_cents = 2000000
        else:
            acc.cleared_balance_cents = 1000000

    # 2. Fetch all credit accounts belonging to user
    credit_accounts = db.query(CreditAccount).filter(CreditAccount.customer_id == user_id).all()
    for cred_acc in credit_accounts:
        db.query(TransactionAuthorization).filter(TransactionAuthorization.account_id == cred_acc.id).delete()
        db.query(PostedTransaction).filter(PostedTransaction.account_id == cred_acc.id).delete()
        cred_acc.cleared_balance_cents = 0
        cred_acc.available_credit_cents = cred_acc.credit_limit_cents
        
    db.commit()
    logger.info(f"Successfully reset personal demo suite accounts for user_id={user_id}.")


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
