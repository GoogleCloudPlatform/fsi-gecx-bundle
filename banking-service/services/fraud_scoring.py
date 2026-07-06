import logging
from typing import Dict, Any
import random

logger = logging.getLogger(__name__)

class FraudScoringService:
    def __init__(self):
        pass

    def evaluate_transaction_risk(self, payload: Dict[str, Any]) -> int:
        """
        Evaluates the risk of a transaction based on the payload attributes.
        
        For Phase 1, this implements a simple rule engine: it only returns high risk 
        if an explicit simulation flag or risk_score override is present. Otherwise, 
        it returns a nominal baseline score.
        
        In Phase 2, this function will be updated to make a synchronous RPC/HTTP call 
        to a Vertex AI Fraud Inference ML endpoint.
        """
        # If the simulation payload explicitly passes a risk score or fraud flag
        if payload.get("is_fraud_simulation") or payload.get("risk_score"):
            return payload.get("risk_score", 85)
            
        # Nominal baseline score for all normal transactions
        return random.randint(1, 5)
