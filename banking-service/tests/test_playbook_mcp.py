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

import pytest
from unittest.mock import Mock
from routers.mcp import playbooks
from routers.mcp.utils import proposal_runtime_context_var, verified_customer_id_var
from services.action_proposal_context import ProposalRuntimeContext


@pytest.mark.asyncio
async def test_generic_mcp_decodes_business_json_and_binds_trusted_context(monkeypatch):
    db = Mock()
    service = Mock()
    service.prepare_playbook_for_identity.return_value = {"success": True}
    monkeypatch.setattr(playbooks, "SessionLocal", lambda: db)
    monkeypatch.setattr(playbooks, "ActionProposalService", lambda session: service)
    context = ProposalRuntimeContext(
        "support", "ADK_GEMINI_LIVE", "session", "turn", "reset"
    )
    context_token = proposal_runtime_context_var.set(context)
    identity_token = verified_customer_id_var.set("verified-customer")
    try:
        for serialized in ('{"reason":"LOST"}', '{ "reason": "LOST" }'):
            result = await playbooks.prepare_action_proposal.__wrapped__(
                playbook_id="card-reissue",
                revision=2,
                digest="catalog-digest",
                inputs_json=serialized,
            )
            assert result["success"]
        first, second = service.prepare_playbook_for_identity.call_args_list
        assert first.kwargs == second.kwargs
        assert first.kwargs["inputs"] == {"reason": "LOST"}
        assert first.kwargs["customer_identity"] == "verified-customer"
        assert first.kwargs["runtime_context"] is context
        result = await playbooks.prepare_action_proposal.__wrapped__(
            playbook_id="card-reissue",
            revision=2,
            digest="catalog-digest",
            inputs_json="not json",
        )
        assert result["error"] == "INVALID_PLAYBOOK_REQUEST"
        assert service.prepare_playbook_for_identity.call_count == 2
        db.rollback.assert_called_once()
    finally:
        proposal_runtime_context_var.reset(context_token)
        verified_customer_id_var.reset(identity_token)
