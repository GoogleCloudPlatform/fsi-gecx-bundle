from __future__ import annotations

import importlib.util
import inspect
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

COMMIT_CALLBACK = (
    ROOT
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "agents"
    / "Credit_Card_Support_Agent"
    / "before_tool_callbacks"
    / "enforce_proposal_context.py"
)
COMMIT_CALLBACK_SPEC = importlib.util.spec_from_file_location(
    "enforce_proposal_context", COMMIT_CALLBACK
)
commit_callback = importlib.util.module_from_spec(COMMIT_CALLBACK_SPEC)
assert COMMIT_CALLBACK_SPEC.loader
COMMIT_CALLBACK_SPEC.loader.exec_module(commit_callback)

def test_curated_contract_fixture_removes_live_credentials_and_ephemeral_state() -> None:
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
    assert response["fraud_alert"]["fraud_alert_id"] == "eval-alert-1"
    assert "$1,499.00" in fake_tools.fake_propose_fraud_triage(
        None, {}, None
    )["customer_safe_summary"]
    assert (
        fake_tools.fake_commit_wallet_provisioning(None, {}, None)[
            "wallet_provider"
        ]
        == "GOOGLE_WALLET"
    )
    prefixed = fake_tools.fake_tool_call(
        {"name": "banking_service_mcp_toolset_get_open_fraud_alert"},
        {},
        None,
    )
    assert prefixed["fraud_alert"]["card_last_four"] == "0001"
    assert fake_tools.fake_tool_call({"id": "unsupported"}, {}, None) is None


def test_conversational_reference_enumerates_every_charge_and_avoids_phone_copy() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    first = reference["turns"][0]["expected_agent"]

    for item in reference["quality_rules"]["transaction_inventory"]:
        assert item["merchant"] in first
        assert item["canonical_amount"] in first
    assert "Nova Horizon Bank" in first
    assert "calling" not in first.lower()
    assert reference["quality_rules"]["proposal_confirmation_turns"] == 1


def test_conversational_quality_rejects_bad_brand_phone_copy_and_omissions() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    quality = qualification._evaluate_conversational_quality(
        [
            "Hello, this is Nova from Nova Risen Bank. I'm calling about "
            "three suspicious charges. Do you recognize them?",
            "Please confirm the action.",
        ],
        reference,
    )

    assert quality["passed"] is False
    rendered = " ".join(quality["failures"])
    assert "required brand" in rendered
    assert "forbidden phrase" in rendered
    assert "APPLE.COM*ONLINE" in rendered
    assert "card ending in 0001" in rendered


def test_conversational_quality_accepts_reviewed_reference_copy() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    texts = [turn["expected_agent"] for turn in reference["turns"]]

    quality = qualification._evaluate_conversational_quality(texts, reference)

    assert quality["passed"] is True
    assert quality["proposal_confirmation_turns"] == 1


def test_conversational_quality_accepts_correct_spoken_currency() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    texts = [turn["expected_agent"] for turn in reference["turns"]]
    replacements = {
        "$4.99": "four dollars and ninety-nine cents",
        "$1,499.00": "one thousand four hundred and ninety-nine dollars",
        "$2,150.00": "two thousand one hundred and fifty dollars",
        "$1,250.00": "one thousand two hundred and fifty dollars",
        "$950.00": "nine hundred and fifty dollars",
    }
    for index in (0, 1):
        for canonical, spoken in replacements.items():
            texts[index] = texts[index].replace(canonical, spoken)
    texts[1] = texts[1].replace("Is that correct?", "Does that sound good?")

    quality = qualification._evaluate_conversational_quality(texts, reference)

    assert quality["passed"] is True


