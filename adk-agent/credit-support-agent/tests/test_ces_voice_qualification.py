from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "cxas" / "ces_voice_qualification.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("ces_voice_qualification", SCRIPT)
qualification = importlib.util.module_from_spec(SCRIPT_SPEC)
assert SCRIPT_SPEC.loader
SCRIPT_SPEC.loader.exec_module(qualification)

FAKE_TOOLS = (
    ROOT
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "toolsets"
    / "banking_service_mcp_toolset"
    / "evaluation_fake_tools.py"
)
FAKE_SPEC = importlib.util.spec_from_file_location("evaluation_fake_tools", FAKE_TOOLS)
fake_tools = importlib.util.module_from_spec(FAKE_SPEC)
assert FAKE_SPEC.loader
FAKE_SPEC.loader.exec_module(fake_tools)


def test_curated_golden_removes_live_credentials_and_ephemeral_state() -> None:
    golden = {
        "turns": [
            {
                "steps": [
                    {
                        "userInput": {
                            "variables": {
                                "runtime_name": "CES_GEMINI_LIVE",
                                "session_capability": "secret-capability",
                                "customer_ref": "customer:secret",
                                "support_session_id": "support-secret",
                            }
                        }
                    },
                    {
                        "expectation": {
                            "toolCall": {
                                "toolsetTool": {
                                    "toolId": "get_open_fraud_alert"
                                },
                                "args": {"customer_id": "secret-customer"},
                            }
                        }
                    },
                    {
                        "expectation": {
                            "toolResponse": {
                                "toolsetTool": {
                                    "toolId": "get_open_fraud_alert"
                                },
                                "response": {
                                    "text_output": [
                                        {
                                            "success": True,
                                            "customer_id": "secret-customer",
                                        }
                                    ]
                                },
                            }
                        }
                    },
                ]
            },
            {
                "steps": [
                    {"userInput": {"text": "Let's go."}},
                ]
            },
        ]
    }

    curated = qualification._curate_generated_golden(golden)
    rendered = repr(curated)

    assert "secret" not in rendered
    assert curated["turns"][0]["steps"][1]["expectation"]["toolCall"]["args"] == {}
    assert (
        curated["turns"][-1]["steps"][0]["userInput"]["text"]
        == "No, that's all. Thank you."
    )
    response = curated["turns"][0]["steps"][2]["expectation"]["toolResponse"][
        "response"
    ]
    assert "eval-alert-1" in response["output"]


def test_evaluation_fake_tools_are_synthetic_and_tool_specific() -> None:
    response = fake_tools.fake_get_open_fraud_alert(None, {}, None)

    assert "secret" not in repr(response)
    assert "eval-alert-1" in response["output"]
    assert fake_tools.fake_tool_call({"id": "unsupported"}, {}, None) is None
