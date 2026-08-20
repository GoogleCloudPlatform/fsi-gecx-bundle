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

"""Reject standby handoffs that lack a trusted closeout checkpoint."""


def before_agent_callback(callback_context):
    variables = callback_context.variables
    checkpoint_state = str(variables.get("closeout_checkpoint_state") or "")
    authorized = bool(
        variables.get("closeout_delegation_authorized")
        and checkpoint_state == "OFFERED"
        and not str(variables.get("proposal_id") or "")
        and not bool(variables.get("proposal_commit_attempted"))
    )
    variables["closeout_delegation_authorized"] = authorized
    if authorized:
        return None
    return Content(  # noqa: F821
        parts=[
            Part.from_agent_transfer(  # noqa: F821
                agent="Credit Card Support Agent"
            )
        ]
    )
