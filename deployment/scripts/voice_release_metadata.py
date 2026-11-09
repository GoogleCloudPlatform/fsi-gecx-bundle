#!/usr/bin/env python3
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

"""Build and validate immutable voice-release metadata.

The backend release controller owns rollout ordering. This helper owns the
source-derived identity of the pieces that are not container images: the CES
bundle, Knowledge Catalog seed, and database schema head.
"""

from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


CES_AGENT_RELATIVE_PATH = Path("gecx/Credit_Support_Voice_Agent")
CATALOG_RELATIVE_PATH = Path(
    "banking-service/resources/data/fraud_support_guidance.json"
)
ALEMBIC_VERSIONS_RELATIVE_PATH = Path("banking-service/alembic/versions")

IGNORED_PARTS = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
GENERATED_CES_FILES = {
    "environment.json",
    "toolsets/banking_service_mcp_toolset/banking_service_mcp_toolset.yaml",
}
RELEASE_COMPONENTS = (
    "banking-service",
    "banking-ui",
    "credit-support-agent",
    "data-generator",
)

# Manifest schema 4 adds the explicit no-rollback bootstrap shape. Schema 3 and
# unversioned legacy manifests remain readable but always carry a target.
MANIFEST_SCHEMA_VERSION = 4
SUPPORTED_SCHEMA_VERSIONS = {None, 3, MANIFEST_SCHEMA_VERSION}
# Schemas written before rollback targets existed; rollback fields are absent.
PRE_ROLLBACK_SCHEMA_VERSIONS = {None, 1, 2}
NO_ROLLBACK_SENTINEL = "NONE"
ROLLBACK_BOOTSTRAP_REASON = "no_valid_rollback_target"
# Artifact Registry cleanup keeps every version carrying this tag prefix
# (deployment/terraform/artifact_registry.tf).
RELEASE_RETENTION_TAG_PREFIX = "release-"
_IMMUTABLE_IMAGE = re.compile(r"@sha256:([0-9a-f]{64})$")
_FULL_COMMIT = re.compile(r"[0-9a-f]{40}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not IGNORED_PARTS.intersection(path.relative_to(root).parts)
        and path.suffix not in IGNORED_SUFFIXES
        and path.name != ".DS_Store"
        and path.relative_to(root).as_posix() not in GENERATED_CES_FILES
    )
    if not files:
        raise ValueError(f"no release files found under {root}")
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _literal_assignment(path: Path, name: str) -> Any:
    module = ast.parse(path.read_text(), filename=str(path))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"{path} does not define {name}")


def _alembic_heads(versions_dir: Path) -> list[str]:
    revisions: set[str] = set()
    referenced: set[str] = set()
    for path in sorted(versions_dir.glob("*.py")):
        revision = _literal_assignment(path, "revision")
        down_revision = _literal_assignment(path, "down_revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{path} has an invalid revision")
        revisions.add(revision)
        if isinstance(down_revision, str):
            referenced.add(down_revision)
        elif isinstance(down_revision, (tuple, list)):
            referenced.update(item for item in down_revision if item)
        elif down_revision is not None:
            raise ValueError(f"{path} has an invalid down_revision")
    heads = sorted(revisions - referenced)
    if not heads:
        raise ValueError(f"no Alembic head found in {versions_dir}")
    return heads


def _ces_model(app_yaml: Path) -> str:
    in_model_settings = False
    for line in app_yaml.read_text().splitlines():
        if line == "modelSettings:":
            in_model_settings = True
            continue
        if in_model_settings and line.startswith("  model:"):
            return line.split(":", 1)[1].strip()
        if in_model_settings and line and not line.startswith(" "):
            break
    raise ValueError(f"{app_yaml} does not define modelSettings.model")


def inspect_source(root: Path) -> dict[str, Any]:
    ces_root = root / CES_AGENT_RELATIVE_PATH
    catalog = root / CATALOG_RELATIVE_PATH
    versions = root / ALEMBIC_VERSIONS_RELATIVE_PATH
    return {
        "ces_config": {
            "path": CES_AGENT_RELATIVE_PATH.as_posix(),
            "sha256": _sha256_tree(ces_root),
            "model": _ces_model(ces_root / "app.yaml"),
        },
        "knowledge_catalog": {
            "path": CATALOG_RELATIVE_PATH.as_posix(),
            "sha256": _sha256_file(catalog),
        },
        "database": {"alembic_heads": _alembic_heads(versions)},
    }


