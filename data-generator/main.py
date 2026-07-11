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
import uuid
from typing import List, Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, status, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scenarios import ScenarioExecutionRequest, ScenarioRequest, execute_scenario, list_scenario_outcomes, plan_scenario
from scenarios.schemas import BehaviorPolicy, PersonaProfile, ScenarioMode, ScenarioType
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


class FraudPatternRequest(BaseModel):
    card_token: Optional[str] = None
    pattern: Optional[str] = None
    count: int = 1

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
PULSE_ACTIVE_LOCK_TTL_SECONDS = int(os.getenv("PULSE_ACTIVE_LOCK_TTL_SECONDS", str(max(PULSE_WINDOW_SECONDS + 90, 180))))
PULSE_EVENT_DEDUP_TTL_SECONDS = int(os.getenv("PULSE_EVENT_DEDUP_TTL_SECONDS", "3600"))
PULSE_ADMISSION_REDIS_REQUIRED = os.getenv("PULSE_ADMISSION_REDIS_REQUIRED", "true").lower() not in {"0", "false", "no"}
FRAUD_PATTERN_ENABLED = os.getenv("FRAUD_PATTERN_ENABLED", "false").lower() in {"1", "true", "yes"}
FRAUD_PATTERN_RATE = float(os.getenv("FRAUD_PATTERN_RATE", "0.05"))
FRAUD_PATTERN_MAX_PER_PULSE = int(os.getenv("FRAUD_PATTERN_MAX_PER_PULSE", "1"))
FRAUD_PATTERN_TARGET_MODE = os.getenv("FRAUD_PATTERN_TARGET_MODE", "eligible").lower()
FRAUD_PATTERN_NAMES = [
    "cnp_gift_card_burst",
    "electronics_marketplace_burst",
    "international_amount_outlier",
    "impossible_travel_card_present",
    "unusual_ecommerce_country",
    "merchant_category_velocity",
    "near_limit_pressure",
]
OPERATOR_EMAIL_DOMAINS = [
    domain.strip().lower()
    for domain in os.getenv("DATA_GENERATOR_OPERATOR_EMAIL_DOMAINS", "google.com,gcp.solutions,altostrat.com").split(",")
    if domain.strip()
]

_pulse_lock = asyncio.Lock()
_redis_client = None
_redis_disabled = False


class MaintenanceModeError(RuntimeError):
    """Raised when banking-service has temporarily paused writes for maintenance/reset."""


class PulseAdmission:
    def __init__(
        self,
        *,
        admitted: bool,
        status: str = "ADMITTED",
        message: str = "Pulse admitted.",
        pulse_token: str | None = None,
        event_id: str | None = None,
        redis_client: Any | None = None,
        active_lock_key: str = "data-generator:pulse:active",
    ):
        self.admitted = admitted
        self.status = status
        self.message = message
        self.pulse_token = pulse_token
        self.event_id = event_id
        self.redis_client = redis_client
        self.active_lock_key = active_lock_key

    def skipped_response(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "event_id": self.event_id,
        }


def get_pulse_redis_client():
    global _redis_client
    global _redis_disabled

    if _redis_disabled:
        return None

    if _redis_client is None:
        try:
            import redis

            port = int(os.getenv("REDIS_PORT", "6379"))
            _redis_client = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=port,
                password=os.getenv("REDIS_PASSWORD"),
                decode_responses=True,
                ssl=(port == 6378),
                ssl_cert_reqs="none",
                health_check_interval=30,
                socket_keepalive=True,
                retry_on_timeout=True,
                socket_connect_timeout=0.25,
                socket_timeout=0.25,
            )
            _redis_client.ping()
        except Exception as exc:
            logger.warning("Pulse admission Redis client unavailable: %s", exc)
            _redis_client = None
            _redis_disabled = True

    return _redis_client


def extract_pulse_event_id(request: Request, body: Any | None = None) -> str | None:
    """Resolve an idempotency key from Eventarc/CloudEvents or Pub/Sub payloads."""
    for header_name in ("ce-id", "Ce-Id", "CE-ID"):
        header_value = request.headers.get(header_name)
        if header_value:
            return header_value.split("/", 1)[0].strip()

    if isinstance(body, dict):
        message = body.get("message") if isinstance(body.get("message"), dict) else {}
        for key in ("messageId", "message_id", "id"):
            value = message.get(key) or body.get(key)
            if value:
                return str(value).strip()

    return None


