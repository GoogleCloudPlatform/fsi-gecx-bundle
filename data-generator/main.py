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

import csv

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
    merchants_list = [
        {"merchant": "Walmart", "category": "Shopping", "rank": 1},
        {"merchant": "Starbucks", "category": "Food", "rank": 1},
        {"merchant": "Netflix", "category": "Entertainment", "rank": 2},
        {"merchant": "Comcast", "category": "Utilities", "rank": 2},
        {"merchant": "Landlord Inc", "category": "Rent", "rank": 1},
        {"merchant": "GCP Payroll", "category": "Salary", "rank": 1},
    ]

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
        except Exception as parse_err:
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

        def write_data(transaction):
            accounts_data = []
            account_owners_data = []
            transactions_data = []

            for i in range(req.num_accounts):
                account_id = str(uuid.uuid4())
                user_id = random.choice(user_ids)
                account_type = random.choice(["checking", "savings"])
                if account_type == "checking":
                    display_name = random.choice(["Everyday Checking", "Preferred Checking", "Direct Deposit Checking"])
                else:
                    display_name = random.choice(["High Yield Savings", "Statement Savings", "Emergency Fund"])

                accounts_data.append((account_id, user_id, account_type, display_name))
                account_owners_data.append((account_id, user_id, "PRIMARY"))

                start_date = datetime.now() - timedelta(days=90)

                for _ in range(req.transactions_per_account):
                    transaction_id = str(uuid.uuid4())
                    ttype = random.choice(transaction_types)

                    if ttype in ["DEBIT", "TRANSFER"]:
                        amount_val = Decimal(f"{random.uniform(5.0, 500.0):.2f}")
                    else:
                        amount_val = Decimal(f"{random.uniform(50.0, 2000.0):.2f}")

                    description = fake.sentence(nb_words=5)
                    if ttype == "TRANSFER":
                        counterparty = "Self Transfer"
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
                        else:
                            ach_merchants = [m for m in merchants_list if m["category"] in ["Utilities", "Rent"]]
                        
                        if ach_merchants:
                            merchant_info = random.choice(ach_merchants)
                            counterparty = merchant_info["merchant"]
                            category = merchant_info["category"]
                        else:
                            counterparty = "ACH Payment"
                            category = "Utilities"
                    else: # CREDIT
                        credit_merchants = [m for m in merchants_list if m["category"] in ["Salary", "Interest"]]
                        if credit_merchants:
                            merchant_info = random.choice(credit_merchants)
                            counterparty = merchant_info["merchant"]
                            category = merchant_info["category"]
                        else:
                            counterparty = "Misc Deposit"
                            category = "Interest"
                    status = random.choice(["POSTED", "POSTED", "POSTED", "PENDING"])
                    ref_number = str(random.randint(100000000000, 999999999999))
                    timestamp = start_date + timedelta(minutes=random.randint(1, 90 * 24 * 60))

                    transactions_data.append((
                        account_id,
                        transaction_id,
                        amount_val,
                        ttype,
                        description,
                        counterparty,
                        category,
                        status,
                        ref_number,
                        timestamp
                    ))

            # Insert accounts
            transaction.insert(
                table="accounts",
                columns=["account_id", "user_id", "account_type", "display_name"],
                values=accounts_data
            )

            # Insert account owners
            transaction.insert(
                table="account_owners",
                columns=["account_id", "user_id", "owner_type"],
                values=account_owners_data
            )

            # Insert transactions
            transaction.insert(
                table="transactions",
                columns=[
                    "account_id",
                    "transaction_id",
                    "amount",
                    "transaction_type_id",
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
            "accounts_created": req.num_accounts,
            "transactions_created": req.num_accounts * req.transactions_per_account
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
