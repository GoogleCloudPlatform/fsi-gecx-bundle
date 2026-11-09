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

"""Execute the release controller's retention and rollback-fetch refusals.

The functions under test are sourced from release_retention_lib.sh exactly as
run_alloydb_release.sh sources them. ``gcloud`` and ``gsutil`` are stubs on
PATH that record every invocation, so the tests can assert both the refusal
(non-zero exit plus stderr) and the absence of forbidden side effects.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


SCRIPTS = Path(__file__).resolve().parent
LIB = SCRIPTS / "release_retention_lib.sh"
RELEASE = SCRIPTS / "run_alloydb_release.sh"

COMMIT = "0123456789ab" + "c" * 28
DIGEST = "sha256:" + "d" * 64
OTHER_DIGEST = "sha256:" + "e" * 64
REPOSITORY = "us-central1-docker.pkg.dev/source-project/fsi-gecx-bundle/banking-ui"
IMAGE = f"{REPOSITORY}@{DIGEST}"
TAG = f"release-{COMMIT[:12]}-{'d' * 12}"

STUB_GCLOUD = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${STUB_LOG}"
if [[ "$1 $2 $3 $4" == "artifacts docker images describe" ]]; then
  if [[ -n "${STUB_DESCRIBE_ERROR:-}" ]]; then
    echo "${STUB_DESCRIBE_ERROR}" >&2
    exit 1
  fi
  if [[ -f "${STUB_STATE}/tag" ]]; then
    cat "${STUB_STATE}/tag"
    exit 0
  fi
  echo "ERROR: (gcloud.artifacts.docker.images.describe) Image not found." >&2
  exit 1
fi
if [[ "$1 $2 $3 $4" == "artifacts docker tags add" ]]; then
  printf '%s' "${STUB_TAGS_ADD_RESULT:-${5##*@}}" > "${STUB_STATE}/tag"
  exit 0
fi
echo "unexpected gcloud call: $*" >&2
exit 2
"""

STUB_GSUTIL = r"""#!/usr/bin/env bash
set -euo pipefail
printf 'gsutil %s\n' "$*" >> "${STUB_LOG}"
[[ -z "${STUB_GSUTIL_FAIL:-}" ]] || { echo "AccessDeniedException: 403" >&2; exit 1; }
[[ "$1" == "cp" ]] && printf '{}' > "$3"
"""


class Harness:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.state = root / "state"
        self.log = root / "calls.log"
        self.bin.mkdir()
        self.state.mkdir()
        self.log.write_text("")
        for name, body in (("gcloud", STUB_GCLOUD), ("gsutil", STUB_GSUTIL)):
            stub = self.bin / name
            stub.write_text(body)
            stub.chmod(0o755)

    def existing_tag(self, digest: str) -> None:
        (self.state / "tag").write_text(digest)

    def run(self, script: str, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", f'set -euo pipefail; source "{LIB}"; {script}', "_", *args],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                "STUB_LOG": str(self.log),
                "STUB_STATE": str(self.state),
                **env,
            },
            check=False,
        )

    @property
    def calls(self) -> list[str]:
        return self.log.read_text().splitlines()

    def tag_adds(self) -> list[str]:
        return [call for call in self.calls if call.startswith("artifacts docker tags add")]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def test_main_script_sources_the_library_for_every_guarded_step() -> None:
    release = RELEASE.read_text()
    assert 'source "$(dirname "${BASH_SOURCE[0]}")/release_retention_lib.sh"' in release
    assert (
        'fetch_rollback_manifest "${ROLLBACK_MANIFEST_URI}" "${rollback_manifest_path}"'
        in release
    )
    before_terraform = release.split("terraform -chdir=deployment/terraform init", 1)[0]
    assert 'protect_release_image "${RELEASE_COMMIT}" "${images[$component]}"' in before_terraform
    assert (
        'require_release_retention "${RELEASE_COMMIT}" "${images[$component]}"'
        in before_terraform
    )
    # The guarded operations exist only in the library, never inline.
    assert "gsutil cp \"${ROLLBACK_MANIFEST_URI}\"" not in release
    assert "tags add" not in release


def test_qualify_adds_missing_retention_tag_and_reads_it_back(harness: Harness) -> None:
    result = harness.run('protect_release_image "$1" "$2"', COMMIT, IMAGE)

    assert result.returncode == 0, result.stderr
    assert harness.tag_adds() == [
        f"artifacts docker tags add {IMAGE} {REPOSITORY}:{TAG} --quiet"
    ]
    describes = [call for call in harness.calls if "images describe" in call]
    assert len(describes) == 2  # before and after the add


