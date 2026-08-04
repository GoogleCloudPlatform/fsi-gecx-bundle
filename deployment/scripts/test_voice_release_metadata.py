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

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("voice_release_metadata.py")
SPEC = importlib.util.spec_from_file_location("voice_release_metadata", MODULE_PATH)
assert SPEC and SPEC.loader
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


def _write_source(root: Path) -> None:
    ces = root / metadata.CES_AGENT_RELATIVE_PATH
    ces.mkdir(parents=True)
    (ces / "app.yaml").write_text(
        "modelSettings:\n  model: gemini-live-test\nrootAgent: test\n"
    )
    ignored = ces / "__pycache__"
    ignored.mkdir()
    (ignored / "callback.pyc").write_bytes(b"unstable")

    catalog = root / metadata.CATALOG_RELATIVE_PATH
    catalog.parent.mkdir(parents=True)
    catalog.write_text('{"guidance": "test"}\n')

    versions = root / metadata.ALEMBIC_VERSIONS_RELATIVE_PATH
    versions.mkdir(parents=True)
    (versions / "001_first.py").write_text(
        'revision = "001"\ndown_revision = None\n'
    )
    (versions / "002_second.py").write_text(
        'revision = "002"\ndown_revision = "001"\n'
    )


def test_inspect_source_is_content_addressed_and_finds_schema_head(tmp_path: Path) -> None:
    _write_source(tmp_path)
    first = metadata.inspect_source(tmp_path)
    (tmp_path / metadata.CES_AGENT_RELATIVE_PATH / "__pycache__" / "other.pyc").write_bytes(
        b"ignored"
    )
    second = metadata.inspect_source(tmp_path)

    assert first == second
    assert first["ces_config"]["model"] == "gemini-live-test"
    assert first["database"]["alembic_heads"] == ["002"]
    assert len(first["knowledge_catalog"]["sha256"]) == 64


def test_validate_manifest_requires_every_runtime_and_matching_source(
    tmp_path: Path,
) -> None:
    _write_source(tmp_path)
    expected = metadata.inspect_source(tmp_path)
    manifest = {
        "commit": "a" * 40,
        "environment": "demo-project",
        "images": {
            component: f"repo/{component}@sha256:{'a' * 64}"
            for component in (
                "banking-service",
                "banking-ui",
                "credit-support-agent",
                "data-generator",
            )
        },
        "ces": {
            "app": "projects/p/locations/us/apps/a",
            "version": "projects/p/locations/us/apps/a/versions/v",
            "deployment": "projects/p/locations/us/apps/a/deployments/d",
            "config_sha256": expected["ces_config"]["sha256"],
            "model": expected["ces_config"]["model"],
        },
        "knowledge_catalog": expected["knowledge_catalog"],
        "database": expected["database"],
    }
    rollback_manifest = {
        **json.loads(json.dumps(manifest)),
        "commit": "b" * 40,
        "status": "qualified",
        "validation": {"service_health": True},
    }
    rollback_target, rollback_errors = metadata.build_rollback_target(
        rollback_manifest,
        environment="demo-project",
        manifest_uri="gs://demo/releases/rollback.json",
        sha256="c" * 64,
    )
    assert rollback_errors == []
    manifest["rollback_target"] = rollback_target

    assert metadata.validate_manifest(manifest, expected, "a" * 40) == []

    manifest = json.loads(json.dumps(manifest))
    del manifest["images"]["banking-ui"]
    manifest["ces"]["config_sha256"] = "wrong"
    errors = metadata.validate_manifest(manifest, expected, "a" * 40)
    assert "missing immutable image for banking-ui" in errors
    assert any(error.startswith("CES config SHA mismatch") for error in errors)


def test_rollback_target_requires_one_coherent_successful_environment() -> None:
    manifest = {
        "status": "promoted",
        "commit": "a" * 40,
        "environment": "fsi-demo-1841",
        "images": {
            component: f"repo/{component}@sha256:{'b' * 64}"
            for component in metadata.RELEASE_COMPONENTS
        },
        "ces": {
            "app": "apps/a",
            "version": "apps/a/versions/v",
            "deployment": "apps/a/deployments/d",
            "config_sha256": "c" * 64,
            "model": "gemini-live-test",
        },
        "knowledge_catalog": {"sha256": "d" * 64},
        "database": {"alembic_heads": ["head-1"]},
        "validation": {"service_health": True, "ces_deployment": True},
        "completed_at": "2026-08-04T00:00:00Z",
    }

    target, errors = metadata.build_rollback_target(
        manifest,
        environment="fsi-demo-1841",
        manifest_uri="gs://demo/promote.json",
        sha256="e" * 64,
    )

    assert errors == []
    assert target["commit"] == "a" * 40
    assert target["images"] == manifest["images"]
    assert target["manifest_uri"] == "gs://demo/promote.json"

    _, errors = metadata.build_rollback_target(
        manifest,
        environment="another-project",
        manifest_uri="gs://demo/promote.json",
        sha256="e" * 64,
    )
    assert any("environment mismatch" in error for error in errors)


def test_release_requires_exact_commit_images_and_ui_persists_its_tag() -> None:
    root = Path(__file__).resolve().parents[2]
    release = (root / "deployment/scripts/run_alloydb_release.sh").read_text()
    ui_build = (root / "banking-ui/cloudbuild-publish-deploy.yaml").read_text()
    release_build = (
        root / "deployment/cloud_build/cloudbuild-alloydb-release.yaml"
    ).read_text()
    triggers = (root / "deployment/terraform/cloud_build.tf").read_text()

    assert "No image tagged with exact release commit" in release
    assert "gcloud run services describe" not in release.split(
        "if [[ \"${RELEASE_MODE}\"", 1
    )[0]
    assert "printf '%s' \"$$COMMIT_SHA\" > /workspace/image_tag.txt" in ui_build
    assert ui_build.count("IMAGE_TAG=$$(cat /workspace/image_tag.txt)") == 2
    assert "banking-ui:$${COMMIT_SHA:-local}" not in ui_build
    assert "ROLLBACK_MANIFEST_URI is required" in release
    assert "rollback_target:$rollback_target[0]" in release
    assert "schema_version:3" in release
    assert "ROLLBACK_MANIFEST_URI=${_ROLLBACK_MANIFEST_URI}" in release_build
    assert triggers.count('_ROLLBACK_MANIFEST_URI   = "REQUIRED"') == 2


def test_serverless_neg_backends_do_not_set_unsupported_timeouts() -> None:
    root = Path(__file__).resolve().parents[2]
    load_balancer = (root / "deployment/terraform/load_balancer.tf").read_text()
    serverless_section = load_balancer.split("# Backend Services", 1)[1].split(
        "# START DESTROY", 1
    )[0]

    assert 'network_endpoint_type = "SERVERLESS"' not in serverless_section
    assert "timeout_sec" not in serverless_section
