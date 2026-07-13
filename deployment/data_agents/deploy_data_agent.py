#!/usr/bin/env python3
"""Validate and idempotently deploy a Gemini Data Analytics DataAgent."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"API request failed ({status}): {message}")
        self.status = status


JsonRequest = Callable[[str, str, str, Optional[dict[str, Any]]], dict[str, Any]]


def api_endpoint(location: str) -> str:
    if location == "global":
        return "https://geminidataanalytics.googleapis.com"
    if "-" in location:
        return f"https://geminidataanalytics-{location}.googleapis.com"
    return f"https://geminidataanalytics.{location}.rep.googleapis.com"


def load_spec(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as spec_file:
        spec = json.load(spec_file)

    required = {"agent_id", "location", "display_name", "description", "system_instruction", "data_sources"}
    missing = sorted(required - spec.keys())
    if missing:
        raise ValueError(f"Agent specification is missing required fields: {', '.join(missing)}")
    if not spec["data_sources"]:
        raise ValueError("Agent specification must contain at least one data source.")
    return spec


def expand_table_references(spec: dict[str, Any], project_id: str) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source in spec["data_sources"]:
        dataset_id = source.get("dataset_id")
        tables = source.get("tables", [])
        if not dataset_id or not tables:
            raise ValueError("Every data source requires dataset_id and a non-empty tables list.")
        for table_id in tables:
            key = (dataset_id, table_id)
            if key in seen:
                raise ValueError(f"Duplicate BigQuery source: {dataset_id}.{table_id}")
            seen.add(key)
            references.append(
                {"projectId": project_id, "datasetId": dataset_id, "tableId": table_id}
            )
    return references


def build_payload(spec: dict[str, Any], project_id: str) -> dict[str, Any]:
    table_references = expand_table_references(spec, project_id)
    options: dict[str, Any] = {"datasource": {}}
    if spec.get("bigquery_max_billed_bytes"):
        options["datasource"]["bigQueryMaxBilledBytes"] = str(spec["bigquery_max_billed_bytes"])

    context = {
        "systemInstruction": spec["system_instruction"],
        "datasourceReferences": {"bq": {"tableReferences": table_references}},
        "options": options,
    }
    fingerprint_source = {
        "agent_id": spec["agent_id"],
        "display_name": spec["display_name"],
        "description": spec["description"],
        "context": context,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    labels = {**spec.get("labels", {}), "spec-hash": fingerprint}

    return {
        "displayName": spec["display_name"],
        "description": spec["description"],
        "labels": labels,
        "dataAnalyticsAgent": {
            "stagingContext": context,
            "publishedContext": context,
        },
    }


def access_token() -> str:
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def request_json(
    url: str,
    token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        body = error.read().decode()
        try:
            message = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            message = body
        raise ApiError(error.code, message) from error


def validate_sources(
    project_id: str,
    references: list[dict[str, str]],
    token: str,
    requester: JsonRequest = request_json,
) -> None:
    missing: list[str] = []
    for reference in references:
        dataset_id = urllib.parse.quote(reference["datasetId"], safe="")
        table_id = urllib.parse.quote(reference["tableId"], safe="")
        url = (
            f"https://bigquery.googleapis.com/bigquery/v2/projects/{project_id}"
            f"/datasets/{dataset_id}/tables/{table_id}"
        )
        try:
            requester(url, token, "GET", None)
        except ApiError as error:
            if error.status == 404:
                missing.append(f"{reference['datasetId']}.{reference['tableId']}")
                continue
            raise
    if missing:
        raise RuntimeError("Missing BigQuery agent sources: " + ", ".join(missing))


def managed_projection(agent: dict[str, Any]) -> dict[str, Any]:
    contexts = agent.get("dataAnalyticsAgent", {})

    def project_context(context: dict[str, Any]) -> dict[str, Any]:
        references = (
            context.get("datasourceReferences", {}).get("bq", {}).get("tableReferences", [])
        )
        tables = sorted(
            (ref.get("projectId"), ref.get("datasetId"), ref.get("tableId"))
            for ref in references
        )
        max_bytes = context.get("options", {}).get("datasource", {}).get(
            "bigQueryMaxBilledBytes"
        )
        return {
            "systemInstruction": context.get("systemInstruction", ""),
            "tables": tables,
            "bigQueryMaxBilledBytes": None if max_bytes is None else str(max_bytes),
        }

    return {
        "displayName": agent.get("displayName", ""),
        "description": agent.get("description", ""),
        "labels": agent.get("labels", {}),
        "stagingContext": project_context(contexts.get("stagingContext", {})),
        "publishedContext": project_context(contexts.get("publishedContext", {})),
    }


def deploy(
    project_id: str,
    spec: dict[str, Any],
    token: str,
    check_only: bool = False,
    requester: JsonRequest = request_json,
) -> str:
    payload = build_payload(spec, project_id)
    location = spec["location"]
    agent_id = spec["agent_id"]
    base_url = api_endpoint(location)
    resource_name = f"projects/{project_id}/locations/{location}/dataAgents/{agent_id}"
    resource_url = f"{base_url}/v1/{resource_name}"

    validate_sources(project_id, expand_table_references(spec, project_id), token, requester)

    try:
        current = requester(resource_url, token, "GET", None)
    except ApiError as error:
        if error.status != 404:
            raise
        if check_only:
            raise RuntimeError(f"Managed DataAgent does not exist: {resource_name}") from error
        create_url = (
            f"{base_url}/v1/projects/{project_id}/locations/{location}/dataAgents:createSync?"
            + urllib.parse.urlencode({"data_agent_id": agent_id})
        )
        requester(create_url, token, "POST", payload)
        return "created"

    if managed_projection(current) == managed_projection(payload):
        return "current"
    if check_only:
        raise RuntimeError(f"Managed DataAgent configuration has drifted: {resource_name}")

    update_url = resource_url + ":updateSync?" + urllib.parse.urlencode(
        {"updateMask": "displayName,description,labels,dataAnalyticsAgent"}
    )
    requester(update_url, token, "PATCH", payload)
    return "updated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Target Google Cloud project ID")
    parser.add_argument("--spec", type=Path, required=True, help="Path to the agent JSON spec")
    parser.add_argument("--check", action="store_true", help="Fail instead of creating or updating")
    parser.add_argument(
        "--render",
        action="store_true",
        help="Render the environment-specific payload without calling Google Cloud APIs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        spec = load_spec(args.spec)
        if args.render:
            print(json.dumps(build_payload(spec, args.project), indent=2, sort_keys=True))
            return 0
        result = deploy(args.project, spec, access_token(), check_only=args.check)
        print(
            f"DataAgent {spec['agent_id']} is {result} in {args.project} ({spec['location']})."
        )
        return 0
    except (ApiError, OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as error:
        print(f"DataAgent deployment failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
