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

"""Retrieval adapters preserve published identity and discovery safety."""

from copy import deepcopy
import json

import pytest

from services.playbook_discovery import (
    FullPublishedCatalogRetriever,
    PublishedPlaybookPin,
    discover_playbooks,
)
from services.proposal_definitions import CATALOG_PATH, load_action_registry


@pytest.fixture
def registry():
    return load_action_registry(None)


class RecordedRetriever:
    """An isolated adapter double; it makes no semantic or eligibility decision."""

    mode = "RECORDED_CANDIDATES"

    def __init__(self, pins):
        self.pins = tuple(pins)

    def retrieve(self, registry, customer_need):
        return self.pins


def test_full_catalog_returns_every_published_playbook_without_eligibility(registry):
    result = discover_playbooks(registry, "I need help with my card.")
    pins = FullPublishedCatalogRetriever().retrieve(
        registry, "I need help with my card."
    )
    assert {p.playbook_id for p in pins} == {
        registry.require(action).definition_id for action in registry.action_types
    }
    assert result["retrieval_mode"] == "FULL_PUBLISHED_CATALOG"
    assert all(
        candidate["eligibility"] == "NOT_CHECKED" for candidate in result["playbooks"]
    )
    assert all(
        "payload" not in candidate and "operation" not in candidate
        for candidate in result["playbooks"]
    )


def test_adapter_can_return_a_subset_without_changing_canonical_metadata(registry):
    pins = FullPublishedCatalogRetriever().retrieve(registry, "replacement")
    result = discover_playbooks(
        registry, "  replacement  ", retriever=RecordedRetriever(pins[:1])
    )
    default = discover_playbooks(registry, "replacement")
    assert result["playbooks"] == default["playbooks"][:1]
    assert result["customer_need"] == "replacement"
    assert result["retrieval_mode"] == "RECORDED_CANDIDATES"


def test_empty_retrieval_is_valid_without_implying_authorization(registry):
    result = discover_playbooks(registry, "Thank you", retriever=RecordedRetriever(()))
    assert result["playbooks"] == []
    assert "Do not infer eligibility or authorization" in result["model_instruction"]


@pytest.mark.parametrize("fault", ["digest", "unknown", "duplicate"])
def test_faulty_adapter_cannot_supply_unpublished_or_duplicate_pins(registry, fault):
    pin = FullPublishedCatalogRetriever().retrieve(registry, "replacement")[0]
    if fault == "digest":
        pins = [PublishedPlaybookPin(pin.playbook_id, pin.revision, "0" * 64)]
    elif fault == "unknown":
        pins = [PublishedPlaybookPin("unknown", 1, "0" * 64)]
    else:
        pins = [pin, pin]
    with pytest.raises(ValueError):
        discover_playbooks(registry, "replacement", retriever=RecordedRetriever(pins))


def test_historical_pin_is_not_a_current_candidate():
    document = next(
        document
        for path in sorted(CATALOG_PATH.glob("*.json"))
        if (document := json.loads(path.read_text())).get("schema_version") == 2
    )
    old_registry = load_action_registry(None, [document])
    pin = FullPublishedCatalogRetriever().retrieve(old_registry, "replacement")[0]
    newer = deepcopy(document)
    newer["revision"] += 1
    newer["discovery"]["title"] += " revised"
    registry = load_action_registry(None, [document, newer])
    assert registry.resolve(pin.playbook_id, pin.revision, pin.digest)
    with pytest.raises(ValueError, match="currently published"):
        discover_playbooks(registry, "replacement", retriever=RecordedRetriever([pin]))
