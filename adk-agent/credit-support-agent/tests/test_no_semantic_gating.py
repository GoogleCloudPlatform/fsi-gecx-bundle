import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GATING_PATHS = (
    REPO_ROOT
    / "adk-agent"
    / "credit-support-agent"
    / "agent"
    / "workflow_authorization.py",
    REPO_ROOT
    / "adk-agent"
    / "credit-support-agent"
    / "agent"
    / "workflow_plugin.py",
    REPO_ROOT
    / "adk-agent"
    / "credit-support-agent"
    / "agent"
    / "fraud_voice.py",
    REPO_ROOT
    / "adk-agent"
    / "credit-support-agent"
    / "agent"
    / "closeout.py",
    REPO_ROOT
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "agents"
    / "Credit_Card_Support_Agent"
    / "before_tool_callbacks"
    / "enforce_proposal_context.py",
    REPO_ROOT
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "agents"
    / "Credit_Card_Support_Agent"
    / "after_tool_callbacks"
    / "capture_proposal.py",
)


def test_production_gates_do_not_import_regex_engines() -> None:
    for path in GATING_PATHS:
        tree = ast.parse(path.read_text(), filename=str(path))
        regex_imports = [
            node
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Import)
                and any(alias.name == "re" for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module == "re")
        ]
        assert regex_imports == [], f"semantic regex gate reintroduced in {path}"


def test_production_gates_do_not_define_transcript_classifiers() -> None:
    prohibited_names = {
        "classify_confirmation_response",
        "classify_google_wallet_response",
        "customer_confirmed_google_wallet",
        "customer_explicitly_closed",
        "assistant_requested_closeout",
    }
    for path in GATING_PATHS:
        tree = ast.parse(path.read_text(), filename=str(path))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert not (defined & prohibited_names), (
            f"transcript classifier reintroduced in {path}: "
            f"{sorted(defined & prohibited_names)}"
        )
