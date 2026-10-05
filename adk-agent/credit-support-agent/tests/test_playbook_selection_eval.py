"""Offline checks for the read-only selection evaluation contract."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from playbook_selection_eval import evaluate, file_catalog, load_catalog, score

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


def test_missing_recording_is_not_counted_as_correct():
    report = evaluate(CASES, [], CATALOG)
    assert report["passed"] == 0
    assert report["recorded_count"] == 0
    assert all(row["failures"] == ["missing_output"] for row in report["cases"])


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
