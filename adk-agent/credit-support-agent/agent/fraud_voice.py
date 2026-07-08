def build_fraud_playbook(voice_context: dict | None) -> dict:
    """Derive a compact fraud-session playbook from trusted voice context."""
    fraud_alert = (voice_context or {}).get("fraud_alert") or {}
    has_active_alert = bool((voice_context or {}).get("has_active_fraud_alert") and fraud_alert)
    if not has_active_alert:
        return {
            "entry_mode": "GENERAL_SUPPORT",
            "opening_style": "GENERIC_GREETING",
            "must_inspect_open_alert_first": False,
            "open_alert_inspected": False,
            "resolution_completed": False,
            "resolution_path": None,
            "fraud_alert_id": None,
            "card_last_four": None,
        }

    return {
        "entry_mode": "FRAUD_ALERT",
        "opening_style": "ACKNOWLEDGE_SUSPICIOUS_ACTIVITY",
        "must_inspect_open_alert_first": True,
        "open_alert_inspected": False,
        "resolution_completed": False,
        "resolution_path": "CONFIRM_RECOGNIZED_OR_CONFIRMED_FRAUD",
        "fraud_alert_id": fraud_alert.get("fraud_alert_id"),
        "card_last_four": fraud_alert.get("card_last_four"),
        "suspicious_transactions_count": len(fraud_alert.get("suspicious_transactions") or []),
    }


def build_initial_greeting(fraud_playbook: dict | None) -> str:
    if (fraud_playbook or {}).get("entry_mode") == "FRAUD_ALERT":
        card_last_four = (fraud_playbook or {}).get("card_last_four", "their card")
        return (
            "Please introduce yourself briefly, acknowledge that you can see a suspicious activity alert "
            f"on the customer's card ending in {card_last_four}, state that you will review the flagged charges, "
            "and inspect the open fraud alert before recommending next steps."
        )

    return (
        "Please introduce yourself as Nova Horizon Bank's Credit Card Support Voice Assistant "
        "and ask the customer how you can help them today."
    )
