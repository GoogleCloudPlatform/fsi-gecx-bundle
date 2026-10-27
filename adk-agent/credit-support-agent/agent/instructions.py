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

from pathlib import Path


RESOURCE_DIR = Path(__file__).resolve().parent / "resources"
BASE_INSTRUCTION_PATH = RESOURCE_DIR / "instruction.txt"
FLOWS_DIR = RESOURCE_DIR / "flows"

# Gemini 3.x Live calls tools asynchronously by default; cap silent retries.
LIVE_TOOL_RETRY_POLICY = (
    "When a tool returns no results, a refusal, or an error, tell the customer "
    "before calling a tool again. Never retry the same tool more than twice in "
    "a row without speaking to the customer. The required playbook sequence "
    "(discover_playbooks, record_playbook_decision, prepare_action_proposal) "
    "is not a retry."
)


def load_base_instruction() -> str:
    base = BASE_INSTRUCTION_PATH.read_text(encoding="utf-8").rstrip()
    return f"{base}\n\n{LIVE_TOOL_RETRY_POLICY}\n"


def load_flow_instruction(flow_name: str) -> str:
    return (FLOWS_DIR / f"{flow_name}.txt").read_text(encoding="utf-8")


def apply_avatar_name(instruction: str, avatar_name: str | None) -> str:
    return instruction.replace("{{avatar_name}}", avatar_name or "Nova")


def _display_money(field: object) -> str | None:
    if isinstance(field, dict):
        display_text = field.get("display_text")
        if isinstance(display_text, str) and display_text.strip():
            return display_text.strip()
        amount_minor = field.get("amount_minor")
        currency_code = field.get("currency_code") or "USD"
        exponent = int(field.get("exponent", 2))
        if isinstance(amount_minor, int):
            whole, fraction = divmod(abs(amount_minor), 10**exponent)
            digits = f"{whole:,}"
            if exponent:
                digits += f".{fraction:0{exponent}d}"
            if amount_minor < 0:
                digits = f"-{digits}"
            return f"{currency_code} {digits}"
    return None


def format_credit_account_context(credit_account: dict | None) -> str | None:
    """Render trusted card product and credit-limit facts for the session prompt."""
    if not isinstance(credit_account, dict) or not credit_account:
        return None
    product_name = credit_account.get("product_name") or credit_account.get("product_code")
    product_code = credit_account.get("product_code")
    credit_limit = _display_money(credit_account.get("credit_limit"))
    available_credit = _display_money(credit_account.get("available_credit"))
    product_max = _display_money(credit_account.get("product_maximum_limit"))
    lines = ["Customer credit card account context:"]
    if product_name:
        if product_code and product_code != product_name:
            lines.append(f"- Card product: {product_name} ({product_code}).")
        else:
            lines.append(f"- Card product: {product_name}.")
    if credit_limit:
        if available_credit:
            lines.append(
                f"- Starting credit limit: {credit_limit} (available credit: {available_credit})."
            )
        else:
            lines.append(f"- Starting credit limit: {credit_limit}.")
    if product_max:
        lines.append(f"- Card product maximum credit limit: {product_max}.")
    if len(lines) == 1:
        return None
    lines.append(
        "- If a credit-limit action is committed during this session, the latest tool result updates the current credit limit and available credit."
    )
    return "\n".join(lines)


def compose_session_instruction(
    *,
    avatar_name: str | None,
    active_flows: list[str] | None = None,
    session_context: str | None = None,
    guidance_summary: str | None = None,
) -> str:
    sections = [apply_avatar_name(load_base_instruction(), avatar_name)]
    for flow_name in active_flows or []:
        sections.append(load_flow_instruction(flow_name))
    if session_context:
        sections.append(session_context)
    if guidance_summary:
        sections.append(
            "Approved support guidance:\n"
            f"{guidance_summary}\n"
            "- This is the canonical business workflow and conversational policy for the active flow. Runtime instructions only map it to ADK tools. Do not add confirmation checkpoints. Live tools and trusted session context remain operational truth; fail closed if policy conflicts with a protected banking requirement."
        )
    return "\n\n".join(section.strip() for section in sections if section and section.strip())


INSTRUCTION_TEXT = load_base_instruction()
