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
import logging
import os
import random
import sys
from typing import List, Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, status, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from utils.internal_auth import get_internal_switch_token
from utils.runtime import get_cors_origins, is_local_dev


class CardPayload(BaseModel):
    card_token: str
    cardholder_name: str
    persona: str
    mccs: List[str]
    amount_min: int
    amount_max: int
    available_credit_cents: Optional[int] = None
    generator_eligible: bool = True


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
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configs
BANKING_SERVICE_URL = os.getenv("BANKING_SERVICE_URL", "http://localhost:8000")
PULSE_WINDOW_SECONDS = int(os.getenv("PULSE_WINDOW_SECONDS", "58"))
PULSE_MIN_EVENTS = int(os.getenv("PULSE_MIN_EVENTS", "8"))
PULSE_MAX_EVENTS = int(os.getenv("PULSE_MAX_EVENTS", "12"))
SWIPE_WORKFLOW_CONCURRENCY = int(os.getenv("SWIPE_WORKFLOW_CONCURRENCY", "4"))
SURGE_TOTAL_EVENTS = int(os.getenv("SURGE_TOTAL_EVENTS", "50"))
SURGE_STAGGER_SECONDS = float(os.getenv("SURGE_STAGGER_SECONDS", "0.2"))
ACTIVE_CARD_FETCH_TIMEOUT_SECONDS = float(os.getenv("ACTIVE_CARD_FETCH_TIMEOUT_SECONDS", "10"))
AUTO_PAYDOWN_MAX_ACCOUNTS_PER_PULSE = int(os.getenv("AUTO_PAYDOWN_MAX_ACCOUNTS_PER_PULSE", "6"))
SWIPE_REQUEST_TIMEOUT_SECONDS = float(os.getenv("SWIPE_REQUEST_TIMEOUT_SECONDS", "10"))

_pulse_lock = asyncio.Lock()


class MaintenanceModeError(RuntimeError):
    """Raised when banking-service has temporarily paused writes for maintenance/reset."""


def get_card_network_token() -> str:
    """Resolve the internal switch token lazily so the container can still boot and report health."""
    return get_internal_switch_token()


def verify_switch_or_presenter_token(
    x_card_network_token: Optional[str] = Header(None, alias="X-Card-Network-Token")
):
    if x_card_network_token and x_card_network_token == get_card_network_token():
        return True
    if is_local_dev():
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
    "Streaming & Entertainment": "4899",
    "Electronics & Software": "5311",
    "Electronics": "5311",
    "Home Improvement": "5200",
    "Pharmacies & Health": "5912",
    "Rideshare & Transport": "4121",
}

merchants_list: List[Dict[str, Any]] = []

_cached_oidc_token = None
_cached_token_time = 0


def build_generic_merchant(mcc: str = "5311", country_code: str = "USA", is_international: bool = False) -> Dict[str, Any]:
    return {
        "merchant": "Generic Merchant",
        "descriptor": "GENERIC MERCHANT",
        "category": "Retail",
        "mcc": mcc,
        "country_code": country_code,
        "is_international": is_international,
        "risk_score": 20 if is_international else 0,
    }

def get_service_headers() -> Dict[str, str]:
    """
    Constructs required headers for communicating with banking-service.
    Includes X-Card-Network-Token for application auth and an automatic Google OIDC ID token
    for Google Cloud Run IAM invoker verification.
    """
    global _cached_oidc_token, _cached_token_time
    import time
    
    headers = {"X-Card-Network-Token": get_card_network_token()}
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
            raise RuntimeError(
                f"Could not fetch Google OIDC ID token for banking-service at {BANKING_SERVICE_URL}: {auth_err}"
            ) from auth_err

        if "Authorization" not in headers:
            raise RuntimeError(
                f"Missing OIDC authorization header for remote banking-service at {BANKING_SERVICE_URL}."
            )
    return headers


