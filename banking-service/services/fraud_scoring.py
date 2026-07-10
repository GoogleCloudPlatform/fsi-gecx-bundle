import logging
import os
import datetime
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

FRAUD_SCORER_VERSION = "local-deterministic-v1"
DEFAULT_FRAUD_FLAG_THRESHOLD = int(os.getenv("FRAUD_FLAG_THRESHOLD", "20"))
DEFAULT_FRAUD_ALERT_THRESHOLD = int(os.getenv("FRAUD_ALERT_THRESHOLD", "70"))
FRAUD_MODEL_ALERTS_ENABLED = os.getenv("FRAUD_MODEL_ALERTS_ENABLED", "true").lower() in {"1", "true", "yes"}
HIGH_RISK_MCCS = {"5947", "5967", "6051", "6211", "7995"}
DESCRIPTOR_FLAG_KEYWORDS = {
    "ONLINE": "ONLINE",
    ".COM": "ONLINE",
    "MKTPLACE": "MARKETPLACE",
    "GIFT": "GIFT_CARD",
    "RAZER": "GAMING",
    "GAME": "GAMING",
    "BEST BUY": "ELECTRONICS",
    "APPLE": "ELECTRONICS",
    "CRYPTO": "CRYPTO_LIKE",
}


def _coerce_datetime(value: Any) -> datetime.datetime | None:
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(datetime.timezone.utc)
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@dataclass(frozen=True)
class FraudDecision:
    score: int
    threshold: int
    decision: str
    reason_codes: list[str] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    model_version: str = FRAUD_SCORER_VERSION

    @property
    def is_flagged(self) -> bool:
        return self.decision == "FLAGGED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "threshold": self.threshold,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "features": dict(self.features),
            "model_version": self.model_version,
        }


