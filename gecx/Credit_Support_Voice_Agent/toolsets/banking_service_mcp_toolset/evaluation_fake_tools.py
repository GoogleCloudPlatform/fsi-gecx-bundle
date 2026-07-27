"""Synthetic banking responses used only when a CES evaluation selects fake mode."""

import json


def fake_tool_call(tool, input, callback_context):
    tool_id = (
        getattr(tool, "tool_id", "")
        or getattr(tool, "id", "")
        or getattr(tool, "name", "")
    )
    if isinstance(tool, dict):
        tool_id = tool.get("id") or tool.get("name") or tool_id
    tool_id = str(tool_id).rsplit("/", 1)[-1]
    authorizations = [
        {
            "authorization_id": "eval-auth-1",
            "merchant_name": "GAME*TEST TOKEN ONLINE",
            "amount_cents": 499,
        },
        {
            "authorization_id": "eval-auth-2",
            "merchant_name": "APPLE.COM*ONLINE",
            "amount_cents": 149900,
        },
        {
            "authorization_id": "eval-auth-3",
            "merchant_name": "BEST BUY*MKTPLACE",
            "amount_cents": 215000,
        },
        {
            "authorization_id": "eval-auth-4",
            "merchant_name": "RAZER GOLD GIFT CARD",
            "amount_cents": 125000,
        },
        {
            "authorization_id": "eval-auth-5",
            "merchant_name": "TARGET.COM GIFT CARDS",
            "amount_cents": 95000,
        },
    ]
    if tool_id == "get_open_fraud_alert":
        output = {
            "success": True,
            "fraud_alert": {
                "fraud_alert_id": "eval-alert-1",
                "status": "OPEN",
                "card_last_four": "0001",
                "suspicious_transactions": authorizations,
            },
            "support_guidance": {
                "source": "knowledge_catalog",
                "topic_ids": ["fraud_golden_path", "replacement_card"],
                "snapshot_id": "eval-catalog-snapshot",
                "content_version": "2.2+2.4+2.5",
            },
        }
    elif tool_id == "propose_fraud_triage":
        output = {
            "success": True,
            "status": "PROPOSED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to dispute all five listed charges on card "
                "ending 0001, block the current card, and issue a replacement."
            ),
        }
    elif tool_id == "commit_fraud_triage":
        output = {
            "success": True,
            "status": "COMMITTED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "outcome": "PENDING_SPECIALIST_REVIEW",
            "replacement_card": {
                "new_last_four": "0002",
                "is_virtual": True,
                "status": "ACTIVE",
            },
            "customer_safe_result_summary": (
                "Your fraud report was submitted for specialist review. Five "
                "pending charges were released. Your compromised card was blocked, "
                "and a replacement virtual card ending in 0002 is active. A secure "
                "message with the case details was sent."
            ),
        }
    else:
        return None
    return {"output": json.dumps(output, separators=(",", ":"))}


def fake_get_open_fraud_alert(tool, input, callback_context):
    return fake_tool_call({"id": "get_open_fraud_alert"}, input, callback_context)


def fake_propose_fraud_triage(tool, input, callback_context):
    return fake_tool_call({"id": "propose_fraud_triage"}, input, callback_context)


def fake_commit_fraud_triage(tool, input, callback_context):
    return fake_tool_call({"id": "commit_fraud_triage"}, input, callback_context)