def validate_manifest(
    manifest: dict[str, Any], expected: dict[str, Any], commit: str
) -> list[str]:
    errors: list[str] = []
    if manifest.get("commit") != commit:
        errors.append(
            f"commit mismatch: manifest={manifest.get('commit')!r}, source={commit!r}"
        )
    for component in RELEASE_COMPONENTS:
        image = manifest.get("images", {}).get(component)
        if not isinstance(image, str) or "@sha256:" not in image:
            errors.append(f"missing immutable image for {component}")

    comparisons = (
        (
            "CES config SHA",
            manifest.get("ces", {}).get("config_sha256"),
            expected["ces_config"]["sha256"],
        ),
        (
            "CES model",
            manifest.get("ces", {}).get("model"),
            expected["ces_config"]["model"],
        ),
        (
            "Knowledge Catalog SHA",
            manifest.get("knowledge_catalog", {}).get("sha256"),
            expected["knowledge_catalog"]["sha256"],
        ),
        (
            "Alembic heads",
            manifest.get("database", {}).get("alembic_heads"),
            expected["database"]["alembic_heads"],
        ),
    )
    for label, actual, wanted in comparisons:
        if actual != wanted:
            errors.append(f"{label} mismatch: manifest={actual!r}, source={wanted!r}")

    ces = manifest.get("ces", {})
    for field in ("app", "version", "deployment"):
        if not isinstance(ces.get(field), str) or not ces[field]:
            errors.append(f"missing CES {field}")
    errors.extend(_validate_rollback_fields(manifest))
    return errors


def _is_explicit_rollback_bootstrap(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"reason", "acknowledged"}
        and value["reason"] == ROLLBACK_BOOTSTRAP_REASON
        and value["acknowledged"] is True
    )


def _validate_rollback_fields(manifest: dict[str, Any]) -> list[str]:
    """Check that a manifest names a rollback target or an explicit bootstrap.

    A manifest either records a coherent environment-local rollback target and
    no bootstrap, or (schema 4 only) records ``rollback_target: null`` together
    with the exact acknowledged bootstrap block. Every other shape fails.
    """
    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return [f"unsupported manifest schema_version {schema_version!r}"]
    rollback_target = manifest.get("rollback_target")
    bootstrap = manifest.get("rollback_bootstrap")
    if rollback_target is None:
        if schema_version != MANIFEST_SCHEMA_VERSION:
            return ["missing coherent rollback target"]
        if not _is_explicit_rollback_bootstrap(bootstrap):
            return [
                "missing coherent rollback target and no explicit rollback "
                "bootstrap acknowledgement"
            ]
        return []
    if not isinstance(rollback_target, dict):
        return ["missing coherent rollback target"]
    if bootstrap is not None:
        return ["manifest records both a rollback target and a rollback bootstrap"]
    return _validate_release_identity(
        rollback_target,
        expected_environment=str(manifest.get("environment") or ""),
        label="rollback target",
    )