async def parse_request_json(request: Request) -> Any | None:
    try:
        return await request.json()
    except Exception:
        return None


def admit_pulse(event_id: str | None) -> PulseAdmission:
    pulse_token = str(uuid.uuid4())
    redis_client = get_pulse_redis_client()

    if not redis_client:
        if is_local_dev() or not PULSE_ADMISSION_REDIS_REQUIRED:
            return PulseAdmission(
                admitted=True,
                pulse_token=pulse_token,
                event_id=event_id,
                message="Pulse admitted with process-local admission control.",
            )
        return PulseAdmission(
            admitted=False,
            status="SKIPPED_ADMISSION_UNAVAILABLE",
            message="Pulse admission control is unavailable; skipped to avoid scheduler retry amplification.",
            event_id=event_id,
        )

    try:
        if event_id:
            event_key = f"data-generator:pulse:event:{event_id}"
            event_admitted = redis_client.set(
                event_key,
                pulse_token,
                nx=True,
                ex=PULSE_EVENT_DEDUP_TTL_SECONDS,
            )
            if not event_admitted:
                return PulseAdmission(
                    admitted=False,
                    status="SKIPPED_DUPLICATE_EVENT",
                    message="Scheduler/Eventarc pulse event was already admitted.",
                    event_id=event_id,
                    redis_client=redis_client,
                )

        active_lock_key = "data-generator:pulse:active"
        active_admitted = redis_client.set(
            active_lock_key,
            pulse_token,
            nx=True,
            ex=PULSE_ACTIVE_LOCK_TTL_SECONDS,
        )
        if not active_admitted:
            return PulseAdmission(
                admitted=False,
                status="SKIPPED_ACTIVE_PULSE",
                message="Another simulation pulse is already active.",
                event_id=event_id,
                redis_client=redis_client,
            )
    except Exception as exc:
        logger.warning("Pulse admission failed; skipping pulse to avoid duplicate traffic: %s", exc)
        return PulseAdmission(
            admitted=False,
            status="SKIPPED_ADMISSION_UNAVAILABLE",
            message="Pulse admission control failed; skipped to avoid scheduler retry amplification.",
            event_id=event_id,
        )

    return PulseAdmission(
        admitted=True,
        pulse_token=pulse_token,
        event_id=event_id,
        redis_client=redis_client,
        active_lock_key="data-generator:pulse:active",
    )


def release_pulse_admission(admission: PulseAdmission) -> None:
    if not admission.redis_client or not admission.pulse_token:
        return
    try:
        current_token = admission.redis_client.get(admission.active_lock_key)
        if current_token == admission.pulse_token:
            admission.redis_client.delete(admission.active_lock_key)
    except Exception as exc:
        logger.warning("Failed to release pulse admission lock: %s", exc)


def get_card_network_token() -> str:
    """Resolve the internal switch token lazily so the container can still boot and report health."""
    return get_internal_switch_token()


def _normalize_iap_email(header_value: str | None) -> str | None:
    if not header_value:
        return None
    return header_value.replace("accounts.google.com:", "").strip().lower() or None


def _is_allowed_operator_email(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1]
    return domain in OPERATOR_EMAIL_DOMAINS


def extract_operator_identity(request: Request) -> str | None:
    iap_email = _normalize_iap_email(request.headers.get("x-goog-authenticated-user-email"))
    if iap_email:
        return iap_email
    return None


def verify_switch_or_presenter_token(
    x_card_network_token: Optional[str] = Header(None, alias="X-Card-Network-Token"),
    x_goog_authenticated_user_email: Optional[str] = Header(None, alias="X-Goog-Authenticated-User-Email"),
):
    if x_card_network_token and x_card_network_token == get_card_network_token():
        return True
    if _is_allowed_operator_email(_normalize_iap_email(x_goog_authenticated_user_email)):
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
        "city": None,
        "region": None,
        "postal_code": None,
        "latitude": None,
        "longitude": None,
        "card_present_capable": not is_international,
        "ecommerce_capable": False,
        "high_risk_flags": [],
        "is_international": is_international,
        "risk_score": 20 if is_international else 0,
    }


