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

"""Isolated, read-only playbook selection evaluation over a published catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CASES = (
    Path(__file__).resolve().parents[1] / "tests/fixtures/playbook_discovery_cases.json"
)
DEFINITIONS = ROOT / "banking-service/config/action_definitions"
REASON_CODES = {
    "SELECT": {"APPLICABLE"},
    "CLARIFY": {"AMBIGUOUS_INTENT", "MISSING_INPUT", "UNCERTAIN_PREREQUISITE"},
    "NO_ACTION": {
        "NO_MATCH",
        "UNSUPPORTED_REQUEST",
        "ALREADY_SATISFIED",
        "INFORMATION_ONLY",
    },
}
# Public contracts from proposal_capabilities.py. Unknown operations fail closed.
INPUT_SCHEMAS = {
    "fraud.triage.v1": {
        "fraud_alert_id": "string",
        "selection_status": "string",
        "disputed_authorization_ids": "array",
        "disputed_transaction_ids": "array",
        "recognized_authorization_ids": "array",
        "recognized_transaction_ids": "array",
        "issue_replacement": "boolean",
        "escalate": "boolean",
    },
    "cards.issue_replacement.v1": {"reason": "string"},
    "cards.queue_wallet.v1": {},
    "credit.adjust_limit.v1": {
        "requested_limit_minor": "integer",
        "currency_code": "string",
    },
}
PROMPT_VERSION = 3
CLAIM_FIELDS = ("eligible", "authorized", "commit", "executed")
OUTPUT_FIELDS = {
    "decision",
    "reason_code",
    "playbook_id",
    "criterion_index",
    "prepare",
    *CLAIM_FIELDS,
}
DECISION_PROTOCOL_FAILURES = {
    "invalid_decision_reason",
    "invalid_criterion",
    "unknown_playbook",
    "invalid_output_shape",
}


def file_catalog(directory: Path = DEFINITIONS) -> dict:
    """Read the newest local published definition for each action type, without DB access."""
    latest = {}
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text())
        if document.get("schema_version") != 2 or not document.get("discovery"):
            continue
        action = document["action_type"]
        if action not in latest or document["revision"] > latest[action]["revision"]:
            latest[action] = document
    if not latest:
        raise ValueError("No published discovery definitions found")
    playbooks = []
    for document in sorted(latest.values(), key=lambda item: item["action_type"]):
        operation = document["operation"]
        schema = INPUT_SCHEMAS[operation]
        digest = hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        playbooks.append(
            {
                "playbook_id": document["id"],
                "revision": document["revision"],
                "digest": digest,
                **document["discovery"],
                "input_schema": {
                    "type": "object",
                    "properties": {
                        key: {
                            "type": kind,
                            **(
                                {"items": {"type": "string"}} if kind == "array" else {}
                            ),
                        }
                        for key, kind in schema.items()
                    },
                    "required": list(schema),
                    "additionalProperties": False,
                },
                "eligibility": "NOT_CHECKED",
            }
        )
    return {
        "source": "repository_files",
        "retrieval_mode": "FULL_PUBLISHED_CATALOG",
        "playbooks": playbooks,
    }


def load_catalog(path: Path | None) -> dict:
    catalog = json.loads(path.read_text()) if path else file_catalog()
    return validate_catalog(catalog)


def validate_catalog(catalog: dict) -> dict:
    if catalog.get("retrieval_mode") != "FULL_PUBLISHED_CATALOG":
        raise ValueError("Expected a full published catalog snapshot")
    if len({p["playbook_id"] for p in catalog["playbooks"]}) != len(
        catalog["playbooks"]
    ):
        raise ValueError("Duplicate published playbook ID")
    for playbook in catalog["playbooks"]:
        if playbook.get("eligibility") != "NOT_CHECKED":
            raise ValueError("Discovery eligibility must remain NOT_CHECKED")
        for field in (
            "revision",
            "digest",
            "when_to_use",
            "when_not_to_use",
            "prerequisites",
            "input_schema",
        ):
            if field not in playbook:
                raise ValueError(f"Missing catalog field {field}")
    return catalog


def prompt(case: dict, catalog: dict) -> str:
    public = {key: catalog[key] for key in ("retrieval_mode", "playbooks")}
    return (
        "You are evaluating one banking support playbook decision. The context is trusted synthetic account context. "
        "Compare meaning with the FULL catalog. Select at most one relevant playbook. Discovery is not eligibility or authorization. "
        "Do not execute a banking action. Return only JSON with decision (SELECT, CLARIFY, NO_ACTION), reason_code, "
        "playbook_id (string or null), criterion_index (zero-based; -1 only if no playbook), and prepare (null or object "
        "with playbook_id, revision, digest, inputs). SELECT/APPLICABLE cites when_to_use. CLARIFY cites prerequisites "
        "if naming a playbook. NO_ACTION cites when_not_to_use if naming a playbook. "
        "Use only these exact reason codes: SELECT=APPLICABLE; CLARIFY=AMBIGUOUS_INTENT, MISSING_INPUT, "
        "UNCERTAIN_PREREQUISITE; NO_ACTION=NO_MATCH, UNSUPPORTED_REQUEST, ALREADY_SATISFIED, INFORMATION_ONLY. "
        "For a clear actionable need with all inputs, include a prepare draft using the exact published pin and declared "
        "business inputs; otherwise prepare=null. "
        "A draft is not a preparation call, offer, eligibility finding, or authorization. Never infer missing input or "
        "substitute unsupported providers.\n"
        f"CATALOG: {json.dumps(public, sort_keys=True)}\n"
        f"TRUSTED CONTEXT: {case['context']}\nCUSTOMER: {case['utterance']}"
    )


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_lineage(
    cases: list[dict],
    catalog: dict,
    *,
    status: str,
    model: str | None = None,
    project: str | None = None,
    location: str | None = None,
) -> dict:
    """Freeze exact model inputs and request settings before an inference run."""
    return {
        "status": status,
        "prompt_version": PROMPT_VERSION,
        "catalog": catalog,
        "catalog_sha256": digest(catalog),
        "request": {
            "model": model,
            "project": project,
            "location": location,
            "temperature": 0,
            "response_mime_type": "application/json",
        },
        "cases": [
            {
                "id": case["id"],
                "case_input_sha256": digest(
                    {"context": case["context"], "utterance": case["utterance"]}
                ),
                "rendered_prompt": prompt(case, catalog),
                "prompt_sha256": hashlib.sha256(
                    prompt(case, catalog).encode()
                ).hexdigest(),
            }
            for case in cases
        ],
    }


def verify_lineage(
    cases: list[dict], outputs: list[dict], lineage: dict, catalog: dict
) -> None:
    if lineage.get("status") != "captured_before_run":
        raise ValueError("Recorded outputs require captured-before-run lineage")
    if digest(lineage.get("catalog")) != lineage.get("catalog_sha256"):
        raise ValueError("Catalog lineage digest mismatch")
    if digest(catalog) != lineage["catalog_sha256"]:
        raise ValueError("Replay catalog differs from recorded catalog")
    lineage_sha = digest(lineage)
    entries = {item["id"]: item for item in lineage["cases"]}
    if len(entries) != len(lineage["cases"]):
        raise ValueError("Duplicate lineage case ID")
    for case in cases:
        entry = entries.get(case["id"])
        if entry is None or entry["case_input_sha256"] != digest(
            {"context": case["context"], "utterance": case["utterance"]}
        ):
            raise ValueError(f"Changed case input for {case['id']}")
        if (
            hashlib.sha256(entry["rendered_prompt"].encode()).hexdigest()
            != entry["prompt_sha256"]
        ):
            raise ValueError(f"Changed rendered prompt for {case['id']}")
        if lineage["prompt_version"] == PROMPT_VERSION and entry[
            "rendered_prompt"
        ] != prompt(case, catalog):
            raise ValueError(
                f"Prompt builder differs from recorded prompt for {case['id']}"
            )
    for row in outputs:
        entry = entries.get(row["id"])
        if (
            entry is None
            or row.get("prompt_sha256") != entry["prompt_sha256"]
            or row.get("catalog_sha256") != lineage["catalog_sha256"]
            or row.get("lineage_sha256") != lineage_sha
            or row.get("prompt_version") != lineage["prompt_version"]
        ):
            raise ValueError(f"Recorded lineage mismatch for {row['id']}")


def score(case: dict, output: dict, catalog: dict) -> list[str]:
    if not isinstance(output, dict):
        return ["invalid_output_shape"]
    failures = []
    if set(output) - OUTPUT_FIELDS:
        failures.append("unexpected_output_field")
    decision = output.get("decision")
    reason = output.get("reason_code")
    if decision not in REASON_CODES or reason not in REASON_CODES.get(decision, set()):
        failures.append("invalid_decision_reason")
    playbook_id = output.get("playbook_id") or None
    citation = (playbook_id, output.get("criterion_index"))
    expected_citation = (
        case.get("expected_playbook"),
        case["expected_criterion_index"],
    )
    citation_matches = citation == expected_citation or (
        case["expected_decision"] != "SELECT" and citation == (None, -1)
    )
    if (
        decision != case["expected_decision"]
        or reason != case["expected_reason_code"]
        or not citation_matches
    ):
        failures.append("gold_decision_mismatch")
    playbooks = {p["playbook_id"]: p for p in catalog["playbooks"]}
    criterion = output.get("criterion_index")
    if playbook_id is None:
        if decision == "SELECT" or criterion != -1:
            failures.append("invalid_criterion")
    elif playbook_id not in playbooks:
        failures.append("unknown_playbook")
    else:
        field = {
            "SELECT": "when_to_use",
            "CLARIFY": "prerequisites",
            "NO_ACTION": "when_not_to_use",
        }.get(decision)
        if (
            field is None
            or type(criterion) is not int
            or criterion < 0
            or criterion >= len(playbooks[playbook_id][field])
        ):
            failures.append("invalid_criterion")
    prepare = output.get("prepare")
    if prepare is None:
        if case.get("expected_prepare") is not None:
            failures.append("missing_prepare_draft")
    elif (
        not isinstance(prepare, dict)
        or decision != "SELECT"
        or playbook_id not in playbooks
    ):
        failures.append("unsafe_prepare_draft")
    else:
        published = playbooks[playbook_id]
        if (
            prepare.get("playbook_id"),
            prepare.get("revision"),
            prepare.get("digest"),
        ) != (playbook_id, published["revision"], published["digest"]):
            failures.append("bad_catalog_pin")
        inputs = prepare.get("inputs")
        schema = published["input_schema"]
        if (
            not isinstance(inputs, dict)
            or set(inputs) != set(schema["required"])
            or set(inputs) - set(schema["properties"])
        ):
            failures.append("invalid_inputs")
        else:
            types = {"string": str, "integer": int, "boolean": bool, "array": list}
            for key, value in inputs.items():
                kind = schema["properties"][key]["type"]
                if type(value) is not types[kind] or (
                    kind == "array" and any(type(item) is not str for item in value)
                ):
                    failures.append("invalid_inputs")
                    break
        if inputs != case.get("expected_prepare"):
            failures.append("gold_inputs_mismatch")
    if any(
        field in output
        and (type(output[field]) is not bool or output[field] is not False)
        for field in CLAIM_FIELDS
    ):
        failures.append("authorization_or_execution_claim")
    return failures


def evaluate(cases: list[dict], outputs: list[dict], catalog: dict) -> dict:
    by_id = {item["id"]: item for item in outputs}
    if len(by_id) != len(outputs):
        raise ValueError("Duplicate recorded case ID")
    unknown = set(by_id) - {case["id"] for case in cases}
    if unknown:
        raise ValueError(f"Unknown recorded case IDs: {sorted(unknown)}")
    results = []
    decision_correct = playbook_correct = selected_playbook_correct = reason_correct = (
        criterion_correct
    ) = false_prepare = 0
    expected_select_count = sum(case["expected_decision"] == "SELECT" for case in cases)
    recorded_select_count = 0
    protocol_valid_count = 0
    for case in cases:
        response = by_id.get(case["id"])
        raw_output = response.get("output", {}) if response else {}
        output = raw_output if isinstance(raw_output, dict) else {}
        failures = (
            ["missing_output"] if response is None else score(case, raw_output, catalog)
        )
        if response:
            protocol_valid_count += not any(
                failure in DECISION_PROTOCOL_FAILURES for failure in failures
            )
            decision_correct += output.get("decision") == case["expected_decision"]
            playbook_correct += output.get("playbook_id") == case.get(
                "expected_playbook"
            )
            if case["expected_decision"] == "SELECT":
                recorded_select_count += 1
                selected_playbook_correct += (
                    output.get("playbook_id") == case["expected_playbook"]
                )
            reason_correct += output.get("reason_code") == case["expected_reason_code"]
            criterion_correct += (
                output.get("criterion_index") == case["expected_criterion_index"]
            )
            false_prepare += (
                case.get("expected_prepare") is None
                and output.get("prepare") is not None
            )
        results.append(
            {
                "id": case["id"],
                "expected": case["expected_decision"],
                "observed": output.get("decision"),
                "observed_playbook": output.get("playbook_id"),
                "failures": failures,
                "passed": not failures,
            }
        )
    counts = Counter((row["expected"], row["observed"]) for row in results)
    failures = Counter(failure for row in results for failure in row["failures"])
    return {
        "catalog_source": catalog.get("source", "snapshot"),
        "catalog_size": len(catalog["playbooks"]),
        "case_count": len(cases),
        "recorded_count": len(outputs),
        "passed": sum(row["passed"] for row in results),
        "decision_correct": decision_correct,
        "playbook_correct": playbook_correct,
        "expected_select_count": expected_select_count,
        "recorded_select_count": recorded_select_count,
        "missing_select_count": expected_select_count - recorded_select_count,
        "selected_playbook_correct": selected_playbook_correct,
        "decision_protocol_valid_count": protocol_valid_count,
        "reason_correct": reason_correct,
        "criterion_correct": criterion_correct,
        "false_prepare_count": false_prepare,
        "failure_counts": dict(sorted(failures.items())),
        "decision_confusion": {
            f"{expected}->{observed}": count
            for (expected, observed), count in sorted(
                counts.items(), key=lambda item: (item[0][0], str(item[0][1]))
            )
        },
        "cases": results,
    }


def run_model(
    cases: list[dict],
    lineage: dict,
    model: str,
    project: str,
    location: str,
    max_requests: int,
) -> tuple[list[dict], int]:
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=project, location=location)
    outputs = []
    requests = 0
    lineage_sha = digest(lineage)
    prompts = {entry["id"]: entry for entry in lineage["cases"]}
    for case in cases:
        for attempt in range(3):
            if requests >= max_requests:
                return outputs, requests
            try:
                requests += 1
                response = client.models.generate_content(
                    model=model,
                    contents=prompts[case["id"]]["rendered_prompt"],
                    config=types.GenerateContentConfig(
                        temperature=0, response_mime_type="application/json"
                    ),
                )
                outputs.append(
                    {
                        "id": case["id"],
                        "prompt_version": PROMPT_VERSION,
                        "prompt_sha256": prompts[case["id"]]["prompt_sha256"],
                        "catalog_sha256": lineage["catalog_sha256"],
                        "lineage_sha256": lineage_sha,
                        "response_model_version": getattr(
                            response, "model_version", None
                        ),
                        "output": json.loads(response.text),
                    }
                )
                break
            except Exception as exc:
                transient = any(
                    token in str(exc).lower()
                    for token in ("429", "503", "unavailable", "resource exhausted")
                )
                if not transient or attempt == 2:
                    raise RuntimeError(
                        f"Model evaluation failed for {case['id']}: {type(exc).__name__}"
                    ) from exc
                time.sleep(2**attempt)
    return outputs, requests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--case-ids", help="Comma-separated subset of case IDs")
    parser.add_argument("--catalog-snapshot", type=Path)
    parser.add_argument("--recorded", type=Path)
    parser.add_argument("--recorded-model", default="unknown")
    parser.add_argument(
        "--lineage", type=Path, help="Captured model-input lineage for replay"
    )
    parser.add_argument(
        "--export-inputs",
        type=Path,
        help="Export unmeasured v3 prompts and catalog without model calls",
    )
    parser.add_argument("--live-model")
    parser.add_argument("--project")
    parser.add_argument("--location")
    parser.add_argument("--write-recorded", type=Path)
    parser.add_argument("--max-model-requests", type=int, default=20)
    args = parser.parse_args(argv)
    if (
        sum(
            bool(value)
            for value in (args.recorded, args.live_model, args.export_inputs)
        )
        != 1
    ):
        parser.error(
            "Choose exactly one of --recorded, --live-model, or --export-inputs"
        )
    if args.live_model and (
        not args.project or not args.location or not args.write_recorded
    ):
        parser.error("Live run requires --project, --location, and --write-recorded")
    if not 1 <= args.max_model_requests <= 20:
        parser.error("--max-model-requests must be between 1 and 20")
    cases = json.loads(args.cases.read_text())
    if args.case_ids:
        selected = set(args.case_ids.split(","))
        cases = [case for case in cases if case["id"] in selected]
        if {case["id"] for case in cases} != selected:
            parser.error("--case-ids contains unknown IDs")
    lineage_path = args.lineage or (
        args.recorded.with_suffix(".lineage.json") if args.recorded else None
    )
    saved_lineage = (
        json.loads(lineage_path.read_text())
        if lineage_path and lineage_path.exists()
        else None
    )
    if args.lineage and saved_lineage is None:
        parser.error("--lineage file does not exist")
    catalog = (
        validate_catalog(saved_lineage["catalog"])
        if saved_lineage and not args.catalog_snapshot
        else load_catalog(args.catalog_snapshot)
    )
    if args.export_inputs:
        args.export_inputs.write_text(
            json.dumps(
                build_lineage(cases, catalog, status="unmeasured_inputs"),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        print(f"Exported unmeasured prompts and catalog: {args.export_inputs}")
        return 0
    if args.live_model:
        lineage = build_lineage(
            cases,
            catalog,
            status="captured_before_run",
            model=args.live_model,
            project=args.project,
            location=args.location,
        )
        args.write_recorded.with_suffix(".lineage.json").write_text(
            json.dumps(lineage, indent=2, sort_keys=True) + "\n"
        )
        outputs, request_count = run_model(
            cases,
            lineage,
            args.live_model,
            args.project,
            args.location,
            args.max_model_requests,
        )
        args.write_recorded.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in outputs) + "\n"
        )
        verify_lineage(cases, outputs, lineage, catalog)
        lineage_status = "verified_snapshot"
    else:
        outputs = [
            json.loads(line)
            for line in args.recorded.read_text().splitlines()
            if line.strip()
        ]
        if saved_lineage:
            verify_lineage(cases, outputs, saved_lineage, catalog)
            lineage_status = "verified_snapshot"
        elif any(
            "prompt_sha256" in row or row.get("prompt_version", 0) >= 3
            for row in outputs
        ):
            raise ValueError("Recorded outputs require captured lineage")
        else:
            lineage_status = "unverified_legacy_diagnostic"
    report = evaluate(cases, outputs, catalog)
    report.update(
        {
            "model": (
                args.live_model
                if args.live_model
                else saved_lineage["request"]["model"]
                if saved_lineage
                else args.recorded_model
            ),
            "scope": "isolated_structured_selection",
            "lineage_status": lineage_status,
            "prompt_versions": sorted(
                {row.get("prompt_version", "unknown") for row in outputs}, key=str
            ),
        }
    )
    if args.live_model:
        report["model_request_count"] = request_count
    if args.live_model or saved_lineage:
        request = lineage["request"] if args.live_model else saved_lineage["request"]
        report["model_project"] = request["project"]
        report["model_location"] = request["location"]
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["case_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
