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


def score(case: dict, output: dict, catalog: dict) -> list[str]:
    failures = []
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
    if (
        output.get("commit") is not None
        or output.get("authorized") is True
        or output.get("eligible") is True
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
    selected_count = 0
    for case in cases:
        response = by_id.get(case["id"])
        output = response.get("output", {}) if response else {}
        failures = (
            ["missing_output"] if response is None else score(case, output, catalog)
        )
        if response:
            decision_correct += output.get("decision") == case["expected_decision"]
            playbook_correct += output.get("playbook_id") == case.get(
                "expected_playbook"
            )
            if case["expected_decision"] == "SELECT":
                selected_count += 1
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
        "selected_count": selected_count,
        "selected_playbook_correct": selected_playbook_correct,
        "reason_correct": reason_correct,
        "criterion_correct": criterion_correct,
        "false_prepare_count": false_prepare,
        "failure_counts": dict(sorted(failures.items())),
        "decision_confusion": {
            f"{expected}->{observed}": count
            for (expected, observed), count in sorted(counts.items())
        },
        "cases": results,
    }


def run_model(
    cases: list[dict],
    catalog: dict,
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
    for case in cases:
        for attempt in range(3):
            if requests >= max_requests:
                return outputs, requests
            try:
                requests += 1
                response = client.models.generate_content(
                    model=model,
                    contents=prompt(case, catalog),
                    config=types.GenerateContentConfig(
                        temperature=0, response_mime_type="application/json"
                    ),
                )
                outputs.append(
                    {
                        "id": case["id"],
                        "prompt_version": PROMPT_VERSION,
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
    parser.add_argument("--live-model")
    parser.add_argument("--project")
    parser.add_argument("--location")
    parser.add_argument("--write-recorded", type=Path)
    parser.add_argument("--max-model-requests", type=int, default=20)
    args = parser.parse_args(argv)
    if bool(args.recorded) == bool(args.live_model):
        parser.error("Choose exactly one of --recorded or --live-model")
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
    catalog = load_catalog(args.catalog_snapshot)
    if args.live_model:
        outputs, request_count = run_model(
            cases,
            catalog,
            args.live_model,
            args.project,
            args.location,
            args.max_model_requests,
        )
        args.write_recorded.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in outputs) + "\n"
        )
    else:
        outputs = [
            json.loads(line)
            for line in args.recorded.read_text().splitlines()
            if line.strip()
        ]
    report = evaluate(cases, outputs, catalog)
    report.update(
        {
            "model": args.live_model if args.live_model else args.recorded_model,
            "scope": "isolated_structured_selection",
            "prompt_versions": sorted(
                {row.get("prompt_version", "unknown") for row in outputs}, key=str
            ),
        }
    )
    if args.live_model:
        report["model_request_count"] = request_count
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] == report["case_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