def build_persona_profile(card: Dict[str, Any]) -> PersonaProfile:
    persona = str(card.get("persona") or "PRIME").upper()
    cardholder_name = str(card.get("cardholder_name") or "")
    home_metros = ["Mountain View, CA", "San Francisco, CA", "New York, NY", "Chicago, IL", "Seattle, WA", "Dallas, TX", "Los Angeles, CA"]
    home_metro = home_metros[hash(cardholder_name or card.get("card_token", "default")) % len(home_metros)]

    if persona == "HNW":
        return PersonaProfile(
            persona_id="hnw_travel",
            role="high net worth travel cardholder",
            home_metro=home_metro,
            card_profile="premium_travel_card",
            typical_mccs=["4511", "7011", "5812", "4121"],
            travel_propensity=0.45,
            digital_commerce_propensity=0.30,
            card_present_propensity=0.78,
        )
    if persona == "YPRO":
        return PersonaProfile(
            persona_id="young_professional_digital",
            role="young professional digital-first cardholder",
            home_metro=home_metro,
            card_profile="everyday_rewards_card",
            typical_mccs=["5814", "4899", "5812", "4121"],
            travel_propensity=0.12,
            digital_commerce_propensity=0.65,
            card_present_propensity=0.55,
        )
    return PersonaProfile(
        persona_id="prime_everyday",
        role="prime everyday cardholder",
        home_metro=home_metro,
        card_profile="prime_cashback_card",
        typical_mccs=["5411", "5541", "5311", "4121", "5812"],
        travel_propensity=0.18,
        digital_commerce_propensity=0.35,
        card_present_propensity=0.82,
    )


def build_behavior_policy(card: Dict[str, Any], persona: PersonaProfile) -> BehaviorPolicy:
    amount_min = int(card.get("amount_min", 1500))
    amount_max = int(card.get("amount_max", 15000))
    if persona.persona_id == "hnw_travel":
        settlement, reversal, pending = 0.82, 0.05, 0.13
    elif persona.persona_id == "young_professional_digital":
        settlement, reversal, pending = 0.76, 0.08, 0.16
    else:
        settlement, reversal, pending = 0.80, 0.10, 0.10

    return BehaviorPolicy(
        policy_id=f"{persona.persona_id}_baseline_policy",
        preferred_mccs=list(card.get("mccs") or persona.typical_mccs),
        spend_min_cents=max(100, amount_min),
        spend_max_cents=max(max(100, amount_min), amount_max),
        settlement_probability=settlement,
        reversal_probability=reversal,
        pending_probability=pending,
        utilization_trigger=0.65,
        target_utilization=0.35,
        travel_context="Low-rate merchant-geography travel activity." if persona.travel_propensity > 0.2 else None,
        ecommerce_context="Normal ecommerce/subscription activity." if persona.digital_commerce_propensity > 0.3 else None,
    )


def infer_channel_context(merchant: Dict[str, Any], formatted_merchant: str) -> Dict[str, Any]:
    descriptor = formatted_merchant.upper()
    ecommerce_capable = bool(merchant.get("ecommerce_capable"))
    is_ecommerce = ecommerce_capable or any(
        token in descriptor
        for token in ["ONLINE", ".COM", "MKTPLACE", "STREAMING", "SUBSCRIPTION", "DIGITAL", "GIFT CARD"]
    )

    if is_ecommerce:
        country_code = merchant.get("country_code", "USA")
        return {
            "transaction_channel": "ECOMMERCE",
            "entry_mode": "ECOMMERCE",
            "ip_country_code": country_code,
            "shipping_country_code": country_code,
            "is_digital_goods": "DIGITAL_GOODS" in merchant.get("high_risk_flags", []) or "GIFT CARD" in descriptor,
        }

    entry_mode = random.choices(["CHIP", "CONTACTLESS", "MAG_STRIPE"], weights=[65, 25, 10], k=1)[0]
    channel = "WALLET" if entry_mode == "CONTACTLESS" and random.random() < 0.25 else "CARD_PRESENT"
    return {
        "transaction_channel": channel,
        "entry_mode": entry_mode,
        "ip_country_code": None,
        "shipping_country_code": None,
        "is_digital_goods": False,
    }