def get_spendable_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters the active card pool down to cards that still have spendable credit."""
    spendable_cards = []
    for card in cards:
        available_credit = card.get("available_credit_cents")
        if available_credit is None:
            spendable_cards.append(card)
            continue
        if available_credit >= 100:
            spendable_cards.append(card)
    return spendable_cards


def get_generator_eligible_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Excludes presenter and VIP/demo-script accounts from random generator traffic."""
    return [card for card in cards if card.get("generator_eligible", True)]


def _is_maintenance_response(response: httpx.Response) -> bool:
    if response.status_code != status.HTTP_503_SERVICE_UNAVAILABLE:
        return False
    try:
        detail = response.json().get("detail")
    except ValueError:
        return False
    return isinstance(detail, dict) and detail.get("status") == "MAINTENANCE"


async def auto_paydown_high_utilization_cards(
    client: httpx.AsyncClient,
    cards: List[Dict[str, Any]],
    trigger_utilization: float = 0.65,
    target_utilization: float = 0.35,
) -> List[Dict[str, Any]]:
    """Pays down highly utilized mock credit cards from checking first, then savings."""
    results = []
    headers = get_service_headers()
    eligible_cards = []

    for card in cards:
        credit_limit_cents = card.get("credit_limit_cents") or 0
        available_credit_cents = card.get("available_credit_cents")
        customer_id = card.get("customer_id")
        credit_account_id = card.get("credit_account_id")

        if not credit_limit_cents or available_credit_cents is None or not customer_id or not credit_account_id:
            continue

        utilization = 1 - (available_credit_cents / credit_limit_cents)
        if utilization < trigger_utilization:
            continue

        eligible_cards.append(card)

    if not eligible_cards:
        return results

    random.shuffle(eligible_cards)
    if AUTO_PAYDOWN_MAX_ACCOUNTS_PER_PULSE > 0:
        eligible_cards = eligible_cards[:AUTO_PAYDOWN_MAX_ACCOUNTS_PER_PULSE]

    for card in eligible_cards:
        customer_id = card.get("customer_id")
        credit_account_id = card.get("credit_account_id")

        try:
            response = await client.post(
                f"{BANKING_SERVICE_URL}/api/v1/credit-card/internal/auto-paydown",
                json={
                    "customer_id": customer_id,
                    "credit_account_id": credit_account_id,
                    "target_utilization": target_utilization,
                    "trigger_utilization": trigger_utilization,
                },
                headers=headers,
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            logger.warning(
                "Auto-paydown request failed for credit account %s: %s",
                credit_account_id,
                exc,
            )
            results.append(
                {
                    "credit_account_id": credit_account_id,
                    "customer_id": customer_id,
                    "status": "FAILED",
                    "error": str(exc),
                }
            )
            continue

        if _is_maintenance_response(response):
            logger.info("Skipping auto-paydown during banking-service maintenance for credit account %s.", credit_account_id)
            results.append(
                {
                    "credit_account_id": credit_account_id,
                    "customer_id": customer_id,
                    "status": "SKIPPED",
                    "reason": "MAINTENANCE",
                }
            )
            continue

        if response.status_code != 200:
            logger.warning(
                "Auto-paydown failed for credit account %s. HTTP %s: %s",
                credit_account_id,
                response.status_code,
                response.text,
            )
            results.append(
                {
                    "credit_account_id": credit_account_id,
                    "customer_id": customer_id,
                    "status": "FAILED",
                    "error": response.text,
                }
            )
            continue

        result = response.json()
        result["credit_account_id"] = credit_account_id
        result["customer_id"] = customer_id
        results.append(result)

    return results

def get_merchants() -> List[Dict[str, Any]]:
    """Fetches merchant catalog from banking-service and uses a single generic fallback only for local dev."""
    global merchants_list
    if merchants_list:
        return merchants_list

    merchant_endpoints = [
        f"{BANKING_SERVICE_URL}/api/v1/merchants",
        f"{BANKING_SERVICE_URL}/merchants",
    ]

    try:
        with httpx.Client(timeout=5.0) as client:
            for endpoint in merchant_endpoints:
                res = client.get(endpoint, headers=get_service_headers())
                if res.status_code != 200:
                    continue

                data = res.json()
                loaded = []
                for item in data:
                    clean_name = item.get("clean_name", "Unknown")
                    loaded.append({
                        "merchant": clean_name,
                        "descriptor": item.get(
                            "raw_descriptor_pattern",
                            item.get("raw_descriptor", clean_name),
                        ),
                        "category": item.get("category", "Retail"),
                        "mcc": item.get("mcc", item.get("default_mcc", "5311")),
                        "country_code": item.get("country_code", "USA"),
                        "is_international": item.get("is_international", False),
                        "risk_score": item.get("risk_score", 0),
                    })
                if loaded:
                    merchants_list = loaded
                    logger.info("Retrieved %s merchants via HTTP from %s.", len(merchants_list), endpoint)
                    return merchants_list
    except Exception as e:
        logger.warning(f"Could not fetch merchants via HTTP from {BANKING_SERVICE_URL}: {e}")

    if is_local_dev():
        merchants_list = [build_generic_merchant()]
        logger.info("Using single generic local merchant fallback because banking-service catalog is unavailable.")
        return merchants_list

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to resolve merchant catalog from banking-service.",
    )