def test_conversational_quality_accepts_mixed_numeric_currency() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    texts = [turn["expected_agent"] for turn in reference["turns"]]
    replacements = {
        "$4.99": "4 dollars and 99 cents",
        "$1,499.00": "1,499 dollars",
        "$2,150.00": "2,150 dollars",
        "$1,250.00": "1,250 dollars",
        "$950.00": "950 dollars",
    }
    for canonical, spoken in replacements.items():
        texts[0] = texts[0].replace(canonical, spoken)

    quality = qualification._evaluate_conversational_quality(texts, reference)

    assert quality["passed"] is True


def test_conversational_quality_rejects_overstated_commit_result() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    texts = [turn["expected_agent"] for turn in reference["turns"]]
    texts[2] = (
        "The transactions were disputed, your card was blocked, and a "
        "replacement virtual card ending in 0002 is active. A secure message "
        "was sent. Is there anything else I can help you with?"
    )

    quality = qualification._evaluate_conversational_quality(texts, reference)

    assert quality["passed"] is False
    rendered = " ".join(quality["failures"])
    assert "submitted for specialist review" in rendered
    assert "pending charges were released" in rendered


def test_conversational_golden_includes_wallet_recovery_and_close() -> None:
    reference = __import__("json").loads(
        qualification.DEFAULT_CONVERSATIONAL_REFERENCE.read_text()
    )
    golden = qualification._conversational_golden(
        "projects/example/locations/us/apps/app", reference
    )
    rendered = repr(golden)

    assert "propose_wallet_provisioning" in rendered
    assert "commit_wallet_provisioning" in rendered
    assert "end_session" in rendered
    commit_steps = golden["turns"][2]["steps"]
    commit_call = next(
        step["expectation"]["toolCall"]
        for step in commit_steps
        if (step.get("expectation") or {}).get("toolCall")
    )
    assert commit_call["args"] == {}
    proposal_state = next(
        step["expectation"]["updatedVariables"]
        for step in golden["turns"][1]["steps"]
        if "proposal_id"
        in ((step.get("expectation") or {}).get("updatedVariables") or {})
    )
    assert proposal_state["proposal_action_type"] == "TRIAGE_FRAUD_CASE"
    wallet_state = next(
        step["expectation"]["updatedVariables"]
        for step in golden["turns"][3]["steps"]
        if "proposal_id"
        in ((step.get("expectation") or {}).get("updatedVariables") or {})
    )
    assert wallet_state["proposal_action_type"] == "PROVISION_GOOGLE_WALLET"
    assert wallet_state["proposal_id"] == "eval-wallet-proposal-1"
    assert (
        wallet_state["proposal_presentation_turn_id"]
        == "eval-turn-wallet-proposal"
    )
    terminal_steps = golden["turns"][5]["steps"]
    assert len(terminal_steps) == 2
    assert (
        terminal_steps[1]["expectation"]["toolCall"]["tool"].rsplit("/", 1)[-1]
        == "end_session"
    )
    assert len(golden["turns"]) == 6


def test_managed_contract_uses_reviewed_reference_not_a_live_generated_golden() -> None:
    signature = inspect.signature(qualification._managed_contract_evaluation)
    source = inspect.getsource(qualification._managed_contract_evaluation)

    assert "reference" in signature.parameters
    assert "conversation_name" not in signature.parameters
    assert "generateEvaluation" not in source
    assert "_conversational_golden(app, reference)" in source


def test_ces_commit_callback_binds_opaque_proposal_id_when_model_omits_it() -> None:
    from types import SimpleNamespace

    context = SimpleNamespace(
        invocation_id="confirmation-turn",
        variables={
            "proposal_id": "proposal-1",
            "proposal_action_type": "TRIAGE_FRAUD_CASE",
            "proposal_originating_turn_id": "proposal-turn",
            "proposal_presentation_turn_id": "proposal-turn",
        },
        get_last_user_input=lambda: [
            SimpleNamespace(text_or_transcript=lambda: "customer input")
        ],
    )
    tool_input = {}

    result = commit_callback.before_tool_callback(
        SimpleNamespace(name="commit_fraud_triage"),
        tool_input,
        context,
    )

    assert result is None
    assert tool_input == {"proposal_id": "proposal-1"}
    assert context.variables["proposal_confirmation_source"] == "MODEL_TOOL_INTENT"


