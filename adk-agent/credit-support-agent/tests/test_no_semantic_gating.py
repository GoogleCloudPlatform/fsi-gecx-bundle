# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXPLICIT_GATING_PATHS = (
    REPO_ROOT
    / "adk-agent"
    / "credit-support-agent"
    / "agent"
    / "agent.py",
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
    REPO_ROOT
    / "banking-service"
    / "services"
    / "action_proposal_context.py",
    REPO_ROOT
    / "banking-service"
    / "services"
    / "action_proposals.py",
)

DISCOVERED_GATING_PATHS = tuple(
    sorted(
        {
            *(
                REPO_ROOT / "banking-service" / "services"
            ).glob("*proposal*.py"),
            *(
                REPO_ROOT
                / "adk-agent"
                / "credit-support-agent"
                / "agent"
            ).glob("*authorization*.py"),
            *(
                REPO_ROOT
                / "adk-agent"
                / "credit-support-agent"
                / "agent"
            ).glob("*proposal*.py"),
            *(
                REPO_ROOT
                / "gecx"
                / "Credit_Support_Voice_Agent"
                / "agents"
                / "Credit_Card_Support_Agent"
            ).glob("**/*proposal*.py"),
        }
    )
)
GATING_PATHS = tuple(dict.fromkeys((*EXPLICIT_GATING_PATHS, *DISCOVERED_GATING_PATHS)))

PROHIBITED_SEMANTIC_IDENTIFIER_FRAGMENTS = {
    "affirmative_phrase",
    "negative_phrase",
    "confirmation_phrase",
    "decline_phrase",
    "transcript_pattern",
    "spoken_number",
}


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


def test_production_gates_do_not_define_semantic_phrase_parsers() -> None:
    for path in GATING_PATHS:
        tree = ast.parse(path.read_text(), filename=str(path))
        identifiers = {
            node.id.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        identifiers.update(
            node.name.lower()
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        )
        identifiers.update(
            argument.arg.lower()
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
        )
        violations = {
            identifier
            for identifier in identifiers
            if any(
                fragment in identifier
                for fragment in PROHIBITED_SEMANTIC_IDENTIFIER_FRAGMENTS
            )
        }
        assert not violations, (
            f"semantic phrase parser reintroduced in {path}: {sorted(violations)}"
        )
