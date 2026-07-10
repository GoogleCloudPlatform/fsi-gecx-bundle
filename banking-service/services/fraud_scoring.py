import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

FRAUD_SCORER_VERSION = "local-deterministic-v1"
DEFAULT_FRAUD_FLAG_THRESHOLD = int(os.getenv("FRAUD_FLAG_THRESHOLD", "20"))


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
    def __init__(self, flag_threshold: int = DEFAULT_FRAUD_FLAG_THRESHOLD):
        self.flag_threshold = flag_threshold

    def evaluate_authorization(
        self,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> FraudDecision:
        """
        Evaluate the risk of a card authorization and return an explainable decision.

        This first contract slice intentionally keeps scoring simple and deterministic
        while creating the shape later feature extraction and model serving will use.
        """
        context = context or {}
        features = {
            "amount_cents": int(payload.get("amount_cents") or 0),
            "merchant_category_code": str(payload.get("merchant_category_code") or "0000"),
            "merchant_name": str(payload.get("merchant_name") or "Unknown Merchant"),
            "has_explicit_simulation_flag": bool(payload.get("is_fraud_simulation")),
            "has_risk_score_override": "risk_score" in payload and payload.get("risk_score") is not None,
            **context,
        }

        reason_codes: list[str] = []
        if features["has_explicit_simulation_flag"] or features["has_risk_score_override"]:
            score = int(payload.get("risk_score") if payload.get("risk_score") is not None else 85)
            reason_codes.append("EXPLICIT_SIMULATION_OVERRIDE")
        else:
            score = 3
            reason_codes.append("BASELINE_LOW_RISK")

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
