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

"""Small-catalog discovery. Semantic selection belongs to the calling agent."""


def input_schema(operation):
    names = {str: "string", bool: "boolean", list: "array", type(None): "null"}
    properties = {}
    for key, types in (operation.public_input_schema or operation.input_schema).items():
        allowed = types if isinstance(types, tuple) else (types,)
        field = (
            {"type": [names[t] for t in allowed]}
            if len(allowed) > 1
            else {"type": names[allowed[0]]}
        )
        if list in allowed:
            field["items"] = {"type": "string"}
        properties[key] = field
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def discover_playbooks(registry, customer_need):
    if (
        not isinstance(customer_need, str)
        or not customer_need.strip()
        or len(customer_need) > 2000
    ):
        raise ValueError("Describe the customer's current need in 1–2000 characters.")
    candidates = []
    for action_type in sorted(registry.action_types):
        spec = registry.require(action_type)
        metadata = spec.handler.discovery_view()
        if metadata is None:
            continue
        candidates.append(
            {
                "playbook_id": spec.definition_id,
                "revision": spec.definition_revision,
                "digest": spec.definition_digest,
                **metadata,
                "input_schema": input_schema(spec.handler.operation),
                "eligibility": "NOT_CHECKED",
            }
        )
    return {
        "success": True,
        "retrieval_mode": "FULL_PUBLISHED_CATALOG",
        "customer_need": customer_need.strip(),
        "playbooks": candidates,
        "model_instruction": (
            "Compare the customer's need and trusted conversation/account context with these descriptions. "
            "Select at most one relevant playbook; no match is valid. If the requested outcome or provider is unsupported, "
            "explain the limitation without promising it or asking to confirm it. Never substitute providers. "
            "Examples are illustrative, not keyword rules. "
            "Do not infer eligibility or authorization from discovery. If intent or required inputs are unclear, "
            "ask one focused question or use a read tool. Otherwise call prepare_action_proposal with the exact "
            "playbook_id, revision, digest and inputs_json: serialize the declared business inputs as a JSON object string "
            "(use '{}' for no inputs). Do not ask permission to prepare or seek confirmation "
            "before preparation succeeds. Present its returned offer and wait for a later "
            "explicit confirmation before commit_action_proposal. Do not prepare merely because a capability exists."
        ),
    }