class FraudScoringService:
    def __init__(
        self,
        flag_threshold: int = DEFAULT_FRAUD_FLAG_THRESHOLD,
        alert_threshold: int = DEFAULT_FRAUD_ALERT_THRESHOLD,
        alerts_enabled: bool = FRAUD_MODEL_ALERTS_ENABLED,
    ):
        self.flag_threshold = flag_threshold
        self.alert_threshold = alert_threshold
        self.alerts_enabled = alerts_enabled

    def extract_authorization_features(
        self,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
        recent_authorizations: list[Any] | None = None,
        account: Any | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        recent_authorizations = recent_authorizations or []
        amount_cents = int(payload.get("amount_cents") or 0)
        mcc = str(payload.get("merchant_category_code") or "0000")
        merchant_name = str(payload.get("merchant_name") or "Unknown Merchant")
        now = _coerce_datetime(payload.get("created_at")) or datetime.datetime.now(datetime.timezone.utc)
        descriptor = merchant_name.upper()
        descriptor_flags = sorted(
            {flag for keyword, flag in DESCRIPTOR_FLAG_KEYWORDS.items() if keyword in descriptor}
            | set(context.get("merchant_high_risk_flags") or [])
        )

        merchant_country = (context.get("merchant_country_code") or payload.get("merchant_country_code") or "USA")
        merchant_country = str(merchant_country).upper()
        merchant_latitude = _coerce_float(context.get("merchant_latitude"))
        merchant_longitude = _coerce_float(context.get("merchant_longitude"))

        recent_10m = []
        recent_1h = []
        recent_24h = []
        recent_amounts = []
        same_mcc_1h = 0
        recent_flagged_24h = 0
        last_card_present_location = None

        for auth in recent_authorizations:
            created_at = _coerce_datetime(getattr(auth, "created_at", None))
            if created_at is None:
                continue
            age_minutes = (now - created_at).total_seconds() / 60
            if age_minutes < 0:
                continue
            if age_minutes <= 24 * 60:
                recent_24h.append(auth)
                if getattr(auth, "status", None) == "FLAGGED":
                    recent_flagged_24h += 1
            if age_minutes <= 60:
                recent_1h.append(auth)
                if str(getattr(auth, "merchant_category_code", "")) == mcc:
                    same_mcc_1h += 1
            if age_minutes <= 10:
                recent_10m.append(auth)
            if age_minutes <= 24 * 60:
                recent_amounts.append(int(getattr(auth, "transaction_amount_cents", 0) or 0))
            if last_card_present_location is None and getattr(auth, "transaction_channel", None) in {"CARD_PRESENT", "WALLET"}:
                lat = _coerce_float(getattr(auth, "merchant_latitude", None))
                lon = _coerce_float(getattr(auth, "merchant_longitude", None))
                if lat is not None and lon is not None:
                    last_card_present_location = (lat, lon, created_at)

        recent_average = sum(recent_amounts) / len(recent_amounts) if recent_amounts else 0
        amount_to_recent_average_ratio = round(amount_cents / recent_average, 2) if recent_average else None
        distance_from_recent = None
        minutes_since_last_location = None
        if merchant_latitude is not None and merchant_longitude is not None and last_card_present_location:
            last_lat, last_lon, last_seen = last_card_present_location
            distance_from_recent = round(_haversine_miles(last_lat, last_lon, merchant_latitude, merchant_longitude), 1)
            minutes_since_last_location = round((now - last_seen).total_seconds() / 60, 1)

        credit_limit = int(getattr(account, "credit_limit_cents", 0) or 0) if account is not None else 0
        available_credit = int(getattr(account, "available_credit_cents", 0) or 0) if account is not None else 0
        available_credit_ratio = round(available_credit / credit_limit, 4) if credit_limit else None
        credit_utilization_after_auth = None
        if credit_limit:
            credit_utilization_after_auth = round((credit_limit - max(0, available_credit - amount_cents)) / credit_limit, 4)

        features = {
            "amount_cents": amount_cents,
            "merchant_category_code": mcc,
            "merchant_name": merchant_name,
            "transaction_channel": context.get("transaction_channel") or payload.get("transaction_channel") or "CARD_PRESENT",
            "entry_mode": context.get("entry_mode") or payload.get("entry_mode") or "CHIP",
            "merchant_country_code": merchant_country,
            "merchant_city": context.get("merchant_city") or payload.get("merchant_city"),
            "merchant_region": context.get("merchant_region") or payload.get("merchant_region"),
            "merchant_postal_code": context.get("merchant_postal_code") or payload.get("merchant_postal_code"),
            "merchant_latitude": merchant_latitude,
            "merchant_longitude": merchant_longitude,
            "ip_country_code": context.get("ip_country_code") or payload.get("ip_country_code"),
            "shipping_country_code": context.get("shipping_country_code") or payload.get("shipping_country_code"),
            "is_digital_goods": bool(context.get("is_digital_goods", payload.get("is_digital_goods", False))),
            "descriptor_flags": descriptor_flags,
            "is_international_like": merchant_country != "USA",
            "distance_from_recent_card_present_location": distance_from_recent,
            "minutes_since_last_card_present_location": minutes_since_last_location,
            "recent_auth_count_10m": len(recent_10m),
            "recent_auth_count_1h": len(recent_1h),
            "recent_flagged_count_24h": recent_flagged_24h,
            "amount_to_recent_average_ratio": amount_to_recent_average_ratio,
            "same_mcc_count_1h": same_mcc_1h,
            "credit_utilization_after_auth": credit_utilization_after_auth,
            "available_credit_ratio": available_credit_ratio,
            "has_explicit_simulation_flag": bool(payload.get("is_fraud_simulation")),
            "has_risk_score_override": "risk_score" in payload and payload.get("risk_score") is not None,
        }
        return features

    def score_features(self, features: dict[str, Any]) -> tuple[int, list[str]]:
        score = 3
        reason_codes: list[str] = []
        flags = set(features.get("descriptor_flags") or [])
        channel = str(features.get("transaction_channel") or "CARD_PRESENT").upper()
        merchant_country = str(features.get("merchant_country_code") or "USA").upper()
        ip_country = str(features.get("ip_country_code") or "").upper()
        shipping_country = str(features.get("shipping_country_code") or "").upper()

        if str(features.get("merchant_category_code") or "") in HIGH_RISK_MCCS:
            score += 18
            reason_codes.append("HIGH_RISK_MCC")

        if channel in {"CARD_NOT_PRESENT", "ECOMMERCE"} and flags.intersection({"ONLINE", "MARKETPLACE"}):
            score += 8
            reason_codes.append("CARD_NOT_PRESENT_DESCRIPTOR")

        if features.get("is_digital_goods") or flags.intersection({"GIFT_CARD", "DIGITAL_GOODS", "GAMING"}):
            score += 20
            reason_codes.append("GIFT_CARD_OR_DIGITAL_GOODS")

        if "ELECTRONICS" in flags and int(features.get("same_mcc_count_1h") or 0) >= 2:
            score += 12
            reason_codes.append("ELECTRONICS_BURST")

        if int(features.get("recent_auth_count_10m") or 0) >= 3:
            score += 18
            reason_codes.append("VELOCITY_SPIKE_10M")

        if int(features.get("recent_auth_count_1h") or 0) >= 6:
            score += 10
            reason_codes.append("VELOCITY_SPIKE_1H")

        amount_ratio = features.get("amount_to_recent_average_ratio")
        if amount_ratio is not None and amount_ratio >= 4:
            score += 15
            reason_codes.append("AMOUNT_OUTLIER")

        distance = features.get("distance_from_recent_card_present_location")
        minutes_since = features.get("minutes_since_last_card_present_location")
        if distance is not None and minutes_since is not None and distance >= 500 and minutes_since <= 180:
            score += 30
            reason_codes.append("IMPOSSIBLE_TRAVEL")

        if merchant_country != "USA":
            score += 10
            reason_codes.append("INTERNATIONAL_ANOMALY")
            if channel in {"CARD_PRESENT", "WALLET"}:
                score += 12
                reason_codes.append("FOREIGN_CARD_PRESENT_ANOMALY")

        if channel in {"CARD_NOT_PRESENT", "ECOMMERCE"} and merchant_country:
            coarse_countries = {country for country in [ip_country, shipping_country] if country}
            if coarse_countries and merchant_country not in coarse_countries:
                score += 14
                reason_codes.append("UNUSUAL_ECOMMERCE_COUNTRY")

        utilization_after = features.get("credit_utilization_after_auth")
        available_ratio = features.get("available_credit_ratio")
        if (utilization_after is not None and utilization_after >= 0.85) or (available_ratio is not None and available_ratio <= 0.15):
            score += 12
            reason_codes.append("NEAR_LIMIT_PRESSURE")

        if int(features.get("recent_flagged_count_24h") or 0) > 0:
            score += 15
            reason_codes.append("RECENT_FLAGGED_ACTIVITY")

        if not reason_codes:
            reason_codes.append("BASELINE_LOW_RISK")
        return max(0, min(100, score)), reason_codes

    def evaluate_authorization(
        self,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
        recent_authorizations: list[Any] | None = None,
        account: Any | None = None,
    ) -> FraudDecision:
        """
        Evaluate the risk of a card authorization and return an explainable decision.

        This first contract slice intentionally keeps scoring simple and deterministic
        while creating the shape later feature extraction and model serving will use.
        """
        features = self.extract_authorization_features(
            payload,
            context=context,
            recent_authorizations=recent_authorizations,
            account=account,
        )

        reason_codes: list[str] = []
        if features["has_explicit_simulation_flag"] or features["has_risk_score_override"]:
            score = int(payload.get("risk_score") if payload.get("risk_score") is not None else 85)
            reason_codes.append("EXPLICIT_SIMULATION_OVERRIDE")
        else:
            score, reason_codes = self.score_features(features)

        score = max(0, min(100, score))
        decision = "FLAGGED" if score > self.flag_threshold else "APPROVED"
        return FraudDecision(
            score=score,
            threshold=self.flag_threshold,
            decision=decision,
            reason_codes=reason_codes,
            features=features,
        )

    def evaluate_transaction_risk(self, payload: dict[str, Any]) -> int:
        """Backward-compatible integer risk API for existing call sites."""
        return self.evaluate_authorization(payload).score
