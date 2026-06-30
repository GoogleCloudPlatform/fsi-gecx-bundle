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

import asyncio
import csv
import logging
import os
import random
import sqlite3
import sys
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("data-generator")

app = FastAPI(title="Modernized Synthetic Transaction Data Generator")

# Configs
BANKING_SERVICE_URL = os.getenv("BANKING_SERVICE_URL", "http://localhost:8000")
CARD_NETWORK_TOKEN = os.getenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "../banking-service/cards.db")

# Load Merchants
merchants_list: List[Dict[str, Any]] = []
csv_path = os.path.join(os.path.dirname(__file__), "resources", "merchants.csv")

CATEGORY_MCC_MAP = {
    "Airlines & Travel": "4511",
    "Hotels & Lodging": "7011",
    "Fast Food & Dining": "5812",
    "Coffee Shops & Dining": "5814",
    "Groceries & Retail": "5411",
    "Wholesale Clubs": "5411",
    "Gas Stations": "5541",
    "Streaming & Entertainment": "7841",
    "Electronics & Software": "5310",
    "Electronics": "5310",
    "Home Improvement": "5200",
    "Pharmacies & Health": "5912",
    "Rideshare & Transport": "4121",
}

if os.path.exists(csv_path):
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cat = row["Category"]
            mcc = CATEGORY_MCC_MAP.get(cat, "5310")
            merchants_list.append({
                "merchant": row["Merchant"],
                "category": cat,
                "mcc": mcc,
                "rank": int(row["Rank"])
            })
    logger.info(f"Loaded {len(merchants_list)} merchants from CSV.")
else:
    # Minimal fallback list if file doesn't exist
    merchants_list = [
        {"merchant": "Amazon", "category": "Retail", "mcc": "5310", "rank": 1},
        {"merchant": "Starbucks", "category": "Coffee Shops & Dining", "mcc": "5814", "rank": 10},
        {"merchant": "Delta Air Lines", "category": "Airlines & Travel", "mcc": "4511", "rank": 13},
        {"merchant": "Shell", "category": "Gas Stations", "mcc": "5541", "rank": 22},
    ]
    logger.warning("Merchants CSV not found. Using minimal fallback merchants.")

# Static Fallback Personas
DEFAULT_PERSONAS = [
    {
        "card_token": "tok_visa_erik_voit",
        "cardholder_name": "Erik Voit",
        "persona": "HNW",
        "mccs": ["4511", "7011", "5812"],
        "amount_min": 50000,
        "amount_max": 400000,
    },
    {
        "card_token": "tok_visa_mark_servedio",
        "cardholder_name": "Mark Servedio",
        "persona": "PRIME",
        "mccs": ["5411", "5541", "5310", "4121"],
        "amount_min": 1500,
        "amount_max": 15000,
    },
    {
        "card_token": "tok_visa_marcus_vance",
        "cardholder_name": "Marcus Vance",
        "persona": "PRIME",
        "mccs": ["5411", "5541", "5310", "4121"],
        "amount_min": 1500,
        "amount_max": 15000,
    },
    {
        "card_token": "tok_visa_chloe_gomez",
        "cardholder_name": "Chloe Gomez",
        "persona": "YPRO",
        "mccs": ["5814", "7841", "5812"],
        "amount_min": 400,
        "amount_max": 3500,
    }
]