def _validate_release_identity(
    release: dict[str, Any], *, expected_environment: str, label: str
) -> list[str]:
    errors: list[str] = []
    commit = release.get("commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        errors.append(f"{label} has an invalid full commit")
    if release.get("environment") != expected_environment:
        errors.append(
            f"{label} environment mismatch: "
            f"manifest={release.get('environment')!r}, "
            f"expected={expected_environment!r}"
        )
    for component in RELEASE_COMPONENTS:
        image = release.get("images", {}).get(component)
        if not isinstance(image, str) or not re.search(
            r"@sha256:[0-9a-f]{64}$", image
        ):
            errors.append(f"{label} missing immutable image for {component}")
    ces = release.get("ces", {})
    for field in ("app", "version", "deployment", "config_sha256", "model"):
        if not isinstance(ces.get(field), str) or not ces[field]:
            errors.append(f"{label} missing CES {field}")
    heads = release.get("database", {}).get("alembic_heads")
    if not isinstance(heads, list) or len(heads) != 1 or not heads[0]:
        errors.append(f"{label} must contain exactly one Alembic head")
    catalog_sha = release.get("knowledge_catalog", {}).get("sha256")
    if not isinstance(catalog_sha, str) or not re.fullmatch(
        r"[0-9a-f]{64}", catalog_sha
    ):
        errors.append(f"{label} has an invalid Knowledge Catalog SHA")
    return errors


def build_rollback_target(
    manifest: dict[str, Any], *, environment: str, manifest_uri: str, sha256: str
) -> tuple[dict[str, Any], list[str]]:
    errors = _validate_release_identity(
        manifest,
        expected_environment=environment,
        label="rollback manifest",
    )
    if manifest.get("status") not in {"qualified", "promoted"}:
        errors.append("rollback manifest is not a successful release")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or not validation or not all(
        value is True for value in validation.values()
    ):
        errors.append("rollback manifest does not contain successful validation")
    # Manifests written before rollback targets existed (unversioned, schema 1
    # and schema 2) carry no rollback fields and remain usable anchors exactly
    # as before. Any other manifest, or a pre-rollback manifest that carries a
    # rollback key, must have a coherent rollback block. This rejects
    # malformed or downgraded shapes (for example a v3 manifest with a null
    # target, or a v1/v2/unversioned manifest with rollback_target: null or a
    # rollback_bootstrap key). It is a consistency check, not forgery
    # protection: bucket IAM and the operator-supplied URI are the trust anchor.
    if (
        manifest.get("schema_version") not in PRE_ROLLBACK_SCHEMA_VERSIONS
        or "rollback_target" in manifest
        or "rollback_bootstrap" in manifest
    ):
        errors.extend(
            f"rollback manifest: {error}"
            for error in _validate_rollback_fields(manifest)
        )
    target = {
        "manifest_uri": manifest_uri,
        "manifest_sha256": sha256,
        "commit": manifest.get("commit"),
        "environment": manifest.get("environment"),
        "images": manifest.get("images"),
        "ces": manifest.get("ces"),
        "knowledge_catalog": manifest.get("knowledge_catalog"),
        "database": manifest.get("database"),
        "completed_at": manifest.get("completed_at"),
    }
    return target, errors


def build_rollback_plan(
    *,
    manifest_uri: str,
    allow_no_rollback_target: str,
    manifest_bytes: bytes | None,
    environment: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Decide the rollback fields of the next manifest.

    Returns ``{"rollback_target": ..., "rollback_bootstrap": ...}``. Bootstrap
    (no rollback target) happens only when the operator passes both the
    ``NONE`` sentinel URI and ``allow_no_rollback_target == "true"``. An empty
    or missing flag means false. Any mismatch fails closed.
    """
    if allow_no_rollback_target not in {"true", "false", ""}:
        return None, [
            "ALLOW_NO_ROLLBACK_TARGET must be 'true' or 'false', got "
            f"{allow_no_rollback_target!r}"
        ]
    allowed = allow_no_rollback_target == "true"
    if manifest_uri == NO_ROLLBACK_SENTINEL:
        if not allowed:
            return None, [
                f"ROLLBACK_MANIFEST_URI={NO_ROLLBACK_SENTINEL} requires "
                "ALLOW_NO_ROLLBACK_TARGET=true"
            ]
        return {
            "rollback_target": None,
            "rollback_bootstrap": {
                "reason": ROLLBACK_BOOTSTRAP_REASON,
                "acknowledged": True,
            },
        }, []
    if allowed:
        return None, [
            "ALLOW_NO_ROLLBACK_TARGET=true is only valid with "
            f"ROLLBACK_MANIFEST_URI={NO_ROLLBACK_SENTINEL}"
        ]
    if manifest_bytes is None:
        return None, ["a rollback manifest is required"]
    target, errors = build_rollback_target(
        json.loads(manifest_bytes),
        environment=environment,
        manifest_uri=manifest_uri,
        sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    if errors:
        return None, errors
    return {"rollback_target": target, "rollback_bootstrap": None}, []


def release_retention_tag(commit: str, image: str) -> str:
    """Return the cleanup-exempt tag for a release-pinned image digest.

    The tag is derived from both the commit and the digest, so it is stable
    for a given pin and a rebuilt digest for the same commit gets a distinct
    tag instead of moving the old one.
    """
    if not _FULL_COMMIT.fullmatch(commit):
        raise ValueError(f"invalid full commit {commit!r}")
    match = _IMMUTABLE_IMAGE.search(image)
    if not match:
        raise ValueError(f"image is not pinned by digest: {image!r}")
    return f"{RELEASE_RETENTION_TAG_PREFIX}{commit[:12]}-{match.group(1)[:12]}"


def guidance_freshness_errors(root: Path, today: date) -> list[str]:
    """Fail-early mirror of KnowledgeCatalogService.validate_local_guidance.

    The banking-db-reset and knowledge-catalog-sync jobs run late in the
    release; checking the same freshness rule here stops a stale bundle before
    terraform apply or the demo reset. Keep this in step with
    banking-service/services/knowledge_catalog.py (_guidance_freshness).
    """
    try:
        document = json.loads((root / CATALOG_RELATIVE_PATH).read_text())
    except (OSError, ValueError) as error:
        return [f"cannot read fraud support guidance: {error}"]
    topics = document.get("topics") if isinstance(document, dict) else None
    if not isinstance(topics, list) or not topics:
        return ["fraud support guidance has no topics"]
    try:
        max_age_days = int(document.get("max_age_days", 90))
    except (TypeError, ValueError):
        return ["fraud support guidance has invalid max_age_days"]
    errors: list[str] = []
    reviewed: list[date] = []
    for topic in topics:
        topic_id = topic.get("topic_id", "<unknown>") if isinstance(topic, dict) else "<unknown>"
        try:
            reviewed.append(date.fromisoformat(str(topic.get("last_reviewed"))))
        except (AttributeError, ValueError):
            errors.append(f"{topic_id}: invalid last_reviewed")
    if reviewed:
        oldest = min(reviewed)
        age_days = (today - oldest).days
        if age_days > max_age_days:
            errors.append(
                f"guidance is stale; oldest review is {oldest.isoformat()} "
                f"({age_days} days, max {max_age_days})"
            )
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--root", type=Path, default=Path.cwd())

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--root", type=Path, default=Path.cwd())
    validate_parser.add_argument("--manifest", type=Path, required=True)
    validate_parser.add_argument("--commit", required=True)

    rollback_parser = subparsers.add_parser("rollback-target")
    rollback_parser.add_argument("--manifest", type=Path)
    rollback_parser.add_argument("--environment", required=True)
    rollback_parser.add_argument("--manifest-uri", required=True)
    rollback_parser.add_argument("--allow-no-rollback-target", default="false")

    guidance_parser = subparsers.add_parser("check-guidance")
    guidance_parser.add_argument("--root", type=Path, default=Path.cwd())

    tag_parser = subparsers.add_parser("release-tag")
    tag_parser.add_argument("--commit", required=True)
    tag_parser.add_argument("--image", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "rollback-target":
        plan, errors = build_rollback_plan(
            manifest_uri=args.manifest_uri,
            allow_no_rollback_target=args.allow_no_rollback_target,
            manifest_bytes=args.manifest.read_bytes() if args.manifest else None,
            environment=args.environment,
        )
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(json.dumps(plan, sort_keys=True))
        return 0

    if args.command == "check-guidance":
        errors = guidance_freshness_errors(
            args.root.resolve(), datetime.now(timezone.utc).date()
        )
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("Fraud support guidance is fresh.")
        return 0

    if args.command == "release-tag":
        try:
            print(release_retention_tag(args.commit, args.image))
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        return 0

    root = args.root.resolve()
    expected = inspect_source(root)
    if args.command == "inspect":
        print(json.dumps(expected, sort_keys=True))
        return 0

    manifest = json.loads(args.manifest.read_bytes())
    errors = validate_manifest(manifest, expected, args.commit)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Voice release manifest matches the checked-out source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