# Static local-only personas for offline development.
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
        "mccs": ["5411", "5541", "5311", "4121"],
        "amount_min": 1500,
        "amount_max": 15000,
    },
    {
        "card_token": "tok_visa_marcus_vance",
        "cardholder_name": "Marcus Vance",
        "persona": "PRIME",
        "mccs": ["5411", "5541", "5311", "4121"],
        "amount_min": 1500,
        "amount_max": 15000,
    },
    {
        "card_token": "tok_visa_chloe_gomez",
        "cardholder_name": "Chloe Gomez",
        "persona": "YPRO",
        "mccs": ["5814", "4899", "5812"],
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
        with httpx.Client(timeout=ACTIVE_CARD_FETCH_TIMEOUT_SECONDS) as client:
            res = client.get(f"{BANKING_SERVICE_URL}/api/v1/credit-card/active-cards", headers=get_service_headers())
            if res.status_code == 200:
                data = res.json()
                cards = get_generator_eligible_cards(data.get("active_cards", []))
                if cards:
                    logger.info(f"Retrieved {len(cards)} active card tokens via HTTP from banking-service.")
                    return cards
            if _is_maintenance_response(res):
                raise MaintenanceModeError("banking-service reset is in progress")
            logger.warning(f"Active card discovery failed. HTTP {res.status_code}: {res.text}")
    except Exception as e:
        if isinstance(e, MaintenanceModeError):
            raise
        logger.warning(f"Could not fetch active cards via HTTP from {BANKING_SERVICE_URL}: {e}")

    if is_local_dev():
        logger.info("Using static DEFAULT_PERSONAS fallback for local active-card simulation.")
        return get_generator_eligible_cards(DEFAULT_PERSONAS)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to resolve active cards from banking-service; refusing to use static fallback in deployed mode."
    )

