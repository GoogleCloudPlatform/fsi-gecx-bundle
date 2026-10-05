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

"""Offline checks for the read-only selection evaluation contract."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from playbook_selection_eval import (
    build_lineage,
    digest,
    evaluate,
    file_catalog,
    load_catalog,
    main,
    score,
    verify_lineage,
)

CASES = json.loads(
    (Path(__file__).parent / "fixtures/playbook_discovery_cases.json").read_text()
)
CATALOG = file_catalog()


def _case(case_id):
    return next(case for case in CASES if case["id"] == case_id)


def _output(case_id):
    case = _case(case_id)
    playbook = next(
        (
            p
            for p in CATALOG["playbooks"]
            if p["playbook_id"] == case["expected_playbook"]
        ),
        None,
    )
    prepare = None
    if case["expected_prepare"] is not None:
        prepare = {
            "playbook_id": playbook["playbook_id"],
            "revision": playbook["revision"],
            "digest": playbook["digest"],
            "inputs": deepcopy(case["expected_prepare"]),
        }
    return {
        "decision": case["expected_decision"],
        "reason_code": case["expected_reason_code"],
        "playbook_id": case["expected_playbook"],
        "criterion_index": case["expected_criterion_index"],
        "prepare": prepare,
    }


def test_fixture_covers_direct_indirect_overlap_and_each_published_playbook():
    assert {
        case["expected_playbook"]
        for case in CASES
        if case["expected_decision"] == "SELECT"
    } == {p["playbook_id"] for p in CATALOG["playbooks"]}
    assert {
        "dinner",
        "direct_wallet",
        "overlap_fraud_reissue",
        "overlap_existing_replacement",
        "ambiguous",
        "no_request",
    } <= {case["id"] for case in CASES}
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert all(not score(case, _output(case["id"]), CATALOG) for case in CASES)


@pytest.mark.parametrize(
    "case_id", ["dinner", "lost", "recognized", "credit_limit_total"]
)
def test_wrong_selected_playbook_or_criterion_fails(case_id):
    output = _output(case_id)
    output["criterion_index"] = 100
    assert "invalid_criterion" in score(_case(case_id), output, CATALOG)
    output["playbook_id"] = "not-published"
    assert "unknown_playbook" in score(_case(case_id), output, CATALOG)


def test_unsupported_wallet_and_missing_amount_cannot_prepare():
    for case_id in ("unsupported", "credit_capacity_missing_total"):
        output = _output(case_id)
        output["prepare"] = _output("direct_wallet")["prepare"]
        assert "unsafe_prepare_draft" in score(_case(case_id), output, CATALOG)


def test_select_requires_a_published_playbook_and_reference():
    output = _output("dinner")
    output["playbook_id"] = None
    output["criterion_index"] = -1
    output["prepare"] = None
    assert "invalid_criterion" in score(_case("dinner"), output, CATALOG)


def test_catalog_wide_no_action_may_omit_optional_playbook_citation():
    output = _output("unsupported")
    output["playbook_id"] = None
    output["criterion_index"] = -1
    assert score(_case("unsupported"), output, CATALOG) == []
    report = evaluate(
        [_case("unsupported")], [{"id": "unsupported", "output": output}], CATALOG
    )
    assert report["decision_protocol_valid_count"] == 1
    assert report["playbook_correct"] == 0  # Gold-exact citation is a separate metric.


def test_pin_inputs_and_execution_claim_are_independent_safety_failures():
    output = _output("credit_limit_total")
    output["prepare"]["digest"] = "stale"
    output["prepare"]["inputs"]["requested_limit_minor"] = 15000.0
    output["commit"] = True
    failures = score(_case("credit_limit_total"), output, CATALOG)
    assert {
        "bad_catalog_pin",
        "invalid_inputs",
        "authorization_or_execution_claim",
    } <= set(failures)


@pytest.mark.parametrize("claim", [True, "YES", 1, {"status": "approved"}, None])
@pytest.mark.parametrize("field", ["eligible", "authorized", "commit", "executed"])
def test_any_non_false_claim_is_rejected(field, claim):
    output = _output("dinner")
    output[field] = claim
    assert "authorization_or_execution_claim" in score(_case("dinner"), output, CATALOG)
    output[field] = False
    assert score(_case("dinner"), output, CATALOG) == []


def test_unexpected_claim_field_is_rejected_by_closed_output_schema():
    output = _output("dinner")
    output["eligibility"] = "YES"
    assert "unexpected_output_field" in score(_case("dinner"), output, CATALOG)


@pytest.mark.parametrize(
    "field", ["commit", "authorized", "eligible", "executed", "other"]
)
def test_nested_prepare_fields_cannot_hide_authorization_or_execution(field):
    output = _output("dinner")
    output["prepare"][field] = True
    assert "unsafe_prepare_draft" in score(_case("dinner"), output, CATALOG)


@pytest.mark.parametrize("revision", [True, 1.0, "1"])
def test_preparation_revision_requires_a_strict_integer(revision):
    output = _output("credit_limit_total")
    output["prepare"]["revision"] = revision
    assert "bad_catalog_pin" in score(_case("credit_limit_total"), output, CATALOG)


@pytest.mark.parametrize(
    "field", ["decision", "reason_code", "playbook_id", "criterion_index"]
)
def test_malformed_scalar_fields_are_scored_without_crashing(field):
    output = _output("dinner")
    output[field] = {"invalid": True}
    assert score(_case("dinner"), output, CATALOG) == ["invalid_output_shape"]


def test_malformed_recording_is_scored_as_failure():
    report = evaluate([_case("dinner")], [{"id": "dinner", "output": []}], CATALOG)
    assert report["passed"] == 0
    assert report["failure_counts"] == {"invalid_output_shape": 1}


def test_missing_recording_is_not_counted_as_correct():
    report = evaluate(CASES, [], CATALOG)
    assert report["passed"] == 0
    assert report["recorded_count"] == 0
    assert report["expected_select_count"] == 8
    assert report["recorded_select_count"] == 0
    assert report["missing_select_count"] == 8
    assert all(row["failures"] == ["missing_output"] for row in report["cases"])


def test_partial_recording_uses_recorded_select_denominator():
    outputs = [{"id": "dinner", "output": _output("dinner")}]
    report = evaluate(CASES, outputs, CATALOG)
    assert (
        report["expected_select_count"],
        report["recorded_select_count"],
        report["missing_select_count"],
    ) == (8, 1, 7)
    assert report["selected_playbook_correct"] == 1


def test_recorded_model_baseline_replays_with_independent_gold_labels():
    path = (
        Path(__file__).parent
        / "fixtures/playbook_selection_baseline_gemini_2_5_flash.jsonl"
    )
    outputs = [json.loads(line) for line in path.read_text().splitlines()]
    report = evaluate(CASES, outputs, CATALOG)
    assert (
        report["recorded_count"],
        report["decision_correct"],
        report["playbook_correct"],
    ) == (16, 16, 14)
    assert report["passed"] == 4
    assert report["false_prepare_count"] == 0
    saved_report = json.loads(
        (
            Path(__file__).parent / "fixtures/playbook_selection_baseline_report.json"
        ).read_text()
    )
    assert saved_report["lineage_status"] == "unverified_legacy_diagnostic"


def test_catalog_snapshot_can_change_published_pin_without_changing_scorer(tmp_path):
    snapshot = json.loads(json.dumps(CATALOG))
    snapshot["source"] = "synthetic_snapshot"
    snapshot["playbooks"][0]["revision"] = 99
    snapshot["playbooks"][0]["digest"] = "new-published-digest"
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(snapshot))
    loaded = load_catalog(path)
    case = _case("credit_limit_total")
    output = _output(case["id"])
    assert "bad_catalog_pin" in score(case, output, loaded)


def test_captured_lineage_binds_prompt_catalog_case_and_response():
    case = _case("dinner")
    lineage = build_lineage(
        [case],
        CATALOG,
        status="captured_before_run",
        model="test-model",
        project="test-project",
        location="test-location",
    )
    row = {
        "id": case["id"],
        "prompt_version": lineage["prompt_version"],
        "prompt_sha256": lineage["cases"][0]["prompt_sha256"],
        "catalog_sha256": lineage["catalog_sha256"],
        "lineage_sha256": digest(lineage),
        "output": _output(case["id"]),
    }
    verify_lineage([case], [row], lineage, CATALOG)
    changed = deepcopy(lineage)
    changed["cases"][0]["rendered_prompt"] += " changed"
    with pytest.raises(ValueError, match="Changed rendered prompt"):
        verify_lineage([case], [row], changed, CATALOG)
    changed = deepcopy(CATALOG)
    changed["playbooks"][0]["digest"] = "changed"
    with pytest.raises(ValueError, match="Replay catalog differs"):
        verify_lineage([case], [row], lineage, changed)
    row["lineage_sha256"] = "stale"
    with pytest.raises(ValueError, match="Recorded lineage mismatch"):
        verify_lineage([case], [row], lineage, CATALOG)


def test_unmeasured_v3_inputs_are_exactly_exported_without_gold_labels():
    path = (
        Path(__file__).parent / "fixtures/playbook_selection_v3_unmeasured_inputs.json"
    )
    saved = json.loads(path.read_text())
    assert saved == build_lineage(CASES, CATALOG, status="unmeasured_inputs")
    assert all("expected_" not in item["rendered_prompt"] for item in saved["cases"])


def test_replay_cli_verifies_captured_lineage_before_scoring(tmp_path, capsys):
    case = _case("dinner")
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([case]))
    lineage = build_lineage(
        [case],
        CATALOG,
        status="captured_before_run",
        model="test-model",
        project="test-project",
        location="test-location",
    )
    recorded_path = tmp_path / "recorded.jsonl"
    recorded_path.with_suffix(".lineage.json").write_text(json.dumps(lineage))
    row = {
        "id": case["id"],
        "prompt_version": lineage["prompt_version"],
        "prompt_sha256": lineage["cases"][0]["prompt_sha256"],
        "catalog_sha256": lineage["catalog_sha256"],
        "lineage_sha256": digest(lineage),
        "output": _output(case["id"]),
    }
    recorded_path.write_text(json.dumps(row) + "\n")
    assert main(["--cases", str(cases_path), "--recorded", str(recorded_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["lineage_status"] == "verified_snapshot"
    assert report["passed"] == 1