def get_active_cards() -> List[Dict[str, Any]]:
    """
    Attempts to fetch active card tokens dynamically from local SQLite cards.db.
    Falls back to static DEFAULT_PERSONAS manifest.
    """
    if os.path.exists(SQLITE_DB_PATH):
        try:
            conn = sqlite3.connect(SQLITE_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT card_token, cardholder_name FROM issued_card WHERE status = 'ACTIVE'")
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                cards = []
                for row in rows:
                    token, name = row[0], row[1]
                    name_lower = name.lower()
                    
                    # Deduce profile persona mapping based on name
                    if "erik" in name_lower:
                        persona, mccs, a_min, a_max = "HNW", ["4511", "7011", "5812"], 50000, 400000
                    elif "servedio" in name_lower or "marcus" in name_lower:
                        persona, mccs, a_min, a_max = "PRIME", ["5411", "5541", "5310", "4121"], 1500, 15000
                    elif "chloe" in name_lower:
                        persona, mccs, a_min, a_max = "YPRO", ["5814", "7841", "5812"], 400, 3500
                    else:
                        # Fallback random persona
                        persona = random.choice(["HNW", "PRIME", "YPRO"])
                        if persona == "HNW":
                            mccs, a_min, a_max = ["4511", "7011", "5812"], 50000, 400000
                        elif persona == "PRIME":
                            mccs, a_min, a_max = ["5411", "5541", "5310", "4121"], 1500, 15000
                        else:
                            mccs, a_min, a_max = ["5814", "7841", "5812"], 400, 3500
                            
                    cards.append({
                        "card_token": token,
                        "cardholder_name": name,
                        "persona": persona,
                        "mccs": mccs,
                        "amount_min": a_min,
                        "amount_max": a_max
                    })
                logger.info(f"Retrieved {len(cards)} active card tokens from SQLite.")
                return cards
        except Exception as e:
            logger.warning(f"Failed to query SQLite cards.db: {e}. Falling back to default personas.")
            
    return DEFAULT_PERSONAS

async def simulate_swipe_event(client: httpx.AsyncClient, card: Dict[str, Any]) -> None:
    """Simulates a single credit card auth/settle/reverse workflow against the issuing bank gateway."""
    # Filter merchants matching persona MCCs
    matching_merchants = [m for m in merchants_list if m["mcc"] in card["mccs"]]
    if not matching_merchants:
        matching_merchants = merchants_list
        
    merchant = random.choice(matching_merchants)
    amount_cents = random.randint(card["amount_min"], card["amount_max"])
    rrn = "".join(random.choices("0123456789", k=12))
    
    headers = {"X-Card-Network-Token": CARD_NETWORK_TOKEN}
    auth_payload = {
        "card_token": card["card_token"],
        "amount_cents": amount_cents,
        "retrieval_reference_number": rrn,
        "merchant_category_code": merchant["mcc"],
        "merchant_name": merchant["merchant"],
        "card_network": "VISA"
    }
    
    auth_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    
    try:
        # 1. Authorize hold
        auth_resp = await client.post(auth_url, json=auth_payload, headers=headers, timeout=5.0)
        if auth_resp.status_code != 200:
            logger.warning(f"Auth request failed. HTTP {auth_resp.status_code}: {auth_resp.text}")
            return
            
        auth_data = auth_resp.json()
        if auth_data.get("action_code") != "00":
            logger.info(f"Swipe declined by gateway: card={card['cardholder_name']}, reason={auth_data.get('decline_reason')}")
            return
            
        # 2. Decide clearing resolution
        resolution = random.choices(["SETTLE", "REVERSE", "PENDING"], weights=[80, 10, 10], k=1)[0]
        
        if resolution == "SETTLE":
            # Add potential restaurant tip (15-20%) for food categories
            final_amount = amount_cents
            if merchant["mcc"] in ["5812", "5814"] and random.random() < 0.8:
                tip = int(amount_cents * random.choice([0.15, 0.18, 0.20]))
                final_amount += tip
                
            settle_payload = {
                "retrieval_reference_number": rrn,
                "amount_cents": final_amount,
                "description": f"{merchant['merchant']} Capture"
            }
            settle_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/settle"
            settle_resp = await client.post(settle_url, json=settle_payload, headers=headers, timeout=5.0)
            if settle_resp.status_code == 200:
                logger.info(f"Swipe settled successfully. Card: {card['cardholder_name']}, Merchant: {merchant['merchant']}, Amount: ${final_amount/100:.2f} (Hold: ${amount_cents/100:.2f})")
            else:
                logger.error(f"Settlement failed. HTTP {settle_resp.status_code}: {settle_resp.text}")
                
        elif resolution == "REVERSE":
            rev_payload = {"retrieval_reference_number": rrn}
            reverse_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse"
            rev_resp = await client.post(reverse_url, json=rev_payload, headers=headers, timeout=5.0)
            if rev_resp.status_code == 200:
                logger.info(f"Swipe hold reversed successfully. Card: {card['cardholder_name']}, RRN: {rrn}")
            else:
                logger.error(f"Reversal failed. HTTP {rev_resp.status_code}: {rev_resp.text}")
                
        else:
            logger.info(f"Swipe hold left PENDING (active hold). Card: {card['cardholder_name']}, Amount: ${amount_cents/100:.2f}")
            
    except Exception as exc:
        logger.error(f"Failed to execute simulation cycle for card {card['cardholder_name']}: {exc}")

async def run_activity_surge_task() -> None:
    """Fires 50 rapid-fire swipes staggered over 10 seconds."""
    logger.info("Starting activity surge simulation (50 swipes over 10s)...")
    cards = get_active_cards()
    if not cards:
        logger.warning("No cards resolved. Surge aborted.")
        return
        
    async with httpx.AsyncClient() as client:
        tasks = []
        for _ in range(50):
            card = random.choice(cards)
            tasks.append(simulate_swipe_event(client, card))
            await asyncio.sleep(0.2) # Stagger swipes
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Activity surge simulation completed successfully.")

@app.get("/health")
def health():
    return {"status": "ok", "service": "data-generator"}

@app.post("/simulate-pulse", status_code=status.HTTP_200_OK)
async def simulate_pulse():
    """Wakes up and fires a randomized batch of 3-5 swipes across the persona pool."""
    logger.info("Triggered simulated activity pulse...")
    cards = get_active_cards()
    if not cards:
        raise HTTPException(status_code=400, detail="No active cards found to swipe.")
        
    batch_size = random.randint(3, 5)
    swipes_to_run = [random.choice(cards) for _ in range(batch_size)]
    
    async with httpx.AsyncClient() as client:
        tasks = [simulate_swipe_event(client, card) for card in swipes_to_run]
        await asyncio.gather(*tasks, return_exceptions=True)
        
    return {"status": "SUCCESS", "swipes_attempted": batch_size}

@app.post("/simulate-surge", status_code=status.HTTP_200_OK)
def simulate_surge(background_tasks: BackgroundTasks):
    """Triggers an async rapid-fire activity surge of 50 swipes."""
    background_tasks.add_task(run_activity_surge_task)
    return {"status": "ACCEPTED", "message": "Simulation surge initiated in background."}

if __name__ == "__main__":
    # Support running as a simple standalone script to trigger a pulse
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--pulse":
        async def run_cli_pulse():
            cards = get_active_cards()
            async with httpx.AsyncClient() as client:
                await simulate_swipe_event(client, random.choice(cards))
        asyncio.run(run_cli_pulse())
    else:
        import uvicorn
        port = int(os.getenv("PORT", "8001"))
        uvicorn.run(app, host="0.0.0.0", port=port)
