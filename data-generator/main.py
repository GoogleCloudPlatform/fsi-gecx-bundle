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
import sys
from typing import List, Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class CardPayload(BaseModel):
    card_token: str
    cardholder_name: str
    persona: str
    mccs: List[str]
    amount_min: int
    amount_max: int


class SurgeRequest(BaseModel):
    active_cards: Optional[List[CardPayload]] = None


class AnomalyRequest(BaseModel):
    card_token: Optional[str] = None
    user_id: Optional[str] = None
    email: Optional[str] = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("data-generator")

app = FastAPI(title="Modernized Synthetic Transaction Data Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configs
BANKING_SERVICE_URL = os.getenv("BANKING_SERVICE_URL", "http://localhost:8000")
CARD_NETWORK_TOKEN = os.getenv("CARD_NETWORK_SWITCH_TOKEN", "switch-secret-key-12345")

def is_local_mode() -> bool:
    return os.getenv("ENV", "local") == "local" and not os.getenv("K_SERVICE")

def verify_switch_or_presenter_token(
    x_card_network_token: Optional[str] = Header(None, alias="X-Card-Network-Token")
):
    if x_card_network_token and x_card_network_token == CARD_NETWORK_TOKEN:
        return True
    if is_local_mode():
        return True
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized access to data generator.")

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

merchants_list: List[Dict[str, Any]] = []

_cached_oidc_token = None
_cached_token_time = 0

def get_service_headers() -> Dict[str, str]:
    """
    Constructs required headers for communicating with banking-service.
    Includes X-Card-Network-Token for application auth and an automatic Google OIDC ID token
    for Google Cloud Run IAM invoker verification.
    """
    global _cached_oidc_token, _cached_token_time
    import time
    
    headers = {"X-Card-Network-Token": CARD_NETWORK_TOKEN}
    if BANKING_SERVICE_URL and "localhost" not in BANKING_SERVICE_URL and "127.0.0.1" not in BANKING_SERVICE_URL:
        # Cache token for 50 minutes (expires in 60 min)
        if _cached_oidc_token and (time.time() - _cached_token_time) < 3000:
            headers["Authorization"] = f"Bearer {_cached_oidc_token}"
            return headers
            
        try:
            import google.auth
            import google.auth.transport.requests
            from google.oauth2 import id_token
            auth_req = google.auth.transport.requests.Request()
            oidc_token = id_token.fetch_id_token(auth_req, BANKING_SERVICE_URL)
            if oidc_token:
                _cached_oidc_token = oidc_token
                _cached_token_time = time.time()
                headers["Authorization"] = f"Bearer {oidc_token}"
        except Exception as auth_err:
            logger.warning(f"Could not fetch Google OIDC ID token for {BANKING_SERVICE_URL}: {auth_err}")
    return headers

def get_merchants() -> List[Dict[str, Any]]:
    """Fetches merchant catalog via HTTP from banking-service, falling back to local resources or static defaults."""
    global merchants_list
    if merchants_list:
        return merchants_list
        
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{BANKING_SERVICE_URL}/api/v1/merchants", headers=get_service_headers())
            if res.status_code == 200:
                data = res.json()
                loaded = []
                for item in data:
                    loaded.append({
                        "merchant": item.get("clean_name", "Unknown"),
                        "descriptor": item.get("raw_descriptor", item.get("clean_name", "Unknown")),
                        "category": item.get("category", "Retail"),
                        "mcc": item.get("default_mcc", "5310"),
                        "country_code": item.get("country_code", "USA"),
                        "is_international": item.get("is_international", False),
                        "risk_score": item.get("risk_score", 0)
                    })
                if loaded:
                    merchants_list = loaded
                    logger.info(f"Retrieved {len(merchants_list)} merchants via HTTP from {BANKING_SERVICE_URL}/api/v1/merchants.")
                    return merchants_list
    except Exception as e:
        logger.warning(f"Could not fetch merchants via HTTP from {BANKING_SERVICE_URL}: {e}")

    # Fallback to local CSV in data-generator/resources/merchants.csv if present
    csv_path = os.path.join(os.path.dirname(__file__), "resources", "merchants.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                loaded = []
                for row in reader:
                    cat = row.get("Category", "Retail")
                    mcc = CATEGORY_MCC_MAP.get(cat, "5310")
                    loaded.append({
                        "merchant": row.get("Merchant", "Unknown"),
                        "descriptor": row.get("Merchant", "Unknown"),
                        "category": cat,
                        "mcc": mcc,
                        "country_code": "USA",
                        "is_international": False,
                        "risk_score": 0
                    })
                if loaded:
                    merchants_list = loaded
                    logger.info(f"Loaded {len(merchants_list)} merchants from local CSV.")
                    return merchants_list
        except Exception as e:
            logger.error(f"Error reading local CSV: {e}")

    # Minimal fallback list
    merchants_list = [
        {"merchant": "Amazon", "descriptor": "AMAZON.COM*MKTPLACE", "category": "Retail", "mcc": "5310", "country_code": "USA", "is_international": False, "risk_score": 0},
        {"merchant": "Starbucks", "descriptor": "STARBUCKS - MOUNTAIN VIEW CA", "category": "Coffee Shops & Dining", "mcc": "5814", "country_code": "USA", "is_international": False, "risk_score": 0},
        {"merchant": "Delta Air Lines", "descriptor": "DELTA AIR LINES", "category": "Airlines & Travel", "mcc": "4511", "country_code": "USA", "is_international": False, "risk_score": 0},
        {"merchant": "Coco Bongo", "descriptor": "COCO BONGO CANCUN [MEX]", "category": "Fast Food & Dining", "mcc": "5812", "country_code": "MEX", "is_international": True, "risk_score": 25},
    ]
    return merchants_list

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
    Attempts to fetch active card tokens dynamically via HTTP GET from banking-service.
    Falls back to static DEFAULT_PERSONAS manifest.
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards", headers=get_service_headers())
            if res.status_code == 200:
                data = res.json()
                cards = data.get("active_cards", [])
                if cards:
                    logger.info(f"Retrieved {len(cards)} active card tokens via HTTP from banking-service.")
                    return cards
            logger.warning(f"Active card discovery failed. HTTP {res.status_code}: {res.text}")
    except Exception as e:
        logger.warning(f"Could not fetch active cards via HTTP from {BANKING_SERVICE_URL}: {e}")

    if is_local_mode():
        logger.info("Using static DEFAULT_PERSONAS fallback for local active-card simulation.")
        return DEFAULT_PERSONAS
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to resolve active cards from banking-service; refusing to use static fallback in deployed mode."
    )

async def simulate_swipe_event(client: httpx.AsyncClient, card: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates a single credit card auth/settle/reverse workflow against the issuing bank gateway."""
    merchants = get_merchants()
    mccs = card.get("mccs", ["5310", "5411", "5541", "4121"])
    matching_merchants = [m for m in merchants if m.get("mcc") in mccs]
    if not matching_merchants:
        matching_merchants = merchants
        
    is_googler = "GOOGLE" in str(card.get("cardholder_name", "")).upper() or "PRESENTER" in str(card.get("cardholder_name", "")).upper() or "DEMO" in str(card.get("cardholder_name", "")).upper()
    metros = ["MOUNTAIN VIEW CA", "SAN FRANCISCO CA", "NEW YORK NY", "CHICAGO IL", "SEATTLE WA", "DALLAS TX", "LOS ANGELES CA"]
    if is_googler:
        home_metro = ["MOUNTAIN VIEW CA", "SAN FRANCISCO CA"][hash(card.get("cardholder_name", "default")) % 2]
    else:
        home_metro = metros[hash(card.get("cardholder_name", "default")) % len(metros)]

    is_intl_swipe = is_googler and (random.random() < 0.25)
    if is_intl_swipe:
        region_merchants = [m for m in merchants if m.get("is_international") and m.get("country_code") == "MEX" and m.get("mcc") in mccs]
        if not region_merchants:
            region_merchants = [m for m in merchants if m.get("is_international") and m.get("country_code") == "MEX"]
    else:
        region_merchants = [m for m in merchants if not m.get("is_international") and m.get("mcc") in mccs]
        if not region_merchants:
            region_merchants = [m for m in merchants if not m.get("is_international")]

    matching_merchants = region_merchants if region_merchants else merchants
    merchant = random.choice(matching_merchants)
    amount_min = card.get("amount_min", 1500)
    amount_max = card.get("amount_max", 15000)
    amount_cents = random.randint(amount_min, amount_max)
    
    if merchant.get("mcc") == "5814": # Coffee
        amount_cents = min(amount_cents, 5000)
    elif merchant.get("mcc") == "5812": # Dining
        amount_cents = min(amount_cents, 30000)
    elif merchant.get("mcc") == "5541": # Gas
        amount_cents = min(amount_cents, 10000)

    raw_name = merchant.get("merchant", "Store")
    if merchant.get("descriptor") and merchant["descriptor"] != raw_name:
        formatted_merchant = merchant["descriptor"]
    elif merchant.get("category") in ["Streaming & Entertainment", "Electronics & Software"] or raw_name in ["Amazon", "Netflix", "Spotify", "Apple"]:
        formatted_merchant = f"{raw_name.upper()}*ONLINE" if "Amazon" not in raw_name else "AMAZON.COM*MKTPLACE"
    else:
        formatted_merchant = f"{raw_name.upper()} - {home_metro}"

    rrn = "".join(random.choices("0123456789", k=12))
    
    headers = get_service_headers()
    auth_payload = {
        "card_token": card["card_token"],
        "amount_cents": amount_cents,
        "retrieval_reference_number": rrn,
        "merchant_category_code": merchant.get("mcc", "5310"),
        "merchant_name": formatted_merchant,
        "card_network": "VISA"
    }
    
    auth_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    
    try:
        auth_resp = await client.post(auth_url, json=auth_payload, headers=headers, timeout=5.0)
        if auth_resp.status_code != 200:
            logger.warning(f"Auth request failed. HTTP {auth_resp.status_code}: {auth_resp.text}")
            return {
                "card_token": card.get("card_token"),
                "rrn": rrn,
                "authorized": False,
                "settled": False,
                "reversed": False,
                "decline_reason": f"HTTP_{auth_resp.status_code}",
                "error": auth_resp.text,
            }
            
        auth_data = auth_resp.json()
        if auth_data.get("action_code") != "00":
            logger.info(f"Swipe declined by gateway: card={card.get('cardholder_name')}, reason={auth_data.get('decline_reason')}")
            return {
                "card_token": card.get("card_token"),
                "rrn": rrn,
                "authorized": False,
                "settled": False,
                "reversed": False,
                "decline_reason": auth_data.get("decline_reason"),
                "error": None,
            }
            
        resolution = random.choices(["SETTLE", "REVERSE", "PENDING"], weights=[80, 10, 10], k=1)[0]
        
        if resolution == "SETTLE":
            final_amount = amount_cents
            if merchant.get("mcc") in ["5812", "5814"] and random.random() < 0.8:
                tip = int(amount_cents * random.choice([0.15, 0.18, 0.20]))
                final_amount += tip
                
            settle_payload = {
                "retrieval_reference_number": rrn,
                "amount_cents": final_amount,
                "description": f"{merchant.get('merchant', 'Store')} Capture"
            }
            settle_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/settle"
            settle_resp = await client.post(settle_url, json=settle_payload, headers=headers, timeout=5.0)
            if settle_resp.status_code == 200:
                logger.info(f"Swipe settled successfully. Card: {card.get('cardholder_name')}, Merchant: {merchant.get('merchant')}, Amount: ${final_amount/100:.2f} (Hold: ${amount_cents/100:.2f})")
                return {
                    "card_token": card.get("card_token"),
                    "rrn": rrn,
                    "authorized": True,
                    "settled": True,
                    "reversed": False,
                    "decline_reason": None,
                    "error": None,
                }
            else:
                logger.error(f"Settlement failed. HTTP {settle_resp.status_code}: {settle_resp.text}")
                return {
                    "card_token": card.get("card_token"),
                    "rrn": rrn,
                    "authorized": True,
                    "settled": False,
                    "reversed": False,
                    "decline_reason": None,
                    "error": f"SETTLE_HTTP_{settle_resp.status_code}: {settle_resp.text}",
                }
                
        elif resolution == "REVERSE":
            rev_payload = {"retrieval_reference_number": rrn}
            reverse_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/reverse"
            rev_resp = await client.post(reverse_url, json=rev_payload, headers=headers, timeout=5.0)
            if rev_resp.status_code == 200:
                logger.info(f"Swipe hold reversed successfully. Card: {card.get('cardholder_name')}, RRN: {rrn}")
                return {
                    "card_token": card.get("card_token"),
                    "rrn": rrn,
                    "authorized": True,
                    "settled": False,
                    "reversed": True,
                    "decline_reason": None,
                    "error": None,
                }
            else:
                logger.error(f"Reversal failed. HTTP {rev_resp.status_code}: {rev_resp.text}")
                return {
                    "card_token": card.get("card_token"),
                    "rrn": rrn,
                    "authorized": True,
                    "settled": False,
                    "reversed": False,
                    "decline_reason": None,
                    "error": f"REVERSE_HTTP_{rev_resp.status_code}: {rev_resp.text}",
                }
                
        else:
            logger.info(f"Swipe hold left PENDING (active hold). Card: {card.get('cardholder_name')}, Amount: ${amount_cents/100:.2f}")
            return {
                "card_token": card.get("card_token"),
                "rrn": rrn,
                "authorized": True,
                "settled": False,
                "reversed": False,
                "decline_reason": None,
                "error": None,
            }
            
    except Exception as exc:
        logger.error(f"Failed to execute simulation cycle for card {card.get('cardholder_name')}: {repr(exc)}")
        return {
            "card_token": card.get("card_token"),
            "rrn": rrn,
            "authorized": False,
            "settled": False,
            "reversed": False,
            "decline_reason": None,
            "error": repr(exc),
        }


def summarize_swipe_results(results: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "swipes_attempted": len(results),
        "authorizations_created": sum(1 for r in results if r.get("authorized")),
        "settlements_created": sum(1 for r in results if r.get("settled")),
        "reversals_created": sum(1 for r in results if r.get("reversed")),
        "declines": sum(1 for r in results if r.get("decline_reason")),
        "failures": sum(1 for r in results if r.get("error")),
    }

async def run_activity_surge_task(active_cards: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
    """Fires 50 rapid-fire swipes staggered over 10 seconds."""
    logger.info("Starting activity surge simulation (50 swipes over 10s)...")
    cards = active_cards or get_active_cards()
    if not cards:
        logger.warning("No cards resolved. Surge aborted.")
        raise HTTPException(status_code=400, detail="No active cards resolved. Surge aborted.")
        
    async with httpx.AsyncClient() as client:
        tasks = []
        for _ in range(50):
            card = random.choice(cards)
            tasks.append(simulate_swipe_event(client, card))
            await asyncio.sleep(0.2)
        results = await asyncio.gather(*tasks, return_exceptions=False)
    summary = summarize_swipe_results(results)
    logger.info(f"Activity surge simulation completed: {summary}")
    return summary

@app.get("/health")
def health():
    return {"status": "ok", "service": "data-generator"}

@app.post("/generate", status_code=status.HTTP_200_OK)
@app.post("/simulate-pulse", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_pulse():
    """Wakes up and fires a randomized batch of 3-5 swipes every 10 seconds for a full minute."""
    logger.info("Triggered simulated activity pulse (6 bursts over 60s)...")
    cards = get_active_cards()
    if not cards:
        raise HTTPException(status_code=400, detail="No active cards found to swipe.")
        
    all_results = []
    
    async with httpx.AsyncClient() as client:
        for _ in range(6):
            batch_size = random.randint(3, 5)
            swipes_to_run = [random.choice(cards) for _ in range(batch_size)]
            
            tasks = [simulate_swipe_event(client, card) for card in swipes_to_run]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            all_results.extend(results)
            await asyncio.sleep(10)
        
    summary = summarize_swipe_results(all_results)
    if summary["authorizations_created"] == 0:
        raise HTTPException(status_code=502, detail={"message": "No transaction authorizations were created.", **summary})
    return {"status": "SUCCESS", **summary, "active_cards_count": len(cards)}

@app.post("/simulate-surge", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_surge(payload: SurgeRequest):
    """Triggers an async rapid-fire activity surge of 50 swipes."""
    active_cards = [c.model_dump() for c in payload.active_cards] if payload.active_cards else None
    if not active_cards:
        active_cards = get_active_cards()
    if not active_cards:
        raise HTTPException(status_code=400, detail="No active cards supplied or discovered for surge.")
    summary = await run_activity_surge_task(active_cards)
    if summary["authorizations_created"] == 0:
        raise HTTPException(status_code=502, detail={"message": "No transaction authorizations were created.", **summary})
    return {
        "status": "SUCCESS",
        "message": "Simulation surge completed against active card pool.",
        "active_cards_count": len(active_cards),
        **summary,
    }

@app.post("/inject-anomaly", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def inject_anomaly(req: Optional[AnomalyRequest] = None):
    """
    Accepts a card token (or defaults to CE presenter) and fires 4 rapid-fire Mexico/Cancun fraud authorizations
    against /api/v1/card-network/authorize.
    """
    target_token = req.card_token if req and req.card_token else None
    if not target_token:
        cards = get_active_cards()
        if not cards:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active cards found to target for anomaly.")
        for c in cards:
            name_upper = str(c.get("cardholder_name", "")).upper()
            if "PRESENTER" in name_upper or "SERVEDIO" in name_upper or "MARCUS" in name_upper:
                target_token = c["card_token"]
                break
        if not target_token:
            target_token = cards[0]["card_token"]

    swipes = [
        ("GAME*TEST TOKEN ONLINE", 499, "5814", "USA", 0),
        ("APPLE.COM*ONLINE", 149900, "5310", "USA", 0),
        ("BEST BUY*MKTPLACE", 215000, "5310", "USA", 0),
        ("LUXURY BOUTIQUE CANCUN [MEX]", 320000, "5310", "MEX", 30),
    ]

    injected_auths = []
    headers = get_service_headers()
    auth_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"

    async with httpx.AsyncClient() as client:
        for idx, (desc, amt, mcc, country, risk) in enumerate(swipes):
            payload = {
                "card_token": target_token,
                "amount_cents": amt,
                "retrieval_reference_number": f"REF{random.randint(100000000, 999999999)}",
                "merchant_category_code": mcc,
                "merchant_name": desc,
                "card_network": "VISA"
            }
            try:
                res = await client.post(auth_url, json=payload, headers=headers, timeout=5.0)
                if res.status_code == 200:
                    data = res.json()
                    injected_auths.append(data)
                else:
                    logger.warning(f"Anomaly auth hold failed for {desc}: HTTP {res.status_code} - {res.text}")
            except Exception as e:
                logger.error(f"Error injecting anomaly auth hold for {desc}: {e}")

    return {
        "status": "ANOMALY_INJECTED",
        "card_token": target_token,
        "injected_swipes_count": len(injected_auths),
        "total_fraud_cents": sum(amt for _, amt, _, _, _ in swipes),
        "message": "Targeted fraud anomaly surge successfully dispatched against card-network gateway."
    }

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
