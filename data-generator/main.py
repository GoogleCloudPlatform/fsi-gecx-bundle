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

import base64
import csv
import json
import os
import random
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from google.cloud import spanner, bigquery
from faker import Faker

app = FastAPI(title="Synthetic Transaction Data Generator")

SPANNER_INSTANCE = os.getenv("SPANNER_INSTANCE", "banking-data")
SPANNER_DATABASE = os.getenv("SPANNER_DATABASE", "banking")

spanner_client = spanner.Client()
instance = spanner_client.instance(SPANNER_INSTANCE)
database = instance.database(SPANNER_DATABASE)


bq_client = bigquery.Client()
PROJECT_ID = bq_client.project

# Load merchants from CSV
merchants_list = []
csv_path = os.path.join(os.path.dirname(__file__), "resources", "merchants.csv")
if os.path.exists(csv_path):
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            merchants_list.append({
                "merchant": row["Merchant"],
                "category": row["Category"],
                "rank": int(row["Rank"])
            })
else:
    raise FileNotFoundError(f"Required merchants lookup CSV file not found at: {csv_path}")

fake = Faker()

class SeedRequest(BaseModel):
    num_accounts: int = 10
    transactions_per_account: int = 20
    user_ids: Optional[List[str]] = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/generate")
async def generate_synthetic_data(request: Request):
    try:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        if "message" in body and isinstance(body["message"], dict) and "data" in body["message"]:
            try:
                pubsub_data = body["message"]["data"]
                decoded_bytes = base64.b64decode(pubsub_data)
                decoded_str = decoded_bytes.decode("utf-8")
                payload = json.loads(decoded_str)
            except Exception as decode_err:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to decode Pub/Sub message payload: {str(decode_err)}"
                )
        else:
            payload = body

        try:
            req = SeedRequest(**payload)
        except Exception as val_err:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid seed request payload: {str(val_err)}"
            )

        # 1. Fetch valid transaction types from Spanner
        transaction_types = []
        def read_transaction_types(transaction):
            results = transaction.execute_sql("SELECT transaction_type_id FROM transaction_types")
            return [row[0] for row in results]

        try:
            transaction_types = database.run_in_transaction(read_transaction_types)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to read transaction_types. Ensure database is seeded. Error: {str(e)}"
            )

        if not transaction_types:
            raise HTTPException(
                status_code=400,
                detail="No transaction types found in the database. Please seed transaction_types table first."
            )

        user_ids = req.user_ids
        if not user_ids:
            try:
                query = f"SELECT user_id FROM `{PROJECT_ID}.banking.user` LIMIT 100"
                query_job = bq_client.query(query)
                user_ids = [row.user_id for row in query_job]
            except Exception as bq_err:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to query BigQuery user table: {str(bq_err)}"
                )

        if not user_ids:
            raise HTTPException(
                status_code=400,
                detail="No user_ids provided in request, and none found in BigQuery table 'banking.user'."
            )

        sample_size = max(1, int(len(user_ids) * 0.25))
        target_users = random.sample(user_ids, sample_size)

        accounts_data = []
        account_owners_data = []
        transactions_data = []

        def write_data(transaction):
            for user_id in target_users:
                # 1. Fetch existing accounts from Spanner
                results = transaction.execute_sql(
                    """
                    SELECT a.account_id, a.account_type, COALESCE(b.balance, 0)
                    FROM account_owners ao
                    JOIN accounts a ON ao.account_id = a.account_id
                    LEFT JOIN account_balances b ON a.account_id = b.account_id
                    WHERE ao.user_id = @user_id
                    """,
                    params={"user_id": user_id},
                    param_types={"user_id": spanner.param_types.STRING}
                )

                existing_accounts = []
                for row in results:
                    existing_accounts.append({
                        "account_id": row[0],
                        "account_type": row[1],
                        "balance": row[2]
                    })

                has_checking = any(a["account_type"] == "checking" for a in existing_accounts)
                has_savings = any(a["account_type"] == "savings" for a in existing_accounts)

                accounts_to_create = []
                if not has_checking:
                    accounts_to_create.append("checking")
                if not has_savings:
                    accounts_to_create.append("savings")

                # 1/1000 chance to create an extra account beyond checking & savings (if within limit)
                total_count = len(existing_accounts) + len(accounts_to_create)
                if total_count >= 2 and total_count < req.num_accounts:
                    if random.random() < 0.001:
                        accounts_to_create.append(random.choice(["checking", "savings"]))

                new_accounts_info = []
                for atype in accounts_to_create:
                    new_id = str(uuid.uuid4())
                    if atype == "checking":
                        display_name = random.choice(["Everyday Checking", "Preferred Checking", "Direct Deposit Checking"])
                    else:
                        display_name = random.choice(["High Yield Savings", "Statement Savings", "Emergency Fund"])

                    accounts_data.append((new_id, user_id, atype, display_name))
                    account_owners_data.append((new_id, user_id, "PRIMARY"))

                    new_accounts_info.append({
                        "account_id": new_id,
                        "account_type": atype,
                        "balance": Decimal("0.00"),
                        "is_new": True
                    })

                active_accounts = []
                for acc in existing_accounts:
                    active_accounts.append({
                        "account_id": acc["account_id"],
                        "account_type": acc["account_type"],
                        "balance": Decimal(str(acc["balance"])),
                        "is_new": False
                    })
                active_accounts.extend(new_accounts_info)

                for acc in active_accounts:
                    acc_id = acc["account_id"]
                    running_balance = acc["balance"]
                    start_date = datetime.now() - timedelta(days=90)

                    # Initial deposit if new
                    if acc["is_new"]:
                        deposit_id = str(uuid.uuid4())
                        skew_factor = random.random() ** 4
                        deposit_val = 200.0 + (skew_factor * (250000.0 - 200.0))
                        deposit_amount = Decimal(f"{deposit_val:.2f}")
                        running_balance += deposit_amount
                        transactions_data.append((
                            acc_id,
                            deposit_id,
                            deposit_amount,
                            "CREDIT",
                            "CREDIT",
                            "Initial Account Deposit",
                            "Branch Deposit",
                            "Transfer",
                            "POSTED",
                            str(random.randint(100000000000, 999999999999)),
                            start_date
                        ))

                    tx_time = start_date
                    num_txs = random.randint(0, req.transactions_per_account)
                    time_interval = max(1, req.transactions_per_account)
                    for _ in range(num_txs):
                        tx_id = str(uuid.uuid4())
                        ttype = random.choice(transaction_types)
                        tx_time += timedelta(minutes=random.randint(1, 90 * 24 * 60 // time_interval))

                        if ttype in ["DEBIT", "TRANSFER"]:
                            amount_val = Decimal(f"{random.uniform(5.0, 500.0):.2f}")
                            direction = "DEBIT"
                        else:
                            amount_val = Decimal(f"{random.uniform(50.0, 2000.0):.2f}")
                            direction = "CREDIT"

                        description = fake.sentence(nb_words=5)
                        status = random.choice(["POSTED", "POSTED", "POSTED", "PENDING"])
                        ref_number = str(random.randint(100000000000, 999999999999))

                        if ttype == "TRANSFER":
                            other_own_accounts = [o for o in active_accounts if o["account_id"] != acc_id]
                            
                            # 70% chance to transfer to own other account (if exists)
                            if other_own_accounts and random.random() < 0.70:
                                dest_acc = random.choice(other_own_accounts)
                                dest_acc_id = dest_acc["account_id"]
                                dest_type = dest_acc["account_type"]
                                
                                counterparty = f"Transfer to {dest_type}"
                                direction = "DEBIT"
                                category = "Transfer"
                                
                                # Find dest account in local list and credit it
                                for o in active_accounts:
                                    if o["account_id"] == dest_acc_id:
                                        o["balance"] += amount_val
                                        transactions_data.append((
                                            dest_acc_id,
                                            str(uuid.uuid4()),
                                            amount_val,
                                            "TRANSFER",
                                            "CREDIT",
                                            description,
                                            f"Transfer from {acc['account_type']}",
                                            "Transfer",
                                            status,
                                            ref_number,
                                            tx_time
                                        ))
                                        break
                            else:
                                # Peer-to-peer transfer: query a random destination account not owned by this user
                                dest_results = transaction.execute_sql(
                                    "SELECT account_id, account_type FROM accounts WHERE account_id != @current_id LIMIT 10",
                                    params={"current_id": acc_id},
                                    param_types={"current_id": spanner.param_types.STRING}
                                )
                                dest_rows = [row for row in dest_results]
                                
                                if dest_rows:
                                    dest_row = random.choice(dest_rows)
                                    dest_acc_id = dest_row[0]
                                    
                                    counterparty = f"Transfer to Acc ...{dest_acc_id[-4:]}"
                                    direction = "DEBIT"
                                    category = "Transfer"
                                    
                                    # Insert matching CREDIT transaction
                                    transactions_data.append((
                                        dest_acc_id,
                                        str(uuid.uuid4()),
                                        amount_val,
                                        "TRANSFER",
                                        "CREDIT",
                                        description,
                                        f"Transfer from Acc ...{acc_id[-4:]}",
                                        "Transfer",
                                        status,
                                        ref_number,
                                        tx_time
                                    ))
                                else:
                                    counterparty = "External Transfer"
                                    direction = "DEBIT"
                                    category = "Transfer"
                        elif ttype == "DEBIT":
                            debit_merchants = [m for m in merchants_list if m["category"] not in ["Salary", "Interest", "Transfer"]]
                            merchant_info = random.choice(debit_merchants)
                            counterparty = merchant_info["merchant"]
                            category = merchant_info["category"]
                        elif ttype == "ACH":
                            is_deposit = random.choice([True, False])
                            if is_deposit:
                                ach_merchants = [m for m in merchants_list if m["category"] in ["Salary"]]
                                direction = "CREDIT"
                            else:
                                ach_merchants = [m for m in merchants_list if m["category"] in ["Utilities", "Rent"]]
                                direction = "DEBIT"

                            if ach_merchants:
                                merchant_info = random.choice(ach_merchants)
                                counterparty = merchant_info["merchant"]
                                category = merchant_info["category"]
                            else:
                                counterparty = "ACH Payment"
                                category = "Utilities"
                        else: # CREDIT
                            credit_merchants = [m for m in merchants_list if m["category"] in ["Salary", "Interest"]]
                            direction = "CREDIT"
                            if credit_merchants:
                                merchant_info = random.choice(credit_merchants)
                                counterparty = merchant_info["merchant"]
                                category = merchant_info["category"]
                            else:
                                counterparty = "Misc Deposit"
                                category = "Interest"

                        if direction == "CREDIT":
                            running_balance += amount_val
                        else:
                            running_balance -= amount_val


                        transactions_data.append((
                            acc_id,
                            tx_id,
                            amount_val,
                            ttype,
                            direction,
                            description,
                            counterparty,
                            category,
                            status,
                            ref_number,
                            tx_time
                        ))

                        # Overdraft Protection Deposit if balance drops below 0
                        if running_balance < 0:
                            if random.random() < 0.90:
                                overdraft_id = str(uuid.uuid4())
                                overdraft_amount = Decimal(f"{random.uniform(5.0, 2000.0):.2f}")
                                running_balance += overdraft_amount
                                tx_time += timedelta(seconds=1)

                                transactions_data.append((
                                    acc_id,
                                    overdraft_id,
                                    overdraft_amount,
                                    "CREDIT",
                                    "CREDIT",
                                    "Overdraft Protection Deposit",
                                    "Overdraft Protection",
                                    "Transfer",
                                    "POSTED",
                                    str(random.randint(100000000000, 999999999999)),
                                    tx_time
                                ))

            if accounts_data:
                transaction.insert(
                    table="accounts",
                    columns=["account_id", "user_id", "account_type", "display_name"],
                    values=accounts_data
                )

            if account_owners_data:
                transaction.insert(
                    table="account_owners",
                    columns=["account_id", "user_id", "owner_type"],
                    values=account_owners_data
                )

            if transactions_data:
                transaction.insert(
                    table="transactions",
                    columns=[
                        "account_id",
                        "transaction_id",
                        "amount",
                        "transaction_type_id",
                        "direction",
                        "description",
                        "counterparty_name",
                        "category",
                        "status",
                        "reference_number",
                        "timestamp"
                    ],
                    values=transactions_data
                )

        database.run_in_transaction(write_data)

        return {
            "message": "Successfully generated synthetic data",
            "users_processed": len(target_users),
            "accounts_created": len(accounts_data),
            "transactions_created": len(transactions_data)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
