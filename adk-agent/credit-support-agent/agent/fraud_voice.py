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
            "recognized_activity_confirmed": False,
            "confirmed_fraud": False,
            "card_blocked": False,
            "replacement_issued": False,
            "wallet_push_queued": False,
            "required_sequence": [],
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
        "recognized_activity_confirmed": False,
        "confirmed_fraud": False,
        "card_blocked": False,
        "replacement_issued": False,
        "wallet_push_queued": False,
        "required_sequence": [
            "get_open_fraud_alert",
            "report_lost_stolen_card",
            "issue_replacement_card_tool",
            "push_card_to_google_wallet",
            "resolve_fraud_alert",
        ],
    }


def build_initial_greeting(fraud_playbook: dict | None) -> str:
    if (fraud_playbook or {}).get("entry_mode") == "FRAUD_ALERT":
        card_last_four = (fraud_playbook or {}).get("card_last_four", "their card")
        suspicious_count = (fraud_playbook or {}).get("suspicious_transactions_count") or "the"
        return (
            "Please introduce yourself briefly, acknowledge that you can see a suspicious activity alert "
            f"on the customer's card ending in {card_last_four}, explain that you are reviewing {suspicious_count} flagged charges now, "
            "inspect the open fraud alert before recommending next steps, and ask whether the customer recognizes the transactions."
        )

    return (
        "Please introduce yourself as Nova Horizon Bank's Credit Card Support Voice Assistant "
        "and ask the customer how you can help them today."
    )


def validate_fraud_tool_sequence(fraud_playbook: dict | None, tool_name: str, args: dict | None = None) -> str | None:
    """Return an operator-safe sequencing error when a fraud mitigation tool is called out of order."""
    playbook = fraud_playbook or {}
    if playbook.get("entry_mode") != "FRAUD_ALERT":
        return None

    args = args or {}
    if tool_name == "get_open_fraud_alert":
        return None

    if tool_name in {
        "report_lost_stolen_card",
        "issue_replacement_card_tool",
        "push_card_to_google_wallet",
        "resolve_fraud_alert",
    } and not playbook.get("open_alert_inspected"):
        return "Inspect the open fraud alert before taking mitigation actions."

    if tool_name == "issue_replacement_card_tool" and not playbook.get("card_blocked"):
        return "Block the card before issuing a replacement card."

    if tool_name == "push_card_to_google_wallet" and not playbook.get("replacement_issued"):
        return "Issue the replacement card before queueing Google Wallet provisioning."

    if tool_name == "resolve_fraud_alert":
        resolution = str((args or {}).get("resolution") or "").strip().upper()
        if resolution == "CUSTOMER_RECOGNIZED":
            return None
        if resolution == "CUSTOMER_CONFIRMED_FRAUD":
            if not playbook.get("card_blocked"):
                return "Block the card before resolving the alert as confirmed fraud."
            if not playbook.get("replacement_issued"):
                return "Issue the replacement card before resolving the alert as confirmed fraud."
            if not playbook.get("wallet_push_queued"):
                return "Queue Google Wallet provisioning before resolving the alert as confirmed fraud."
    return None


def mark_fraud_tool_completed(
    fraud_playbook: dict | None,
    tool_name: str,
    tool_response: dict | None = None,
) -> dict:
    """Update fraud playbook progress from successful tool completion."""
    playbook = dict(fraud_playbook or {})
    if not playbook:
        return playbook

    if tool_name == "get_open_fraud_alert":
        playbook["open_alert_inspected"] = True
        return playbook

    if tool_name == "report_lost_stolen_card":
        playbook["card_blocked"] = True
        playbook["confirmed_fraud"] = True
        return playbook

    if tool_name == "issue_replacement_card_tool":
        playbook["replacement_issued"] = True
        return playbook

    if tool_name == "push_card_to_google_wallet":
        playbook["wallet_push_queued"] = True
        return playbook

    if tool_name == "resolve_fraud_alert":
        resolution = str((((tool_response or {}).get("fraud_alert") or {}).get("resolution")) or "").strip().upper()
        playbook["resolution_completed"] = True
        if resolution == "CUSTOMER_RECOGNIZED":
            playbook["recognized_activity_confirmed"] = True
        if resolution == "CUSTOMER_CONFIRMED_FRAUD":
            playbook["confirmed_fraud"] = True
        return playbook

    return playbook
