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
from typing import Dict, Any
from sqlalchemy.orm import Session

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "data")

from utils.database import SessionLocal
from utils.encryption import encrypt_pii
from utils.audit import record_audit_event

# Models
from models.identity import User, UserAddress
from models.kyc import KYCRecord, UserCreditProfile
from models.origination import Account, AccountLedgerEntry, Transaction
from models.credit_card import CreditAccount, IssuedCard, PostedTransaction, CreditProduct, TransactionAuthorization
from models.origination import DepositProduct
from models.settings import SystemSetting
from models.reference import MerchantCategoryCode
from services.taxonomy_service import DEFAULT_TAXONOMY_MAP, TaxonomyService
from services.merchant_service import MerchantEnrichmentService
from services.card_network import process_authorization, process_settlement

logger = logging.getLogger(__name__)

import os

def get_base_personas():
    path = os.path.join(os.path.dirname(__file__), "..", "resources", "data", "static_personas.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required seeding resource static_personas.json not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_vip_googlers():
    path = os.path.join(os.path.dirname(__file__), "..", "resources", "data", "vip_googlers.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required seeding resource vip_googlers.json not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_seeding_personas():
    base_personas = get_base_personas()
    vip_googlers = load_vip_googlers()
    
    for p in base_personas:
        p["is_vip_googler"] = False
        p.setdefault("home_metro", "CHICAGO IL")
        p.setdefault("address", {
            "street": "100 Market St",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60601"
        })

    formatted_vips = []
    for vip in vip_googlers:
        name_parts = vip["name"].split(maxsplit=1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else "Googler"
        token = f"tok_visa_{first_name.lower()}_{last_name.lower()}"
        vip_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, vip["email"]))
        score = vip["fico_score"]
        
        formatted_vips.append({
            "id": vip_id,
            "first_name": first_name,
            "last_name": last_name,
            "cardholder_name": f"{first_name} {last_name}",
            "card_token": token,
            "email": vip["email"],
            "phone_number": "650-253-0000",
            "ssn": f"999-{random.randint(10, 99)}-{random.randint(1000, 9999)}",
            "credit_score": score,
            "credit_tier": vip["credit_tier"],
            "stated_annual_income_cents": 35000000,
            "credit_limit_cents": 2500000,
            "credit_product": "CASHBACK_EVERYDAY",
            "home_metro": vip["home_metro"],
            "is_vip_googler": True,
            "address": {
                "street": vip["residential_address"]["street"],
                "city": vip["residential_address"]["city"],
                "state": vip["residential_address"]["state"],
                "postal_code": vip["residential_address"]["postal_code"],
            },
            "accounts": [
                {"type": "CHECKING", "product_name": "Googler Executive Checking", "product_code": "CHECKING_EVERYDAY", "balance_cents": 1500000},
                {"type": "SAVINGS", "product_name": "Googler High Yield Savings", "product_code": "SAVINGS_HIGH_YIELD", "balance_cents": 5000000},
            ],
            "cards": [
                {"type": "VIRTUAL", "network": "VISA", "status": "ACTIVE"}
            ]
        })
        
    meta_path = os.path.join(os.path.dirname(__file__), "..", "resources", "data", "seeding_metadata.json")
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Required seeding resource seeding_metadata.json not found at {meta_path}")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
            
    reserved_first_names = {p["first_name"].lower() for p in base_personas}.union({v["first_name"].lower() for v in formatted_vips})
    first_names = [fn for fn in meta["first_names"] if fn.lower() not in reserved_first_names]
    last_names = meta["last_names"]
    metros = meta["metros"]
    street_names = meta["street_names"]
    underwriting_tiers = meta["underwriting_tiers"]
    
    mock_needed = max(0, 200 - len(base_personas))
    generated_mock = []
    
    rng = random.Random(42)
    all_pairs = [(fn, ln) for fn in first_names for ln in last_names]
    rng.shuffle(all_pairs)
    
    existing_names = {f"{p['first_name']} {p['last_name']}".lower() for p in base_personas}
    for vip in formatted_vips:
        existing_names.add(vip["cardholder_name"].lower())
        
    pair_idx = 0
    for i in range(mock_needed):
        while pair_idx < len(all_pairs):
            fn, ln = all_pairs[pair_idx]
            pair_idx += 1
            if f"{fn} {ln}".lower() not in existing_names:
                break
        else:
            fn, ln = f"User{i}", f"Mock{i}"
            
        existing_names.add(f"{fn} {ln}".lower())
        email = f"{fn.lower()}.{ln.lower()}@mockbanking.local"
        uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, email))
        
        metro_obj = metros[i % len(metros)]
        metro_name = metro_obj["name"]
        city = metro_obj["city"]
        state = metro_obj["state"]
        zip_code = rng.choice(metro_obj["zips"])
        street = f"{rng.randint(100, 9999)} {rng.choice(street_names)}"
        
        tier_roll = i % 10
        if tier_roll < 3:
            t_info = underwriting_tiers[0]
        elif tier_roll < 7:
            t_info = underwriting_tiers[1 % len(underwriting_tiers)]
        elif tier_roll < 9:
            t_info = underwriting_tiers[2 % len(underwriting_tiers)]
        else:
            t_info = underwriting_tiers[3 % len(underwriting_tiers)]
            
        tier = t_info["tier"]
        score = rng.randint(t_info["fico_min"], t_info["fico_max"])
        limit = rng.randint(t_info["limit_min_cents"] // 10000, t_info["limit_max_cents"] // 10000) * 10000
        income = rng.randint(t_info["income_min_cents"] // 10000, t_info["income_max_cents"] // 10000) * 10000
        
        generated_mock.append({
            "id": uid,
            "first_name": fn,
            "last_name": ln,
            "cardholder_name": f"{fn} {ln}",
            "card_token": f"tok_visa_{fn.lower()}_{ln.lower()}",
            "email": email,
            "phone_number": f"555-100-{i:04d}",
            "ssn": f"900-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}",
            "credit_score": score,
            "credit_tier": tier,
            "stated_annual_income_cents": income,
            "credit_limit_cents": limit,
            "credit_product": "CASHBACK_EVERYDAY",
            "home_metro": metro_name,
            "is_vip_googler": False,
            "address": {
                "street": street,
                "city": city,
                "state": state,
                "postal_code": zip_code,
            },
            "accounts": [
                {"type": "CHECKING", "product_name": "Standard Checking", "product_code": "CHECKING_EVERYDAY", "balance_cents": rng.randint(1000, 10000) * 100},
                {"type": "SAVINGS", "product_name": "High Yield Savings", "product_code": "SAVINGS_HIGH_YIELD", "balance_cents": rng.randint(2000, 25000) * 100},
            ],
            "cards": [
                {"type": "VIRTUAL", "network": "VISA", "status": "ACTIVE"}
            ]
        })
        
    return base_personas + generated_mock + formatted_vips

PERSONAS = get_base_personas()


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
        path = os.path.join(RESOURCE_DIR, "credit_products.json")
        with open(path, "r") as f:
            data = json.load(f)
        products = [CreditProduct(**item) for item in data]
        db.add_all(products)

    if db.query(DepositProduct).count() == 0:
        logger.info("Seeding DepositProduct catalog...")
        path = os.path.join(RESOURCE_DIR, "deposit_products.json")
        with open(path, "r") as f:
            data = json.load(f)
        deposits = [DepositProduct(**item) for item in data]
        db.add_all(deposits)
        
    if db.query(MerchantCategoryCode).count() == 0:
        logger.info("Seeding MerchantCategoryCode merchants catalog...")
        mcc_records = [
            MerchantCategoryCode(
                mcc=code,
                primary_category=data["primary"],
                detailed_category=data["detailed"]
            )
            for code, data in DEFAULT_TAXONOMY_MAP.items()
        ]
        db.add_all(mcc_records)
        db.flush()
        TaxonomyService.invalidate_cache()
        
    MerchantEnrichmentService.seed_merchant_catalog(db)
    db.flush()

def seed_system_settings_if_missing(db: Session) -> None:
    """Ensures default voice and live avatar system settings are seeded."""
    path = os.path.join(RESOURCE_DIR, "system_settings.json")
    with open(path, "r") as f:
        default_keys = json.load(f)
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
        
        seeding_personas = get_seeding_personas()
        cards_manifest = {}
        
        logger.info(f"Initializing {len(seeding_personas)} user profiles and bank accounts...")
        
        for p in seeding_personas:
            user_uuid = uuid.UUID(p["id"])
            auth_uid = p.get("auth_provider_uid") or f"auth-{p['email']}"
            
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
            record_audit_event(
                db,
                "USER_CREATED",
                {
                    "user_id": str(user_uuid),
                    "email": p["email"],
                    "first_name": p["first_name"],
                    "last_name": p["last_name"],
                },
            )
            
            # 1b. Create 3NF UserAddress
            addr_conf = p["address"]
            user_addr = UserAddress(
                id=uuid.uuid4(),
                user_id=user_uuid,
                address_type="RESIDENTIAL",
                is_primary=True,
                street_line_1=addr_conf["street"],
                city=addr_conf["city"],
                state=addr_conf["state"],
                postal_code=addr_conf["postal_code"],
                country_code=addr_conf.get("country", "USA")
            )
            db.add(user_addr)
            
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
            record_audit_event(
                db,
                "KYC_RECORD_CREATED",
                {
                    "user_id": str(user_uuid),
                    "kyc_record_id": str(kyc_rec.id),
                },
            )
            
            # 3. Create UserCreditProfile
            credit_prof = UserCreditProfile(
                id=uuid.uuid4(),
                user_id=user_uuid,
                credit_score=p["credit_score"],
                credit_tier=p["credit_tier"],
                stated_annual_income_cents=p["stated_annual_income_cents"]
            )
            db.add(credit_prof)
            record_audit_event(
                db,
                "USER_CREDIT_PROFILE_CREATED",
                {
                    "user_id": str(user_uuid),
                    "credit_score": p["credit_score"],
                },
            )
            db.flush()
            
            # 4. Provision checking/savings deposit accounts
            checking_acc = None
            savings_acc = None
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
                if acc_conf["type"] == "CHECKING":
                    checking_acc = dep_acc
                elif acc_conf["type"] == "SAVINGS":
                    savings_acc = dep_acc
                record_audit_event(
                    db,
                    "DEPOSIT_ACCOUNT_CREATED",
                    {
                        "user_id": str(user_uuid),
                        "account_id": str(dep_acc.id),
                        "account_number": dep_acc.account_number,
                        "account_type": dep_acc.account_type,
                    },
                )
                
            # 5. Create Credit Line Account
            cred_acc_id = uuid.UUID(p["credit_account_id"]) if "credit_account_id" in p else uuid.uuid4()
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
            record_audit_event(
                db,
                "CREDIT_ACCOUNT_CREATED",
                {
                    "user_id": str(user_uuid),
                    "account_id": str(cred_acc.id),
                    "product_code": p["credit_product"],
                },
            )
            db.flush()
            
            # 6. Issue Card
            card_id = uuid.UUID(p["card_id"]) if "card_id" in p else uuid.uuid4()
            card_num = generate_luhn_card_number(prefix="4111", length=16)
            cvv = str(random.randint(100, 999))
            exp_month = datetime.datetime.now(datetime.timezone.utc).month
            exp_year = datetime.datetime.now(datetime.timezone.utc).year + 3
            last_four = p["last_four"] if "last_four" in p else card_num[-4:]
            
            card = IssuedCard(
                id=card_id,
                account_id=cred_acc_id,
                cardholder_name=p["cardholder_name"],
                card_token=p["card_token"],
                last_four=last_four,
                exp_month=exp_month,
                exp_year=exp_year,
                status="ACTIVE",
                is_active=True
            )
            db.add(card)
            record_audit_event(
                db,
                "CREDIT_CARD_ISSUED",
                {
                    "user_id": str(user_uuid),
                    "account_id": str(cred_acc_id),
                    "card_token": p["card_token"],
                },
            )
            
            _seed_user_transactions(db, user_uuid=user_uuid, checking_acc=checking_acc, savings_acc=savings_acc, cred_acc=cred_acc, card=card, first_name=p["first_name"], last_name=p["last_name"])
            
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


def _seed_user_transactions(db: Session, user_uuid: uuid.UUID, checking_acc: Account, savings_acc: Account, cred_acc: CreditAccount, card: IssuedCard, first_name: str, last_name: str) -> None:
    """Seeds consistent pending and posted transactions across checking, savings, and credit card accounts."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # 1. Clear any existing transactions for these accounts
    if checking_acc:
        db.query(AccountLedgerEntry).filter(AccountLedgerEntry.account_id == checking_acc.id).delete()
    if savings_acc:
        db.query(AccountLedgerEntry).filter(AccountLedgerEntry.account_id == savings_acc.id).delete()
    if cred_acc:
        db.query(TransactionAuthorization).filter(TransactionAuthorization.account_id == cred_acc.id).delete()
        db.query(PostedTransaction).filter(PostedTransaction.account_id == cred_acc.id).delete()

    # 2. Checking Account Seeding (Pending & Posted)
    if checking_acc:
        chk_pending_1 = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"idemp_chk_p1_{uuid.uuid4()}",
            user_id=user_uuid,
            status="PENDING",
            description="Target Store #1042 - Pending Debit Hold"
        )
        chk_p1_entry = AccountLedgerEntry(
            entry_id=uuid.uuid4(),
            transaction_id=chk_pending_1.id,
            account_id=checking_acc.id,
            amount_cents=4550,
            entry_type="CREDIT",
            posted_at=now - datetime.timedelta(hours=4)
        )
        chk_pending_2 = Transaction(
            id=uuid.uuid4(),
            idempotency_key=f"idemp_chk_p2_{uuid.uuid4()}",
            user_id=user_uuid,
            status="PENDING",
            description="Amazon.com - Pending Authorization"
        )
        chk_p2_entry = AccountLedgerEntry(
            entry_id=uuid.uuid4(),
            transaction_id=chk_pending_2.id,
            account_id=checking_acc.id,
            amount_cents=8999,
            entry_type="CREDIT",
            posted_at=now - datetime.timedelta(hours=2)
        )
        db.add_all([chk_pending_1, chk_p1_entry, chk_pending_2, chk_p2_entry])

        chk_posted_items = [
            ("Direct Deposit - Employer Payroll", 250000, "DEBIT", 12),
            ("Con Edison Electric Utility", 12000, "CREDIT", 10),
            ("Whole Foods Market", 14520, "CREDIT", 8),
            ("Venmo Payment - Rent", 120000, "CREDIT", 6),
            ("Spotify USA Subscription", 1699, "CREDIT", 5),
            ("Shell Gas Station", 4850, "CREDIT", 4),
            ("Apple Store Online", 12900, "CREDIT", 3),
            ("Trader Joe's Grocery", 8540, "CREDIT", 1),
        ]
        for desc, amount, etype, days_ago in chk_posted_items:
            tx = Transaction(
                id=uuid.uuid4(),
                idempotency_key=f"idemp_chk_{days_ago}_{uuid.uuid4()}",
                user_id=user_uuid,
                status="POSTED",
                description=desc
            )
            entry = AccountLedgerEntry(
                entry_id=uuid.uuid4(),
                transaction_id=tx.id,
                account_id=checking_acc.id,
                amount_cents=amount,
                entry_type=etype,
                posted_at=now - datetime.timedelta(days=days_ago, hours=random.randint(1, 10))
            )
            db.add_all([tx, entry])

    # 3. Savings Account Seeding (Posted)
    if savings_acc:
        sav_items = [
            ("Monthly Interest Paid", 4512, "DEBIT", 14),
            ("Automated Transfer from Checking", 50000, "DEBIT", 7),
            ("Online Transfer to Checking", 20000, "CREDIT", 2),
        ]
        for desc, amount, etype, days_ago in sav_items:
            tx = Transaction(
                id=uuid.uuid4(),
                idempotency_key=f"idemp_sav_{days_ago}_{uuid.uuid4()}",
                user_id=user_uuid,
                status="POSTED",
                description=desc
            )
            entry = AccountLedgerEntry(
                entry_id=uuid.uuid4(),
                transaction_id=tx.id,
                account_id=savings_acc.id,
                amount_cents=amount,
                entry_type=etype,
                posted_at=now - datetime.timedelta(days=days_ago, hours=random.randint(1, 10))
            )
            db.add_all([tx, entry])

    # 4. Credit Card Seeding (Pending Authorizations & Posted Transactions via Gateway)
    if cred_acc and card:
        # Assign a consistent geographical home metro and international travel trip for this customer's demo card
        from models.identity import User
        user_obj = db.query(User).filter(User.id == user_uuid).first()
        is_googler = user_obj and ("GOOGLE" in str(user_obj.email).upper() or "PRESENTER" in str(user_obj.last_name).upper() or "NOVA.HORIZON" in str(user_obj.email).upper())
        if is_googler:
            user_home_metro = random.choice(["MOUNTAIN VIEW CA", "SAN FRANCISCO CA"])
            user_travel_country = "MEX"
        else:
            user_home_metro = random.choice(["MOUNTAIN VIEW CA", "SAN FRANCISCO CA", "NEW YORK NY", "CHICAGO IL", "SEATTLE WA", "DALLAS TX", "LOS ANGELES CA", "ATLANTA GA", "MIAMI FL"])
            user_travel_country = None

        if not is_googler:
            ovr_rrn = f"OVR_{str(user_uuid)[:8]}"
            auth_ovr = process_authorization(db, {
                "card_token": card.card_token,
                "amount_cents": 3500,
                "retrieval_reference_number": ovr_rrn,
                "merchant_category_code": "FEE",
                "merchant_name": "Overdraft Fee",
                "card_network": "VISA",
                "created_at": now - datetime.timedelta(days=4)
            })
            if auth_ovr.get("action_code") == "00":
                process_settlement(db, {
                    "retrieval_reference_number": ovr_rrn,
                    "amount_cents": 3500,
                    "description": "Overdraft Fee",
                    "posted_at": now - datetime.timedelta(days=3)
                })

        meta_path = os.path.join(os.path.dirname(__file__), "..", "resources", "data", "seeding_metadata.json")
        mex_charges = []
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                mex_charges = json.load(f).get("mexico_travel_charges", [])

        for i in range(12):
            is_pending = (i >= 10)
            if is_googler and i == 8:
                store_desc = "AEROMEXICO AIRLINES RIVIERA MAYA [MEX]"
                mcc_val = "3000"
                amount_cents = 65000
                posted_date = now - datetime.timedelta(days=3)
            elif is_googler and i == 9:
                store_desc = "LA CASA DE LA PLAYA RIVIERA MAYA [MEX]"
                mcc_val = "7011"
                amount_cents = 95000
                posted_date = now - datetime.timedelta(days=2)
            elif is_googler and i == 10:
                store_desc = "ESTERO RESTAURANTE RIVIERA MAYA [MEX]"
                mcc_val = "5812"
                amount_cents = 16500
                posted_date = now - datetime.timedelta(hours=8)
            elif is_googler and i == 11:
                store_desc = "SENSE SPA MAYAKOBA PLAYA DEL CARMEN [MEX]"
                mcc_val = "7298"
                amount_cents = 22000
                posted_date = now - datetime.timedelta(hours=2)
            else:
                mch, store_desc = MerchantEnrichmentService.get_random_merchant(
                    db, 
                    is_international=False, 
                    country=None, 
                    home_metro=user_home_metro
                )
                mcc_val = mch.mcc if mch else "5310"
                amount_cents = random.randint(1250, 45000)
                if is_pending:
                    posted_date = now - datetime.timedelta(hours=(12 - i) * 2)
                else:
                    posted_date = now - datetime.timedelta(days=(14 - i), hours=random.randint(0, 12))

            rrn = f"REF_{str(user_uuid)[:5]}_{i:02d}"
            
            auth_res = process_authorization(db, {
                "card_token": card.card_token,
                "amount_cents": amount_cents,
                "retrieval_reference_number": rrn,
                "merchant_category_code": mcc_val,
                "merchant_name": store_desc,
                "card_network": "VISA",
                "created_at": posted_date - datetime.timedelta(hours=2)
            })
            if auth_res.get("action_code") == "00" and not is_pending:
                process_settlement(db, {
                    "retrieval_reference_number": rrn,
                    "amount_cents": amount_cents,
                    "description": store_desc,
                    "posted_at": posted_date
                })


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
            record_audit_event(
                db,
                "USER_CREATED",
                {
                    "user_id": str(user_uuid),
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
            )

            is_googler_email = "google.com" in email.lower() or "presenter" in email.lower()
            user_addr = UserAddress(
                id=uuid.uuid4(),
                user_id=user_uuid,
                address_type="RESIDENTIAL",
                is_primary=True,
                street_line_1="1600 Amphitheatre Pkwy" if is_googler_email else "500 Market St",
                city="Mountain View" if is_googler_email else "San Francisco",
                state="CA",
                postal_code="94043" if is_googler_email else "94105",
                country_code="USA"
            )
            db.add(user_addr)

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
            record_audit_event(
                db,
                "KYC_RECORD_CREATED",
                {
                    "user_id": str(user_uuid),
                    "kyc_record_id": str(kyc_rec.id),
                },
            )

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
            record_audit_event(
                db,
                "USER_CREDIT_PROFILE_CREATED",
                {
                    "user_id": str(user_uuid),
                    "credit_score": 720,
                },
            )
        db.flush()

        # 6. Provision checking/savings deposit accounts with harmonized default balances
        chk_balance = 4500000 if email == "erikvoit@google.com" else (6000000 if email == "mservedio@google.com" else 1000000)
        sav_balance = 15000000 if email == "erikvoit@google.com" else 2000000
        checking_acc = Account(
            id=uuid.uuid4(),
            user_id=user_uuid,
            account_number=f"CHK-{random.randint(10000000, 99999999)}",
            account_type="CHECKING",
            product_name="Nova Signature Checking",
            product_code="CHECKING_SIGNATURE",
            cleared_balance_cents=chk_balance,
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
            cleared_balance_cents=sav_balance,
            routing_number="021000021",
            status="ACTIVE"
        )
        db.add_all([checking_acc, savings_acc])
        record_audit_event(
            db,
            "DEPOSIT_ACCOUNT_CREATED",
            {
                "user_id": str(user_uuid),
                "account_id": str(checking_acc.id),
                "account_number": checking_acc.account_number,
                "account_type": "CHECKING",
            },
        )
        record_audit_event(
            db,
            "DEPOSIT_ACCOUNT_CREATED",
            {
                "user_id": str(user_uuid),
                "account_id": str(savings_acc.id),
                "account_number": savings_acc.account_number,
                "account_type": "SAVINGS",
            },
        )

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
        record_audit_event(
            db,
            "CREDIT_ACCOUNT_CREATED",
            {
                "user_id": str(user_uuid),
                "account_id": str(cred_acc.id),
                "product_code": "CASHBACK_EVERYDAY",
            },
        )
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
        record_audit_event(
            db,
            "CREDIT_CARD_ISSUED",
            {
                "user_id": str(user_uuid),
                "account_id": str(cred_acc_id),
                "card_token": card_token,
            },
        )

        # 9. Seed unified transactions across checking, savings, and credit cards
        _seed_user_transactions(db, user_uuid=user_uuid, checking_acc=checking_acc, savings_acc=savings_acc, cred_acc=cred_acc, card=card, first_name=first_name, last_name=last_name)
        
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

    # 2. Fetch credit accounts belonging to user
    credit_accounts = db.query(CreditAccount).filter(CreditAccount.customer_id == user_id).all()
    cred_acc = credit_accounts[0] if credit_accounts else None
    card = db.query(IssuedCard).filter(IssuedCard.account_id == cred_acc.id).first() if cred_acc else None
    
    user = db.query(User).filter(User.id == user_id).first()
    checking_acc = db.query(Account).filter(Account.user_id == user_id, Account.account_type == "CHECKING").first()
    savings_acc = db.query(Account).filter(Account.user_id == user_id, Account.account_type == "SAVINGS").first()
    
    _seed_user_transactions(
        db, 
        user_uuid=user_id, 
        checking_acc=checking_acc, 
        savings_acc=savings_acc, 
        cred_acc=cred_acc, 
        card=card, 
        first_name=user.first_name if user else "Erik", 
        last_name=user.last_name if user else "Vance"
    )
        
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