async def simulate_swipe_event(client: httpx.AsyncClient, card: Dict[str, Any]) -> Dict[str, Any]:
    """Simulates a single credit card auth/settle/reverse workflow against the issuing bank gateway."""
    merchants = get_merchants()
    mccs = card.get("mccs", ["5311", "5411", "5541", "4121"])
    default_mcc = next((mcc for mcc in mccs if mcc), "5311")
    matching_merchants = [m for m in merchants if m.get("mcc") in mccs]
    if not matching_merchants:
        matching_merchants = [build_generic_merchant(mcc=default_mcc)]
        
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

    matching_merchants = region_merchants if region_merchants else matching_merchants
    if not matching_merchants:
        fallback_country = "MEX" if is_intl_swipe else "USA"
        matching_merchants = [
            build_generic_merchant(
                mcc=default_mcc,
                country_code=fallback_country,
                is_international=is_intl_swipe,
            )
        ]
    merchant = random.choice(matching_merchants)
    available_credit = card.get("available_credit_cents")
    amount_min = card.get("amount_min", 1500)
    amount_max = card.get("amount_max", 15000)

    if available_credit is not None:
        amount_max = min(amount_max, int(available_credit))
        amount_min = min(amount_min, amount_max)
        if amount_max < 100:
            return {
                "card_token": card.get("card_token"),
                "rrn": None,
                "authorized": False,
                "settled": False,
                "reversed": False,
                "decline_reason": "INSUFFICIENT_AVAILABLE_CREDIT",
                "error": None,
            }

    amount_floor = max(100, amount_min)
    if amount_max < amount_floor:
        amount_floor = amount_max
    amount_cents = random.randint(amount_floor, amount_max)
    
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
        "merchant_category_code": merchant.get("mcc", "5311"),
        "merchant_name": formatted_merchant,
        "card_network": "VISA"
    }
    
    auth_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    
    try:
        auth_resp = await client.post(auth_url, json=auth_payload, headers=headers, timeout=SWIPE_REQUEST_TIMEOUT_SECONDS)
        if _is_maintenance_response(auth_resp):
            logger.info("Skipping swipe because banking-service is in maintenance mode.")
            return {
                "card_token": card.get("card_token"),
                "rrn": rrn,
                "authorized": False,
                "settled": False,
                "reversed": False,
                "decline_reason": "MAINTENANCE",
                "error": None,
            }
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
            }
            settle_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/settle"
            settle_resp = await client.post(settle_url, json=settle_payload, headers=headers, timeout=SWIPE_REQUEST_TIMEOUT_SECONDS)
            if _is_maintenance_response(settle_resp):
                logger.info("Skipping settlement because banking-service entered maintenance mode.")
                return {
                    "card_token": card.get("card_token"),
                    "rrn": rrn,
                    "authorized": True,
                    "settled": False,
                    "reversed": False,
                    "decline_reason": "MAINTENANCE",
                    "error": None,
                }
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
            rev_resp = await client.post(reverse_url, json=rev_payload, headers=headers, timeout=SWIPE_REQUEST_TIMEOUT_SECONDS)
            if _is_maintenance_response(rev_resp):
                logger.info("Skipping reversal because banking-service entered maintenance mode.")
                return {
                    "card_token": card.get("card_token"),
                    "rrn": rrn,
                    "authorized": True,
                    "settled": False,
                    "reversed": False,
                    "decline_reason": "MAINTENANCE",
                    "error": None,
                }
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


def build_randomized_pulse_plan(total_events: int, window_seconds: int = 58) -> List[float]:
    """Distributes swipe events across the minute using randomized offsets."""
    if total_events <= 0:
        return []
    return sorted(random.uniform(0, window_seconds) for _ in range(total_events))

