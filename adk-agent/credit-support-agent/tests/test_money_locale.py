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

from copy import deepcopy
import json
from pathlib import Path
import pytest

from agent.money_locale import change_voice_language, select_banking_presentation
from agent.proposal_evidence import (create_pending_proposal, mark_proposal_presented,
    attest_model_decision, proposal_evidence_error, AWAITING_PRESENTATION, COMMIT_RETRY)


CONTENT = json.loads((Path(__file__).resolve().parents[3] / "banking-service/resources/data/money_fraud_voice_content.json").read_text())


def state():
    projection = create_pending_proposal(proposal_id="p", action_type="TRIAGE_FRAUD_CASE",
        contract_version="fraud-triage.v1", originating_customer_turn_id="c1")
    projection = mark_proposal_presented(projection, assistant_turn_id="a1", observed_at_epoch_s=2)
    return {"voice_locale": "en-US", "money_voice_content": deepcopy(CONTENT),
            "fraud_playbook": {"pending_proposal": projection},
            "banking_proposal_presentation": {"proposal_id": "p", "money_facts": [{"money": {"amount_minor": 19900, "currency_code": "MXN"}}],
              "presentations": {"en-US": {"speech_text": "English"}, "es-MX": {"speech_text": "Español"}}}}


def test_language_switch_preserves_identity_and_money_but_rejects_stale_confirmation():
    current = state()
    before = deepcopy(current["banking_proposal_presentation"])
    result = change_voice_language(current, "es-MX")
    assert result["effective_locale"] == "es-MX"
    assert result["requires_fresh_confirmation"] is True
    assert result["proposal"]["presentation"]["speech_text"] == "Español"
    assert current["banking_proposal_presentation"] == before
    pending = current["fraud_playbook"]["pending_proposal"]
    assert pending["proposal_id"] == "p"
    assert pending["evidence_state"] == AWAITING_PRESENTATION
    stale = attest_model_decision(pending, proposal_id="p", action_type="TRIAGE_FRAUD_CASE",
        customer_turn_id="c2", customer_observed_at_epoch_s=3)
    assert proposal_evidence_error(stale, proposal_id="p", action_type="TRIAGE_FRAUD_CASE")
    presented = mark_proposal_presented(pending, assistant_turn_id="a2", observed_at_epoch_s=4)
    confirmed = attest_model_decision(presented, proposal_id="p", action_type="TRIAGE_FRAUD_CASE",
        customer_turn_id="c3", customer_observed_at_epoch_s=5)
    assert proposal_evidence_error(confirmed, proposal_id="p", action_type="TRIAGE_FRAUD_CASE") is None


def test_unreviewed_spanish_falls_back_to_english_with_fresh_evidence():
    current = state()
    current["money_voice_content"]["review_status"] = "PENDING_HUMAN_REVIEW"
    result = change_voice_language(current, "es-MX")
    assert result["fallback"] is True
    assert result["effective_locale"] == "en-US"
    assert result["requires_fresh_confirmation"] is True


def test_language_switch_does_not_discard_uncertain_commit_retry():
    current = state()
    current["fraud_playbook"]["pending_proposal"]["evidence_state"] = COMMIT_RETRY
    before = deepcopy(current)
    assert change_voice_language(current, "es-MX")["success"] is False
    assert current == before


def test_no_missing_presentation_translation_or_fallback_guess():
    with pytest.raises(ValueError):
        select_banking_presentation({"presentations": {"en-US": {"speech_text": "English"}}}, "es-MX")


@pytest.mark.asyncio
async def test_live_language_change_closes_old_stream_before_restart():
    from types import SimpleNamespace
    from agent.money_locale import stream_with_language_changes
    locale = "en-US"
    closed = []
    restarts = []
    async def stream():
        selected = locale
        try:
            if selected == "en-US":
                yield SimpleNamespace(actions=SimpleNamespace(state_delta={"voice_locale": "es-MX"}))
                raise AssertionError("Old-language stream must stop immediately")
            yield SimpleNamespace(actions=SimpleNamespace(state_delta={}), output="Spanish output")
        finally:
            closed.append(selected)
    async def restart(selected):
        nonlocal locale
        assert closed == ["en-US"]
        restarts.append(selected)
        locale = selected
    outputs = [event async for event in stream_with_language_changes(
        stream_factory=stream, current_locale=lambda: locale, restart=restart)]
    assert [event.output for event in outputs] == ["Spanish output"]
    assert restarts == ["es-MX"]
    assert closed == ["en-US", "es-MX"]


def test_runtime_fallback_preserves_banking_facts_and_invalidates_confirmation():
    current = state()
    current['voice_locale'] = 'es-MX'
    before = deepcopy(current['banking_proposal_presentation'])
    result = change_voice_language(current, 'es-MX', runtime_unavailable=True)
    assert result['effective_locale'] == 'en-US'
    assert result['message'] == CONTENT['en-US']['fallback']
    assert result['requires_fresh_confirmation']
    assert current['banking_proposal_presentation'] == before
    assert current['fraud_playbook']['pending_proposal']['evidence_state'] == AWAITING_PRESENTATION


@pytest.mark.asyncio
async def test_live_runtime_rejection_falls_back_once_after_persisting_evidence():
    from agent.money_locale import stream_with_language_changes
    locale = 'es-MX'
    calls = []
    async def stream():
        if locale == 'es-MX':
            raise RuntimeError('Language es-MX is not supported')
        yield 'English output'
    async def fallback():
        calls.append('persist')
        return True
    async def restart(selected):
        nonlocal locale
        assert calls == ['persist']
        locale = selected
        calls.append(selected)
    output = [event async for event in stream_with_language_changes(
        stream_factory=stream, current_locale=lambda: locale,
        restart=restart, runtime_fallback=fallback)]
    assert output == ['English output']
    assert calls == ['persist', 'en-US']


@pytest.mark.asyncio
@pytest.mark.parametrize('error,locale,allowed', [
    ('Connection timeout', 'es-MX', True),
    ('Language not supported', 'en-US', True),
    ('Language not supported', 'es-MX', False),
])
async def test_live_fallback_does_not_hide_unrelated_errors_or_uncertain_commits(error, locale, allowed):
    from agent.money_locale import stream_with_language_changes
    async def stream():
        raise RuntimeError(error)
        yield
    async def fallback():
        return allowed
    async def restart(selected):
        pytest.fail('Must not restart')
    with pytest.raises(RuntimeError, match=error):
        async for _ in stream_with_language_changes(stream_factory=stream,
            current_locale=lambda: locale, restart=restart, runtime_fallback=fallback):
            pass