def test_ces_commit_callback_rejects_conflicting_model_proposal_id() -> None:
    from types import SimpleNamespace

    context = SimpleNamespace(
        invocation_id="confirmation-turn",
        variables={
            "proposal_id": "proposal-1",
            "proposal_action_type": "TRIAGE_FRAUD_CASE",
            "proposal_originating_turn_id": "proposal-turn",
            "proposal_presentation_turn_id": "proposal-turn",
        },
        get_last_user_input=lambda: [
            SimpleNamespace(text_or_transcript=lambda: "customer input")
        ],
    )
    tool_input = {"proposal_id": "proposal-other"}

    result = commit_callback.before_tool_callback(
        SimpleNamespace(name="commit_fraud_triage"),
        tool_input,
        context,
    )

    assert result["error"] == "PROTECTED_CONFIRMATION_REQUIRED"
    assert tool_input == {"proposal_id": "proposal-other"}


def test_ces_commit_callback_requires_a_real_later_customer_invocation() -> None:
    from types import SimpleNamespace

    context = SimpleNamespace(
        invocation_id="proposal-turn",
        variables={
            "proposal_id": "proposal-1",
            "proposal_action_type": "TRIAGE_FRAUD_CASE",
            "proposal_originating_turn_id": "proposal-turn",
            "proposal_presentation_turn_id": "proposal-turn",
        },
        get_last_user_input=lambda: [],
    )

    result = commit_callback.before_tool_callback(
        SimpleNamespace(name="commit_fraud_triage"),
        {},
        context,
    )

    assert result["error"] == "PROTECTED_CONFIRMATION_REQUIRED"
    assert not context.variables.get("proposal_confirmation_source")


def test_latest_conversation_selects_completed_live_across_pages() -> None:
    class FakeApi:
        def request(self, method, path, body=None, query=None):
            assert method == "GET"
            assert path == "projects/example/locations/us/apps/app/conversations"
            if not query.get("pageToken"):
                return {
                    "conversations": [
                        {
                            "name": f"{path}/live-old",
                            "source": "LIVE",
                            "startTime": "2026-07-27T01:00:00Z",
                            "endTime": "2026-07-27T01:01:00Z",
                        },
                        {
                            "name": f"{path}/evaluation-newer",
                            "source": "EVAL",
                            "startTime": "2026-07-27T04:00:00Z",
                            "endTime": "2026-07-27T04:01:00Z",
                        },
                    ],
                    "nextPageToken": "page-2",
                }
            assert query["pageToken"] == "page-2"
            return {
                "conversations": [
                    {
                        "name": f"{path}/live-running",
                        "source": "LIVE",
                        "startTime": "2026-07-27T05:00:00Z",
                    },
                    {
                        "name": f"{path}/live-latest",
                        "source": "LIVE",
                        "startTime": "2026-07-27T02:00:00Z",
                        "endTime": "2026-07-27T02:01:00Z",
                    },
                ]
            }

    selected = qualification._latest_live_conversation(
        FakeApi(), "projects/example/locations/us/apps/app"
    )

    assert selected.endswith("/conversations/live-latest")


def test_latest_conversation_fails_when_no_completed_live_session_exists() -> None:
    class FakeApi:
        def request(self, method, path, body=None, query=None):
            return {
                "conversations": [
                    {
                        "name": f"{path}/evaluation",
                        "source": "EVAL",
                        "endTime": "2026-07-27T01:00:00Z",
                    }
                ]
            }

    try:
        qualification._latest_live_conversation(
            FakeApi(), "projects/example/locations/us/apps/app"
        )
    except ValueError as error:
        assert "No completed LIVE conversations" in str(error)
    else:
        raise AssertionError("Expected a missing-live-conversation error.")
