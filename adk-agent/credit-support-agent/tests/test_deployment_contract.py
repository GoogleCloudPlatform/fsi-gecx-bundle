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

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MCP_RUNTIME_VERSION = "1.28.1"


def test_container_runtime_pins_adk_compatible_mcp_api() -> None:
    package = (ROOT / "adk-agent/credit-support-agent/pyproject.toml").read_text()
    requirements = (
        ROOT / "adk-agent/credit-support-agent/requirements.txt"
    ).read_text()

    expected = f"mcp=={MCP_RUNTIME_VERSION}"
    assert f'"{expected}"' in package
    assert expected in requirements.splitlines()

    from mcp.client.streamable_http import McpHttpClientFactory

    assert McpHttpClientFactory is not None


def test_agent_build_and_terraform_share_capacity_contract() -> None:
    cloudbuild = (ROOT / "adk-agent/credit-support-agent/cloudbuild-deploy.yaml").read_text()
    cloud_build_tf = (ROOT / "deployment/terraform/cloud_build.tf").read_text()
    cloud_run_tf = (ROOT / "deployment/terraform/cloud_run_v2.tf").read_text()

    settings = (
        "VOICE_AGENT_MAX_CONCURRENT_SESSIONS",
        "VOICE_AGENT_AUDIO_SESSION_CAPACITY_UNITS",
        "VOICE_AGENT_VIDEO_SESSION_CAPACITY_UNITS",
    )
    for setting in settings:
        assert setting in cloudbuild
        assert setting in cloud_run_tf

    trigger_start = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "credit_support_agent_deploy_trigger"'
    )
    trigger_end = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "data_generator_deploy_trigger"',
        trigger_start,
    )
    agent_trigger = cloud_build_tf[trigger_start:trigger_end]
    assert "_VOICE_AGENT_MAX_INSTANCE_REQUEST_CONCURRENCY" in agent_trigger
    assert "_VOICE_AGENT_MAX_CONCURRENT_SESSIONS" in agent_trigger

    ui_start = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "banking_ui_deploy_trigger"'
    )
    ui_end = cloud_build_tf.index(
        'resource "google_cloudbuild_trigger" "iap_login_ui_deploy_trigger"',
        ui_start,
    )
    assert "_VOICE_AGENT_" not in cloud_build_tf[ui_start:ui_end]


def test_agent_archive_build_prepares_repository_for_linguist() -> None:
    cloudbuild = (ROOT / "adk-agent/credit-support-agent/cloudbuild-deploy.yaml").read_text()

    prepare_index = cloudbuild.index('id: "prepare-linguist-repository"')
    linguist_index = cloudbuild.index('id: "run-linguist"')

    assert prepare_index < linguist_index
    assert "git init -q /workspace" in cloudbuild


def test_agent_image_validates_runtime_imports_before_push() -> None:
    cloudbuild = (ROOT / "adk-agent/credit-support-agent/cloudbuild-deploy.yaml").read_text()

    validation_index = cloudbuild.index('id: "validate-runtime-imports"')
    push_index = cloudbuild.index('id: "push-image"')

    assert validation_index < push_index
    assert "create_mcp_http_client" in cloudbuild[validation_index:push_index]
