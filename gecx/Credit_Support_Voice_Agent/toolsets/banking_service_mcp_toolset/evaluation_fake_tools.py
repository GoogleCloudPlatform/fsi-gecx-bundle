"""Synthetic banking responses used only when a CES evaluation selects fake mode."""


def fake_tool_call(tool, input, callback_context):
    tool_id = (
        getattr(tool, "tool_id", "")
        or getattr(tool, "id", "")
        or getattr(tool, "name", "")
    )
    if isinstance(tool, dict):
        tool_id = tool.get("id") or tool.get("name") or tool_id
    tool_id = str(tool_id).rsplit("/", 1)[-1]
    # CES supplies MCP tool names with the toolset display-name prefix in
    # managed replays (for example,
    # banking_service_mcp_toolset_get_open_fraud_alert).
    known_tool_ids = (
        "get_open_fraud_alert",
        "propose_fraud_triage",
        "commit_fraud_triage",
        "propose_card_reissue",
        "commit_card_reissue",
        "propose_wallet_provisioning",
        "commit_wallet_provisioning",
        "decide_action_proposal",
        "offer_session_closeout",
    )
    tool_id = next(
        (
            known_tool_id
            for known_tool_id in known_tool_ids
            if tool_id.endswith(known_tool_id)
        ),
        tool_id,
    )
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
                "summary": (
                    "Customer has an active fraud alert on card ending in 0001. "
                    "Flagged transactions are $4.99 at GAME*TEST TOKEN ONLINE, "
                    "$1,499.00 at APPLE.COM*ONLINE, $2,150.00 at BEST "
                    "BUY*MKTPLACE, $1,250.00 at RAZER GOLD GIFT CARD, and "
                    "$950.00 at TARGET.COM GIFT CARDS."
                ),
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
                "Confirm that you want to dispute $4.99 at GAME*TEST TOKEN ONLINE, "
                "$1,499.00 at APPLE.COM*ONLINE, $2,150.00 at BEST BUY*MKTPLACE, "
                "$1,250.00 at RAZER GOLD GIFT CARD, and $950.00 at TARGET.COM "
                "GIFT CARDS on card ending 0001, block the current card, and issue "
                "a replacement."
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
    elif tool_id == "propose_card_reissue":
        output = {
            "success": True,
            "status": "PROPOSED",
            "action_type": "REISSUE_CARD",
            "contract_version": "card-reissue.v1",
            "proposal_id": "eval-reissue-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to block the card ending 0001 and issue "
                "a replacement virtual card."
            ),
        }
    elif tool_id == "commit_card_reissue":
        output = {
            "success": True,
            "status": "COMMITTED",
            "action_type": "REISSUE_CARD",
            "contract_version": "card-reissue.v1",
            "proposal_id": "eval-reissue-proposal-1",
            "replacement_card": {
                "new_last_four": "0002",
                "is_virtual": True,
                "status": "ACTIVE",
            },
        }
    elif tool_id == "propose_wallet_provisioning":
        output = {
            "success": True,
            "status": "PROPOSED",
            "action_type": "PROVISION_GOOGLE_WALLET",
            "contract_version": "wallet-provisioning.v1",
            "proposal_id": "eval-wallet-proposal-1",
            "customer_safe_summary": (
                "Confirm that you want to queue the virtual card ending 0002 "
                "for Google Wallet."
            ),
        }
    elif tool_id == "commit_wallet_provisioning":
        output = {
            "success": True,
            "status": "COMMITTED",
            "action_type": "PROVISION_GOOGLE_WALLET",
            "contract_version": "wallet-provisioning.v1",
            "proposal_id": "eval-wallet-proposal-1",
            "message": "Virtual card provisioning is queued for Google Wallet.",
            "card_token": "eval-replacement-token",
            "wallet_provider": "GOOGLE_WALLET",
            "wallet_provisioning_status": "QUEUED",
        }
    elif tool_id == "decide_action_proposal":
        decision = str((input or {}).get("decision") or "").strip().upper()
        output = {
            "success": decision in {"DECLINE", "REVISE", "CANCEL"},
            "status": "DECLINED" if decision == "DECLINE" else "INVALIDATED",
            "action_type": "TRIAGE_FRAUD_CASE",
            "contract_version": "fraud-triage.v1",
            "proposal_id": "eval-proposal-1",
            "decision": decision,
            "invalidation_reason": {
                "DECLINE": "CUSTOMER_DECLINED",
                "REVISE": "CUSTOMER_REVISED",
                "CANCEL": "CUSTOMER_CANCELLED",
            }.get(decision),
        }
    elif tool_id == "offer_session_closeout":
        output = {
            "success": True,
            "status": "CLOSEOUT_OFFERED",
            "customer_prompt": "Is there anything else I can help you with?",
        }
    else:
        return None
    # ToolFakeConfig callbacks return the tool's logical response directly.
    # The MCP transport envelope is added only by the real remote MCP client;
    # returning that envelope here causes CES to expose an empty response to
    # the model during stable replay.
    return output


def fake_get_open_fraud_alert(tool, input, callback_context):
    return fake_tool_call({"id": "get_open_fraud_alert"}, input, callback_context)


def fake_propose_fraud_triage(tool, input, callback_context):
    return fake_tool_call({"id": "propose_fraud_triage"}, input, callback_context)


def fake_commit_fraud_triage(tool, input, callback_context):
    return fake_tool_call({"id": "commit_fraud_triage"}, input, callback_context)


def fake_propose_card_reissue(tool, input, callback_context):
    return fake_tool_call({"id": "propose_card_reissue"}, input, callback_context)


def fake_commit_card_reissue(tool, input, callback_context):
    return fake_tool_call({"id": "commit_card_reissue"}, input, callback_context)


def fake_propose_wallet_provisioning(tool, input, callback_context):
    return fake_tool_call({"id": "propose_wallet_provisioning"}, input, callback_context)


def fake_commit_wallet_provisioning(tool, input, callback_context):
    return fake_tool_call({"id": "commit_wallet_provisioning"}, input, callback_context)


def fake_offer_session_closeout(tool, input, callback_context):
    return fake_tool_call({"id": "offer_session_closeout"}, input, callback_context)


def fake_decide_action_proposal(tool, input, callback_context):
    return fake_tool_call({"id": "decide_action_proposal"}, input, callback_context)
