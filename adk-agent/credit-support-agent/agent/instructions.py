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


def load_base_instruction() -> str:
    return BASE_INSTRUCTION_PATH.read_text(encoding="utf-8")


def load_flow_instruction(flow_name: str) -> str:
    return (FLOWS_DIR / f"{flow_name}.txt").read_text(encoding="utf-8")


def apply_avatar_name(instruction: str, avatar_name: str | None) -> str:
    return instruction.replace("{{avatar_name}}", avatar_name or "Nova")


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
