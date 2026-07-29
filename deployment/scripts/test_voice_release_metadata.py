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
        "commit": "abc123",
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

    assert metadata.validate_manifest(manifest, expected, "abc123") == []

    manifest = json.loads(json.dumps(manifest))
    del manifest["images"]["banking-ui"]
    manifest["ces"]["config_sha256"] = "wrong"
    errors = metadata.validate_manifest(manifest, expected, "abc123")
    assert "missing immutable image for banking-ui" in errors
    assert any(error.startswith("CES config SHA mismatch") for error in errors)


def test_release_requires_exact_commit_images_and_ui_persists_its_tag() -> None:
    root = Path(__file__).resolve().parents[2]
    release = (root / "deployment/scripts/run_alloydb_release.sh").read_text()
    ui_build = (root / "banking-ui/cloudbuild-publish-deploy.yaml").read_text()

    assert "No image tagged with exact release commit" in release
    assert "gcloud run services describe" not in release.split(
        "if [[ \"${RELEASE_MODE}\"", 1
    )[0]
    assert "printf '%s' \"$$COMMIT_SHA\" > /workspace/image_tag.txt" in ui_build
    assert ui_build.count("IMAGE_TAG=$$(cat /workspace/image_tag.txt)") == 2
    assert "banking-ui:$${COMMIT_SHA:-local}" not in ui_build
