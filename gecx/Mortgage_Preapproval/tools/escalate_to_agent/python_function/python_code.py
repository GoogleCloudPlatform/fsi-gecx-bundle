def escalate_to_agent() -> None:
    context.variables["TELEPHONY_PAYLOAD"] = {
      "ujet": {
        "type": "action",
        "action": "escalation",
        "escalation_reason": "by_virtual_agent"
      }
    }
    print("TELEPHONY_PAYLOAD" + str(context.variables["TELEPHONY_PAYLOAD"]))