def build_fraud_pattern_payloads(card: Dict[str, Any], pattern: str) -> List[Dict[str, Any]]:
    token = card["card_token"]
    available_credit = int(card.get("available_credit_cents") or 150000)
    base_amount = max(1000, min(available_credit // 3, 95000))

    def payload(
        *,
        merchant_name: str,
        amount_cents: int,
        mcc: str,
        channel: str,
        entry_mode: str,
        country: str = "USA",
        city: str | None = None,
        region: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        ip_country: str | None = None,
        shipping_country: str | None = None,
        digital_goods: bool = False,
        flags: Optional[List[str]] = None,
        sequence: int = 1,
    ) -> Dict[str, Any]:
        return {
            "card_token": token,
            "amount_cents": max(100, min(amount_cents, max(available_credit - 100, 100))),
            "retrieval_reference_number": "".join(random.choices("0123456789", k=12)),
            "merchant_category_code": mcc,
            "merchant_name": merchant_name,
            "card_network": "VISA",
            "transaction_channel": channel,
            "entry_mode": entry_mode,
            "merchant_country_code": country,
            "merchant_city": city,
            "merchant_region": region,
            "merchant_latitude": lat,
            "merchant_longitude": lon,
            "ip_country_code": ip_country,
            "shipping_country_code": shipping_country,
            "is_digital_goods": digital_goods,
            "merchant_high_risk_flags": flags or [],
            "synthetic_fraud_label": "FRAUD_PATTERN",
            "fraud_pattern_label": pattern,
            "fraud_pattern_sequence": sequence,
        }

    if pattern == "cnp_gift_card_burst":
        return [
            payload(merchant_name=name, amount_cents=amt, mcc="5947", channel="ECOMMERCE", entry_mode="ECOMMERCE", digital_goods=True, flags=["DIGITAL_GOODS", "GIFT_CARD"], sequence=idx)
            for idx, (name, amt) in enumerate(
                [("RAZER GOLD GIFT CARD ONLINE", base_amount), ("TARGET.COM GIFT CARDS", base_amount - 500), ("GAME*TEST TOKEN ONLINE", 4900)],
                start=1,
            )
        ]
    if pattern == "electronics_marketplace_burst":
        return [
            payload(merchant_name=name, amount_cents=amt, mcc="5311", channel="ECOMMERCE", entry_mode="ECOMMERCE", digital_goods=False, flags=["ELECTRONICS"], sequence=idx)
            for idx, (name, amt) in enumerate(
                [("BEST BUY*MKTPLACE", base_amount), ("APPLE.COM*ONLINE", base_amount - 1000), ("AMAZON.COM*MKTPLACE ELECTRONICS", base_amount - 2000)],
                start=1,
            )
        ]
    if pattern == "international_amount_outlier":
        return [
            payload(merchant_name="CANCUN RESORT POS", amount_cents=base_amount, mcc="7011", channel="CARD_PRESENT", entry_mode="CHIP", country="MEX", city="Cancun", region="QR", lat=21.1619, lon=-86.8515, sequence=1)
        ]
    if pattern == "impossible_travel_card_present":
        return [
            payload(merchant_name="LOCAL MARKET - SAN FRANCISCO CA", amount_cents=2400, mcc="5411", channel="CARD_PRESENT", entry_mode="CHIP", country="USA", city="San Francisco", region="CA", lat=37.7749, lon=-122.4194, sequence=1),
            payload(merchant_name="GROCERY - NEW YORK NY", amount_cents=4500, mcc="5411", channel="CARD_PRESENT", entry_mode="CHIP", country="USA", city="New York", region="NY", lat=40.7128, lon=-74.0060, sequence=2),
        ]
    if pattern == "unusual_ecommerce_country":
        return [
            payload(merchant_name="LONDON DIGITAL MARKETPLACE", amount_cents=base_amount, mcc="5816", channel="ECOMMERCE", entry_mode="ECOMMERCE", country="GBR", ip_country="USA", shipping_country="USA", digital_goods=True, flags=["DIGITAL_GOODS", "ONLINE"], sequence=1)
        ]
    if pattern == "merchant_category_velocity":
        return [
            payload(merchant_name=f"COFFEE SHOP VELOCITY {idx}", amount_cents=1800 + idx * 100, mcc="5814", channel="CARD_PRESENT", entry_mode="CONTACTLESS", country="USA", city="Seattle", region="WA", lat=47.6062, lon=-122.3321, sequence=idx)
            for idx in range(1, 5)
        ]
    if pattern == "near_limit_pressure":
        amount = max(1000, min(int(available_credit * 0.9), available_credit - 100))
        return [
            payload(merchant_name="HIGH VALUE MARKETPLACE ONLINE", amount_cents=amount, mcc="5311", channel="ECOMMERCE", entry_mode="ECOMMERCE", country="USA", ip_country="USA", shipping_country="USA", flags=["ONLINE"], sequence=1)
        ]
    raise ValueError(f"Unknown fraud pattern: {pattern}")


async def dispatch_fraud_pattern(client: httpx.AsyncClient, card: Dict[str, Any], pattern: str) -> Dict[str, Any]:
    headers = get_service_headers()
    auth_url = f"{BANKING_SERVICE_URL}/api/v1/card-network/authorize"
    payloads = build_fraud_pattern_payloads(card, pattern)
    results = []
    for payload in payloads:
        response = await client.post(auth_url, json=payload, headers=headers, timeout=SWIPE_REQUEST_TIMEOUT_SECONDS)
        results.append(
            {
                "pattern": pattern,
                "rrn": payload["retrieval_reference_number"],
                "status_code": response.status_code,
                "action_code": response.json().get("action_code") if response.status_code == 200 else None,
            }
        )
    return {
        "pattern": pattern,
        "attempted": len(payloads),
        "authorized": sum(1 for result in results if result["status_code"] == 200 and result["action_code"] == "00"),
        "results": results,
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
                        "city": item.get("city"),
                        "region": item.get("region"),
                        "postal_code": item.get("postal_code"),
                        "latitude": item.get("latitude"),
                        "longitude": item.get("longitude"),
                        "card_present_capable": item.get("card_present_capable", True),
                        "ecommerce_capable": item.get("ecommerce_capable", False),
                        "high_risk_flags": item.get("high_risk_flags", []),
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
    persona = build_persona_profile(card)
    behavior_policy = build_behavior_policy(card, persona)
    mccs = behavior_policy.preferred_mccs or ["5311", "5411", "5541", "4121"]
    default_mcc = next((mcc for mcc in mccs if mcc), "5311")
    matching_merchants = [m for m in merchants if m.get("mcc") in mccs]
    if not matching_merchants:
        matching_merchants = [build_generic_merchant(mcc=default_mcc)]

    home_metro = (persona.home_metro or "Mountain View, CA").upper().replace(",", "")
    is_intl_swipe = random.random() < persona.travel_propensity
    prefer_ecommerce = random.random() < persona.digital_commerce_propensity
    if is_intl_swipe:
        region_merchants = [m for m in merchants if m.get("is_international") and m.get("country_code") == "MEX" and m.get("mcc") in mccs]
        if not region_merchants:
            region_merchants = [m for m in merchants if m.get("is_international") and m.get("country_code") == "MEX"]
    elif prefer_ecommerce:
        region_merchants = [m for m in merchants if m.get("ecommerce_capable") and m.get("mcc") in mccs]
        if not region_merchants:
            region_merchants = [m for m in merchants if m.get("ecommerce_capable")]
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
    amount_min = behavior_policy.spend_min_cents
    amount_max = behavior_policy.spend_max_cents

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
    channel_context = infer_channel_context(merchant, formatted_merchant)

    rrn = "".join(random.choices("0123456789", k=12))
    
    headers = get_service_headers()
    auth_payload = {
        "card_token": card["card_token"],
        "amount_cents": amount_cents,
        "retrieval_reference_number": rrn,
        "merchant_category_code": merchant.get("mcc", "5311"),
        "merchant_name": formatted_merchant,
        "card_network": "VISA",
        "transaction_channel": channel_context["transaction_channel"],
        "entry_mode": channel_context["entry_mode"],
        "merchant_country_code": merchant.get("country_code", "USA"),
        "merchant_city": merchant.get("city"),
        "merchant_region": merchant.get("region"),
        "merchant_postal_code": merchant.get("postal_code"),
        "merchant_latitude": merchant.get("latitude"),
        "merchant_longitude": merchant.get("longitude"),
        "ip_country_code": channel_context["ip_country_code"],
        "shipping_country_code": channel_context["shipping_country_code"],
        "is_digital_goods": channel_context["is_digital_goods"],
        "merchant_high_risk_flags": merchant.get("high_risk_flags", []),
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
            
        resolution = random.choices(
            ["SETTLE", "REVERSE", "PENDING"],
            weights=[
                behavior_policy.settlement_probability,
                behavior_policy.reversal_probability,
                behavior_policy.pending_probability,
            ],
            k=1,
        )[0]
        
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


@app.get("/simulation/status", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
def get_simulation_status():
    """Returns current generator control-surface status for direct GUI and future agentic clients."""
    return {
        "status": "READY",
        "service": "data-generator",
        "control_surface": "direct-fastapi",
        "banking_service_url_configured": bool(BANKING_SERVICE_URL),
        "pulse": {
            "window_seconds": PULSE_WINDOW_SECONDS,
            "min_events": PULSE_MIN_EVENTS,
            "max_events": PULSE_MAX_EVENTS,
            "workflow_concurrency": SWIPE_WORKFLOW_CONCURRENCY,
            "admission_redis_required": PULSE_ADMISSION_REDIS_REQUIRED,
        },
        "surge": {
            "total_events": SURGE_TOTAL_EVENTS,
            "stagger_seconds": SURGE_STAGGER_SECONDS,
        },
        "fraud_patterns": {
            "enabled": FRAUD_PATTERN_ENABLED,
            "rate": FRAUD_PATTERN_RATE,
            "max_per_pulse": FRAUD_PATTERN_MAX_PER_PULSE,
            "target_mode": FRAUD_PATTERN_TARGET_MODE,
        },
        "supported_routes": [
            "/scenarios/plan",
            "/scenarios/dry-run",
            "/scenarios/execute",
            "/scenarios/replay",
            "/scenarios/{scenario_id}/outcomes",
        ],
    }


@app.post("/scenarios/plan", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
def plan_generation_scenario(request: ScenarioRequest):
    """Returns a validated dry-run scenario plan without writing synthetic data."""
    plan = plan_scenario(request)
    logger.info("Planned data-generator scenario %s (%s).", plan.scenario_id, plan.scenario_type)
    return plan


@app.post("/scenarios/dry-run", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def dry_run_generation_scenario(request: ScenarioRequest, http_request: Request):
    """Plans and dry-runs a scenario through the same execution result contract without writing data."""
    plan = plan_scenario(request.model_copy(update={"mode": ScenarioMode.DRY_RUN}))
    operator = extract_operator_identity(http_request)
    result = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.DRY_RUN,
            idempotency_key=f"dry-run:{plan.scenario_id}:{uuid.uuid4().hex}",
            operator=operator,
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers={},
        timeout_seconds=SWIPE_REQUEST_TIMEOUT_SECONDS,
    )
    logger.info("Scenario dry-run %s prepared by %s.", result.execution_id, operator or "unknown-operator")
    return result


@app.post("/scenarios/execute", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def execute_generation_scenario(request: ScenarioExecutionRequest, http_request: Request):
    """Executes a validated scenario plan through bounded data-generator primitives."""
    operator = request.operator or extract_operator_identity(http_request)
    if operator and request.operator != operator:
        request = request.model_copy(update={"operator": operator})
    default_card_token = request.default_card_token
    default_card_tokens = request.default_card_tokens
    if (request.mode or request.plan.mode).value in {"execute", "replay"} and not (default_card_token or default_card_tokens):
        cards = get_spendable_cards(get_generator_eligible_cards(get_active_cards()))
        if not cards:
            raise HTTPException(status_code=409, detail="No eligible active cards available for scenario execution.")
        default_card_tokens = [card["card_token"] for card in cards]
        request = request.model_copy(update={"default_card_tokens": default_card_tokens})

    result = await execute_scenario(
        request,
        banking_service_url=BANKING_SERVICE_URL,
        headers=get_service_headers(),
        default_card_token=default_card_token,
        timeout_seconds=SWIPE_REQUEST_TIMEOUT_SECONDS,
    )
    logger.info("Scenario execution %s finished with status %s.", result.execution_id, result.status)
    return result


@app.post("/scenarios/replay", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def replay_generation_scenario(request: ScenarioExecutionRequest, http_request: Request):
    """Replays a validated scenario plan with an explicit replay mode and idempotency key."""
    replay_request = request.model_copy(
        update={
            "mode": ScenarioMode.REPLAY,
            "operator": request.operator or extract_operator_identity(http_request),
        }
    )
    return await execute_generation_scenario(replay_request, http_request)


@app.get("/scenarios/{scenario_id}/outcomes", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
def get_generation_scenario_outcomes(scenario_id: str):
    """Returns synthetic feedback labels captured for a scenario execution."""
    outcomes = list_scenario_outcomes(scenario_id)
    return {
        "scenario_id": scenario_id,
        "count": len(outcomes),
        "outcomes": outcomes,
    }


@app.post("/generate", status_code=status.HTTP_200_OK)
@app.post("/simulate-pulse", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_pulse(request: Request):
    """Wakes up once a minute and fans transactions across the next 58 seconds."""
    request_body = await parse_request_json(request)
    event_id = extract_pulse_event_id(request, request_body)
    admission = admit_pulse(event_id)
    if not admission.admitted:
        logger.info("Skipping simulation pulse during admission: %s event_id=%s", admission.status, event_id)
        return admission.skipped_response()

    try:
        if _pulse_lock.locked():
            logger.info("Skipping pulse because another simulation pulse is already running.")
            return {
                "status": "SKIPPED_ACTIVE_PULSE",
                "message": "Another simulation pulse is already in progress.",
                "event_id": event_id,
            }

        async with _pulse_lock:
            return await execute_simulation_pulse(event_id=event_id)
    finally:
        release_pulse_admission(admission)


async def execute_simulation_pulse(event_id: str | None = None) -> Dict[str, Any]:
    """Execute one admitted synthetic activity pulse."""
    logger.info("Triggered randomized simulation pulse for the next %s seconds.", PULSE_WINDOW_SECONDS)
    try:
        cards = get_spendable_cards(get_active_cards())
    except MaintenanceModeError:
        return {
            "status": "SKIPPED",
            "message": "banking-service reset is in progress.",
            "active_cards_count": 0,
            "event_id": event_id,
        }
    except HTTPException as exc:
        logger.warning("Skipping simulation pulse because active card discovery is unavailable: %s", exc.detail)
        return {
            "status": "SKIPPED",
            "message": "Active card discovery is temporarily unavailable.",
            "reason": exc.detail,
            "active_cards_count": 0,
            "event_id": event_id,
        }
    if not cards:
        return {
            "status": "SKIPPED",
            "message": "No spendable active cards found to swipe.",
            "active_cards_count": 0,
            "event_id": event_id,
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
        fraud_pattern_results = []
        if FRAUD_PATTERN_ENABLED and random.random() < FRAUD_PATTERN_RATE:
            fraud_count = max(0, min(FRAUD_PATTERN_MAX_PER_PULSE, len(cards)))
            target_cards = random.sample(cards, fraud_count) if fraud_count else []
            for card in target_cards:
                pattern = random.choice(FRAUD_PATTERN_NAMES)
                fraud_pattern_results.append(await dispatch_fraud_pattern(client, card, pattern))
        paydown_results = await auto_paydown_high_utilization_cards(client, cards)

    summary = summarize_swipe_results(all_results)
    summary["fraud_patterns_attempted"] = len(fraud_pattern_results)
    summary["fraud_pattern_authorizations_created"] = sum(result["authorized"] for result in fraud_pattern_results)
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
        "event_id": event_id,
    }

@app.post("/simulate-surge", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_surge(payload: SurgeRequest):
    """Triggers a scenario-backed lakehouse spend velocity surge."""
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

    plan = plan_scenario(
        ScenarioRequest(
            goal="Run the Active Lakehouse spend velocity surge.",
            scenario_type=ScenarioType.LAKEHOUSE_SPEND_VELOCITY_SURGE,
            mode=ScenarioMode.EXECUTE,
            seed=random.randint(1, 999_999),
            max_events=SURGE_TOTAL_EVENTS,
            target_cohort_size=len(active_cards),
        )
    )
    execution = await execute_scenario(
        ScenarioExecutionRequest(
            plan=plan,
            mode=ScenarioMode.EXECUTE,
            idempotency_key=f"surge:{plan.scenario_id}:{uuid.uuid4().hex}",
            default_card_tokens=[card["card_token"] for card in active_cards],
        ),
        banking_service_url=BANKING_SERVICE_URL,
        headers=get_service_headers(),
        timeout_seconds=SWIPE_REQUEST_TIMEOUT_SECONDS,
    )
    async with httpx.AsyncClient() as paydown_client:
        paydown_results = await auto_paydown_high_utilization_cards(paydown_client, active_cards)

    summary = {
        "swipes_attempted": execution.attempted_events,
        "authorizations_created": execution.authorizations_created,
        "settlements_created": execution.settlements_created,
        "reversals_created": execution.reversals_created,
        "declines": sum(1 for step in execution.steps if step.resolution == "declined"),
        "failures": execution.failed_events,
        "auto_paydowns_processed": sum(1 for result in paydown_results if result.get("status") == "SUCCESS"),
    }
    if summary["authorizations_created"] == 0:
        raise HTTPException(status_code=502, detail={"message": "No transaction authorizations were created.", **summary})
    return {
        "status": "SUCCESS",
        "message": "Scenario-backed lakehouse spend velocity surge completed against active card pool.",
        "scenario_id": plan.scenario_id,
        "execution_id": execution.execution_id,
        "planned_event_count": len(plan.timeline),
        "pending_holds_created": execution.pending_holds_created,
        "validation_hints": [validation.model_dump(mode="json") for validation in plan.expected_validations],
        "active_cards_count": len(active_cards),
        **summary,
    }


@app.post("/simulate-fraud-patterns", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_switch_or_presenter_token)])
async def simulate_fraud_patterns(req: FraudPatternRequest):
    """Runs labeled model-detection fraud patterns without explicit risk-score overrides."""
    pattern_count = max(1, min(req.count, FRAUD_PATTERN_MAX_PER_PULSE if FRAUD_PATTERN_MAX_PER_PULSE > 0 else 1))
    patterns = [req.pattern] if req.pattern else []
    for _ in range(pattern_count - len(patterns)):
        patterns.append(random.choice(FRAUD_PATTERN_NAMES))

    for pattern in patterns:
        if pattern not in FRAUD_PATTERN_NAMES:
            raise HTTPException(status_code=400, detail=f"Unknown fraud pattern: {pattern}")

    if req.card_token:
        cards = [{"card_token": req.card_token, "available_credit_cents": 150000, "generator_eligible": True}]
    else:
        try:
            cards = get_spendable_cards(get_generator_eligible_cards(get_active_cards()))
        except MaintenanceModeError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="banking-service reset is in progress.")
        if FRAUD_PATTERN_TARGET_MODE == "eligible":
            cards = get_generator_eligible_cards(cards)
        if not cards:
            raise HTTPException(status_code=409, detail="No eligible active cards found for fraud pattern simulation.")

    async with httpx.AsyncClient() as client:
        results = []
        for pattern in patterns:
            card = cards[0] if req.card_token else random.choice(cards)
            results.append(await dispatch_fraud_pattern(client, card, pattern))

    return {
        "status": "FRAUD_PATTERNS_SIMULATED",
        "patterns_attempted": len(results),
        "authorizations_created": sum(result["authorized"] for result in results),
        "patterns": results,
        "message": "Labeled fraud-pattern traffic dispatched without explicit risk-score overrides.",
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
                "card_network": "VISA",
                "transaction_channel": "ECOMMERCE",
                "entry_mode": "ECOMMERCE",
                "merchant_country_code": country,
                "ip_country_code": country,
                "shipping_country_code": country,
                "is_digital_goods": "GIFT" in desc.upper() or "ONLINE" in desc.upper(),
                "merchant_high_risk_flags": ["DIGITAL_GOODS"] if "ONLINE" in desc.upper() or "GIFT" in desc.upper() else [],
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
