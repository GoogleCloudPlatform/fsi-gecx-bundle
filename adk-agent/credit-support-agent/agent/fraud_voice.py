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
            "triage_submitted": False,
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
        "triage_submitted": False,
        "required_sequence": [
            "get_open_fraud_alert",
            "triage_fraud_case",
        ],
    }


def build_initial_greeting(fraud_playbook: dict | None) -> str:
    if (fraud_playbook or {}).get("entry_mode") == "FRAUD_ALERT":
        card_last_four = (fraud_playbook or {}).get("card_last_four", "their card")
        suspicious_count = (fraud_playbook or {}).get("suspicious_transactions_count") or "the"
        return (
            "Please introduce yourself briefly, acknowledge that you can see a suspicious activity alert "
            f"on the customer's card ending in {card_last_four}, explain that you are reviewing {suspicious_count} flagged charges now, "
            "inspect the open fraud alert before recommending next steps, and ask whether the customer recognizes the flagged transactions."
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

    legacy_fraud_mitigation_tools = {
        "report_lost_stolen_card",
        "issue_replacement_card_tool",
        "resolve_fraud_alert",
    }
    if tool_name in legacy_fraud_mitigation_tools:
        return "Use triage_fraud_case for active fraud alert mitigation instead of sequencing low-level fraud tools."

    if tool_name == "push_card_to_google_wallet" and not playbook.get("replacement_issued"):
        return "Complete fraud triage and replacement before queueing Google Wallet provisioning."

    if tool_name == "triage_fraud_case" and not playbook.get("open_alert_inspected"):
        return "Inspect the open fraud alert before taking mitigation actions."

    if tool_name == "triage_fraud_case":
        fraud_alert_id = str((args or {}).get("fraud_alert_id") or "").strip()
        expected_alert_id = str(playbook.get("fraud_alert_id") or "").strip()
        if expected_alert_id and not fraud_alert_id:
            return "Use the active fraud alert id from the inspected alert when triaging the fraud case."
        if expected_alert_id and fraud_alert_id and fraud_alert_id != expected_alert_id:
            return "Use the active fraud alert id from the inspected alert when triaging the fraud case."
        if playbook.get("triage_submitted") or playbook.get("resolution_completed"):
            return "The fraud case has already been triaged. Do not submit the fraud workflow again."
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

    if tool_name == "triage_fraud_case":
        outcome = str((tool_response or {}).get("outcome") or "").strip().upper()
        playbook["triage_submitted"] = True
        playbook["resolution_completed"] = True
        if outcome == "CUSTOMER_RECOGNIZED":
            playbook["recognized_activity_confirmed"] = True
        else:
            playbook["confirmed_fraud"] = True
            if (tool_response or {}).get("replacement_card"):
                playbook["card_blocked"] = True
                playbook["replacement_issued"] = True
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