async def run_activity_surge_task(active_cards: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
    """Fires 50 rapid-fire swipes staggered over 10 seconds."""
    logger.info("Starting activity surge simulation (%s swipes over staggered intervals)...", SURGE_TOTAL_EVENTS)
    cards = active_cards or get_active_cards()
    cards = get_spendable_cards(cards)
    if not cards:
        logger.warning("No spendable cards resolved. Surge aborted.")
        raise HTTPException(status_code=409, detail="No spendable active cards resolved. Surge aborted.")

    semaphore = asyncio.Semaphore(SWIPE_WORKFLOW_CONCURRENCY)

    async def bounded_swipe(client: httpx.AsyncClient, card: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            return await simulate_swipe_event(client, card)

    async with httpx.AsyncClient() as client:
        tasks = []
        for _ in range(SURGE_TOTAL_EVENTS):
            card = random.choice(cards)
            tasks.append(bounded_swipe(client, card))
            await asyncio.sleep(SURGE_STAGGER_SECONDS)
        results = await asyncio.gather(*tasks, return_exceptions=False)
        paydown_results = await auto_paydown_high_utilization_cards(client, cards)
    summary = summarize_swipe_results(results)
    summary["auto_paydowns_processed"] = sum(1 for result in paydown_results if result.get("status") == "SUCCESS")
    logger.info(f"Activity surge simulation completed: {summary}")
    return summary

@app.get("/health")
def health():
    from utils.version import BUILD_VERSION, BUILD_COMMIT_ID
    return {
        "status": "ok",
        "service": "data-generator",
        "version": BUILD_VERSION,
        "commit": BUILD_COMMIT_ID,
    }

@app.post("/generate", status_code=status.HTTP_200_OK)
@app.post("/simulate-pulse", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_pulse():
    """Wakes up once a minute and fans transactions across the next 58 seconds."""
    if _pulse_lock.locked():
        logger.info("Skipping pulse because another simulation pulse is already running.")
        return {
            "status": "SKIPPED",
            "message": "Another simulation pulse is already in progress.",
        }

    async with _pulse_lock:
        logger.info("Triggered randomized simulation pulse for the next %s seconds.", PULSE_WINDOW_SECONDS)
        try:
            cards = get_spendable_cards(get_active_cards())
        except MaintenanceModeError:
            return {
                "status": "SKIPPED",
                "message": "banking-service reset is in progress.",
                "active_cards_count": 0,
            }
        except HTTPException as exc:
            logger.warning("Skipping simulation pulse because active card discovery is unavailable: %s", exc.detail)
            return {
                "status": "SKIPPED",
                "message": "Active card discovery is temporarily unavailable.",
                "reason": exc.detail,
                "active_cards_count": 0,
            }
        if not cards:
            return {
                "status": "SKIPPED",
                "message": "No spendable active cards found to swipe.",
                "active_cards_count": 0,
            }

        total_events = random.randint(PULSE_MIN_EVENTS, PULSE_MAX_EVENTS)
        event_offsets = build_randomized_pulse_plan(total_events=total_events, window_seconds=PULSE_WINDOW_SECONDS)
        semaphore = asyncio.Semaphore(SWIPE_WORKFLOW_CONCURRENCY)

        async def dispatch_after_offset(client: httpx.AsyncClient, offset_seconds: float, card: Dict[str, Any]) -> Dict[str, Any]:
            await asyncio.sleep(offset_seconds)
            async with semaphore:
                return await simulate_swipe_event(client, card)

        async with httpx.AsyncClient() as client:
            tasks = [
                dispatch_after_offset(client, offset, random.choice(cards))
                for offset in event_offsets
            ]
            all_results = await asyncio.gather(*tasks, return_exceptions=False)
            paydown_results = await auto_paydown_high_utilization_cards(client, cards)

        summary = summarize_swipe_results(all_results)
        summary["auto_paydowns_processed"] = sum(1 for result in paydown_results if result.get("status") == "SUCCESS")
        status_label = "SUCCESS" if summary["authorizations_created"] > 0 else "NOOP"
        message = (
            "Simulation pulse completed."
            if summary["authorizations_created"] > 0
            else "Simulation pulse completed without creating new authorizations."
        )
        return {
            "status": status_label,
            "message": message,
            "distribution_window_seconds": PULSE_WINDOW_SECONDS,
            "scheduled_events": total_events,
            **summary,
            "active_cards_count": len(cards),
        }

@app.post("/simulate-surge", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_surge(payload: SurgeRequest):
    """Triggers an async rapid-fire activity surge of 50 swipes."""
    active_cards = [c.model_dump() for c in payload.active_cards] if payload.active_cards else None
    if not active_cards:
        try:
            active_cards = get_active_cards()
        except MaintenanceModeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="banking-service reset is in progress.",
            )
    active_cards = get_spendable_cards(get_generator_eligible_cards(active_cards))
    if not active_cards:
        raise HTTPException(status_code=409, detail="No spendable active cards supplied or discovered for surge.")
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
    Accepts a card token (or defaults to CE presenter) and fires 5 rapid-fire digital fraud authorizations
    against /api/v1/card-network/authorize.
    """
    target_token = req.card_token if req and req.card_token else None
    if not target_token:
        try:
            cards = get_active_cards()
        except MaintenanceModeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="banking-service reset is in progress.",
            )
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
        ("APPLE.COM*ONLINE", 149900, "4899", "USA", 0),
        ("BEST BUY*MKTPLACE", 215000, "5311", "USA", 0),
        ("RAZER GOLD GIFT CARD", 125000, "5947", "USA", 30),
        ("TARGET.COM GIFT CARDS", 95000, "5311", "USA", 30),
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
