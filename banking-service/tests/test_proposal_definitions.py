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

"""Configuration boundaries and version pinning for declarative actions."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from services.proposal_definitions import (
    CATALOG_PATH,
    load_action_registry,
    ServiceActionHandler,
)


def documents():
    return [
        json.loads(path.read_text()) for path in sorted(CATALOG_PATH.glob("*.json"))
    ]


def test_fourth_action_requires_only_a_definition():
    docs = documents()
    fourth = deepcopy(docs[0])
    fourth.update(id="replacement-followup", action_type="REPLACEMENT_FOLLOWUP")
    registry = load_action_registry(None, [*docs, fourth])
    assert len(registry.action_types) == 4
    assert {type(registry.require(key).handler) for key in registry.action_types} == {
        ServiceActionHandler
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(extra=True),
        lambda d: d.update(type="python"),
        lambda d: d.update(revision=True),
        lambda d: d.update(operation="os.system"),
        lambda d: d.update(authorization_policy="none"),
        lambda d: d["presentation"].update(public_payload_fields=["card_token"]),
        lambda d: d["presentation"].update(required_facts=[]),
        lambda d: d["presentation"].update(template="{card_last_four.__class__}"),
        lambda d: d["payload"].update(compromised_card_id={"literal": "another-card"}),
        lambda d: d["parameters"].update(require_virtual=0),
    ],
)
def test_invalid_definitions_rejected_before_execution(mutation):
    d = documents()[0]
    mutation(d)
    with pytest.raises(ValueError):
        load_action_registry(None, [d])


def test_pinned_revision_and_digest_survive_activation():
    first = documents()[0]
    old = load_action_registry(None, [first]).require(first["action_type"])
    second = deepcopy(first)
    second["revision"] = 2
    second["presentation"]["template"] += " Please confirm."
    registry = load_action_registry(None, [first, second])
    proposal = SimpleNamespace(
        definition_id=old.definition_id,
        definition_revision=old.definition_revision,
        definition_digest=old.definition_digest,
        action_type=old.action_type,
        contract_version=old.contract_version,
    )
    assert registry.require(old.action_type).definition_revision == 2
    assert registry.for_proposal(proposal).definition_revision == 1
    with pytest.raises(ValueError, match="Unknown or changed"):
        load_action_registry(None, [second]).for_proposal(proposal)
    modified = deepcopy(first)
    modified["presentation"]["template"] += " Changed."
    with pytest.raises(ValueError, match="Unknown or changed"):
        load_action_registry(None, [modified]).for_proposal(proposal)


def test_duplicate_revisions_rejected():
    d = documents()[0]
    with pytest.raises(ValueError, match="exactly once"):
        load_action_registry(None, [d, d])


def test_reset_migration_requires_definition_identity_and_preserves_other_data():
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, text, inspect

    path = (
        Path(__file__).parents[1]
        / "alembic/versions/f7e0f4a9c306_proposal_definition_identity.py"
    )
    spec = importlib.util.spec_from_file_location("definition_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        if "operations" in {
            row[1] for row in connection.execute(text("PRAGMA database_list"))
        }:
            connection.execute(text("DETACH DATABASE operations"))
        connection.execute(text("ATTACH DATABASE ':memory:' AS operations"))
        connection.execute(
            text("CREATE TABLE operations.action_proposals (id TEXT PRIMARY KEY)")
        )
        connection.execute(
            text("INSERT INTO operations.action_proposals VALUES ('old')")
        )
        connection.execute(text("CREATE TABLE operations.other_data (id TEXT)"))
        connection.execute(text("INSERT INTO operations.other_data VALUES ('keep')"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM operations.action_proposals")
            ).scalar()
            == 0
        )
        assert (
            connection.execute(text("SELECT id FROM operations.other_data")).scalar()
            == "keep"
        )
        columns = {
            c["name"]: c
            for c in inspect(connection).get_columns(
                "action_proposals", schema="operations"
            )
        }
        assert all(
            not columns[key]["nullable"]
            for key in ("definition_id", "definition_revision", "definition_digest")
        )


def test_discovery_uses_only_published_revisions_and_excludes_private_bindings():
    from services.playbook_discovery import discover_playbooks

    result = discover_playbooks(
        load_action_registry(None), "How will I pay for dinner?"
    )
    assert result["retrieval_mode"] == "FULL_PUBLISHED_CATALOG"
    assert len(result["playbooks"]) == 3
    assert all(
        p["revision"] == 2 and p["eligibility"] == "NOT_CHECKED"
        for p in result["playbooks"]
    )
    assert "card_token" not in json.dumps(result)
    assert "authorization_policy" not in json.dumps(result)
    for candidate in result["playbooks"]:
        spec = load_action_registry(None).resolve(
            candidate["playbook_id"], candidate["revision"], candidate["digest"]
        )
        assert spec.handler.discovery_view()["purpose"] == candidate["purpose"]


def test_fourth_definition_is_discoverable_without_tool_or_engine_changes():
    from services.playbook_discovery import discover_playbooks

    docs = documents()
    fourth = deepcopy(
        next(d for d in docs if d["id"] == "card-reissue" and d["revision"] == 2)
    )
    fourth.update(id="new-replacement", action_type="NEW_REPLACEMENT")
    result = discover_playbooks(
        load_action_registry(None, [*docs, fourth]), "Replace my card"
    )
    assert len(result["playbooks"]) == 4
    assert next(
        p for p in result["playbooks"] if p["playbook_id"] == "new-replacement"
    )["input_schema"]["required"] == ["reason"]


@pytest.mark.parametrize(
    "field,value", [("purpose", ""), ("examples", []), ("prerequisites", "text")]
)
def test_discovery_metadata_is_validated_with_executable_definition(field, value):
    d = next(d for d in documents() if d["revision"] == 2)
    d["discovery"][field] = value
    with pytest.raises(ValueError, match="Discovery"):
        load_action_registry(None, [d])


def test_repository_publication_rejects_executable_without_discovery(
    tmp_path, monkeypatch
):
    first = next(d for d in documents() if d["revision"] == 1)
    (tmp_path / "incomplete.json").write_text(json.dumps(first))
    monkeypatch.setattr("services.proposal_definitions.CATALOG_PATH", tmp_path)
    with pytest.raises(ValueError, match="requires discovery metadata"):
        load_action_registry(None)
