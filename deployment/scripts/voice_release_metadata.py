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
import hashlib
import json
from pathlib import Path
import re
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
    rollback_target = manifest.get("rollback_target")
    if not isinstance(rollback_target, dict):
        errors.append("missing coherent rollback target")
    else:
        errors.extend(
            _validate_release_identity(
                rollback_target,
                expected_environment=str(manifest.get("environment") or ""),
                label="rollback target",
            )
        )
    return errors


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
    rollback_parser.add_argument("--manifest", type=Path, required=True)
    rollback_parser.add_argument("--environment", required=True)
    rollback_parser.add_argument("--manifest-uri", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "rollback-target":
        manifest_bytes = args.manifest.read_bytes()
        manifest = json.loads(manifest_bytes)
        target, errors = build_rollback_target(
            manifest,
            environment=args.environment,
            manifest_uri=args.manifest_uri,
            sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print(json.dumps(target, sort_keys=True))
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