def test_qualify_accepts_existing_tag_on_same_digest_without_rewriting(
    harness: Harness,
) -> None:
    harness.existing_tag(DIGEST)
    result = harness.run('protect_release_image "$1" "$2"', COMMIT, IMAGE)

    assert result.returncode == 0, result.stderr
    assert harness.tag_adds() == []


def test_qualify_refuses_when_retention_tag_names_another_digest(
    harness: Harness,
) -> None:
    harness.existing_tag(OTHER_DIGEST)
    result = harness.run('protect_release_image "$1" "$2"', COMMIT, IMAGE)

    assert result.returncode != 0
    assert (
        f"Retention tag {REPOSITORY}:{TAG} resolves to '{OTHER_DIGEST}', expected {DIGEST}"
        in result.stderr
    )
    assert harness.tag_adds() == []


def test_qualify_refuses_when_added_tag_does_not_read_back(harness: Harness) -> None:
    result = harness.run(
        'protect_release_image "$1" "$2"', COMMIT, IMAGE, STUB_TAGS_ADD_RESULT=OTHER_DIGEST
    )

    assert result.returncode != 0
    assert f"resolves to '{OTHER_DIGEST}', expected {DIGEST}" in result.stderr


def test_qualify_fails_closed_on_describe_errors_other_than_not_found(
    harness: Harness,
) -> None:
    result = harness.run(
        'protect_release_image "$1" "$2"',
        COMMIT,
        IMAGE,
        STUB_DESCRIBE_ERROR="ERROR: PERMISSION_DENIED: caller lacks artifactregistry.versions.get",
    )

    assert result.returncode != 0
    assert f"Could not resolve {REPOSITORY}:{TAG}:" in result.stderr
    assert "PERMISSION_DENIED" in result.stderr
    assert harness.tag_adds() == []


@pytest.mark.parametrize(
    ("existing", "describe_error", "message"),
    (
        (None, "", f"Qualified image {IMAGE} lacks retention tag {TAG}; re-qualify"),
        (OTHER_DIGEST, "", f"Qualified image {IMAGE} lacks retention tag {TAG}; re-qualify"),
        (None, "ERROR: UNAVAILABLE: try again", f"Could not resolve {REPOSITORY}:{TAG}:"),
    ),
    ids=("tag-missing", "tag-points-elsewhere", "describe-error"),
)
def test_promote_refuses_unprotected_digest_without_writing(
    harness: Harness, existing: str | None, describe_error: str, message: str
) -> None:
    if existing:
        harness.existing_tag(existing)
    result = harness.run(
        'require_release_retention "$1" "$2"',
        COMMIT,
        IMAGE,
        STUB_DESCRIBE_ERROR=describe_error,
    )

    assert result.returncode != 0
    assert message in result.stderr
    assert harness.tag_adds() == []


def test_promote_accepts_protected_digest_read_only(harness: Harness) -> None:
    harness.existing_tag(DIGEST)
    result = harness.run('require_release_retention "$1" "$2"', COMMIT, IMAGE)

    assert result.returncode == 0, result.stderr
    assert harness.tag_adds() == []
    assert all("images describe" in call for call in harness.calls)


FETCH = 'fetch_rollback_manifest "$1" "$2"; printf "%s|" ${rollback_manifest_args[@]+"${rollback_manifest_args[@]}"}'


def test_rollback_fetch_is_skipped_only_for_exact_none(harness: Harness) -> None:
    destination = str(harness.root / "rollback.json")
    result = harness.run(FETCH, "NONE", destination)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "|"  # empty argument list
    assert harness.calls == []


@pytest.mark.parametrize(
    "uri", ("none", " NONE", "NONE ", "gs://env-fsi-release-manifests/alloydb/c/qualify.json")
)
def test_rollback_fetch_downloads_every_other_uri(harness: Harness, uri: str) -> None:
    destination = str(harness.root / "rollback.json")
    result = harness.run(FETCH, uri, destination)

    assert result.returncode == 0, result.stderr
    assert harness.calls == [f"gsutil cp {uri} {destination}"]
    assert result.stdout == f"--manifest|{destination}|"


def test_rollback_fetch_failure_aborts(harness: Harness) -> None:
    result = harness.run(
        FETCH, "gs://env/alloydb/c/qualify.json", str(harness.root / "r.json"), STUB_GSUTIL_FAIL="1"
    )

    assert result.returncode != 0
    assert "AccessDeniedException" in result.stderr
    assert result.stdout == ""
